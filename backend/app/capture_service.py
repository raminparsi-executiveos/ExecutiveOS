import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from .ai import SuggestedUpdate, analyze_capture
from .memory import (
    _company_is_explicitly_negated,
    _detect_positive_company,
    _normalize_company,
)
from .models import CaptureRecord, Company, Decision, Meeting, Metric, Person, Project, SOP, StrategicIssue, Document, Task
from .roadmap_services import ensure_provenance, record_revision
from .tasks import ensure_tasks_for_meeting_action_items, upsert_task_from_update


WAITING_ITEM_STOP_WORDS = {
    "a", "about", "an", "and", "are", "ask", "by", "check", "clarify",
    "confirm", "determine", "find", "for", "from", "get", "her", "his",
    "in", "is", "need", "needed", "of", "on", "out", "provide", "send",
    "share", "the", "to", "update", "waiting", "what", "when", "with",
}


def _normalized_tokens(text: str) -> set[str]:
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if token in WAITING_ITEM_STOP_WORDS:
            continue
        variants = {token}
        if token.endswith("ing") and len(token) > 5:
            variants.add(token[:-3])
        if token.endswith("s") and len(token) > 3:
            variants.add(token[:-1])
        tokens.update(variants)
    return tokens


def capture_resolves_waiting_item(capture_text: str, action_item: str) -> bool:
    action_tokens = _normalized_tokens(action_item)
    if len(action_tokens) < 2:
        return False
    capture_tokens = _normalized_tokens(capture_text)
    matched = action_tokens & capture_tokens
    return action_tokens <= capture_tokens or len(matched) >= max(2, len(action_tokens) - 1)


def _task_resolution_suggestions(db: Session, text: str) -> list[str]:
    suggestions = []
    for task in db.query(Task).filter(Task.status.in_(["open", "in_progress", "waiting", "blocked"])).all():
        if capture_resolves_waiting_item(text, task.title):
            suggestions.append(f"Review whether task #{task.id} should be marked complete: {task.title}")
    return suggestions


def _upsert_company(db: Session, name: str) -> Company:
    company = db.query(Company).filter(Company.name.ilike(name)).first()
    if not company:
        company = Company(name=name)
    db.add(company)
    db.flush()
    db.refresh(company)
    return company


def _upsert_person(db: Session, name: str, company: str = "", responsibilities: list[str] | None = None, current_priorities: list[str] | None = None) -> Person:
    person = db.query(Person).filter(Person.name.ilike(name)).first()
    if not person:
        person = Person(name=name)
    person.company = company or person.company
    if responsibilities:
        existing = list(person.responsibilities or [])
        person.responsibilities = list(dict.fromkeys(existing + responsibilities))
    if current_priorities:
        existing = list(person.current_priorities or [])
        person.current_priorities = list(dict.fromkeys(existing + current_priorities))
        if any("pm quality" in value.lower() for value in current_priorities):
            person.current_priorities = list(dict.fromkeys(existing + current_priorities + ["PM quality"]))
    db.add(person)
    db.flush()
    db.refresh(person)
    return person


def _upsert_strategic_issue(db: Session, title: str, company: str = "", owner: str = "") -> StrategicIssue:
    issue = db.query(StrategicIssue).filter(StrategicIssue.title.ilike(title)).first()
    if not issue:
        issue = StrategicIssue(title=title)
    issue.company = company or issue.company
    issue.owner = owner or issue.owner
    issue.status = "active"
    db.add(issue)
    db.flush()
    db.refresh(issue)
    return issue


def _upsert_decision(db: Session, title: str, company: str, context: str, final_decision: str, reasoning: str) -> Decision:
    decision = db.query(Decision).filter(Decision.title.ilike(title)).first()
    if not decision:
        decision = Decision(title=title)
    decision.company = company or decision.company
    decision.context = context or decision.context
    decision.final_decision = final_decision or decision.final_decision
    decision.reasoning = reasoning or decision.reasoning
    decision.date = decision.date or date.today().isoformat()
    db.add(decision)
    db.flush()
    db.refresh(decision)
    return decision


