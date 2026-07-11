from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from .capture_service import capture_explicitly_resolves_item, capture_resolves_waiting_item
from .clarification_service import briefing_clarification_items
from .memory import _result_summary, company_label_for_text
from .models import BriefingView, CaptureRecord, Decision, Meeting, Metric, Person, Project, StrategicIssue, Task
from .tasks import OPEN_TASK_STATUSES, task_is_overdue


EXECUTIVE_OWNER_ALIASES = {"ceo", "founder", "owner", "ramin", "local-development", "admin"}
PRIORITY_POINTS = {"critical": 80, "high": 55, "medium": 25, "low": 10}
STATUS_POINTS = {"blocked": 45, "waiting": 28, "in_progress": 18, "open": 12}


def _as_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _days_until(value: str, today: date) -> int | None:
    parsed = _as_date(value)
    return (parsed - today).days if parsed else None


def _updated_at(item: Any) -> datetime | None:
    timestamp = getattr(item, "updated_at", None) or getattr(item, "created_at", None)
    if timestamp and timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def _aware(timestamp: datetime | None) -> datetime | None:
    if timestamp and timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def _is_executive_owner(owner: str, username: str) -> bool:
    normalized = str(owner or "").strip().lower()
    if not normalized:
        return False
    return normalized == username.lower() or normalized in EXECUTIVE_OWNER_ALIASES


def _source_for(item: Any, record_type: str) -> dict[str, Any]:
    source_type = getattr(item, "source_type", "") or record_type
    source_id = getattr(item, "source_id", "") or str(getattr(item, "id", ""))
    summary = getattr(item, "source_summary", "") or _result_summary(item)
    return {"type": source_type, "id": source_id, "summary": summary}


def _dashboard_item(
    item: Any,
    *,
    record_type: str,
    title: str,
    why: str,
    score: int,
    next_action: str,
    owner: str = "",
    company: str = "",
    status: str = "",
    due_date: str = "",
    source: dict[str, Any] | None = None,
    score_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "label": title,
        "title": title,
        "company": company,
        "owner": owner,
        "why_it_matters": why,
        "status": status,
        "due_date": due_date,
        "recommended_next_action": next_action,
        "source": source or _source_for(item, record_type),
        "score": score,
        "score_reasons": score_reasons or [],
        "record_type": record_type,
        "record_id": getattr(item, "id", None),
    }


def _score_task(task: Task, today: date, username: str) -> tuple[int, list[str]]:
    score = PRIORITY_POINTS.get(task.priority, 20)
    reasons = [f"{task.priority or 'medium'} priority"]
    days = _days_until(task.due_date, today)
    if days is not None:
        if days < 0:
            score += min(90, 35 + abs(days) * 4)
            reasons.append(f"{abs(days)} days overdue")
        elif days <= 2:
            score += 35
            reasons.append("due within 2 days")
        elif days <= 7:
            score += 20
            reasons.append("due this week")
    if task.status in STATUS_POINTS:
        score += STATUS_POINTS[task.status]
        reasons.append(task.status.replace("_", " "))
    if task.blocked_by:
        score += 45
        reasons.append("blocked dependency")
    if not task.owner:
        score += 30
        reasons.append("missing owner")
    elif _is_executive_owner(task.owner, username):
        score += 30
        reasons.append("executive-owned")
    if task.updated_at and task.updated_at.date() >= today - timedelta(days=1):
        score += 10
        reasons.append("recently updated")
    return score, reasons


def _task_item(task: Task, today: date, username: str) -> dict[str, Any]:
    score, reasons = _score_task(task, today, username)
    if task.status == "blocked":
        why = f"Blocked by {task.blocked_by or 'an unresolved dependency'}."
        action = task.next_action or "Remove the blocker or assign a clear unblock owner."
    elif task_is_overdue(task, today):
        why = "This commitment is overdue and still open."
        action = task.next_action or "Confirm whether it should be completed, escalated, or rescheduled."
    elif not task.owner:
        why = "This open commitment has no accountable owner."
        action = task.next_action or "Assign an owner and confirm the next action."
    elif _is_executive_owner(task.owner, username):
        why = "You are listed as the owner of this open commitment."
        action = task.next_action or "Decide the next move or delegate it."
    else:
        why = f"{task.owner} owns this, but it still needs monitoring."
        action = task.next_action or "Follow up with the owner."
    return _dashboard_item(
        task,
        record_type="task",
        title=task.title,
        why=why,
        score=score,
        next_action=action,
        owner=task.owner or "",
        company=task.company or "",
        status=task.status or "",
        due_date=task.due_date or "",
        score_reasons=reasons,
    )


