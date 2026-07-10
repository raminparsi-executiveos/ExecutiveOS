from datetime import date, datetime, timezone
from itertools import combinations
from typing import Any

from sqlalchemy.orm import Session

from .memory import _match_score, _serialize_model, company_label_for_text
from .models import (
    CaptureRecord,
    Company,
    DashboardConfig,
    Decision,
    EntityAlias,
    IntegrationInboxItem,
    Metric,
    Person,
    Project,
    ProvenanceRecord,
    RevisionRecord,
    ReviewAlert,
    SearchConversation,
    StrategicIssue,
    Task,
)
from .tasks import OPEN_TASK_STATUSES, task_is_overdue


SOURCE_TYPES = {
    "manual_entry",
    "capture_text",
    "screenshot_or_uploaded_document",
    "google_calendar_event",
    "meeting_prep",
    "imported_legacy_record",
    "system_generated_suggestion",
}
REVIEW_ACTIONS = {"confirm", "update", "merge", "supersede", "dismiss"}
DASHBOARD_DEFAULTS = {
    "PEC": ["Sales pipeline", "Client-risk accounts", "Project delivery", "PM quality", "Staffing and performance", "Buyer diligence", "Open decisions", "Overdue commitments"],
    "RYSE Wellness": ["Census", "Admissions pipeline", "Staffing", "Overtime", "Clinical risks", "Compliance", "Insurance and collections", "Open decisions"],
    "EverPole": ["Partnerships", "Installations", "Manufacturing", "Product improvements", "Distributor pipeline", "Field issues", "Open decisions"],
    "MyndLog": ["Platform migration", "Product roadmap", "Privacy", "Backup strategy", "AI journaling work", "Open decisions"],
}