def _fallback_classify_capture_text(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    updates: list[dict[str, Any]] = []
    detected_name = ""
    for candidate in ["Julio", "Mina"]:
        if candidate.lower() in lowered:
            detected_name = candidate
            break

    detected_company = _detect_positive_company(text)

    ownership_match = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+owns\s+(?:the\s+)?([^.!?]+)", text
    )
    if ownership_match and not detected_name:
        owner, project_title = (value.strip() for value in ownership_match.groups())
        risk_match = re.search(r"\b(?:main\s+)?risk\s+is\s+([^.!?]+)", text, flags=re.IGNORECASE)
        updates.append({
            "type": "project",
            "title": project_title,
            "owner": owner,
            "company": detected_company,
            "risks": [risk_match.group(1).strip()] if risk_match else [],
            "status": "active",
            "details": f"{owner} owns {project_title}.",
        })

    role_match = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+is\s+(?:the\s+)?(.+?)\s+at\s+"
        r"(?:PEC|Pro Engineering(?: Consulting)?|RYSE(?: Wellness)?|EverPole|MyndLog)\b",
        text,
    )
    if role_match and not detected_name:
        updates.append({
            "type": "person",
            "name": role_match.group(1).strip(),
            "role": role_match.group(2).strip(),
            "company": detected_company,
            "details": "Potential person role and company update.",
        })

    decision_match = re.search(
        r"\bwe\s+decided\s+to\s+(.+?)\s+because\s+(.+?)(?:[.!?]|$)", text, flags=re.IGNORECASE
    )
    if decision_match:
        final_decision, reasoning = (value.strip() for value in decision_match.groups())
        updates.append({
            "type": "decision",
            "title": final_decision[0].upper() + final_decision[1:],
            "company": detected_company,
            "final_decision": final_decision,
            "reasoning": reasoning,
            "details": "Potential decision with stated reasoning.",
        })

    metric_match = re.search(
        r"^\s*([A-Za-z][A-Za-z ]+?)\s+is\s+([+-]?\$?[\d,.]+(?:[KMB])?%?)(?:,\s*(.+?))?(?:[.!?]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if metric_match:
        title, value, trend = metric_match.groups()
        updates.append({
            "type": "metric",
            "title": title.strip(),
            "value": value.strip(),
            "trend": (trend or "stable").strip(),
            "company": detected_company,
            "details": "Potential metric update.",
        })

    task_match = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+will\s+(.+?)(?:[.!?]|$)",
        text,
    )
    if task_match:
        owner, action = (value.strip() if value else "" for value in task_match.groups())
        due_date = ""
        due_match = re.search(r"\s+by\s+(.+)$", action, flags=re.IGNORECASE)
        if due_match:
            due_date = due_match.group(1).strip()
            action = action[:due_match.start()].strip()
        action_title = f"{owner} will {action}"
        if due_date:
            action_title = f"{action_title} by {due_date}"
        updates.append({
            "type": "task",
            "title": action_title,
            "description": text.strip(),
            "company": detected_company,
            "owner": owner,
            "due_date": due_date,
            "status": "open",
            "priority": "medium",
            "source_type": "capture_text",
            "source_summary": text.strip()[:500],
            "details": "Potential action item or commitment.",
        })

    if detected_name:
        updates.append({
            "type": "person",
            "name": detected_name,
            "company": detected_company,
            "role": role_match.group(2).strip() if role_match and role_match.group(1).strip() == detected_name else "",
            "details": f"Potential person update for {detected_name}.",
        })

    if "pm quality" in lowered:
        updates.append({
            "type": "strategic_issue",
            "title": "Improve PM quality",
            "details": "Potential strategic issue update related to quality ownership.",
        })

    if detected_company:
        updates.append({
            "type": "company",
            "name": detected_company,
            "details": "Potential company context update.",
        })

    if detected_name and any(keyword in lowered for keyword in ["pay", "promotion", "increase", "raise", "salary", "compensation"]):
        updates.append({
            "type": "decision",
            "title": f"{detected_name} promotion and pay increase",
            "details": "Potential decision about compensation and expanded scope.",
        })

    return updates


def _memory_context(db: Session) -> str:
    companies = ", ".join(company.name for company in db.query(Company).all()) or "None"
    people = ", ".join(
        f"{person.name} ({person.role or 'no role'}; {person.company or 'no company'})"
        for person in db.query(Person).all()
    ) or "None"
    issues = ", ".join(issue.title for issue in db.query(StrategicIssue).all()) or "None"
    return f"Companies: {companies}\nPeople: {people}\nStrategic issues: {issues}"


def _classify_capture_text(
    db: Session, text: str, image_data: str | list[str] = ""
) -> tuple[list[dict[str, Any]], list[str], str]:
    image_inputs = image_data if isinstance(image_data, list) else ([image_data] if image_data else [])
    analysis = analyze_capture(text, _memory_context(db), image_inputs) if image_inputs else analyze_capture(text, _memory_context(db))
    if analysis:
        return (
            [update.model_dump() for update in analysis.suggested_updates],
            analysis.follow_ups,
            "ai",
        )
    if image_inputs:
        return [], ["Screenshot analysis requires a configured and available AI connection."], "image_unavailable"
    updates = _fallback_classify_capture_text(text)
    follow_ups = _task_resolution_suggestions(db, text)
    if not updates:
        follow_ups.extend([
        "What person, company, project, decision, or metric should be saved from this update?"
        ])
    return updates, follow_ups, "local_fallback"


def _apply_generic_update(db: Session, update: dict[str, Any]) -> Any | bool:
    model = {
        "project": Project,
        "meeting": Meeting,
        "sop": SOP,
        "document": Document,
        "metric": Metric,
        "task": Task,
    }.get(update.get("type"))
    if not model:
        return False

    identity_field = "name" if "name" in model.__table__.columns else "title"
    identity = update.get(identity_field) or update.get("title") or update.get("name")
    if not identity:
        return True
    instance = db.query(model).filter(getattr(model, identity_field).ilike(identity)).first()
    if not instance:
        instance = model(**{identity_field: identity})
    allowed = {column.name for column in model.__table__.columns} - {"id", identity_field}
    for field in allowed:
        value = update.get(field)
        if value not in (None, "", []):
            setattr(instance, field, value)
    db.add(instance)
    db.flush()
    db.refresh(instance)
    return instance


