from typing import Any

from sqlalchemy.orm import Session

from .memory import _model_for_object_type, _serialize_model
from .models import Company, Decision, Meeting, Metric, Person, Project, SOP, StrategicIssue, Task


LINKABLE_MODELS = [Company, Person, StrategicIssue, Project, Decision, Meeting, Metric, Task, SOP]
MODEL_TYPES = {
    Company: "companies",
    Person: "people",
    StrategicIssue: "strategic-issues",
    Project: "projects",
    Decision: "decisions",
    Meeting: "meetings",
    Metric: "metrics",
    Task: "tasks",
    SOP: "sops",
}
LABEL_FIELD = {Company: "name"}
EXPLICIT_LINKS = {
    Person: {
        "linked_projects": Project,
        "linked_decisions": Decision,
        "linked_meetings": Meeting,
    },
    StrategicIssue: {
        "linked_projects": Project,
        "linked_decisions": Decision,
        "linked_metrics": Metric,
    },
    Project: {
        "linked_people": Person,
        "linked_decisions": Decision,
    },
    Decision: {
        "linked_people": Person,
        "linked_projects": Project,
        "linked_strategic_issues": StrategicIssue,
    },
    Meeting: {
        "linked_people": Person,
        "linked_projects": Project,
        "linked_strategic_issues": StrategicIssue,
    },
}


def _label(item: Any) -> str:
    field = LABEL_FIELD.get(type(item), "title")
    return str(getattr(item, field, "") or "")


def _compact(item: Any, record_type: str, reason: str) -> dict[str, Any]:
    return {
        "record_type": record_type,
        "id": item.id,
        "label": _label(item),
        "company": getattr(item, "company", "") or (item.name if isinstance(item, Company) else ""),
        "reason": reason,
        "summary": (
            getattr(item, "current_thinking", "")
            or getattr(item, "objective", "")
            or getattr(item, "context", "")
            or getattr(item, "summary", "")
            or getattr(item, "description", "")
            or getattr(item, "role", "")
            or getattr(item, "value", "")
            or getattr(item, "status", "")
            or ""
        ),
    }


def _append_unique(groups: dict[str, list[dict[str, Any]]], item: Any, reason: str) -> None:
    record_type = MODEL_TYPES[type(item)]
    existing = {(entry["record_type"], entry["id"]) for entries in groups.values() for entry in entries}
    key = (record_type, item.id)
    if key in existing:
        return
    groups.setdefault(record_type, []).append(_compact(item, record_type, reason))


def _matches_label(value: Any, label: str) -> bool:
    return str(value or "").strip().lower() == label.strip().lower()


def _find_by_labels(db: Session, model: type[Any], labels: list[str]) -> list[Any]:
    wanted = {str(label or "").strip().lower() for label in labels if str(label or "").strip()}
    if not wanted:
        return []
    field = LABEL_FIELD.get(model, "title")
    return [
        item for item in db.query(model).all()
        if str(getattr(item, field, "") or "").strip().lower() in wanted
    ]


def related_records(db: Session, object_type: str, object_id: int) -> dict[str, Any]:
    model = _model_for_object_type(object_type)
    item = db.get(model, object_id)
    if not item:
        return {}

    groups: dict[str, list[dict[str, Any]]] = {}
    item_label = _label(item)
    company = getattr(item, "company", "") or (item.name if isinstance(item, Company) else "")

    if isinstance(item, Company):
        for related_model in LINKABLE_MODELS:
            if related_model is Company:
                continue
            for related in db.query(related_model).filter(getattr(related_model, "company", "") == item.name).limit(12).all():
                _append_unique(groups, related, "Company memory")
    elif company:
        company_record = db.query(Company).filter(Company.name.ilike(company)).first()
        if company_record:
            _append_unique(groups, company_record, "Company")
        for related_model in [Person, StrategicIssue, Project, Decision, Meeting, Metric, Task]:
            if related_model is model:
                continue
            for related in db.query(related_model).filter(getattr(related_model, "company", "") == company).limit(6).all():
                _append_unique(groups, related, "Same company")

    for field, target_model in EXPLICIT_LINKS.get(model, {}).items():
        for related in _find_by_labels(db, target_model, list(getattr(item, field, None) or [])):
            _append_unique(groups, related, f"Explicit {field.replace('_', ' ')} link")

    for related_model, fields in EXPLICIT_LINKS.items():
        if related_model is model:
            continue
        for related in db.query(related_model).all():
            if any(any(_matches_label(value, item_label) for value in getattr(related, field, None) or []) for field in fields):
                _append_unique(groups, related, "Reciprocal explicit link")

    if isinstance(item, Task) and item.source_type == "meeting" and item.source_id:
        meeting = db.get(Meeting, int(item.source_id)) if str(item.source_id).isdigit() else None
        if meeting:
            _append_unique(groups, meeting, "Task source meeting")
    if isinstance(item, Meeting):
        for task in db.query(Task).filter(Task.source_type == "meeting", Task.source_id == str(item.id)).all():
            _append_unique(groups, task, "Linked meeting task")
        for person in _find_by_labels(db, Person, list(item.attendees or [])):
            _append_unique(groups, person, "Meeting attendee")

    ordered_groups = {
        record_type: sorted(entries, key=lambda entry: entry["label"].lower())[:10]
        for record_type, entries in sorted(groups.items())
    }
    return {
        "object": _serialize_model(item),
        "object_type": object_type,
        "related": ordered_groups,
        "total": sum(len(entries) for entries in ordered_groups.values()),
    }
