import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import CaptureRecord, Meeting, Project, ResolvableItem, RevisionRecord, StrategicIssue


OPEN_RESOLVABLE_STATUSES = {"open", "reopened"}
RESOLUTION_WORDS = {"resolved", "complete", "completed", "done", "closed", "fixed"}
STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "by", "for", "from", "in", "is",
    "mark", "of", "on", "resolved", "complete", "completed", "done", "closed",
    "fixed", "set", "the", "to", "with",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token not in STOP_WORDS}


def _resolution_target(text: str) -> str:
    pattern = r"(?:resolved|complete|completed|done|closed|fixed)"
    match = re.search(rf"\b(?:mark|set)\s+(.+?)\s+as\s+{pattern}\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(" :-")
    match = re.search(rf"\b(?:mark|set)\s+as\s+{pattern}\s*[:\-]\s*(.+)$", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(" :-")
    return ""


def _capture_matches_item(text: str, display_text: str) -> bool:
    target = _resolution_target(text) or text
    target_tokens = _tokens(target)
    item_tokens = _tokens(display_text)
    raw_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    if not target_tokens or not item_tokens:
        return False
    if not (raw_tokens & RESOLUTION_WORDS):
        return len(target_tokens & item_tokens) >= 2 and bool(raw_tokens & {"will", "working", "hours", "owns", "confirmed"})
    return item_tokens <= target_tokens or len(target_tokens & item_tokens) >= max(1, min(len(target_tokens), len(item_tokens)))


def _dedupe_key(parent_type: str, parent_id: int, item_type: str, display_text: str) -> str:
    digest = hashlib.sha1(_normalize_text(display_text).encode("utf-8")).hexdigest()[:16]
    return f"{parent_type}:{parent_id}:{item_type}:{digest}"


def serialize_resolvable_item(item: ResolvableItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "parent_type": item.parent_type,
        "parent_id": item.parent_id,
        "item_type": item.item_type,
        "display_text": item.display_text,
        "label": item.display_text,
        "title": item.display_text,
        "company": item.company or "",
        "status": item.status,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else "",
        "resolved_by": item.resolved_by or "",
        "resolution_source": item.resolution_source or "",
        "resolution_note": item.resolution_note or "",
        "record_type": item.item_type,
        "record_id": item.id,
        "resolvable_item_id": item.id,
        "resolvable": item.status in OPEN_RESOLVABLE_STATUSES,
    }


def _record_revision(db: Session, item: ResolvableItem, change_type: str) -> None:
    db.add(RevisionRecord(
        object_type="resolvable_item",
        object_id=item.id or 0,
        change_type=change_type,
        after=serialize_resolvable_item(item),
        source_type=item.resolution_source or "manual",
    ))


def ensure_resolvable_item(
    db: Session,
    *,
    parent_type: str,
    parent_id: int,
    item_type: str,
    display_text: str,
    company: str = "",
) -> ResolvableItem | None:
    display_text = str(display_text or "").strip()
    if not display_text or not parent_id:
        return None
    key = _dedupe_key(parent_type, parent_id, item_type, display_text)
    item = db.query(ResolvableItem).filter(ResolvableItem.dedupe_key == key).first()
    if not item:
        item = ResolvableItem(
            parent_type=parent_type,
            parent_id=parent_id,
            item_type=item_type,
            display_text=display_text,
            status="open",
            company=company or "",
            dedupe_key=key,
        )
    else:
        item.display_text = display_text
        item.company = company or item.company
    db.add(item)
    db.flush()
    db.refresh(item)
    return item


def sync_resolvable_items(db: Session, *, company: str = "") -> list[ResolvableItem]:
    items: list[ResolvableItem] = []
    active_keys: set[str] = set()
    historical_captures = db.query(CaptureRecord).order_by(CaptureRecord.id.desc()).limit(500).all()

    def apply_historical_resolution(item: ResolvableItem) -> None:
        if item.status not in OPEN_RESOLVABLE_STATUSES:
            return
        if any(_capture_matches_item(capture.raw_text, item.display_text) for capture in historical_captures):
            item.status = "resolved"
            item.resolved_at = datetime.now(timezone.utc)
            item.resolution_source = "historical_capture_backfill"
            db.add(item)
    meetings = db.query(Meeting).all()
    projects = db.query(Project).all()
    issues = db.query(StrategicIssue).all()
    if company:
        meetings = [item for item in meetings if (item.company or "").lower() == company.lower()]
        projects = [item for item in projects if (item.company or "").lower() == company.lower()]
        issues = [item for item in issues if (item.company or "").lower() == company.lower()]
    for meeting in meetings:
        for action in meeting.action_items or []:
            item = ensure_resolvable_item(
                db,
                parent_type="meeting",
                parent_id=meeting.id or 0,
                item_type="meeting_action",
                display_text=str(action),
                company=meeting.company or "",
            )
            if item:
                apply_historical_resolution(item)
                active_keys.add(item.dedupe_key)
                items.append(item)
    for project in projects:
        for risk in project.risks or []:
            item = ensure_resolvable_item(
                db,
                parent_type="project",
                parent_id=project.id or 0,
                item_type="risk",
                display_text=str(risk),
                company=project.company or "",
            )
            if item:
                apply_historical_resolution(item)
                active_keys.add(item.dedupe_key)
                items.append(item)
    for issue in issues:
        for risk in issue.risks or []:
            item = ensure_resolvable_item(
                db,
                parent_type="strategic_issue",
                parent_id=issue.id or 0,
                item_type="risk",
                display_text=str(risk),
                company=issue.company or "",
            )
            if item:
                apply_historical_resolution(item)
                active_keys.add(item.dedupe_key)
                items.append(item)
    query = db.query(ResolvableItem).filter(
        ResolvableItem.item_type.in_(["risk", "meeting_action"]),
        ResolvableItem.status.in_(OPEN_RESOLVABLE_STATUSES),
    )
    if company:
        query = query.filter(ResolvableItem.company == company)
    for item in query.all():
        if item.dedupe_key not in active_keys:
            item.status = "resolved"
            item.resolved_at = datetime.now(timezone.utc)
            item.resolution_source = "source_record_update"
            db.add(item)
    db.flush()
    return items


def list_resolvable_items(
    db: Session,
    *,
    status: str = "open",
    company: str = "",
    item_type: str = "",
    include_sync: bool = True,
    limit: int = 200,
) -> list[ResolvableItem]:
    if include_sync:
        sync_resolvable_items(db, company=company)
    query = db.query(ResolvableItem)
    if status == "open":
        query = query.filter(ResolvableItem.status.in_(OPEN_RESOLVABLE_STATUSES))
    elif status:
        query = query.filter(ResolvableItem.status == status)
    if company:
        query = query.filter(ResolvableItem.company == company)
    if item_type:
        query = query.filter(ResolvableItem.item_type == item_type)
    return query.order_by(ResolvableItem.updated_at.desc(), ResolvableItem.id.desc()).limit(limit).all()


def resolve_resolvable_item(
    db: Session,
    item: ResolvableItem,
    *,
    actor: str = "",
    source: str = "manual",
    note: str = "",
) -> ResolvableItem:
    item.status = "resolved"
    item.resolved_at = datetime.now(timezone.utc)
    item.resolved_by = actor or item.resolved_by
    item.resolution_source = source
    item.resolution_note = note or item.resolution_note
    db.add(item)
    db.flush()
    db.refresh(item)
    _record_revision(db, item, "resolve")
    return item


def reopen_resolvable_item(db: Session, item: ResolvableItem, *, actor: str = "", note: str = "") -> ResolvableItem:
    item.status = "reopened"
    item.reopened_at = datetime.now(timezone.utc)
    item.resolved_at = None
    item.resolution_source = "reopen"
    item.resolution_note = note or item.resolution_note
    item.resolved_by = actor or item.resolved_by
    db.add(item)
    db.flush()
    db.refresh(item)
    _record_revision(db, item, "reopen")
    return item


def resolvable_item_or_404(db: Session, item_id: int) -> ResolvableItem:
    item = db.get(ResolvableItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Resolvable item not found")
    return item


def resolve_items_from_capture_text(db: Session, text: str, *, actor: str = "") -> list[ResolvableItem]:
    sync_resolvable_items(db)
    raw_tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    explicit = bool(raw_tokens & RESOLUTION_WORDS)
    candidates = [
        item for item in db.query(ResolvableItem).filter(ResolvableItem.status.in_(OPEN_RESOLVABLE_STATUSES)).all()
        if _capture_matches_item(text, item.display_text)
        and (explicit or item.item_type == "meeting_action")
    ]
    if not explicit:
        return [
            resolve_resolvable_item(db, item, actor=actor, source="capture_answer", note=text[:500])
            for item in candidates
        ]
    exact = [
        item for item in candidates
        if _normalize_text(item.display_text) in _normalize_text(text)
    ]
    selected = exact or candidates
    if len(selected) != 1:
        return []
    return [resolve_resolvable_item(db, selected[0], actor=actor, source="capture", note=text[:500])]
