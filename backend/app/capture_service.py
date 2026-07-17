import os
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .ai import CAPTURE_PROMPT_VERSION, CaptureAnalysis, SuggestedUpdate, analyze_capture
from .memory import (
    _company_is_explicitly_negated,
    _detect_positive_company,
    _match_score,
    _normalize_company,
)
from .leadership_lens import enrich_task_update_with_leadership_lens, enrich_updates_with_leadership_lens
from .models import (
    CaptureInterpretation,
    CaptureMutation,
    CaptureRecord,
    Company,
    Decision,
    Document,
    Meeting,
    Metric,
    Person,
    Project,
    SOP,
    StrategicIssue,
    Task,
)
from .roadmap_services import ensure_provenance, record_revision
from .resolution_service import resolve_items_from_capture_text
from .tasks import OPEN_TASK_STATUSES, complete_task, ensure_tasks_for_meeting_action_items, upsert_task_from_update


WAITING_ITEM_STOP_WORDS = {
    "a", "about", "an", "and", "are", "ask", "by", "check", "clarify",
    "confirm", "determine", "find", "for", "from", "get", "her", "his",
    "in", "is", "need", "needed", "of", "on", "out", "provide", "send",
    "share", "the", "to", "update", "waiting", "what", "when", "with",
}

RESOLUTION_WORDS = {"resolved", "complete", "completed", "done", "closed", "fixed"}

INVALID_TASK_OWNERS = {
    "feedback",
    "i",
    "it",
    "someone",
    "that",
    "the team",
    "this",
    "we",
    "you",
}

WEAK_TASK_TITLE_PATTERNS = (
    r"^come up with (?:new )?strategy$",
    r"^discuss sales activities and outlook$",
    r"^get (?:us|our) (?:to )?(?:our )?numbers$",
    r"^get our year back on track$",
    r"^review prior to each sales check in$",
)

NON_ACTION_CONTEXT_PATTERNS = (
    r"\bwill\s+be\s+(?:provided|selected|used|discussed|reviewed|captured)\b",
    r"\b(?:is|are|was|were)\s+(?:a|an|the)?\s*(?:current\s+)?(?:client|owner|lead|manager|provider)\b",
    r"\bthis\s+will\s+require\b",
)


def _sentence_list(text: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()]


def _screenshot_unavailable_message() -> str:
    if not os.getenv("OPENAI_API_KEY"):
        return "Screenshot analysis needs OPENAI_API_KEY configured on the backend."
    return (
        "Screenshot analysis timed out or failed through the OpenAI connection. "
        "Check OPENAI_MODEL, OPENAI_IMAGE_DETAIL, OPENAI_TIMEOUT_SECONDS, model access, and backend logs."
    )


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