def serialize_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [_serialize_model(row) for row in rows]


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def record_revision(
    db: Session,
    object_type: str,
    object_id: int,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    change_type: str = "update",
    changed_by: str = "user",
    source_type: str = "",
    source_id: str = "",
) -> RevisionRecord:
    revision = RevisionRecord(
        object_type=object_type,
        object_id=object_id,
        before=_json_safe(before or {}),
        after=_json_safe(after or {}),
        change_type=change_type,
        changed_by=changed_by,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(revision)
    db.flush()
    return revision


def ensure_provenance(
    db: Session,
    object_type: str,
    object_id: int,
    *,
    source_type: str = "manual_entry",
    source_id: str = "",
    source_title: str = "",
    source_date: str = "",
    source_excerpt: str = "",
    created_by: str = "user",
    confidence: str = "user_confirmed",
    verification_state: str = "user_confirmed",
    memory_classification: str = "confirmed_fact",
) -> ProvenanceRecord:
    normalized_source = source_type if source_type in SOURCE_TYPES else "manual_entry"
    existing = (
        db.query(ProvenanceRecord)
        .filter(
            ProvenanceRecord.object_type == object_type,
            ProvenanceRecord.object_id == object_id,
            ProvenanceRecord.original_source_type == normalized_source,
            ProvenanceRecord.original_source_id == str(source_id or ""),
        )
        .first()
    )
    record = existing or ProvenanceRecord(object_type=object_type, object_id=object_id)
    record.original_source_type = normalized_source
    record.original_source_id = str(source_id or "")
    record.source_title = source_title or record.source_title
    record.source_date = source_date or record.source_date
    record.source_excerpt = source_excerpt[:4000] or record.source_excerpt
    record.created_by = created_by
    record.confidence = confidence
    record.verification_state = verification_state
    record.memory_classification = memory_classification
    db.add(record)
    db.flush()
    return record


def provenance_bundle(db: Session, object_type: str, object_id: int) -> dict[str, Any]:
    provenance = (
        db.query(ProvenanceRecord)
        .filter(ProvenanceRecord.object_type == object_type, ProvenanceRecord.object_id == object_id)
        .order_by(ProvenanceRecord.created_at.desc())
        .all()
    )
    revisions = (
        db.query(RevisionRecord)
        .filter(RevisionRecord.object_type == object_type, RevisionRecord.object_id == object_id)
        .order_by(RevisionRecord.changed_at.desc())
        .all()
    )
    return {"provenance": serialize_rows(provenance), "revisions": serialize_rows(revisions)}


def _alert_exists(db: Session, alert_type: str, object_type: str, object_id: int, related_id: int | None = None) -> bool:
    query = db.query(ReviewAlert).filter(
        ReviewAlert.alert_type == alert_type,
        ReviewAlert.object_type == object_type,
        ReviewAlert.object_id == object_id,
        ReviewAlert.status.in_(["open", "confirmed"]),
    )
    if related_id is not None:
        query = query.filter(ReviewAlert.related_object_id == related_id)
    return query.first() is not None


def _add_alert(
    db: Session,
    *,
    alert_type: str,
    title: str,
    description: str,
    severity: str = "medium",
    object_type: str = "",
    object_id: int | None = None,
    related_object_type: str = "",
    related_object_id: int | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> ReviewAlert | None:
    if object_id and _alert_exists(db, alert_type, object_type, object_id, related_object_id):
        return None
    alert = ReviewAlert(
        alert_type=alert_type,
        title=title,
        description=description,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        evidence=evidence or [],
    )
    db.add(alert)
    db.flush()
    return alert


def generate_review_alerts(db: Session) -> list[ReviewAlert]:
    today = date.today()
    created: list[ReviewAlert] = []

    for left, right in combinations(db.query(Person).all(), 2):
        if left.name.strip().lower() == right.name.strip().lower() and left.role and right.role and left.role != right.role:
            alert = _add_alert(
                db,
                alert_type="conflicting_active_roles",
                title=f"Review role conflict for {left.name}",
                description=f"{left.name} appears with roles '{left.role}' and '{right.role}'.",
                object_type="people",
                object_id=left.id,
                related_object_type="people",
                related_object_id=right.id,
                evidence=[{"role": left.role}, {"role": right.role}],
            )
            if alert:
                created.append(alert)

    for left, right in combinations(db.query(Project).filter(Project.status == "active").all(), 2):
        if left.title.strip().lower() == right.title.strip().lower() and left.owner and right.owner and left.owner != right.owner:
            alert = _add_alert(
                db,
                alert_type="multiple_active_project_owners",
                title=f"Review project owner conflict: {left.title}",
                description=f"{left.title} has active owners '{left.owner}' and '{right.owner}'.",
                object_type="projects",
                object_id=left.id,
                related_object_type="projects",
                related_object_id=right.id,
                evidence=[{"owner": left.owner}, {"owner": right.owner}],
            )
            if alert:
                created.append(alert)

    for task in db.query(Task).all():
        if task_is_overdue(task, today):
            alert = _add_alert(
                db,
                alert_type="task_overdue",
                title=f"Overdue task: {task.title}",
                description=f"{task.title} was due {task.due_date} and is still {task.status}.",
                severity="high" if task.priority in {"critical", "high"} else "medium",
                object_type="tasks",
                object_id=task.id,
                evidence=[{"due_date": task.due_date, "status": task.status, "priority": task.priority}],
            )
            if alert:
                created.append(alert)

    for decision in db.query(Decision).all():
        if decision.review_date and decision.review_date < today.isoformat():
            alert = _add_alert(
                db,
                alert_type="decision_review_overdue",
                title=f"Decision review overdue: {decision.title}",
                description=f"{decision.title} had a review date of {decision.review_date}.",
                object_type="decisions",
                object_id=decision.id,
                evidence=[{"review_date": decision.review_date}],
            )
            if alert:
                created.append(alert)

    for metric in db.query(Metric).all():
        if metric.date and metric.date < (today.replace(day=1)).isoformat():
            alert = _add_alert(
                db,
                alert_type="stale_metric",
                title=f"Metric may be stale: {metric.title}",
                description=f"{metric.title} was last updated for {metric.date}.",
                object_type="metrics",
                object_id=metric.id,
                evidence=[{"date": metric.date, "value": metric.value}],
            )
            if alert:
                created.append(alert)

    for left, right in combinations(db.query(Decision).all(), 2):
        if left.company == right.company and _match_score(left, ["title", "final_decision"], right.title) >= 12:
            if any(word in (right.final_decision or "").lower() for word in ["reverse", "pause", "cancel", "stop"]):
                alert = _add_alert(
                    db,
                    alert_type="decision_may_reverse_prior",
                    title=f"Decision may supersede earlier decision: {right.title}",
                    description=f"{right.title} may reverse or supersede {left.title}.",
                    object_type="decisions",
                    object_id=right.id,
                    related_object_type="decisions",
                    related_object_id=left.id,
                    evidence=[{"new": right.final_decision}, {"prior": left.final_decision}],
                )
                if alert:
                    created.append(alert)

    db.commit()
    return created


def resolve_alert(db: Session, alert: ReviewAlert, action: str, resolution: str) -> ReviewAlert:
    if action not in REVIEW_ACTIONS:
        action = "confirm"
    alert.status = "dismissed" if action == "dismiss" else "resolved"
    alert.resolution = resolution or action
    alert.resolved_at = datetime.now(timezone.utc)
    db.add(alert)
    db.flush()
    return alert


def default_modules(company: str) -> list[dict[str, Any]]:
    names = DASHBOARD_DEFAULTS.get(company, ["Open decisions", "Overdue commitments", "Risks", "Projects", "Metrics"])
    return [{"name": name, "visible": True, "order": index} for index, name in enumerate(names)]


def get_dashboard_config(db: Session, company: str) -> DashboardConfig:
    config = db.query(DashboardConfig).filter(DashboardConfig.company.ilike(company)).first()
    if not config:
        config = DashboardConfig(company=company, modules=default_modules(company))
        db.add(config)
        db.flush()
    return config


def company_dashboard(db: Session, company: str) -> dict[str, Any]:
    config = get_dashboard_config(db, company)
    projects = db.query(Project).filter(Project.company.ilike(company)).all()
    decisions = db.query(Decision).filter(Decision.company.ilike(company)).all()
    metrics = db.query(Metric).filter(Metric.company.ilike(company)).all()
    tasks = db.query(Task).filter(Task.company.ilike(company)).all()
    issues = db.query(StrategicIssue).filter(StrategicIssue.company.ilike(company)).all()
    freshness_values = [item.updated_at or item.created_at for item in [*projects, *decisions, *metrics, *tasks, *issues] if getattr(item, "created_at", None)]
    module_rows = []
    for module in sorted(config.modules or [], key=lambda item: item.get("order", 0)):
        if module.get("visible") is False:
            continue
        name = module.get("name", "Module")
        query = name.lower()
        items = []
        if "decision" in query:
            items = decisions
        elif "commitment" in query or "task" in query or "overdue" in query:
            items = [task for task in tasks if task.status in OPEN_TASK_STATUSES]
        elif "metric" in query or any(token in query for token in ["census", "pipeline", "overtime", "privacy", "backup"]):
            items = metrics
        elif "risk" in query or "compliance" in query or "clinical" in query:
            items = [issue for issue in issues if issue.risks or "risk" in issue.title.lower() or "compliance" in issue.title.lower()]
        else:
            items = [item for item in [*projects, *issues, *tasks] if _match_score(item, ["title", "objective", "current_thinking", "description", "tags"], name)]
        module_rows.append({
            "name": name,
            "visible": True,
            "items": [_serialize_model(item) for item in items[:10]],
            "has_current_data": bool(items),
        })
    return {
        "company": company,
        "modules": module_rows,
        "data_freshness": max(freshness_values).isoformat() if freshness_values else "",
    }


def suggest_updates_from_text(text: str, source_type: str, source_title: str = "") -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    company = company_label_for_text(text)
    if source_title:
        suggestions.append({
            "type": "document",
            "title": source_title,
            "company": company,
            "summary": text[:500],
            "source": source_type,
            "memory_classification": "unverified_information",
            "verification_state": "ai_extracted_pending_review",
        })
    if "will " in text.lower() or "follow up" in text.lower():
        suggestions.append({
            "type": "task",
            "title": text.strip().split(".")[0][:200],
            "company": company,
            "status": "open",
            "priority": "medium",
            "source_type": source_type,
            "source_summary": text[:500],
            "memory_classification": "commitment",
            "verification_state": "ai_extracted_pending_review",
        })
    return suggestions


def create_inbox_item(db: Session, payload: Any) -> IntegrationInboxItem:
    allowed = {"google_calendar_event", "uploaded_document", "screenshot_or_uploaded_document"}
    source_type = payload.source_type if payload.source_type in allowed else "uploaded_document"
    duplicate = None
    if payload.source_identifier:
        duplicate = db.query(IntegrationInboxItem).filter(
            IntegrationInboxItem.source_type == source_type,
            IntegrationInboxItem.source_identifier == payload.source_identifier,
        ).first()
    item = duplicate or IntegrationInboxItem(source_type=source_type, source_identifier=payload.source_identifier)
    item.source_title = payload.source_title
    item.source_date = payload.source_date
    item.source_metadata = payload.metadata
    item.extracted_text = payload.extracted_text
    item.suggested_updates = suggest_updates_from_text(payload.extracted_text, source_type, payload.source_title)
    item.status = "new" if item.suggested_updates else "error"
    item.error = "" if item.suggested_updates else "No readable supported updates found."
    db.add(item)
    db.flush()
    return item


def entity_resolution_suggestions(db: Session) -> list[dict[str, Any]]:
    suggestions = []
    people = db.query(Person).all()
    for left, right in combinations(people, 2):
        if not left.name or not right.name:
            continue
        left_tokens = set(left.name.lower().split())
        right_tokens = set(right.name.lower().split())
        if left_tokens & right_tokens and left.name.lower() != right.name.lower():
            suggestions.append({
                "entity_type": "people",
                "candidate_ids": [left.id, right.id],
                "names": [left.name, right.name],
                "reason": "Names share tokens; confirm before merging.",
                "confidence": "possible",
            })
    companies = db.query(Company).all()
    for company in companies:
        aliases = [alias.alias for alias in db.query(EntityAlias).filter(EntityAlias.entity_type == "companies", EntityAlias.entity_id == company.id).all()]
        suggestions.append({
            "entity_type": "companies",
            "candidate_ids": [company.id],
            "names": [company.name, *aliases],
            "reason": "Known company aliases are preserved for resolution.",
            "confidence": "user_confirmed" if aliases else "none",
        })
    return suggestions


def update_search_conversation(db: Session, conversation_id: str, query: str, result_ids: list[dict[str, Any]]) -> str:
    if not conversation_id:
        conversation_id = f"search-{datetime.now(timezone.utc).timestamp():.6f}"
    conversation = db.query(SearchConversation).filter(SearchConversation.conversation_id == conversation_id).first()
    if not conversation:
        conversation = SearchConversation(conversation_id=conversation_id)
    conversation.last_query = query
    conversation.context = {"results": result_ids}
    db.add(conversation)
    db.flush()
    return conversation_id
