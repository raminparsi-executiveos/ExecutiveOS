import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .memory import _serialize_model
from .models import Clarification, Decision, Metric, Project, RevisionRecord, Task
from .roadmap_services import record_revision
from .tasks import OPEN_TASK_STATUSES, complete_task


OPEN_CLARIFICATION_STATUSES = {"open", "snoozed"}
TERMINAL_CLARIFICATION_STATUSES = {"answered", "dismissed", "intentionally_unknown", "suppressed"}
CLARIFICATION_RULE_VERSION = "clarification-rules-v1"
CLARIFICATION_DAILY_LIMIT = 5
AMBIGUOUS_ACTION_PHRASES = (
    "soon",
    "almost complete",
    "handling it",
    "waiting on them",
    "follow up later",
    "pricing looks good",
)


OBJECT_MODELS = {
    "tasks": Task,
    "task": Task,
    "projects": Project,
    "project": Project,
    "decisions": Decision,
    "decision": Decision,
    "metrics": Metric,
    "metric": Metric,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _record_type_for(instance: Any) -> str:
    if isinstance(instance, Task):
        return "tasks"
    if isinstance(instance, Project):
        return "projects"
    if isinstance(instance, Decision):
        return "decisions"
    if isinstance(instance, Metric):
        return "metrics"
    return getattr(instance, "__tablename__", "records")


def _evidence_for(instance: Any, text: str, *, field: str = "") -> dict[str, Any]:
    return {
        "source_type": _record_type_for(instance),
        "source_id": getattr(instance, "id", None),
        "field": field,
        "text": str(text or "")[:500],
    }


def _fingerprint(evidence: list[dict[str, Any]]) -> str:
    return json.dumps(evidence, sort_keys=True, default=str)


def _base_payload(
    *,
    clarification_type: str,
    subtype: str,
    question: str,
    why_it_matters: str,
    target: Any,
    evidence: list[dict[str, Any]],
    score: int,
    score_reasons: list[str],
    suggested_answers: list[dict[str, Any]] | None = None,
    proposed_update: dict[str, Any] | None = None,
    uncertainty: str = "",
    dedupe_suffix: str = "",
) -> dict[str, Any]:
    record_type = _record_type_for(target)
    target_id = getattr(target, "id", None)
    subtype_key = f"{subtype}:{dedupe_suffix}" if dedupe_suffix else subtype
    return {
        "clarification_type": clarification_type,
        "subtype": subtype,
        "question": question,
        "why_it_matters": why_it_matters,
        "target_record_type": record_type,
        "target_record_id": target_id,
        "company": getattr(target, "company", "") or "",
        "evidence": evidence,
        "score": score,
        "score_reasons": score_reasons,
        "suggested_answers": suggested_answers or [],
        "proposed_update": proposed_update or {},
        "confidence": "deterministic",
        "uncertainty": uncertainty,
        "dedupe_key": f"{clarification_type}:{subtype_key}:{record_type}:{target_id}",
        "evidence_fingerprint": _fingerprint(evidence),
        "generation_rule_version": CLARIFICATION_RULE_VERSION,
    }


def _suggest_people_owner(db: Session, company: str) -> list[dict[str, Any]]:
    from .models import Person

    query = db.query(Person)
    if company:
        query = query.filter(Person.company.ilike(company))
    suggestions = []
    for person in query.order_by(Person.id.desc()).limit(3).all():
        suggestions.append({
            "label": person.name,
            "value": person.name,
            "inference": True,
            "reason": f"{person.name} is already associated with {company or 'this workspace'}.",
            "evidence": [_evidence_for(person, f"{person.name} - {person.role or 'known person'}", field="name")],
        })
    return suggestions


def _task_missing_due_date_payload(task: Task) -> dict[str, Any]:
    return _base_payload(
        clarification_type="missing_material_context",
        subtype="task_due_date",
        question=f"When should '{task.title}' be followed up or completed?",
        why_it_matters="This commitment is important enough to track, but it has no date to drive follow-up.",
        target=task,
        evidence=[_evidence_for(task, task.title, field="due_date")],
        score=75 + (10 if task.priority in {"critical", "high"} else 0),
        score_reasons=["open commitment", "missing due date"] + (["high priority"] if task.priority in {"critical", "high"} else []),
        proposed_update={"updates": [{"object_type": "tasks", "object_id": task.id, "attributes": {"due_date": ""}}]},
        uncertainty="The system knows this is open, but not when it should be revisited.",
    )


def _task_missing_next_action_payload(task: Task) -> dict[str, Any]:
    return _base_payload(
        clarification_type="missing_material_context",
        subtype="task_next_action",
        question=f"What is the next action for '{task.title}'?",
        why_it_matters="A blocked or waiting task needs a concrete next step so it does not sit indefinitely.",
        target=task,
        evidence=[_evidence_for(task, task.title, field="next_action")],
        score=72,
        score_reasons=["waiting or blocked", "missing next action"],
        proposed_update={"updates": [{"object_type": "tasks", "object_id": task.id, "attributes": {"next_action": ""}}]},
    )


def _project_missing_owner_payload(db: Session, project: Project) -> dict[str, Any]:
    return _base_payload(
        clarification_type="missing_material_context",
        subtype="project_owner",
        question=f"Who owns '{project.title}'?",
        why_it_matters="An active project without an owner is likely to stall or route follow-up back to you.",
        target=project,
        evidence=[_evidence_for(project, " | ".join([
            project.objective or project.title,
            "Risks: " + "; ".join(project.risks or []) if project.risks else "",
        ]).strip(" |"), field="owner")],
        score=84 + (8 if project.risks else 0),
        score_reasons=["active project", "missing owner"] + (["explicit risk"] if project.risks else []),
        suggested_answers=_suggest_people_owner(db, project.company or ""),
        proposed_update={"updates": [{"object_type": "projects", "object_id": project.id, "attributes": {"owner": ""}}]},
    )


def _decision_missing_reasoning_payload(decision: Decision) -> dict[str, Any]:
    return _base_payload(
        clarification_type="missing_material_context",
        subtype="decision_reasoning",
        question=f"What was the reasoning behind '{decision.title}'?",
        why_it_matters="A decision without reasoning is harder to defend, revisit, or explain later.",
        target=decision,
        evidence=[_evidence_for(decision, decision.final_decision or decision.context or decision.title, field="reasoning")],
        score=67,
        score_reasons=["decision", "missing reasoning"],
        proposed_update={"updates": [{"object_type": "decisions", "object_id": decision.id, "attributes": {"reasoning": ""}}]},
    )


def _metric_missing_period_payload(metric: Metric) -> dict[str, Any]:
    return _base_payload(
        clarification_type="missing_material_context",
        subtype="metric_period",
        question=f"What reporting period does '{metric.title}' represent?",
        why_it_matters="A metric without a period or date can be misleading in briefing and dashboard comparisons.",
        target=metric,
        evidence=[_evidence_for(metric, f"{metric.title}: {metric.value}", field="date")],
        score=61,
        score_reasons=["metric", "missing reporting period"],
        proposed_update={"updates": [{"object_type": "metrics", "object_id": metric.id, "attributes": {"date": ""}}]},
    )


def _stale_project_payload(project: Project, stale_after: datetime) -> dict[str, Any]:
    evidence_text = f"Last updated {project.updated_at.isoformat() if project.updated_at else 'unknown'}; expected after {stale_after.date().isoformat()}"
    return _base_payload(
        clarification_type="stale_information",
        subtype="active_project_stale",
        question=f"Is '{project.title}' still current?",
        why_it_matters="The project is active but has not changed recently, so briefing may be relying on stale context.",
        target=project,
        evidence=[_evidence_for(project, evidence_text, field="updated_at")],
        score=58,
        score_reasons=["active project", "stale update"],
        suggested_answers=[
            {"label": "Still active", "value": "active"},
            {"label": "Completed", "value": "completed"},
            {"label": "Paused", "value": "paused"},
        ],
        proposed_update={"updates": [{"object_type": "projects", "object_id": project.id, "attributes": {"status": ""}}]},
    )


def _project_owner_conflict_payload(left: Project, right: Project) -> dict[str, Any]:
    return _base_payload(
        clarification_type="contradiction",
        subtype="project_owner_conflict",
        question=f"Which owner is correct for '{left.title}'?",
        why_it_matters="Two active records for the same initiative name different owners. The system should not choose one silently.",
        target=left,
        evidence=[
            _evidence_for(left, f"Owner: {left.owner}", field="owner"),
            _evidence_for(right, f"Owner: {right.owner}", field="owner"),
        ],
        score=92,
        score_reasons=["contradiction", "active project", "owner conflict"],
        suggested_answers=[
            {"label": left.owner, "value": left.owner, "inference": True, "reason": "One active record names this owner."},
            {"label": right.owner, "value": right.owner, "inference": True, "reason": "Another active record names this owner."},
        ],
        proposed_update={
            "updates": [
                {"object_type": "projects", "object_id": left.id, "attributes": {"owner": ""}},
                {"object_type": "projects", "object_id": right.id, "attributes": {"owner": ""}},
            ]
        },
        dedupe_suffix=str(right.id),
    )


def _ambiguous_task_payload(task: Task, phrase: str) -> dict[str, Any]:
    return _base_payload(
        clarification_type="ambiguous_language",
        subtype="task_ambiguous_action",
        question=f"What does '{phrase}' mean for '{task.title}'?",
        why_it_matters="The phrase affects an actionable task field, but it is not specific enough to drive follow-up.",
        target=task,
        evidence=[_evidence_for(task, task.description or task.title, field="description")],
        score=63,
        score_reasons=["ambiguous language", "open task"],
        proposed_update={"updates": [{"object_type": "tasks", "object_id": task.id, "attributes": {"next_action": ""}}]},
        uncertainty=f"'{phrase}' needs a concrete owner, date, status, or next action.",
        dedupe_suffix=phrase.replace(" ", "_"),
    )


def _disconnected_decision_payload(decision: Decision) -> dict[str, Any]:
    return _base_payload(
        clarification_type="disconnected_information",
        subtype="decision_missing_company_or_link",
        question=f"What company, project, or issue should '{decision.title}' be linked to?",
        why_it_matters="Disconnected decisions are hard to retrieve in meeting prep, dashboards, and future reviews.",
        target=decision,
        evidence=[_evidence_for(decision, decision.final_decision or decision.context or decision.title, field="links")],
        score=60,
        score_reasons=["decision", "missing company or link"],
        proposed_update={"updates": [{"object_type": "decisions", "object_id": decision.id, "attributes": {"company": ""}}]},
    )


def _candidate_payloads(db: Session, *, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or _now()
    payloads: list[dict[str, Any]] = []

    for project in db.query(Project).filter(Project.status == "active").all():
        if not (project.owner or "").strip():
            payloads.append(_project_missing_owner_payload(db, project))
        updated_at = _aware(project.updated_at)
        if updated_at and updated_at < now - timedelta(days=30):
            payloads.append(_stale_project_payload(project, now - timedelta(days=30)))

    projects = db.query(Project).filter(Project.status == "active").all()
    for index, left in enumerate(projects):
        for right in projects[index + 1:]:
            if (
                left.title.strip().lower() == right.title.strip().lower()
                and left.owner
                and right.owner
                and left.owner.strip().lower() != right.owner.strip().lower()
            ):
                payloads.append(_project_owner_conflict_payload(left, right))

    for task in db.query(Task).filter(Task.status.in_(OPEN_TASK_STATUSES)).all():
        if task.priority in {"critical", "high"} and not (task.due_date or "").strip():
            payloads.append(_task_missing_due_date_payload(task))
        if task.status in {"waiting", "blocked"} and not (task.next_action or "").strip():
            payloads.append(_task_missing_next_action_payload(task))
        source = f"{task.title} {task.description} {task.next_action}".lower()
        for phrase in AMBIGUOUS_ACTION_PHRASES:
            if phrase in source:
                payloads.append(_ambiguous_task_payload(task, phrase))
                break

    for decision in db.query(Decision).all():
        if (decision.final_decision or decision.context) and not (decision.reasoning or "").strip():
            payloads.append(_decision_missing_reasoning_payload(decision))
        linked = any([
            decision.company,
            decision.linked_people,
            decision.linked_projects,
            decision.linked_strategic_issues,
        ])
        if not linked:
            payloads.append(_disconnected_decision_payload(decision))

    for metric in db.query(Metric).all():
        if metric.value and not metric.date:
            payloads.append(_metric_missing_period_payload(metric))

    return payloads


def _apply_payload(clarification: Clarification, payload: dict[str, Any]) -> None:
    clarification.clarification_type = payload["clarification_type"]
    clarification.subtype = payload["subtype"]
    clarification.question = payload["question"]
    clarification.why_it_matters = payload["why_it_matters"]
    clarification.target_record_type = payload["target_record_type"]
    clarification.target_record_id = payload["target_record_id"]
    clarification.company = payload["company"]
    clarification.evidence = payload["evidence"]
    clarification.score = payload["score"]
    clarification.score_reasons = payload["score_reasons"]
    clarification.suggested_answers = payload["suggested_answers"]
    clarification.proposed_update = payload["proposed_update"]
    clarification.confidence = payload["confidence"]
    clarification.uncertainty = payload["uncertainty"]
    clarification.evidence_fingerprint = payload["evidence_fingerprint"]
    clarification.generation_rule_version = payload["generation_rule_version"]


def refresh_expired_snoozes(db: Session, *, now: datetime | None = None) -> None:
    now = now or _now()
    for clarification in db.query(Clarification).filter(Clarification.status == "snoozed").all():
        snoozed_until = _aware(clarification.snoozed_until)
        if snoozed_until and snoozed_until <= now:
            clarification.status = "open"
            clarification.snoozed_until = None
            db.add(clarification)
    db.flush()


def generate_clarifications(db: Session, *, now: datetime | None = None) -> list[Clarification]:
    refresh_expired_snoozes(db, now=now)
    changed: list[Clarification] = []
    for payload in _candidate_payloads(db, now=now):
        clarification = db.query(Clarification).filter(Clarification.dedupe_key == payload["dedupe_key"]).first()
        if clarification:
            evidence_changed = clarification.evidence_fingerprint != payload["evidence_fingerprint"]
            if clarification.status in {"suppressed", "intentionally_unknown"}:
                continue
            if clarification.status == "dismissed" and not evidence_changed:
                continue
            if evidence_changed and clarification.status in TERMINAL_CLARIFICATION_STATUSES:
                clarification.status = "open"
                clarification.answered_at = None
                clarification.dismissed_at = None
                clarification.snoozed_until = None
            _apply_payload(clarification, payload)
        else:
            clarification = Clarification(status="open", dedupe_key=payload["dedupe_key"])
            _apply_payload(clarification, payload)
        db.add(clarification)
        changed.append(clarification)
    db.flush()
    return changed


def serialize_clarification(clarification: Clarification) -> dict[str, Any]:
    return _serialize_model(clarification) | {
        "available_actions": ["answer", "ask_later", "dismiss", "intentionally_unknown", "suppress"],
    }


def list_clarifications(
    db: Session,
    *,
    refresh: bool = True,
    status: str = "open",
    company: str = "",
    clarification_type: str = "",
    target_record_type: str = "",
    min_score: int = 0,
    limit: int = 100,
) -> list[Clarification]:
    if refresh:
        generate_clarifications(db)
    else:
        refresh_expired_snoozes(db)
    query = db.query(Clarification)
    if status:
        query = query.filter(Clarification.status == status)
    if company:
        query = query.filter(Clarification.company.ilike(company))
    if clarification_type:
        query = query.filter(Clarification.clarification_type == clarification_type)
    if target_record_type:
        query = query.filter(Clarification.target_record_type == target_record_type)
    if min_score:
        query = query.filter(Clarification.score >= min_score)
    return query.order_by(Clarification.score.desc(), Clarification.updated_at.desc(), Clarification.id.desc()).limit(limit).all()


def briefing_clarification_items(db: Session, *, limit: int = CLARIFICATION_DAILY_LIMIT, company: str = "") -> list[dict[str, Any]]:
    return [
        {
            "title": clarification.question,
            "record_type": "clarification",
            "record_id": clarification.id,
            "company": clarification.company or company,
            "status": clarification.status,
            "why_it_matters": clarification.why_it_matters,
            "recommended_next_action": "Answer, snooze, dismiss, or mark intentionally unknown.",
            "score": clarification.score,
            "score_reasons": clarification.score_reasons or [],
            "source": {
                "type": clarification.target_record_type,
                "id": str(clarification.target_record_id or ""),
                "summary": (clarification.evidence or [{}])[0].get("text", ""),
            },
        }
        for clarification in list_clarifications(db, status="open", company=company, limit=limit)
    ]


def executive_inbox_items(db: Session, *, refresh: bool = True, status: str = "open", company: str = "") -> list[dict[str, Any]]:
    clarifications = list_clarifications(db, refresh=refresh, status=status, company=company, limit=100)
    items = []
    for clarification in clarifications:
        items.append({
            "id": f"clarification:{clarification.id}",
            "source_type": "clarification",
            "source_id": clarification.id,
            "company": clarification.company or "",
            "title": clarification.question,
            "summary": clarification.why_it_matters,
            "priority": "high" if clarification.score >= 85 else "medium" if clarification.score >= 65 else "low",
            "score": clarification.score,
            "score_reasons": clarification.score_reasons or [],
            "created_at": clarification.created_at.isoformat() if clarification.created_at else "",
            "freshness": "new" if clarification.status == "open" else clarification.status,
            "suggested_action": "Answer or snooze this clarification.",
            "available_actions": ["answer", "ask_later", "dismiss", "intentionally_unknown", "suppress"],
            "status": clarification.status,
            "owner": "",
            "due_date": clarification.snoozed_until.isoformat() if clarification.snoozed_until else "",
            "supporting_sources": clarification.evidence or [],
        })
    return sorted(items, key=lambda item: item["score"], reverse=True)


def _answer_attributes(clarification: Clarification, answer: str) -> list[dict[str, Any]]:
    answer = str(answer or "").strip()
    if not answer:
        raise HTTPException(status_code=422, detail="Answer is required")
    update = clarification.proposed_update or {}
    updates = list(update.get("updates") or [])
    if not updates:
        updates = [{
            "object_type": clarification.target_record_type,
            "object_id": clarification.target_record_id,
            "attributes": {},
        }]
    field_by_subtype = {
        "project_owner": "owner",
        "task_due_date": "due_date",
        "task_next_action": "next_action",
        "decision_reasoning": "reasoning",
        "metric_period": "date",
        "active_project_stale": "status",
        "project_owner_conflict": "owner",
        "task_ambiguous_action": "next_action",
        "decision_missing_company_or_link": "company",
    }
    field = field_by_subtype.get(clarification.subtype)
    if field:
        for mutation in updates:
            mutation.setdefault("attributes", {})[field] = answer
    return updates


def preview_clarification_answer(db: Session, clarification: Clarification, answer: str, note: str = "") -> Clarification:
    mutations = _answer_attributes(clarification, answer)
    clarification.user_response = answer.strip()
    clarification.note = note
    clarification.proposed_update = {"updates": mutations, "requires_confirmation": True}
    db.add(clarification)
    db.flush()
    return clarification


def _model_for_record_type(record_type: str) -> type[Any]:
    model = OBJECT_MODELS.get(record_type)
    if not model:
        raise HTTPException(status_code=422, detail=f"Unsupported target record type: {record_type}")
    return model


def confirm_clarification_update(
    db: Session,
    clarification: Clarification,
    *,
    update_indexes: list[int] | None = None,
    changed_by: str = "user",
) -> Clarification:
    updates = list((clarification.proposed_update or {}).get("updates") or [])
    if not updates:
        raise HTTPException(status_code=422, detail="No proposed update to confirm")
    selected_indexes = set(update_indexes or range(len(updates)))
    applied: list[dict[str, Any]] = []
    for index, mutation in enumerate(updates):
        if index not in selected_indexes:
            continue
        object_type = mutation.get("object_type") or clarification.target_record_type
        object_id = mutation.get("object_id") or clarification.target_record_id
        attributes = mutation.get("attributes") or {}
        if not attributes:
            continue
        model = _model_for_record_type(object_type)
        instance = db.get(model, object_id)
        if not instance:
            raise HTTPException(status_code=404, detail=f"Target record not found: {object_type}/{object_id}")
        before = _serialize_model(instance)
        for field, value in attributes.items():
            if field == "id" or field not in {column.name for column in model.__table__.columns}:
                raise HTTPException(status_code=422, detail=f"Unsupported update field: {field}")
            setattr(instance, field, value)
        if isinstance(instance, Task) and attributes.get("status") == "completed":
            complete_task(db, instance)
        db.add(instance)
        db.flush()
        record_revision(
            db,
            object_type,
            instance.id,
            before=before,
            after=_serialize_model(instance),
            change_type="clarification_answer",
            changed_by=changed_by,
            source_type="clarification",
            source_id=str(clarification.id),
        )
        applied.append({"object_type": object_type, "object_id": instance.id, "attributes": attributes})
    clarification.status = "answered"
    clarification.answered_at = _now()
    clarification.proposed_update = {"updates": updates, "applied_updates": applied}
    db.add(clarification)
    db.flush()
    return clarification


def snooze_clarification(db: Session, clarification: Clarification, snoozed_until: datetime, note: str = "") -> Clarification:
    clarification.status = "snoozed"
    clarification.snoozed_until = snoozed_until
    clarification.note = note
    db.add(clarification)
    db.flush()
    return clarification


def dismiss_clarification(db: Session, clarification: Clarification, reason: str = "") -> Clarification:
    clarification.status = "dismissed"
    clarification.dismissed_at = _now()
    clarification.note = reason
    db.add(clarification)
    db.flush()
    return clarification


def mark_intentionally_unknown(db: Session, clarification: Clarification, note: str = "") -> Clarification:
    clarification.status = "intentionally_unknown"
    clarification.dismissed_at = _now()
    clarification.note = note
    db.add(clarification)
    db.flush()
    return clarification


def suppress_clarification(db: Session, clarification: Clarification, scope: str, reason: str = "") -> Clarification:
    clarification.status = "suppressed"
    clarification.suppression_scope = scope or f"{clarification.target_record_type}:{clarification.target_record_id}:{clarification.subtype}"
    clarification.suppression_reason = reason
    clarification.dismissed_at = _now()
    db.add(clarification)
    db.flush()
    return clarification


def reopen_clarification(db: Session, clarification: Clarification) -> Clarification:
    clarification.status = "open"
    clarification.snoozed_until = None
    clarification.dismissed_at = None
    clarification.answered_at = None
    db.add(clarification)
    db.flush()
    return clarification


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Expected ISO datetime") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