def _decision_item(decision: Decision, today: date) -> dict[str, Any]:
    days = _days_until(decision.review_date, today)
    overdue_days = abs(days or 0) if days is not None and days < 0 else 0
    score = 70 + min(60, overdue_days * 3)
    return _dashboard_item(
        decision,
        record_type="decision",
        title=decision.title,
        why="The review date has passed and the decision may need reaffirmation or revision.",
        score=score,
        next_action="Review whether the decision still holds.",
        company=decision.company or "",
        status="review overdue",
        due_date=decision.review_date or "",
        score_reasons=["review date passed"] + ([f"{overdue_days} days overdue"] if overdue_days else []),
    )


def _risk_item(item: StrategicIssue | Project, risk: str) -> dict[str, Any]:
    owner = getattr(item, "owner", "") or ""
    return _dashboard_item(
        item,
        record_type="risk",
        title=risk,
        why="This risk is attached to an active executive memory record.",
        score=45 + (15 if not owner else 0),
        next_action="Confirm mitigation owner and next step.",
        owner=owner,
        company=getattr(item, "company", "") or "",
        status=getattr(item, "status", "") or "active",
        source=_source_for(item, item.__class__.__name__.lower()),
        score_reasons=["explicit risk"] + (["missing owner"] if not owner else []),
    )


def _changed_item(item: Any, record_type: str) -> dict[str, Any]:
    title = getattr(item, "title", "") or getattr(item, "name", "") or f"{record_type.title()} update"
    if isinstance(item, CaptureRecord):
        title = f"Captured update from {item.created_at.date().isoformat()}"
    return _dashboard_item(
        item,
        record_type=record_type,
        title=title,
        why="Changed since the last briefing view.",
        score=20,
        next_action="Scan for decisions, commitments, or follow-up needed.",
        company=getattr(item, "company", "") or (company_label_for_text(item.raw_text) if isinstance(item, CaptureRecord) else ""),
        status=getattr(item, "status", "") or "updated",
        source=_source_for(item, record_type),
        score_reasons=["changed since last briefing"],
    )


def _unique_dashboard_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for item in sorted(items, key=lambda value: (value["score"], value.get("record_id") or 0), reverse=True):
        identity = (item["record_type"], item["record_id"], item["title"])
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(item)
        if len(unique) == limit:
            break
    return unique


def _without_seen(items: list[dict[str, Any]], seen: set[tuple[str, Any, str]], limit: int) -> list[dict[str, Any]]:
    selected = []
    for item in _unique_dashboard_items(items, len(items)):
        identity = (item["record_type"], item.get("record_id"), item["title"])
        if identity in seen:
            continue
        seen.add(identity)
        selected.append(item)
        if len(selected) == limit:
            break
    return selected