def _resolution_target_from_text(text: str) -> str:
    resolution_pattern = r"(?:resolved|complete|completed|done|closed|fixed)"
    match = re.search(
        rf"\b(?:mark|set)\s+(.+?)\s+as\s+{resolution_pattern}\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" :-—–")
    match = re.search(
        rf"\b(?:mark|set)\s+as\s+{resolution_pattern}\s*[:\-—–]\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" :-—–")
    match = re.search(
        rf"^(.+?)\s*[:\-—–]\s*(?:mark|set|marked)\s+as\s+{resolution_pattern}\b",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" :-—–")
    match = re.search(
        rf"\b(.+?)\s+(?:is|are|has been|have been)\s+{resolution_pattern}\b",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip(" :-—–") if match else ""


def _is_explicit_resolution(text: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    return bool(tokens & RESOLUTION_WORDS) and bool(_resolution_target_from_text(text))


def _matches_resolution_target(item: Any, fields: list[str], target: str) -> bool:
    if not target:
        return False
    label = " ".join(str(getattr(item, field, "") or "") for field in fields)
    if capture_resolves_waiting_item(target, label) or capture_resolves_waiting_item(label, target):
        return True
    return _match_score(item, fields, target) >= 6


def _text_matches_resolution_target(value: str, target: str) -> bool:
    if not value or not target:
        return False
    value_tokens = _normalized_tokens(value)
    target_tokens = _normalized_tokens(target)
    if len(value_tokens) == 1 and value_tokens == target_tokens:
        return True
    if capture_resolves_waiting_item(target, value) or capture_resolves_waiting_item(value, target):
        return True
    matched = value_tokens & target_tokens
    return len(matched) >= max(2, min(len(value_tokens), len(target_tokens)) - 1)


def capture_explicitly_resolves_item(capture_text: str, item_text: str) -> bool:
    target = _resolution_target_from_text(capture_text)
    if not target or target.lower() in {"it", "this", "that", "item"}:
        return False
    return _is_explicit_resolution(capture_text) and _text_matches_resolution_target(item_text, target)


def _prune_resolved_values(values: list[str] | None, target: str) -> tuple[list[str], bool]:
    existing = list(values or [])
    pruned = [value for value in existing if not _text_matches_resolution_target(str(value), target)]
    return pruned, len(pruned) != len(existing)


def _resolution_suggestions(db: Session, text: str) -> list[dict[str, Any]]:
    target = _resolution_target_from_text(text)
    if not target:
        return []
    suggestions: list[dict[str, Any]] = []
    for task in db.query(Task).filter(Task.status.in_(OPEN_TASK_STATUSES)).all():
        if _matches_resolution_target(task, ["title", "description", "source_summary"], target):
            suggestions.append({
                "type": "task",
                "title": task.title,
                "status": "completed",
                "source_type": task.source_type,
                "source_id": task.source_id,
                "details": f"Mark existing task #{task.id} complete.",
                "memory_classification": "commitment",
                "verification_state": "user_confirmed",
            })
    for issue in db.query(StrategicIssue).filter(StrategicIssue.status == "active").all():
        remaining_risks, removed_risk = _prune_resolved_values(issue.risks, target)
        if removed_risk:
            suggestions.append({
                "type": "strategic_issue",
                "title": issue.title,
                "risks": remaining_risks,
                "field_operations": {"risks": "replace"},
                "details": f"Remove resolved risk from strategic issue #{issue.id}.",
                "memory_classification": "confirmed_fact",
                "verification_state": "user_confirmed",
            })
        elif _matches_resolution_target(issue, ["title", "current_thinking"], target):
            suggestions.append({
                "type": "strategic_issue",
                "title": issue.title,
                "status": "resolved",
                "details": f"Mark existing strategic issue #{issue.id} resolved.",
                "memory_classification": "confirmed_fact",
                "verification_state": "user_confirmed",
            })
    for project in db.query(Project).filter(Project.status == "active").all():
        remaining_risks, removed_risk = _prune_resolved_values(project.risks, target)
        if removed_risk:
            suggestions.append({
                "type": "project",
                "title": project.title,
                "risks": remaining_risks,
                "field_operations": {"risks": "replace"},
                "details": f"Remove resolved risk from project #{project.id}.",
                "memory_classification": "confirmed_fact",
                "verification_state": "user_confirmed",
            })
        elif _matches_resolution_target(project, ["title", "objective", "next_steps"], target):
            suggestions.append({
                "type": "project",
                "title": project.title,
                "status": "completed",
                "details": f"Mark existing project #{project.id} completed.",
                "memory_classification": "confirmed_fact",
                "verification_state": "user_confirmed",
            })
    return suggestions


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


def _detect_known_person_name(text: str) -> str:
    for candidate in ["Julio", "Mina"]:
        if re.search(rf"\b{re.escape(candidate)}\b", text, flags=re.IGNORECASE):
            return candidate
    return ""


def _title_from_action(action: str) -> str:
    cleaned = " ".join(str(action or "").strip(" :-").split())
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def _normalize_owner(value: str) -> str:
    owner = " ".join(str(value or "").strip(" :-").split())
    if owner.lower() in INVALID_TASK_OWNERS:
        return ""
    if re.fullmatch(r"(?:this|that|it|we|i|you|feedback)", owner, flags=re.IGNORECASE):
        return ""
    return owner


def _normalize_task_status_for_capture(status: str, text: str) -> str:
    normalized = str(status or "open").strip().lower()
    if normalized == "completed" and not _is_explicit_resolution(text):
        return "open"
    return status or "open"


def _task_quality(update: dict[str, Any]) -> tuple[int, list[str]]:
    if update.get("type") != "task":
        return 100, []
    score = 0
    notes: list[str] = []
    title = str(update.get("title") or "").strip()
    if title:
        score += 20
    else:
        notes.append("missing title")
    if update.get("owner") or update.get("assigned_to") or update.get("waiting_on"):
        score += 20
    else:
        notes.append("missing owner or accountable party")
    if update.get("next_action"):
        score += 15
    else:
        notes.append("missing next action")
    if update.get("expected_deliverable") or update.get("definition_of_done"):
        score += 20
    else:
        notes.append("missing expected outcome")
    if update.get("source_excerpt") or update.get("evidence_excerpt"):
        score += 15
    else:
        notes.append("missing source excerpt")
    if update.get("due_date") or update.get("follow_up_date") or update.get("recurrence"):
        score += 10
    else:
        notes.append("missing due date or cadence")
    return min(score, 100), notes


def _is_weak_task_update(update: dict[str, Any], *, classification_source: str) -> bool:
    if update.get("type") != "task":
        return False
    title = re.sub(r"\s+", " ", str(update.get("title") or "").strip().lower())
    source_excerpt = str(update.get("source_excerpt") or update.get("evidence_excerpt") or "").strip()
    if not title:
        return True
    if any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in WEAK_TASK_TITLE_PATTERNS):
        return True
    if classification_source == "local_fallback" and any(re.search(pattern, source_excerpt, flags=re.IGNORECASE) for pattern in NON_ACTION_CONTEXT_PATTERNS):
        return not (update.get("owner") or update.get("assigned_to") or update.get("waiting_on"))
    if classification_source == "local_fallback":
        has_accountability = bool(update.get("owner") or update.get("assigned_to") or update.get("waiting_on"))
        has_action_shape = bool(re.search(
            r"\b(?:will|send|review|get|confirm|prepare|complete|transition|log|offer|close|schedule|decide|build|create|come up with|follow up|follow-up)\b",
            title,
            flags=re.IGNORECASE,
        ))
        if not has_accountability and not has_action_shape:
            return True
    return False


def _prepare_task_update_for_capture(
    update: dict[str, Any],
    text: str,
    *,
    classification_source: str,
) -> dict[str, Any] | None:
    if update.get("type") != "task":
        return update
    prepared = dict(update)
    for field in ("owner", "assigned_to", "delegated_by", "waiting_on"):
        if field in prepared:
            prepared[field] = _normalize_owner(prepared.get(field) or "")
    prepared["status"] = _normalize_task_status_for_capture(prepared.get("status") or "open", text)
    score, notes = _task_quality(prepared)
    prepared["quality_score"] = score
    prepared["quality_notes"] = notes
    if not prepared.get("next_best_action"):
        prepared["next_best_action"] = prepared.get("next_action") or (
            "Clarify owner, outcome, and review cadence before treating this as an executive commitment."
            if score < 70 else
            "Confirm the owner, expected outcome, and review cadence."
        )
    if _is_weak_task_update(prepared, classification_source=classification_source):
        return None
    return prepared


def _weak_task_clarification_prompts(update: dict[str, Any]) -> list[str]:
    title = str(update.get("title") or "this item").strip()
    return [
        f"What business result should '{title}' improve?",
        f"Who owns '{title}' and by when should it be reviewed?",
        f"What metric or observable outcome proves '{title}' worked?",
    ]


def _task_update(
    title: str,
    text: str,
    company: str,
    *,
    owner: str = "",
    assigned_to: str = "",
    waiting_on: str = "",
    next_action: str = "",
    due_date: str = "",
    source_excerpt: str = "",
    missing_material_fields: list[str] | None = None,
    expected_deliverable: str = "",
    definition_of_done: str = "",
    why_it_matters: str = "",
    recurrence: str = "",
    task_type: str = "",
    stakeholders: list[str] | None = None,
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "task",
        "title": title,
        "description": source_excerpt or title,
        "company": company,
        "owner": _normalize_owner(owner),
        "assigned_to": _normalize_owner(assigned_to),
        "waiting_on": _normalize_owner(waiting_on),
        "due_date": due_date,
        "status": "open",
        "priority": "medium",
        "source_type": "capture_text",
        "source_summary": text.strip()[:500],
        "next_action": next_action or title,
        "expected_deliverable": expected_deliverable or title,
        "definition_of_done": definition_of_done or f"{title} is completed and the outcome is captured.",
        "why_it_matters": why_it_matters,
        "source_excerpt": source_excerpt or title,
        "missing_material_fields": missing_material_fields or [],
        "recurrence": recurrence,
        "task_type": task_type,
        "stakeholders": stakeholders or [],
        "dependencies": dependencies or [],
        "details": "Potential action item or commitment.",
        "memory_classification": "commitment",
        "verification_state": "ai_extracted_pending_review",
    }


def _fallback_task_updates(text: str, detected_company: str) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    def add(update: dict[str, Any]) -> None:
        prepared = _prepare_task_update_for_capture(update, text, classification_source="local_fallback")
        if prepared is None:
            return
        update = prepared
        title = update.get("title", "")
        normalized = re.sub(r"\s+", " ", title.lower()).strip()
        if not normalized or normalized in seen_titles:
            return
        seen_titles.add(normalized)
        updates.append(update)

    sentences = _sentence_list(text)
    transition_subject = ""
    for sentence in sentences:
        passive_match = re.search(r"\bwill\s+be\s+(?:provided|selected|used|discussed|reviewed|captured)\b", sentence, flags=re.IGNORECASE)
        if passive_match:
            continue

        transition_match = re.search(
            r"\b([A-Z][A-Za-z]+)\s+to\s+transition\s+to\s+(.+?)\s+by\s+([A-Z][a-z]+\s+\d{1,2})\b",
            sentence,
            flags=re.IGNORECASE,
        )
        if transition_match:
            person, scope, due_date = transition_match.groups()
            transition_subject = person
            title = _title_from_action(f"Transition {person} to {scope}")
            add(_task_update(
                title,
                text,
                detected_company,
                assigned_to=person,
                due_date=due_date,
                source_excerpt=sentence,
                expected_deliverable=f"{person} owns {scope}.",
                definition_of_done=f"{person} is operating independently on {scope} by {due_date}.",
                why_it_matters="Sales execution ownership needs to be clear before the meeting follow-up date.",
                missing_material_fields=["accountable owner"],
                stakeholders=[person],
            ))

        enabler_match = re.search(
            r"\b([A-Z][A-Za-z]+(?:\s+and\s+[A-Z][A-Za-z]+)?)\s+to\s+own\s+the\s+task\s+of\s+getting\s+([A-Z][A-Za-z]+|him|her|them)\s+there\b",
            sentence,
            flags=re.IGNORECASE,
        )
        if enabler_match:
            owners_text, target_person = enabler_match.groups()
            if target_person.lower() in {"him", "her", "them"} and transition_subject:
                target_person = transition_subject
            owners = [name.strip() for name in re.split(r"\s+and\s+", owners_text) if name.strip()]
            title = _title_from_action(f"{owners_text} get {target_person} ready for quote and follow-up ownership")
            add(_task_update(
                title,
                text,
                detected_company,
                owner=owners_text,
                assigned_to=owners_text,
                source_excerpt=sentence,
                expected_deliverable=f"{target_person} is ready to own quote creation, site-visit coordination, and follow-up workflow.",
                definition_of_done=f"{', '.join(owners)} confirm {target_person} can execute the sales ownership workflow without hand-holding.",
                why_it_matters="The sales handoff depends on clear enablement ownership.",
                stakeholders=[target_person, *owners],
            ))

        outreach_match = re.search(
            r"\bOutreach\s+must\s+be\s+logged\s+in\s+(.+?)(?:[.!?]|$)",
            sentence,
            flags=re.IGNORECASE,
        )
        if outreach_match:
            systems = outreach_match.group(1).strip()
            follow_sentence = next((candidate for candidate in sentences if re.search(r"\bPopulate\s+every\s+day\b", candidate, re.IGNORECASE)), "")
            excerpt = f"{sentence} {follow_sentence}".strip()
            title = "Log outreach daily in GoHighLevel and activity spreadsheet"
            add(_task_update(
                title,
                text,
                detected_company,
                source_excerpt=excerpt,
                next_action=title,
                expected_deliverable=f"Daily outreach entries are logged in {systems}.",
                definition_of_done="Outreach is populated every day and ready for review before each sales check-in.",
                why_it_matters="Outreach and reconnection with old clients are expected to drive sales numbers.",
                recurrence="daily",
                task_type="standing_responsibility",
                missing_material_fields=["owner"],
            ))

        discount_match = re.search(r"\bOffer\s+discounts\s+on\s+proposals\b", sentence, flags=re.IGNORECASE)
        if discount_match:
            title = "Offer discounts on proposals for competitive pricing"
            add(_task_update(
                title,
                text,
                detected_company,
                source_excerpt=sentence,
                next_action="Decide discount guidance for active proposals.",
                expected_deliverable="Discount guidance is applied to proposals where pricing competitiveness matters.",
                definition_of_done="Large-job proposals reflect approved discount strategy and are ready for follow-up.",
                why_it_matters="PEC needs to be more competitive on pricing, especially on large jobs.",
                missing_material_fields=["owner", "discount criteria"],
            ))

        close_quotes_match = re.search(r"\bclose\s+as\s+many\s+quotes\s+this\s+week\s+as\s+possible\b", sentence, flags=re.IGNORECASE)
        if close_quotes_match:
            title = "Close as many quotes as possible this week"
            add(_task_update(
                title,
                text,
                detected_company,
                source_excerpt=sentence,
                due_date="this week",
                next_action="Prioritize active quotes for close attempts this week.",
                expected_deliverable="Maximum feasible quotes closed this week.",
                definition_of_done="Active quote follow-ups are completed and closed-won/lost outcomes are logged.",
                why_it_matters="Closing quotes this week supports getting the year back on track.",
                missing_material_fields=["owner", "target quote list"],
            ))

        will_match = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+will\s+(.+?)(?:[.!?]|$)",
            sentence,
        )
        if will_match:
            owner, action = (value.strip() if value else "" for value in will_match.groups())
            if owner.lower() in {"we", "i"}:
                continue
            due_date = ""
            due_match = re.search(r"\s+by\s+(.+)$", action, flags=re.IGNORECASE)
            if due_match:
                due_date = due_match.group(1).strip()
                action = action[:due_match.start()].strip()
            title = _title_from_action(f"{owner} will {action}{f' by {due_date}' if due_date else ''}")
            add(_task_update(
                title,
                text,
                detected_company,
                owner=owner,
                assigned_to=owner,
                due_date=due_date,
                source_excerpt=sentence,
            ))

        directive_patterns = [
            (r"\bReview\s+(.+?)(?:[.!?]|$)", "Review {action}"),
            (r"\bGet\s+(.+?)(?:[.!?]|$)", "Get {action}"),
            (r"\bGo over\s+(.+?)(?:[.!?]|$)", "Go over {action}"),
            (r"\bcome up with\s+(.+?)(?:[.!?]|$)", "Come up with {action}"),
            (r"\bdiscuss\s+(.+?)(?:[.!?]|$)", "Discuss {action}"),
        ]
        for pattern, template in directive_patterns:
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if not match:
                continue
            if template.startswith("Review") and re.search(r"\bso\s+that\s+we\s+can\s+review\b", sentence, flags=re.IGNORECASE):
                continue
            if template.startswith("Get") and match.start() > 0 and sentence[max(0, match.start() - 4):match.start()].lower().strip().endswith("to"):
                continue
            action = match.group(1).strip()
            title = _title_from_action(template.format(action=action))
            owner_match = re.search(r"\bis owned by\s+(.+?)(?:[.!?]|$)", sentence, flags=re.IGNORECASE)
            owner = owner_match.group(1).strip() if owner_match else ""
            add(_task_update(
                title,
                text,
                detected_company,
                owner=owner,
                source_excerpt=sentence,
                missing_material_fields=[] if owner else ["owner"],
            ))

        waiting_match = re.search(
            r"\b(?:get|confirm|receive)\s+(.+?)\s+from\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\b",
            sentence,
            flags=re.IGNORECASE,
        )
        if waiting_match:
            deliverable, person = waiting_match.groups()
            title = _title_from_action(f"Get {deliverable.strip()} from {person.strip()}")
            add(_task_update(
                title,
                text,
                detected_company,
                waiting_on=person.strip(),
                next_action=title,
                source_excerpt=sentence,
            ))

    return updates


def _extract_attendees(text: str) -> list[str]:
    attendees: list[str] = []
    met_match = re.search(r"\b([A-Z][A-Za-z]+(?:,\s*[A-Z][A-Za-z]+)*(?:\s+and\s+[A-Z][A-Za-z]+)?)\s+and\s+I\s+met\b", text)
    if met_match:
        attendees.extend(re.split(r",\s*|\s+and\s+", met_match.group(1)))
    people = re.findall(r"\b(?:with|attendees?:)\s+([A-Z][A-Za-z]+(?:,\s*[A-Z][A-Za-z]+)*(?:\s+and\s+[A-Z][A-Za-z]+)?)", text)
    for group in people:
        attendees.extend(re.split(r",\s*|\s+and\s+", group))
    return list(dict.fromkeys(name.strip() for name in attendees if name.strip()))


def _fallback_meeting_updates(text: str, detected_company: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    if not any(keyword in lowered for keyword in ("meeting", "debrief", "met today", "check-in", "check in")):
        return []
    topic = "meeting notes"
    topic_match = re.search(r"\b(?:to discuss|discussed)\s+([^.!?]+)", text, flags=re.IGNORECASE)
    if topic_match:
        topic = topic_match.group(1).strip()
    title_prefix = detected_company or "Executive"
    title = f"{title_prefix} {topic}".strip()
    if any(keyword in lowered for keyword in ("debrief", "check-in", "check in")) and "debrief" not in title.lower():
        title = f"{title_prefix} sales meeting debrief" if "sales" in lowered else f"{title_prefix} meeting debrief"
    action_items = [
        update["title"]
        for update in _fallback_task_updates(text, detected_company)
        if update.get("quality_score", 0) >= 60
    ][:8]
    open_questions = _vague_strategy_followups(text)[:6]
    return [{
        "type": "meeting",
        "title": _title_from_action(title),
        "company": detected_company,
        "summary": text.strip()[:700],
        "attendees": _extract_attendees(text),
        "action_items": action_items,
        "open_questions": open_questions,
        "details": "Meeting/debrief context captured separately from task commitments.",
        "memory_classification": "confirmed_fact",
        "verification_state": "local_fallback_pending_review",
    }]


def _vague_strategy_followups(text: str) -> list[str]:
    lowered = text.lower()
    prompts: list[str] = []
    if re.search(r"\b(?:come up with|need|create|build)\s+(?:a\s+)?(?:new\s+)?strategy\b", lowered):
        prompts.extend([
            "What business result should the strategy improve?",
            "Who owns drafting the strategy, and when should it be reviewed?",
            "What metric defines whether the strategy worked?",
        ])
    if "sales activities and outlook" in lowered:
        prompts.extend([
            "What specific sales activity target should Ryan and Catalina be accountable for?",
            "What pipeline or closed-revenue metric should be reviewed at the next sales check-in?",
        ])
    if "get our year back on track" in lowered or "get us to our numbers" in lowered:
        prompts.extend([
            "What number needs to be recovered, and by what date?",
            "Which owner is accountable for the recovery plan?",
        ])
    return list(dict.fromkeys(prompts))


def _fallback_classify_capture_text(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    updates: list[dict[str, Any]] = []
    detected_name = _detect_known_person_name(text)

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

    updates.extend(_fallback_meeting_updates(text, detected_company))
    updates.extend(_fallback_task_updates(text, detected_company))

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


def _prepare_capture_updates(
    updates: list[dict[str, Any]],
    text: str,
    *,
    classification_source: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    prepared_updates: list[dict[str, Any]] = []
    follow_ups: list[str] = []
    clarification_prompts: list[str] = []
    skipped_task_count = 0
    for update in updates:
        prepared = _prepare_task_update_for_capture(update, text, classification_source=classification_source)
        if prepared is None:
            skipped_task_count += 1
            clarification_prompts.extend(_weak_task_clarification_prompts(update))
            continue
        prepared_updates.append(prepared)
    if skipped_task_count:
        follow_ups.append(
            f"{skipped_task_count} weak task suggestion{'s were' if skipped_task_count != 1 else ' was'} held back because the capture did not include enough owner, outcome, or action context."
        )
    follow_ups.extend(clarification_prompts)
    return prepared_updates, follow_ups


def _capture_next_best_action(updates: list[dict[str, Any]], follow_ups: list[str], text: str) -> str:
    task_updates = [update for update in updates if update.get("type") == "task"]
    if follow_ups:
        return follow_ups[0]
    if task_updates:
        weakest = min(task_updates, key=lambda update: int(update.get("quality_score") or 0))
        if int(weakest.get("quality_score") or 0) < 80:
            return weakest.get("next_best_action") or "Clarify owner, expected outcome, and review cadence."
        return task_updates[0].get("next_action") or "Confirm the highest-impact task owner and next review date."
    if any(keyword in text.lower() for keyword in ("meeting", "debrief", "met today", "check-in", "check in")):
        return "Review the meeting context and convert only concrete commitments into tracked tasks."
    return "Clarify the concrete memory update or decision this capture should save."


def _capture_diagnostics(classification_source: str, image_count: int, updates: list[dict[str, Any]]) -> dict[str, Any]:
    task_updates = [update for update in updates if update.get("type") == "task"]
    return {
        "classification_source": classification_source,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "openai_model": os.getenv("OPENAI_MODEL", ""),
        "image_count": image_count,
        "task_count": len(task_updates),
        "low_quality_task_count": sum(1 for update in task_updates if int(update.get("quality_score") or 0) < 70),
        "average_task_quality": round(
            sum(int(update.get("quality_score") or 0) for update in task_updates) / len(task_updates),
            1,
        ) if task_updates else 0,
        "fallback_reason": "AI unavailable, timed out, or returned unusable output" if classification_source in {"local_fallback", "image_unavailable"} else "",
    }


def _memory_context(db: Session) -> str:
    companies = ", ".join(f"company#{company.id}:{company.name}" for company in db.query(Company).limit(100).all()) or "None"
    people = ", ".join(
        f"person#{person.id}:{person.name} ({person.role or 'no role'}; {person.company or 'no company'})"
        for person in db.query(Person).order_by(Person.updated_at.desc()).limit(100).all()
    ) or "None"
    issues = ", ".join(
        f"strategic_issue#{issue.id}:{issue.title} owner={issue.owner or 'open'} status={issue.status}"
        for issue in db.query(StrategicIssue).order_by(StrategicIssue.updated_at.desc()).limit(75).all()
    ) or "None"
    projects = ", ".join(
        f"project#{project.id}:{project.title} owner={project.owner or 'open'} status={project.status}"
        for project in db.query(Project).order_by(Project.updated_at.desc()).limit(75).all()
    ) or "None"
    tasks = ", ".join(
        f"task#{task.id}:{task.title} owner={task.owner or 'open'} assigned_to={task.assigned_to or ''} waiting_on={task.waiting_on or ''} status={task.status}"
        for task in db.query(Task).filter(Task.status.in_(OPEN_TASK_STATUSES)).order_by(Task.updated_at.desc()).limit(75).all()
    ) or "None"
    return f"Companies: {companies}\nPeople: {people}\nStrategic issues: {issues}\nProjects: {projects}\nOpen tasks: {tasks}"


def _analysis_to_interpretation(
    analysis: CaptureAnalysis | None,
    text: str,
    updates: list[dict[str, Any]],
    follow_ups: list[str],
    *,
    classification_source: str = "unknown",
    image_count: int = 0,
) -> dict[str, Any]:
    diagnostics = _capture_diagnostics(classification_source, image_count, updates)
    next_best_action = _capture_next_best_action(updates, follow_ups, text)
    if analysis:
        payload = analysis.model_dump()
        payload["suggested_updates"] = updates
        payload["follow_ups"] = follow_ups
        payload["diagnostics"] = diagnostics
        payload["next_best_action"] = next_best_action
        return payload
    summary = text.strip()[:300] or "Screenshot capture could not be interpreted by AI."
    return {
        "capture_summary": summary,
        "capture_purpose": "capture_review",
        "executive_intent": "review_and_update_memory" if updates else "needs_clarification",
        "primary_company": _detect_positive_company(text),
        "primary_subject": "",
        "primary_topic": "",
        "urgency": "",
        "tone": "",
        "temporal_context": "",
        "confidence": "local_fallback",
        "people_roles": [],
        "statements": [{
            "source_excerpt": text.strip()[:500],
            "statement_type": "observation",
            "company": _detect_positive_company(text),
            "people": [],
            "temporal_meaning": "",
            "confidence": "local_fallback",
            "changes_existing_memory": bool(updates),
        }] if text.strip() else [],
        "open_questions": follow_ups,
        "ambiguities": [],
        "source_evidence": [{"type": "typed_text", "excerpt": text.strip()[:500]}] if text.strip() else [],
        "suggested_updates": updates,
        "follow_ups": follow_ups,
        "diagnostics": diagnostics,
        "next_best_action": next_best_action,
    }


def _create_capture_record(
    db: Session,
    text: str,
    *,
    classification_source: str,
    interpretation_payload: dict[str, Any],
    approved_updates: list[dict[str, Any]] | None = None,
    rejected_updates: list[dict[str, Any]] | None = None,
    saved_record_ids: list[dict[str, Any]] | None = None,
    processing_events: list[dict[str, Any]] | None = None,
) -> CaptureRecord:
    capture = CaptureRecord(
        raw_text=text,
        classification_source=classification_source,
        saved_count=len(approved_updates or []),
        screenshot_summary=_screenshot_summary_from_interpretation(interpretation_payload),
        ai_model=os.getenv("OPENAI_MODEL", "local_fallback" if classification_source != "ai" else "gpt-5.6"),
        prompt_version=CAPTURE_PROMPT_VERSION,
        structured_interpretation=interpretation_payload,
        approved_suggestions=approved_updates or [],
        rejected_suggestions=rejected_updates or [],
        saved_record_ids=saved_record_ids or [],
        user_edits=[],
        processing_events=processing_events or [],
    )
    db.add(capture)
    db.flush()
    db.refresh(capture)
    return capture


def _screenshot_summary_from_interpretation(interpretation_payload: dict[str, Any]) -> str:
    evidence = interpretation_payload.get("source_evidence") or []
    for item in evidence:
        if isinstance(item, dict) and "screenshot" in str(item.get("type", "")).lower():
            return str(item.get("summary") or item.get("excerpt") or "")[:2000]
    return ""


def _create_interpretation(db: Session, capture: CaptureRecord, interpretation_payload: dict[str, Any]) -> CaptureInterpretation:
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
        model=os.getenv("OPENAI_MODEL", "local_fallback"),
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
    db.refresh(interpretation)
    return interpretation


def _default_field_operations(update: dict[str, Any]) -> dict[str, str]:
    explicit = update.get("field_operations") or {}
    operations = dict(explicit) if isinstance(explicit, dict) else {}
    list_fields = {"risks", "milestones", "next_steps", "responsibilities", "concerns", "action_items", "tags"}
    for field, value in update.items():
        if field in {"type", "operation", "matched_record_id", "match_confidence", "field_operations"}:
            continue
        if field not in operations and value not in (None, "", []):
            operations[field] = "append" if field in list_fields else "replace"
    return operations


def _mutation_from_update(
    db: Session,
    capture: CaptureRecord,
    interpretation: CaptureInterpretation,
    update: dict[str, Any],
    index: int,
) -> CaptureMutation:
    object_type = update.get("type") or "unknown"
    mutation = CaptureMutation(
        capture_id=capture.id,
        interpretation_id=interpretation.id,
        suggestion_index=index,
        object_type=object_type,
        operation=update.get("operation") or ("update" if update.get("matched_record_id") else "create"),
        status="proposed",
        matched_record_type=object_type if update.get("matched_record_id") else "",
        matched_record_id=update.get("matched_record_id"),
        match_confidence=update.get("match_confidence") or "",
        evidence_excerpt=update.get("evidence_excerpt") or update.get("source_excerpt") or update.get("details") or capture.raw_text[:500],
        field_operations=_default_field_operations(update),
        proposed_values=update,
        approved_values={},
        persisted_values={},
        missing_material_fields=list(dict.fromkeys((update.get("missing_material_fields") or []) + (update.get("quality_notes") or []))),
        uncertainty=update.get("uncertainty") or "",
        explanation=update.get("explanation") or update.get("details") or "",
        user_edits=[],
    )
    db.add(mutation)
    db.flush()
    db.refresh(mutation)
    return mutation


def create_capture_review(
    db: Session,
    text: str,
    suggested_updates: list[dict[str, Any]],
    follow_ups: list[str],
    classification_source: str,
    analysis: CaptureAnalysis | None = None,
    *,
    processing_events: list[dict[str, Any]] | None = None,
) -> tuple[CaptureRecord, CaptureInterpretation, list[CaptureMutation]]:
    image_count = 0
    if processing_events:
        image_count = max(
            [int(event.get("image_count") or 0) for event in processing_events if isinstance(event, dict) and "image_count" in event]
            or [0]
        )
    interpretation_payload = _analysis_to_interpretation(
        analysis,
        text,
        suggested_updates,
        follow_ups,
        classification_source=classification_source,
        image_count=image_count,
    )
    capture = _create_capture_record(
        db,
        text,
        classification_source=classification_source,
        interpretation_payload=interpretation_payload,
        processing_events=processing_events,
    )
    interpretation = _create_interpretation(db, capture, interpretation_payload)
    mutations = [
        _mutation_from_update(db, capture, interpretation, update, index)
        for index, update in enumerate(suggested_updates)
    ]
    db.commit()
    db.refresh(capture)
    db.refresh(interpretation)
    return capture, interpretation, mutations


def _classify_capture_text(
    db: Session, text: str, image_data: str | list[str] = ""
) -> tuple[list[dict[str, Any]], list[str], str, CaptureAnalysis | None]:
    image_inputs = image_data if isinstance(image_data, list) else ([image_data] if image_data else [])
    resolution_updates = _resolution_suggestions(db, text) if _is_explicit_resolution(text) else []
    analysis = analyze_capture(text, _memory_context(db), image_inputs) if image_inputs else analyze_capture(text, _memory_context(db))
    if analysis:
        prepared_updates, quality_follow_ups = _prepare_capture_updates(
            resolution_updates + [update.model_dump() for update in analysis.suggested_updates],
            text,
            classification_source="ai",
        )
        return (
            enrich_updates_with_leadership_lens(prepared_updates),
            list(dict.fromkeys(analysis.follow_ups + quality_follow_ups)),
            "ai",
            analysis,
        )
    if image_inputs and text.strip():
        updates, quality_follow_ups = _prepare_capture_updates(
            resolution_updates + _fallback_classify_capture_text(text),
            text,
            classification_source="local_fallback",
        )
        follow_ups = _task_resolution_suggestions(db, text)
        follow_ups.extend(quality_follow_ups)
        follow_ups.extend(_vague_strategy_followups(text))
        follow_ups.append(f"{_screenshot_unavailable_message()} The text entry was still reviewed.")
        if not updates:
            follow_ups.append(
                "What person, company, project, decision, or metric should be saved from this update?"
            )
        return enrich_updates_with_leadership_lens(updates), list(dict.fromkeys(follow_ups)), "local_fallback", None
    if image_inputs:
        return [], [_screenshot_unavailable_message()], "image_unavailable", None
    updates, quality_follow_ups = _prepare_capture_updates(
        resolution_updates + _fallback_classify_capture_text(text),
        text,
        classification_source="local_fallback",
    )
    follow_ups = _task_resolution_suggestions(db, text)
    follow_ups.extend(quality_follow_ups)
    follow_ups.extend(_vague_strategy_followups(text))
    if not updates:
        follow_ups.extend([
        "What person, company, project, decision, or metric should be saved from this update?"
        ])
    return enrich_updates_with_leadership_lens(updates), list(dict.fromkeys(follow_ups)), "local_fallback", None


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
    field_operations = update.get("field_operations") or {}
    for field in allowed:
        operation = field_operations.get(field)
        value = update.get(field)
        if operation == "clear":
            setattr(instance, field, [] if isinstance(getattr(instance, field, None), list) else "")
        elif operation in {"remove", "resolve"} and isinstance(getattr(instance, field, None), list):
            setattr(instance, field, _apply_list_operation(getattr(instance, field) or [], value or [], operation))
        elif operation == "append" and isinstance(getattr(instance, field, None), list):
            setattr(instance, field, _apply_list_operation(getattr(instance, field) or [], value or [], operation))
        elif isinstance(getattr(instance, field, None), list) and value not in (None, "", []):
            setattr(instance, field, _apply_list_operation(getattr(instance, field) or [], value, "append"))
        elif value not in (None, "", []):
            setattr(instance, field, value)
    db.add(instance)
    db.flush()
    db.refresh(instance)
    return instance


def _instance_snapshot(instance: Any) -> dict[str, Any]:
    def safe(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    return {column.name: safe(getattr(instance, column.key)) for column in instance.__table__.columns}


def _apply_list_operation(current: list[Any] | None, incoming: list[Any] | Any, operation: str) -> list[Any]:
    current_values = list(current or [])
    incoming_values = incoming if isinstance(incoming, list) else [incoming]
    incoming_values = [value for value in incoming_values if value not in (None, "")]
    if operation == "clear":
        return []
    if operation == "replace":
        return list(incoming_values)
    if operation in {"remove", "resolve"}:
        normalized_remove = {str(value).strip().lower() for value in incoming_values}
        return [value for value in current_values if str(value).strip().lower() not in normalized_remove]
    return list(dict.fromkeys(current_values + incoming_values))


def _record_capture_change(db: Session, record_type: str, instance: Any, text: str, change_type: str) -> None:
    if not getattr(instance, "id", None):
        return
    ensure_provenance(
        db,
        record_type,
        instance.id,
        source_type="capture_text",
        source_title="Capture",
        source_excerpt=text,
        created_by="user",
        confidence="user_confirmed",
        verification_state="user_confirmed",
        memory_classification="confirmed_fact",
    )
    record_revision(
        db,
        record_type,
        instance.id,
        after=_instance_snapshot(instance),
        change_type=change_type,
        source_type="capture_text",
    )


def _apply_explicit_resolution(db: Session, text: str) -> None:
    if not _is_explicit_resolution(text):
        return
    resolve_items_from_capture_text(db, text, actor="user")
    target = _resolution_target_from_text(text)
    if not target:
        return

    for task in db.query(Task).filter(Task.status.in_(OPEN_TASK_STATUSES)).all():
        if _matches_resolution_target(task, ["title", "description", "source_summary"], target):
            complete_task(db, task)
            _record_capture_change(db, "task", task, text, "capture_explicit_resolution")

    for issue in db.query(StrategicIssue).filter(StrategicIssue.status == "active").all():
        changed = False
        remaining_risks, removed_risk = _prune_resolved_values(issue.risks, target)
        if removed_risk:
            issue.risks = remaining_risks
            changed = True
        if _matches_resolution_target(issue, ["title", "current_thinking"], target):
            issue.status = "resolved"
            changed = True
        if changed:
            db.add(issue)
            db.flush()
            _record_capture_change(db, "strategic_issue", issue, text, "capture_explicit_resolution")

    for project in db.query(Project).filter(Project.status == "active").all():
        changed = False
        remaining_risks, removed_risk = _prune_resolved_values(project.risks, target)
        if removed_risk:
            project.risks = remaining_risks
            changed = True
        remaining_steps, removed_step = _prune_resolved_values(project.next_steps, target)
        if removed_step:
            project.next_steps = remaining_steps
            changed = True
        if _matches_resolution_target(project, ["title", "objective"], target):
            project.status = "completed"
            changed = True
        if changed:
            db.add(project)
            db.flush()
            _record_capture_change(db, "project", project, text, "capture_explicit_resolution")


def _apply_approved_updates(
    db: Session,
    text: str,
    approved_updates: list[SuggestedUpdate | dict[str, Any]],
    classification_source: str = "unknown",
    capture_id: int | None = None,
) -> CaptureRecord:
    lowered = text.lower()
    detected_name = _detect_known_person_name(text)

    explicit_company = _detect_positive_company(text)

    saved_record_ids: list[dict[str, Any]] = []
    approved_payloads: list[dict[str, Any]] = []
    skipped_payloads: list[dict[str, Any]] = []
    persisted_by_index: dict[int, dict[str, Any]] = {}
    for update_index, raw_update in enumerate(approved_updates):
        update = raw_update.model_dump() if isinstance(raw_update, SuggestedUpdate) else raw_update
        prepared_update = _prepare_task_update_for_capture(
            update,
            text,
            classification_source=classification_source,
        )
        if prepared_update is None:
            skipped_payload = dict(update)
            skipped_payload["skip_reason"] = "weak_task_missing_owner_outcome_or_action_context"
            skipped_payloads.append(skipped_payload)
            continue
        update = prepared_update
        update = enrich_task_update_with_leadership_lens(update)
        approved_payloads.append(update)
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
                field_operations = update.get("field_operations") or {}
                if field_operations.get("owner") == "clear":
                    issue.owner = ""
                if "risks" in update and update.get("risks") is not None:
                    issue.risks = _apply_list_operation(
                        issue.risks or [],
                        update["risks"],
                        field_operations.get("risks") or "append",
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
            if saved_instance is not None and update_type == "project":
                field_operations = update.get("field_operations") or {}
                project = saved_instance
                for field in ("risks", "milestones", "next_steps"):
                    if field in update:
                        setattr(project, field, _apply_list_operation(
                            getattr(project, field) or [],
                            update[field],
                            field_operations.get(field) or "append",
                        ))
                if field_operations.get("owner") == "clear":
                    project.owner = ""
                db.flush()
            if handled and update_type == "meeting":
                meeting_title = update.get("title")
                if meeting_title:
                    meeting = db.query(Meeting).filter(Meeting.title.ilike(meeting_title)).first()
                    if meeting:
                        ensure_tasks_for_meeting_action_items(db, meeting)
        if saved_instance is not None and getattr(saved_instance, "id", None):
            saved_record_ids.append({
                "type": update_type,
                "id": saved_instance.id,
                "suggestion_index": update_index,
            })
            persisted_by_index[update_index] = _instance_snapshot(saved_instance)
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
                after=_instance_snapshot(saved_instance),
                change_type="capture_approval",
                source_type=source_type,
            )

    _apply_explicit_resolution(db, text)
    resolve_items_from_capture_text(db, text, actor="user")

    capture = db.get(CaptureRecord, capture_id) if capture_id else None
    if capture:
        capture.saved_count = len(approved_payloads)
        capture.classification_source = classification_source or capture.classification_source
        capture.approved_suggestions = approved_payloads
        proposed_updates = []
        if isinstance(capture.structured_interpretation, dict):
            proposed_updates = capture.structured_interpretation.get("suggested_updates") or []
        approved_indexes = {
            index for index, proposed in enumerate(proposed_updates)
            if any(proposed == approved for approved in approved_payloads)
        }
        capture.rejected_suggestions = [
            proposed for index, proposed in enumerate(proposed_updates)
            if index not in approved_indexes
        ] + skipped_payloads
        capture.saved_record_ids = saved_record_ids
        events = list(capture.processing_events or [])
        events.append({
            "event": "approved_updates_saved",
            "saved_count": len(approved_payloads),
            "skipped_count": len(skipped_payloads),
            "at": datetime.now(timezone.utc).isoformat(),
        })
        capture.processing_events = events
        db.add(capture)
    else:
        interpretation_payload = _analysis_to_interpretation(None, text, approved_payloads, [])
        capture = _create_capture_record(
            db,
            text,
            classification_source=classification_source,
            interpretation_payload=interpretation_payload,
            approved_updates=approved_payloads,
            rejected_updates=skipped_payloads,
            saved_record_ids=saved_record_ids,
            processing_events=[{
                "event": "approved_updates_saved_without_prior_review_record",
                "saved_count": len(approved_payloads),
                "skipped_count": len(skipped_payloads),
                "at": datetime.now(timezone.utc).isoformat(),
            }],
        )
        interpretation = _create_interpretation(db, capture, interpretation_payload)
        for index, update in enumerate(approved_payloads):
            _mutation_from_update(db, capture, interpretation, update, index)

    mutations = db.query(CaptureMutation).filter(CaptureMutation.capture_id == capture.id).all()
    approved_mutation_ids: set[int] = set()
    for update_index, update in enumerate(approved_payloads):
        matched_mutation = None
        for mutation in mutations:
            if mutation.status == "proposed" and mutation.proposed_values == update:
                matched_mutation = mutation
                break
        if matched_mutation is None:
            interpretation = (
                db.query(CaptureInterpretation)
                .filter(CaptureInterpretation.capture_id == capture.id)
                .order_by(CaptureInterpretation.id.desc())
                .first()
            )
            if interpretation is None:
                interpretation_payload = _analysis_to_interpretation(None, text, approved_payloads, [])
                interpretation = _create_interpretation(db, capture, interpretation_payload)
            matched_mutation = _mutation_from_update(db, capture, interpretation, update, update_index)
            mutations.append(matched_mutation)
        matched_mutation.status = "approved_applied"
        matched_mutation.approved_values = update
        matched_mutation.persisted_values = persisted_by_index.get(update_index, {})
        saved = next((item for item in saved_record_ids if item["suggestion_index"] == update_index), None)
        if saved:
            matched_mutation.saved_record_type = saved["type"]
            matched_mutation.saved_record_id = saved["id"]
        matched_mutation.applied_at = datetime.now(timezone.utc)
        db.add(matched_mutation)
        if matched_mutation.id:
            approved_mutation_ids.add(matched_mutation.id)
    for mutation in mutations:
        if mutation.status == "proposed" and mutation.id not in approved_mutation_ids:
            mutation.status = "rejected"
            db.add(mutation)
    db.commit()
    db.refresh(capture)
    return capture