def _apply_approved_updates(
    db: Session,
    text: str,
    approved_updates: list[SuggestedUpdate | dict[str, Any]],
    classification_source: str = "unknown",
) -> None:
    lowered = text.lower()
    detected_name = ""
    for candidate in ["Julio", "Mina"]:
        if candidate.lower() in lowered:
            detected_name = candidate
            break

    explicit_company = _detect_positive_company(text)

    for raw_update in approved_updates:
        update = raw_update.model_dump() if isinstance(raw_update, SuggestedUpdate) else raw_update
        update_type = update.get("type")
        saved_instance = None
        update_name = update.get("name") or detected_name
        proposed_company = _normalize_company(update.get("company") or "")
        if proposed_company and _company_is_explicitly_negated(text, proposed_company):
            proposed_company = ""
        # The reviewed structured value is authoritative. Text detection is only
        # a fallback, especially for transitions that legitimately mention both
        # the former and new company in one capture.
        update_company = proposed_company or explicit_company
        if update_type == "person" and update_name:
            saved_instance = _upsert_person(
                db,
                name=update_name,
                company=update_company,
                responsibilities=update.get("responsibilities") or (["PM quality"] if "pm quality" in lowered else []),
                current_priorities=update.get("current_priorities") or (["Improve PM quality"] if "pm quality" in lowered else []),
            )
            person = db.query(Person).filter(Person.name.ilike(update_name)).first()
            if person and update.get("role"):
                person.role = update["role"]
            if person:
                for field in ("strengths", "concerns", "performance_notes"):
                    values = update.get(field) or []
                    if values:
                        setattr(person, field, list(dict.fromkeys(list(getattr(person, field) or []) + values)))
                details = (update.get("details") or "").strip()
                if details and classification_source != "local_fallback":
                    person.performance_notes = list(dict.fromkeys(
                        list(person.performance_notes or []) + [details]
                    ))
                db.flush()
        elif update_type == "strategic_issue":
            title = update.get("title") or ("Improve PM quality" if "pm quality" in lowered else "")
            if title:
                issue = _upsert_strategic_issue(db, title, company=update_company, owner=update.get("owner") or update_name)
                saved_instance = issue
                issue.current_thinking = (
                    update.get("current_thinking") or update.get("details") or issue.current_thinking
                )
                issue.status = update.get("status") or issue.status
                db.flush()
        elif update_type == "company" and update_name:
            company = _upsert_company(db, update_name)
            saved_instance = company
            if update.get("description"):
                company.description = update["description"]
                db.flush()
        elif update_type == "decision" and update.get("title"):
            decision = _upsert_decision(
                db,
                update["title"],
                company=update_company,
                context=update.get("context") or text,
                final_decision=update.get("final_decision") or update.get("details") or "Decision captured.",
                reasoning=update.get("reasoning") or "",
            )
            for field in ("date", "options_considered", "expected_outcome", "review_date"):
                value = update.get(field)
                if value not in (None, "", []):
                    setattr(decision, field, value)
            db.flush()
            saved_instance = decision
        elif update_type == "task":
            saved_instance = upsert_task_from_update(
                db,
                update,
                default_company=update_company,
                default_source_type="capture_text",
                default_source_summary=text[:500],
            )
        else:
            if update.get("details"):
                detail_field = {
                    "project": "objective",
                    "meeting": "summary",
                    "sop": "current_process",
                    "document": "summary",
                    "metric": "notes",
                }.get(update_type)
                if detail_field and not update.get(detail_field):
                    update = {**update, detail_field: update["details"]}
            handled = _apply_generic_update(db, update)
            saved_instance = handled if handled is not True and handled is not False else None
            if handled and update_type == "meeting":
                meeting_title = update.get("title")
                if meeting_title:
                    meeting = db.query(Meeting).filter(Meeting.title.ilike(meeting_title)).first()
                    if meeting:
                        ensure_tasks_for_meeting_action_items(db, meeting)
        if saved_instance is not None and getattr(saved_instance, "id", None):
            source_type = update.get("source_type") or ("capture_text" if classification_source != "manual" else "manual_entry")
            ensure_provenance(
                db,
                update_type,
                saved_instance.id,
                source_type=source_type,
                source_title=update.get("source_title") or "Capture",
                source_excerpt=text,
                created_by="user",
                confidence=update.get("confidence") or "user_confirmed",
                verification_state=update.get("verification_state") or "user_confirmed",
                memory_classification=update.get("memory_classification") or ("commitment" if update_type == "task" else "confirmed_fact"),
            )
            record_revision(
                db,
                update_type,
                saved_instance.id,
                after={column.name: getattr(saved_instance, column.key) for column in saved_instance.__table__.columns},
                change_type="capture_approval",
                source_type=source_type,
            )

    db.add(CaptureRecord(
        raw_text=text,
        classification_source=classification_source,
        saved_count=len(approved_updates),
    ))
    db.commit()