def build_ranked_briefing(db: Session, username: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    today = now.date()
    today_iso = today.isoformat()
    view = db.query(BriefingView).filter(BriefingView.username == username).first()
    previous_viewed_at = _aware(view.last_viewed_at if view else None)

    issues = db.query(StrategicIssue).filter(StrategicIssue.status == "active").order_by(StrategicIssue.id.desc()).all()
    people = db.query(Person).order_by(Person.id.desc()).all()
    decisions = db.query(Decision).order_by(Decision.id.desc()).all()
    meetings_today = db.query(Meeting).filter(Meeting.date == today_iso).order_by(Meeting.id.desc()).all()
    all_meetings = db.query(Meeting).all()
    projects = db.query(Project).order_by(Project.id.desc()).all()
    tasks = db.query(Task).order_by(Task.id.desc()).all()
    metrics = db.query(Metric).order_by(Metric.id.desc()).all()
    open_tasks = [task for task in tasks if task.status in OPEN_TASK_STATUSES]

    recent_captures = db.query(CaptureRecord).order_by(CaptureRecord.created_at.desc()).limit(25).all()
    resolution_contexts = [capture.raw_text for capture in recent_captures]
    resolution_contexts.extend(
        " ".join([
            person.name or "",
            person.role or "",
            person.company or "",
            " ".join(person.responsibilities or []),
            " ".join(person.current_priorities or []),
            " ".join(person.performance_notes or []),
        ])
        for person in people
    )

    def action_is_resolved(action: str) -> bool:
        return any(
            capture_resolves_waiting_item(context, action)
            or capture_explicitly_resolves_item(context, action)
            for context in resolution_contexts
        )

    visible_open_tasks = [
        task for task in open_tasks
        if not (
            task.source_type == "meeting"
            and task.status in {"waiting", "blocked", "open"}
            and action_is_resolved(task.title)
        )
    ]
    task_items = [_task_item(task, today, username) for task in visible_open_tasks]

    legacy_waiting = [
        _dashboard_item(
            meeting,
            record_type="meeting_action",
            title=str(action),
            why="Legacy meeting action item has not been converted to a linked completed task.",
            score=30,
            next_action="Convert to or complete a task after review.",
            company=meeting.company or "",
            status="waiting",
            source={"type": "meeting", "id": str(meeting.id), "summary": meeting.title},
            score_reasons=["legacy waiting item"],
        )
        for meeting in all_meetings
        for action in (meeting.action_items or [])
        if not action_is_resolved(str(action))
        and not any(task.title.lower() == str(action).lower() and task.source_type == "meeting" for task in tasks)
    ]
    risk_items = [
        _risk_item(item, risk)
        for item in [*issues, *projects]
        for risk in (item.risks or [])
        if not action_is_resolved(str(risk))
    ]
    context_priorities = [
        _dashboard_item(
            project,
            record_type="project",
            title=project.title,
            why="Active project in executive memory.",
            score=38 + (12 if project.risks else 0) + (10 if not project.owner else 0),
            next_action="Review owner, risk, and next step.",
            owner=project.owner or "",
            company=project.company or "",
            status=project.status or "active",
            source=_source_for(project, "project"),
            score_reasons=["active project"] + (["explicit risk"] if project.risks else []) + (["missing owner"] if not project.owner else []),
        )
        for project in projects
        if project.status == "active"
    ] + [
        _dashboard_item(
            issue,
            record_type="strategic_issue",
            title=issue.title,
            why="Active strategic issue in executive memory.",
            score=36 + (12 if issue.risks else 0) + (10 if not issue.owner else 0),
            next_action="Confirm current owner and decision needed.",
            owner=issue.owner or "",
            company=issue.company or "",
            status=issue.status or "active",
            source=_source_for(issue, "strategic_issue"),
            score_reasons=["active strategic issue"] + (["explicit risk"] if issue.risks else []) + (["missing owner"] if not issue.owner else []),
        )
        for issue in issues
    ]
    overdue_decisions = [
        _decision_item(decision, today)
        for decision in decisions
        if decision.review_date and decision.review_date < today_iso
    ]

    needs_attention = [
        item for item in task_items
        if item["score"] >= 85 or not item["owner"] or _is_executive_owner(item["owner"], username)
        if item["status"] not in {"blocked", "waiting"}
    ] + overdue_decisions + risk_items[:5]
    delegate_follow_up = [
        item for item in task_items
        if item["owner"] and not _is_executive_owner(item["owner"], username) and item["status"] not in {"blocked", "waiting"}
    ]
    visible_task_by_id = {task.id: task for task in visible_open_tasks}
    overdue = [
        item for item in task_items
        if item["record_id"] in visible_task_by_id and task_is_overdue(visible_task_by_id[item["record_id"]], today)
    ] + overdue_decisions
    blocked_waiting = [
        item for item in task_items
        if item["status"] in {"blocked", "waiting"} or any("blocked" in reason for reason in item["score_reasons"])
    ] + legacy_waiting

    upcoming = [
        item | {"why_it_matters": "Due soon and still open.", "recommended_next_action": item["recommended_next_action"]}
        for item in task_items
        if (days := _days_until(item["due_date"], today)) is not None and 0 <= days <= 14
    ] + [
        _dashboard_item(
            decision,
            record_type="decision",
            title=decision.title,
            why="Decision review date is coming up.",
            score=40,
            next_action="Prepare the review criteria.",
            company=decision.company or "",
            status="review upcoming",
            due_date=decision.review_date or "",
            score_reasons=["upcoming review"],
        )
        for decision in decisions
        if (days := _days_until(decision.review_date, today)) is not None and 0 <= days <= 14
    ] + [
        _dashboard_item(
            meeting,
            record_type="meeting",
            title=meeting.title,
            why="Calendar commitment scheduled for today.",
            score=35,
            next_action="Open meeting prep before the meeting.",
            company=meeting.company or "",
            status="today",
            due_date=meeting.date or "",
            score_reasons=["meeting today"],
        )
        for meeting in meetings_today
    ]

    changed_since_last = []
    if previous_viewed_at:
        for record_type, items in {
            "task": tasks,
            "project": projects,
            "strategic_issue": issues,
            "decision": decisions,
            "meeting": all_meetings,
            "person": people,
            "metric": metrics,
            "capture": list(recent_captures),
        }.items():
            for item in items:
                    if isinstance(item, Task) and item.status not in OPEN_TASK_STATUSES:
                        continue
                    changed_at = _updated_at(item)
                    if changed_at and changed_at > previous_viewed_at:
                        changed_since_last.append(_changed_item(item, record_type))

    waiting_on = blocked_waiting
    seen_sections: set[tuple[str, Any, str]] = set()
    needs_your_attention = _without_seen(needs_attention, seen_sections, 4)
    delegate_or_follow_up = _without_seen(delegate_follow_up, seen_sections, 4)
    overdue_section = _without_seen(overdue, seen_sections, 4)
    blocked_or_waiting = _without_seen(blocked_waiting, seen_sections, 4)
    changed_section = _without_seen(changed_since_last, seen_sections, 4)
    upcoming_section = _without_seen(upcoming, seen_sections, 4)
    clarification_section = briefing_clarification_items(db, limit=5)
    priorities = _unique_dashboard_items(needs_attention + delegate_follow_up + context_priorities, 6)
    focus = priorities[0]["title"] if priorities else "Capture the most important current context"

    if not view:
        view = BriefingView(username=username, last_viewed_at=now)
        db.add(view)
    else:
        view.last_viewed_at = now
    db.commit()

    return {
        "generated_at": now.isoformat(),
        "previous_viewed_at": previous_viewed_at.isoformat() if previous_viewed_at else "",
        "needs_your_attention": needs_your_attention,
        "delegate_or_follow_up": delegate_or_follow_up,
        "overdue": overdue_section,
        "blocked_or_waiting": blocked_or_waiting,
        "changed_since_last_briefing": changed_section,
        "upcoming": upcoming_section,
        "clarifications_needed": clarification_section,
        "top_priorities": priorities,
        "strategic_issues": [{"label": issue.title, "company": issue.company or ""} for issue in issues[:8]],
        "meetings_today": [{"label": meeting.title, "company": meeting.company or ""} for meeting in meetings_today],
        "open_decisions": list({
            (decision.title, decision.company or ""): {"label": decision.title, "company": decision.company or ""}
            for decision in decisions
            if not decision.review_date or decision.review_date >= today_iso
        }.values())[:8],
        "people_needing_attention": [
            {"label": person.name, "company": person.company or ""}
            for person in people
            if person.concerns
        ][:5],
        "waiting_on_items": waiting_on[:8],
        "open_tasks": [
            {
                "label": task.title,
                "record_type": "task",
                "record_id": task.id,
                "task_id": task.id,
                "company": task.company or "",
                "owner": task.owner or "",
                "status": task.status,
                "due_date": task.due_date or "",
            }
            for task in visible_open_tasks[:8]
        ],
        "overdue_tasks": [
            {
                "label": task.title,
                "record_type": "task",
                "record_id": task.id,
                "task_id": task.id,
                "company": task.company or "",
                "owner": task.owner or "",
                "status": task.status,
                "due_date": task.due_date or "",
            }
            for task in visible_open_tasks
            if task_is_overdue(task, today)
        ][:8],
        "risks": [{"label": item["title"], "company": item["company"]} for item in risk_items[:8]],
        "recent_updates": [
            {"label": _result_summary(capture), "company": company_label_for_text(capture.raw_text)}
            for capture in recent_captures[:5]
        ],
        "recommended_focus": f"Focus first on {focus}.",
    }
