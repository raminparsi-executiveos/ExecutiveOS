#!/usr/bin/env python3
"""Conservative production data cleanup for ExecutiveOS.

Run from the Render backend shell where DATABASE_URL is already set:
    python scripts/production_data_cleanup.py

Preview only:
    python scripts/production_data_cleanup.py

Apply changes after reviewing the dry-run output:
    python scripts/production_data_cleanup.py --apply

The script writes a JSON backup before applying changes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "backend"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from app.backup_service import export_backup
from app.ai import CAPTURE_PROMPT_VERSION, analyze_capture
from app.capture_service import (
    _analysis_to_interpretation,
    _memory_context,
    _mutation_from_update,
    _prepare_capture_updates,
)
from app.database import SessionLocal
from app.models import (
    CaptureInterpretation,
    CaptureMutation,
    CaptureRecord,
    Clarification,
    Company,
    Decision,
    Document,
    EntityAlias,
    LeadershipReview,
    Meeting,
    Metric,
    Person,
    Project,
    ProvenanceRecord,
    ResolvableItem,
    ReviewAlert,
    RevisionRecord,
    SOP,
    StrategicIssue,
    Task,
)
from app.tasks import TASK_PRIORITIES, TASK_STATUSES, normalize_task_priority, normalize_task_status


IDENTITY_MODELS = [
    (Person, "person", "name"),
    (Company, "company", "name"),
    (StrategicIssue, "strategic_issue", "title"),
    (Project, "project", "title"),
    (Decision, "decision", "title"),
    (Meeting, "meeting", "title"),
    (SOP, "sop", "title"),
    (Document, "document", "title"),
    (Metric, "metric", "title"),
    (Task, "task", "title"),
]

LIST_OPERATION_FIELDS = {
    "action_items",
    "attendees",
    "concerns",
    "current_priorities",
    "decisions",
    "decisions_made",
    "dependencies",
    "escalation_rules",
    "kpis",
    "leadership",
    "linked_decision_ids",
    "linked_decisions",
    "linked_meetings",
    "linked_people",
    "linked_project_ids",
    "linked_projects",
    "linked_strategic_issues",
    "milestones",
    "next_steps",
    "open_questions",
    "options_considered",
    "people",
    "performance_notes",
    "projects",
    "related_projects",
    "responsibilities",
    "risks",
    "stakeholders",
    "strategic_issues",
    "strengths",
    "tags",
}


def normalize_identity(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def object_company(instance: Any) -> str:
    return normalize_identity(getattr(instance, "company", ""))


def identity_key(instance: Any, identity_field: str) -> tuple[str, str]:
    return normalize_identity(getattr(instance, identity_field, "")), object_company(instance)


def compact(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def unique_list(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    output: list[Any] = []
    for value in values:
        if value in (None, "", []):
            continue
        marker = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else str(value).strip().lower()
        if marker in seen:
            continue
        seen.add(marker)
        output.append(value)
    return output


def value_score(value: Any) -> int:
    if value in (None, "", []):
        return 0
    if isinstance(value, list):
        return sum(value_score(item) for item in value)
    if isinstance(value, dict):
        return sum(value_score(item) for item in value.values())
    return min(len(str(value)), 500)


def record_score(instance: Any) -> int:
    score = 0
    for column in instance.__table__.columns:
        if column.name in {"id", "created_at", "updated_at"}:
            continue
        score += value_score(getattr(instance, column.name, None))
    return score


def choose_canonical(records: list[Any]) -> Any:
    return sorted(
        records,
        key=lambda item: (
            record_score(item),
            getattr(item, "updated_at", None) or getattr(item, "created_at", None) or datetime.min.replace(tzinfo=timezone.utc),
            -(item.id or 0),
        ),
        reverse=True,
    )[0]


def merge_record_fields(canonical: Any, duplicate: Any) -> list[str]:
    changed: list[str] = []
    for column in canonical.__table__.columns:
        field = column.name
        if field in {"id", "created_at", "updated_at"}:
            continue
        current = getattr(canonical, field, None)
        incoming = getattr(duplicate, field, None)
        if incoming in (None, "", []):
            continue
        if isinstance(canonical, Task) and field == "status":
            normalized = normalize_task_status(current, fallback_unknown=True)
            if normalized != current:
                setattr(canonical, field, normalized)
                changed.append(field)
            continue
        if isinstance(canonical, Task) and field == "priority":
            normalized = normalize_task_priority(current, fallback_unknown=True)
            if normalized != current:
                setattr(canonical, field, normalized)
                changed.append(field)
            continue
        if field in LIST_OPERATION_FIELDS or isinstance(current, list) or isinstance(incoming, list):
            merged = unique_list(list(current or []) + list(incoming if isinstance(incoming, list) else [incoming]))
            if merged != (current or []):
                setattr(canonical, field, merged)
                changed.append(field)
        elif isinstance(current, dict) and isinstance(incoming, dict):
            merged = {**incoming, **current}
            if merged != current:
                setattr(canonical, field, merged)
                changed.append(field)
        elif current in (None, "") or value_score(incoming) > value_score(current):
            setattr(canonical, field, incoming)
            changed.append(field)
    return changed


def rewrite_references(db, object_type: str, old_id: int, new_id: int) -> int:
    changed = 0
    for mutation in db.query(CaptureMutation).filter(
        CaptureMutation.saved_record_type == object_type,
        CaptureMutation.saved_record_id == old_id,
    ):
        mutation.saved_record_id = new_id
        changed += 1
    for mutation in db.query(CaptureMutation).filter(
        CaptureMutation.matched_record_type == object_type,
        CaptureMutation.matched_record_id == old_id,
    ):
        mutation.matched_record_id = new_id
        changed += 1
    for provenance in db.query(ProvenanceRecord).filter(
        ProvenanceRecord.object_type == object_type,
        ProvenanceRecord.object_id == old_id,
    ):
        provenance.object_id = new_id
        changed += 1
    for revision in db.query(RevisionRecord).filter(
        RevisionRecord.object_type == object_type,
        RevisionRecord.object_id == old_id,
    ):
        revision.object_id = new_id
        changed += 1
    for alert in db.query(ReviewAlert).filter(
        ReviewAlert.object_type == object_type,
        ReviewAlert.object_id == old_id,
    ):
        alert.object_id = new_id
        changed += 1
    for alert in db.query(ReviewAlert).filter(
        ReviewAlert.related_object_type == object_type,
        ReviewAlert.related_object_id == old_id,
    ):
        alert.related_object_id = new_id
        changed += 1
    for item in db.query(ResolvableItem).filter(
        ResolvableItem.parent_type == object_type,
        ResolvableItem.parent_id == old_id,
    ):
        item.parent_id = new_id
        changed += 1
    for clarification in db.query(Clarification).filter(
        Clarification.target_record_type == object_type,
        Clarification.target_record_id == old_id,
    ):
        clarification.target_record_id = new_id
        changed += 1
    for alias in db.query(EntityAlias).filter(
        EntityAlias.entity_type == object_type,
        EntityAlias.entity_id == old_id,
    ):
        alias.entity_id = new_id
        changed += 1
    for review in db.query(LeadershipReview).all():
        changed_review = False
        findings = list(review.findings or [])
        for finding in findings:
            for evidence in finding.get("evidence", []) or []:
                if evidence.get("object_type") == object_type and str(evidence.get("object_id")) == str(old_id):
                    evidence["object_id"] = str(new_id)
                    changed_review = True
        source_record_ids = []
        for source in review.source_record_ids or []:
            if source.get("type") == object_type and str(source.get("id")) == str(old_id):
                source = {**source, "id": new_id}
                changed_review = True
            source_record_ids.append(source)
        if changed_review:
            review.findings = findings
            review.source_record_ids = source_record_ids
            db.add(review)
            changed += 1
    return changed


def cleanup_duplicate_records(db, apply: bool) -> list[str]:
    actions: list[str] = []
    for model, object_type, identity_field in IDENTITY_MODELS:
        groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for record in db.query(model).all():
            key = identity_key(record, identity_field)
            if key[0]:
                groups[key].append(record)
        for key, records in sorted(groups.items()):
            if len(records) < 2:
                continue
            canonical = choose_canonical(records)
            duplicates = [record for record in records if record.id != canonical.id]
            actions.append(
                f"{model.__tablename__}: keep #{canonical.id} for {key}; merge/delete {[record.id for record in duplicates]}"
            )
            if not apply:
                continue
            for duplicate in duplicates:
                changed_fields = merge_record_fields(canonical, duplicate)
                reference_count = rewrite_references(db, object_type, duplicate.id, canonical.id)
                actions.append(
                    f"  applied duplicate #{duplicate.id} -> #{canonical.id}; fields={changed_fields}; references={reference_count}"
                )
                db.delete(duplicate)
            db.add(canonical)
    if apply:
        db.flush()
    return actions


def normalize_old_task_values(db, apply: bool) -> list[str]:
    actions: list[str] = []
    for task in db.query(Task).all():
        normalized_status = normalize_task_status(task.status, fallback_unknown=True)
        normalized_priority = normalize_task_priority(task.priority, fallback_unknown=True)
        if normalized_status == task.status and normalized_priority == task.priority:
            continue
        actions.append(
            f"task#{task.id}: status {task.status!r}->{normalized_status!r}, priority {task.priority!r}->{normalized_priority!r}"
        )
        if apply:
            task.status = normalized_status if normalized_status in TASK_STATUSES else "open"
            task.priority = normalized_priority if normalized_priority in TASK_PRIORITIES else "medium"
            db.add(task)
    return actions


def snapshot_for_saved_record(db, record_type: str, record_id: int | None) -> dict[str, Any]:
    model = {
        "person": Person,
        "company": Company,
        "strategic_issue": StrategicIssue,
        "project": Project,
        "decision": Decision,
        "meeting": Meeting,
        "sop": SOP,
        "metric": Metric,
        "task": Task,
    }.get(record_type)
    if model is None or record_id is None:
        return {}
    instance = db.get(model, record_id)
    if instance is None:
        return {}
    output = {}
    for column in instance.__table__.columns:
        value = getattr(instance, column.name)
        output[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return output


def cleanup_capture_outputs(db, apply: bool) -> list[str]:
    actions: list[str] = []
    for capture in db.query(CaptureRecord).order_by(CaptureRecord.id.asc()).all():
        interpretation = (
            db.query(CaptureInterpretation)
            .filter(CaptureInterpretation.capture_id == capture.id)
            .order_by(CaptureInterpretation.id.desc())
            .first()
        )
        raw = interpretation.raw_response if interpretation and isinstance(interpretation.raw_response, dict) else {}
        mutations = db.query(CaptureMutation).filter(CaptureMutation.capture_id == capture.id).all()
        approved = [mutation for mutation in mutations if mutation.status == "approved_applied"]
        rejected = [mutation for mutation in mutations if mutation.status == "rejected"]
        saved_ids = [
            {
                "type": mutation.saved_record_type,
                "id": mutation.saved_record_id,
                "suggestion_index": mutation.suggestion_index,
            }
            for mutation in approved
            if mutation.saved_record_type and mutation.saved_record_id
        ]

        capture_changes: list[str] = []
        if raw and capture.structured_interpretation != raw:
            capture_changes.append("sync_structured_interpretation_from_latest_ai_output")
            if apply:
                capture.structured_interpretation = raw
        if capture.saved_count != len(approved):
            capture_changes.append(f"saved_count {capture.saved_count}->{len(approved)}")
            if apply:
                capture.saved_count = len(approved)
        if saved_ids and capture.saved_record_ids != saved_ids:
            capture_changes.append("sync_saved_record_ids_from_approved_mutations")
            if apply:
                capture.saved_record_ids = saved_ids
        approved_values = [mutation.approved_values for mutation in approved if mutation.approved_values]
        rejected_values = [mutation.proposed_values for mutation in rejected if mutation.proposed_values]
        if approved_values and capture.approved_suggestions != approved_values:
            capture_changes.append("sync_approved_suggestions_from_mutations")
            if apply:
                capture.approved_suggestions = approved_values
        if rejected_values and capture.rejected_suggestions != rejected_values:
            capture_changes.append("sync_rejected_suggestions_from_mutations")
            if apply:
                capture.rejected_suggestions = rejected_values
        if capture_changes:
            actions.append(f"capture#{capture.id}: {', '.join(capture_changes)}")
            if apply:
                db.add(capture)

        seen_mutation_keys: set[tuple[Any, ...]] = set()
        for mutation in sorted(mutations, key=lambda item: item.id or 0):
            proposed = mutation.proposed_values or {}
            title = proposed.get("title") or proposed.get("name") or proposed.get("details") or ""
            key = (
                mutation.suggestion_index,
                mutation.object_type,
                mutation.operation,
                normalize_identity(title),
            )
            if key in seen_mutation_keys and mutation.status == "proposed":
                actions.append(f"mutation#{mutation.id}: reject duplicate proposed mutation for capture#{capture.id}")
                if apply:
                    mutation.status = "rejected"
                    mutation.explanation = compact(
                        f"{mutation.explanation or ''} Duplicate proposed mutation from the same capture."
                    )
                    db.add(mutation)
            seen_mutation_keys.add(key)

            mutation_changes: list[str] = []
            if mutation.object_type == "task":
                for field, normalizer in (("status", normalize_task_status), ("priority", normalize_task_priority)):
                    if isinstance(mutation.proposed_values, dict) and field in mutation.proposed_values:
                        normalized = normalizer(mutation.proposed_values.get(field), fallback_unknown=True)
                        if mutation.proposed_values.get(field) != normalized:
                            mutation_changes.append(f"proposed.{field}->{normalized}")
                            if apply:
                                mutation.proposed_values = {**mutation.proposed_values, field: normalized}
                    if isinstance(mutation.approved_values, dict) and field in mutation.approved_values:
                        normalized = normalizer(mutation.approved_values.get(field), fallback_unknown=True)
                        if mutation.approved_values.get(field) != normalized:
                            mutation_changes.append(f"approved.{field}->{normalized}")
                            if apply:
                                mutation.approved_values = {**mutation.approved_values, field: normalized}
            if mutation.status == "approved_applied" and mutation.saved_record_type and mutation.saved_record_id and not mutation.persisted_values:
                snapshot = snapshot_for_saved_record(db, mutation.saved_record_type, mutation.saved_record_id)
                if snapshot:
                    mutation_changes.append("backfill_persisted_values")
                    if apply:
                        mutation.persisted_values = snapshot
            if mutation_changes:
                actions.append(f"mutation#{mutation.id}: {', '.join(mutation_changes)}")
                if apply:
                    db.add(mutation)
    return actions


def reprocess_fallback_capture_outputs(db, apply: bool, limit: int, include_approved: bool) -> list[str]:
    actions: list[str] = []
    if limit <= 0:
        return actions
    captures = (
        db.query(CaptureRecord)
        .filter(CaptureRecord.classification_source.in_(["local_fallback", "image_unavailable", "unknown"]))
        .order_by(CaptureRecord.id.desc())
        .limit(limit)
        .all()
    )
    for capture in captures:
        mutations = db.query(CaptureMutation).filter(CaptureMutation.capture_id == capture.id).all()
        approved = [mutation for mutation in mutations if mutation.status == "approved_applied"]
        if approved and not include_approved:
            actions.append(f"capture#{capture.id}: skipped AI reprocess because {len(approved)} updates were already approved")
            continue
        analysis = analyze_capture(capture.raw_text, _memory_context(db))
        if analysis is None:
            actions.append(f"capture#{capture.id}: AI reprocess unavailable; kept existing output")
            continue
        prepared_updates, quality_follow_ups = _prepare_capture_updates(
            [update.model_dump() for update in analysis.suggested_updates],
            capture.raw_text,
            classification_source="ai",
        )
        follow_ups = list(dict.fromkeys(analysis.follow_ups + quality_follow_ups))
        interpretation_payload = _analysis_to_interpretation(
            analysis,
            capture.raw_text,
            prepared_updates,
            follow_ups,
            classification_source="ai",
        )
        actions.append(
            f"capture#{capture.id}: AI rebuilt {len(prepared_updates)} suggested updates and {len(follow_ups)} follow-ups"
        )
        if not apply:
            continue
        capture.classification_source = "ai"
        capture.saved_count = 0
        capture.structured_interpretation = interpretation_payload
        capture.approved_suggestions = []
        capture.rejected_suggestions = []
        capture.saved_record_ids = []
        capture.screenshot_summary = capture.screenshot_summary or ""
        events = list(capture.processing_events or [])
        events.append({
            "event": "fallback_capture_reprocessed_with_ai",
            "suggested_update_count": len(prepared_updates),
            "follow_up_count": len(follow_ups),
            "at": datetime.now(timezone.utc).isoformat(),
        })
        capture.processing_events = events
        db.add(capture)
        interpretation = CaptureInterpretation(
            capture_id=capture.id,
            capture_summary=interpretation_payload.get("capture_summary") or "",
            capture_purpose=interpretation_payload.get("capture_purpose") or "",
            executive_intent=interpretation_payload.get("executive_intent") or "",
            primary_company=interpretation_payload.get("primary_company") or "",
            primary_subject=interpretation_payload.get("primary_subject") or "",
            primary_topic=interpretation_payload.get("primary_topic") or "",
            urgency=interpretation_payload.get("urgency") or "",
            tone=interpretation_payload.get("tone") or "",
            temporal_context=interpretation_payload.get("temporal_context") or "",
            confidence=interpretation_payload.get("confidence") or "",
            model=os.getenv("OPENAI_MODEL", ""),
            prompt_version=CAPTURE_PROMPT_VERSION,
            people_roles=interpretation_payload.get("people_roles") or [],
            statements=interpretation_payload.get("statements") or [],
            open_questions=interpretation_payload.get("open_questions") or interpretation_payload.get("follow_ups") or [],
            ambiguities=interpretation_payload.get("ambiguities") or [],
            source_evidence=interpretation_payload.get("source_evidence") or [],
            raw_response=interpretation_payload,
        )
        db.add(interpretation)
        db.flush()
        for mutation in mutations:
            if include_approved or mutation.status != "approved_applied":
                db.delete(mutation)
        db.flush()
        for index, update in enumerate(prepared_updates):
            _mutation_from_update(db, capture, interpretation, update, index)
    return actions


def repeated_capture_report(db) -> list[str]:
    groups: dict[str, list[CaptureRecord]] = defaultdict(list)
    for capture in db.query(CaptureRecord).all():
        key = normalize_identity(capture.raw_text)
        if key:
            groups[key].append(capture)
    actions = []
    for key, captures in groups.items():
        if len(captures) > 1:
            ids = [capture.id for capture in sorted(captures, key=lambda item: item.id or 0)]
            actions.append(f"repeated capture text: ids={ids}; text={compact(captures[0].raw_text)}")
    return actions


def write_backup(db) -> Path:
    path = Path("/tmp") / f"executiveos-backup-before-cleanup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(export_backup(db), indent=2, default=str))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean duplicate ExecutiveOS production data.")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup changes. Default is dry-run.")
    parser.add_argument(
        "--reprocess-fallback-captures",
        type=int,
        default=0,
        metavar="N",
        help="Use OpenAI to rebuild suggested outputs for the N latest fallback/image-unavailable captures.",
    )
    parser.add_argument(
        "--include-approved-captures",
        action="store_true",
        help="Allow AI reprocessing to replace capture mutation rows even when previous updates were approved.",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL is not set. Run this from the Render backend shell.")

    db = SessionLocal()
    try:
        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"ExecutiveOS production data cleanup ({mode})")
        backup_path = write_backup(db)
        print(f"Backup written: {backup_path}")

        sections = [
            ("Duplicate durable records", cleanup_duplicate_records(db, args.apply)),
            ("Old invalid task values", normalize_old_task_values(db, args.apply)),
            ("Capture/audit output repairs", cleanup_capture_outputs(db, args.apply)),
            (
                "AI reprocessed fallback capture outputs",
                reprocess_fallback_capture_outputs(
                    db,
                    args.apply,
                    args.reprocess_fallback_captures,
                    args.include_approved_captures,
                ),
            ),
            ("Repeated capture report", repeated_capture_report(db)),
        ]
        for title, actions in sections:
            print(f"\n{'=' * 88}\n{title}\n{'=' * 88}")
            if actions:
                for action in actions:
                    print(f"- {action}")
            else:
                print("No changes needed.")

        if args.apply:
            db.commit()
            print("\nCleanup applied.")
        else:
            db.rollback()
            print("\nDry run only. Re-run with --apply to make these changes.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
