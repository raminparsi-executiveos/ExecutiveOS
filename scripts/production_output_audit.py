#!/usr/bin/env python3
"""Production output audit for ExecutiveOS.

Run from the Render backend shell where DATABASE_URL is already set:
    python scripts/production_output_audit.py

This script inspects recent capture records, compares suggested mutations with
saved values, and renders the same briefing/meeting-prep structures used by the
application so their output can be reviewed against source data.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.briefing_service import build_ranked_briefing
from app.database import SessionLocal
from app.main import meeting_prep
from app.models import CaptureInterpretation, CaptureMutation, CaptureRecord, Meeting, Task
from app.schemas import MeetingPrepRequest
from app.tasks import OPEN_TASK_STATUSES


MEETING_QUERIES = [
    "pec daily sales check-in",
    "pec weekly sales meeting",
    "ryse leadership meeting",
    "pec sales meeting",
    "ryse leadership team",
]


def section(title: str) -> None:
    print(f"\n{'=' * 96}\n{title}\n{'=' * 96}")


def short(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def labels(items: list[dict[str, Any]], limit: int = 12) -> list[str]:
    output = []
    for item in items[:limit]:
        title = item.get("title") or item.get("label") or str(item)
        company = item.get("company") or ""
        owner = item.get("owner") or ""
        status = item.get("status") or ""
        meta = " | ".join(part for part in (company, owner, status) if part)
        output.append(f"{title}{f' ({meta})' if meta else ''}")
    return output


def print_json_summary(name: str, value: Any, limit: int = 4000) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True, default=str)
    print(f"{name}:")
    print(rendered[:limit] + ("\n...<truncated>" if len(rendered) > limit else ""))


def task_quality(task: Task) -> tuple[int, list[str]]:
    score = 0
    missing = []
    if task.title:
        score += 20
    else:
        missing.append("title")
    if task.owner or task.assigned_to or task.waiting_on:
        score += 20
    else:
        missing.append("owner/accountable party")
    if task.next_action:
        score += 15
    else:
        missing.append("next_action")
    if task.expected_deliverable or task.definition_of_done:
        score += 20
    else:
        missing.append("expected outcome")
    if task.source_excerpt:
        score += 15
    else:
        missing.append("source_excerpt")
    if task.due_date or task.follow_up_date or task.recurrence:
        score += 10
    else:
        missing.append("due date/cadence")
    return score, missing


def audit_captures(db) -> None:
    section("Latest Captures vs Processing")
    captures = db.query(CaptureRecord).order_by(CaptureRecord.id.desc()).limit(15).all()
    for capture in captures:
        interpretation = (
            db.query(CaptureInterpretation)
            .filter(CaptureInterpretation.capture_id == capture.id)
            .order_by(CaptureInterpretation.id.desc())
            .first()
        )
        mutations = (
            db.query(CaptureMutation)
            .filter(CaptureMutation.capture_id == capture.id)
            .order_by(CaptureMutation.suggestion_index.asc(), CaptureMutation.id.asc())
            .all()
        )
        raw = interpretation.raw_response if interpretation else {}
        diagnostics = raw.get("diagnostics") if isinstance(raw, dict) else {}
        next_best_action = raw.get("next_best_action") if isinstance(raw, dict) else ""
        mutation_counts = Counter(mutation.status or "unknown" for mutation in mutations)
        print(
            f"capture#{capture.id} | source={capture.classification_source} | saved={capture.saved_count} | "
            f"mutations={dict(mutation_counts)} | created={capture.created_at}"
        )
        print(f"  raw: {short(capture.raw_text)}")
        if diagnostics:
            print(f"  diagnostics: {diagnostics}")
        if next_best_action:
            print(f"  next_best_action: {short(next_best_action)}")
        for mutation in mutations[:6]:
            proposed = mutation.proposed_values or {}
            approved = mutation.approved_values or {}
            saved = mutation.persisted_values or {}
            print(
                f"  mutation#{mutation.id} {mutation.object_type}/{mutation.operation}/{mutation.status}: "
                f"proposed={short(proposed.get('title') or proposed.get('name') or proposed.get('details'))} | "
                f"approved={short(approved.get('title') or approved.get('name') or approved.get('details'))} | "
                f"saved={short(saved.get('title') or saved.get('name') or saved.get('summary'))}"
            )
        print()


def audit_tasks(db) -> None:
    section("Task Quality and Created Items")
    tasks = db.query(Task).order_by(Task.id.desc()).limit(80).all()
    open_tasks = [task for task in tasks if task.status in OPEN_TASK_STATUSES]
    quality_rows = [(task, *task_quality(task)) for task in tasks]
    weak = [(task, score, missing) for task, score, missing in quality_rows if score < 70]
    print(f"latest_tasks={len(tasks)} | latest_open_tasks={len(open_tasks)} | weak_under_70={len(weak)}")
    print("Weakest tasks:")
    for task, score, missing in sorted(weak, key=lambda row: row[1])[:20]:
        print(
            f"  task#{task.id} score={score} status={task.status} company={task.company} owner={task.owner or task.assigned_to or task.waiting_on or ''} "
            f"title={short(task.title, 120)} missing={', '.join(missing)}"
        )


def audit_morning_brief(db) -> None:
    section("Morning Brief Output")
    briefing = build_ranked_briefing(db, username=os.getenv("EXECUTIVEOS_USERNAME", "admin"))
    keys = [
        "needs_attention",
        "delegate_follow_up",
        "blocked_waiting",
        "overdue",
        "upcoming",
        "context_priorities",
        "recent_changes",
    ]
    for key in keys:
        items = briefing.get(key) or []
        print(f"{key}: count={len(items)}")
        for line in labels(items, 12):
            print(f"  - {line}")
    print_json_summary("briefing_metadata", {
        key: briefing.get(key)
        for key in ("generated_at", "last_viewed_at", "clarifications_needed")
        if key in briefing
    }, limit=1500)


def audit_meeting_prep(db) -> None:
    section("Meeting Prep Output")
    for query in MEETING_QUERIES:
        prep = meeting_prep(MeetingPrepRequest(meeting=query), db=db, _user="audit")
        print(f"\n--- {query} ---")
        print(f"context_found={prep.get('context_found')}")
        for key in (
            "related_people",
            "related_strategic_issues",
            "related_projects",
            "open_decisions",
            "action_items",
            "risks",
            "questions_to_ask",
            "recent_capture_context",
        ):
            value = prep.get(key) or []
            print(f"{key}: count={len(value)}")
            for item in value[:10]:
                print(f"  - {short(item, 180)}")
        for key in ("action_items_detail", "open_commitments_detail", "overdue_tasks_detail", "risks_detail"):
            value = prep.get(key) or []
            print(f"{key}: count={len(value)}")
            for line in labels(value, 10):
                print(f"  - {line}")


def audit_meeting_records(db) -> None:
    section("Recent Meeting Records")
    meetings = db.query(Meeting).order_by(Meeting.id.desc()).limit(20).all()
    for meeting in meetings:
        print(
            f"meeting#{meeting.id} company={meeting.company} title={short(meeting.title, 120)} "
            f"actions={len(meeting.action_items or [])} questions={len(meeting.open_questions or [])}"
        )
        if meeting.action_items:
            print(f"  actions: {', '.join(short(item, 80) for item in meeting.action_items[:5])}")
        if meeting.open_questions:
            print(f"  questions: {', '.join(short(item, 80) for item in meeting.open_questions[:5])}")


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set. Run this from the Render backend shell.")
    db = SessionLocal()
    try:
        audit_captures(db)
        audit_tasks(db)
        audit_meeting_records(db)
        audit_morning_brief(db)
        audit_meeting_prep(db)
        section("Audit Prompts")
        print("Paste this output back into Codex and ask for the full audit and prioritized improvement plan.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
