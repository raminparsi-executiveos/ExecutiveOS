import re
from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .leadership_lens import enrich_task_update_with_leadership_lens
from .models import Meeting, Task


TASK_STATUSES = {"open", "in_progress", "waiting", "blocked", "completed", "cancelled"}
TASK_PRIORITIES = {"critical", "high", "medium", "low"}
OPEN_TASK_STATUSES = TASK_STATUSES - {"completed", "cancelled"}


def _normalize_enum_value(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    return normalized.strip("_")


def normalize_task_status(value: Any, *, fallback_unknown: bool = False) -> str:
    normalized = _normalize_enum_value(value)
    aliases = {
        "": "open",
        "active": "open",
        "todo": "open",
        "to_do": "open",
        "not_started": "open",
        "pending": "waiting",
        "pending_approval": "waiting",
        "pending_leadership_approval": "waiting",
        "proposed": "waiting",
        "proposed_pending_approval": "waiting",
        "proposed_pending_leadership_approval": "waiting",
        "canceled": "cancelled",
        "cancelled": "cancelled",
    }
    if normalized in aliases:
        return aliases[normalized]
    if normalized in TASK_STATUSES:
        return normalized
    return "open" if fallback_unknown else normalized


def normalize_task_priority(value: Any, *, fallback_unknown: bool = False) -> str:
    normalized = _normalize_enum_value(value)
    aliases = {
        "": "medium",
        "med": "medium",
        "normal": "medium",
        "next": "medium",
        "soon": "medium",
        "urgent": "critical",
    }
    if normalized in aliases:
        return aliases[normalized]
    if normalized in TASK_PRIORITIES:
        return normalized
    return "medium" if fallback_unknown else normalized


def normalize_task_attributes(attributes: dict[str, Any], *, fallback_unknown: bool = False) -> dict[str, Any]:
    normalized = dict(attributes)
    if "status" in normalized:
        normalized["status"] = normalize_task_status(normalized["status"], fallback_unknown=fallback_unknown)
    if "priority" in normalized:
        normalized["priority"] = normalize_task_priority(normalized["priority"], fallback_unknown=fallback_unknown)
    return normalized


def validate_task_attributes(attributes: dict[str, Any], *, partial: bool = False, fallback_unknown: bool = False) -> None:
    attributes.update(normalize_task_attributes(attributes, fallback_unknown=fallback_unknown))
    if not partial and not str(attributes.get("title") or "").strip():
        raise HTTPException(status_code=422, detail="Missing required field: title")
    if "title" in attributes and not str(attributes.get("title") or "").strip():
        raise HTTPException(status_code=422, detail="Missing required field: title")
    if "status" in attributes and attributes["status"] not in TASK_STATUSES:
        raise HTTPException(status_code=422, detail=f"Unsupported task status: {attributes['status']}")
    if "priority" in attributes and attributes["priority"] not in TASK_PRIORITIES:
        raise HTTPException(status_code=422, detail=f"Unsupported task priority: {attributes['priority']}")


def task_is_overdue(task: Task, today: date | None = None) -> bool:
    if task.status not in OPEN_TASK_STATUSES or not task.due_date:
        return False
    try:
        due_date = date.fromisoformat(task.due_date)
    except ValueError:
        return False
    return due_date < (today or date.today())


def serialize_task(task: Task) -> dict[str, Any]:
    return {
        column.name: getattr(task, column.name)
        for column in task.__table__.columns
    } | {"is_overdue": task_is_overdue(task)}


def normalize_task_title(title: str) -> str:
    return " ".join(str(title or "").split())


def _parse_owner_from_title(title: str) -> str:
    owner_match = re.match(r"\s*([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s*(?::|-|\bwill\b)\s+", title)
    return owner_match.group(1).strip() if owner_match else ""


def task_from_action_item(
    db: Session,
    action_item: str,
    *,
    company: str = "",
    source_type: str = "meeting",
    source_id: str | int = "",
    source_summary: str = "",
    owner: str = "",
) -> Task:
    title = normalize_task_title(action_item)
    if not title:
        raise ValueError("Task title is required")
    source_id_value = str(source_id or "")
    task = (
        db.query(Task)
        .filter(
            Task.title.ilike(title),
            Task.source_type == source_type,
            Task.source_id == source_id_value,
        )
        .first()
    )
    created = task is None
    if not task:
        task = Task(title=title)
    task.company = company or task.company
    task.owner = owner or task.owner or _parse_owner_from_title(title)
    if created and source_type == "meeting":
        task.status = "waiting"
    else:
        task.status = task.status if task.status in TASK_STATUSES else "open"
    task.priority = task.priority if task.priority in TASK_PRIORITIES else "medium"
    task.source_type = source_type
    task.source_id = source_id_value
    task.source_summary = source_summary or task.source_summary
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def ensure_tasks_for_meeting_action_items(db: Session, meeting: Meeting) -> list[Task]:
    tasks = []
    for action_item in meeting.action_items or []:
        if not str(action_item or "").strip():
            continue
        tasks.append(task_from_action_item(
            db,
            str(action_item),
            company=meeting.company or "",
            source_type="meeting",
            source_id=meeting.id or "",
            source_summary=meeting.title or "",
        ))
    return tasks


def upsert_task_from_update(
    db: Session,
    update: dict[str, Any],
    *,
    default_company: str = "",
    default_source_type: str = "capture_text",
    default_source_summary: str = "",
) -> Task | None:
    title = normalize_task_title(update.get("title") or update.get("details") or "")
    if not title:
        return None
    update = enrich_task_update_with_leadership_lens({**update, "type": "task", "title": title})
    update = normalize_task_attributes(update, fallback_unknown=True)
    status = update.get("status") or "open"
    priority = update.get("priority") or "medium"
    validate_task_attributes({"title": title, "status": status, "priority": priority}, fallback_unknown=True)
    source_type = update.get("source_type") or default_source_type
    source_id = str(update.get("source_id") or "")
    field_operations = update.get("field_operations") or {}
    query = db.query(Task).filter(Task.title.ilike(title))
    if source_type:
        query = query.filter(Task.source_type == source_type)
    if source_id:
        query = query.filter(Task.source_id == source_id)
    task = query.first() or Task(title=title)
    for field in (
        "description", "owner", "due_date", "status", "priority", "source_type",
        "source_id", "source_summary", "next_action", "blocked_by", "tags",
        "expected_deliverable", "definition_of_done", "why_it_matters",
        "delegated_by", "assigned_to", "waiting_on", "stakeholders",
        "dependencies", "follow_up_date", "recurrence", "task_type",
        "confidence", "interpretation_notes", "source_excerpt",
        "parent_task_id", "linked_project_ids", "linked_decision_ids",
        "linked_people",
    ):
        value = update.get(field)
        if field_operations.get(field) == "clear":
            current_value = getattr(task, field, "")
            setattr(task, field, [] if isinstance(current_value, list) else "")
        elif value not in (None, "", []):
            setattr(task, field, value)
    task.company = update.get("company") or default_company or task.company
    task.source_type = task.source_type or source_type
    task.source_summary = task.source_summary or default_source_summary
    if task.status == "completed" and not task.completed_at:
        task.completed_at = datetime.now(timezone.utc)
    if task.status != "completed":
        task.completed_at = None
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def complete_task(db: Session, task: Task) -> Task:
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    task.last_reviewed_at = task.completed_at
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


def reopen_task(db: Session, task: Task) -> Task:
    task.status = "open"
    task.completed_at = None
    task.last_reviewed_at = datetime.now(timezone.utc)
    db.add(task)
    db.flush()
    db.refresh(task)
    return task
