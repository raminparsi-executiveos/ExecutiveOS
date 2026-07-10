import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import auth_configuration_checks, auth_configured, auth_required, authenticate, require_auth
from .database import Base, engine, get_db
from .models import CaptureRecord, Company, Decision, Meeting, Metric, Person, Project, StrategicIssue, Task
from .schemas import (
    CaptureClassificationRequest,
    CaptureConfirmationRequest,
    CaptureRequest,
    CreateObjectRequest,
    LoginRequest,
    MeetingPrepRequest,
    SearchRequest,
    UpdateObjectRequest,
)
from .seed import seed_data
from .briefing_service import build_ranked_briefing
from .capture_service import _apply_approved_updates, _classify_capture_text
from .tasks import (
    OPEN_TASK_STATUSES,
    complete_task,
    ensure_tasks_for_meeting_action_items,
    reopen_task,
    task_is_overdue,
    validate_task_attributes,
)
from .memory import (
    SEARCH_CONFIG,
    _answer_for_ranked_items,
    _belongs_to_company,
    _company_in_query,
    _entity_name_boost,
    _match_score,
    _meeting_topic_query,
    _merge_memory_labels,
    _model_for_object_type,
    _rank_for_context,
    _result_summary,
    _search_intent_boost,
    _serialize_model,
    _unique_captures,
    RESULT_TYPES,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = next(get_db())
    try:
        seed_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title="ExecutiveOS API", lifespan=lifespan)


@app.middleware("http")
async def add_operational_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response

configured_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    # The MVP uses no cookies or browser credentials. This keeps cross-origin
    # static-site requests valid without the unsafe wildcard+credentials pair.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error
    return {"status": "ok", "database": "connected"}


@app.get("/auth/status")
def authentication_status():
    return {
        "required": auth_required(),
        "configured": auth_configured(),
        "checks": auth_configuration_checks(),
        "requirements": {"password_min_length": 12, "session_secret_min_length": 32},
    }


@app.post("/auth/login")
def login(payload: LoginRequest, request: Request):
    token = authenticate(request, payload.username, payload.password)
    return {"access_token": token, "token_type": "bearer", "expires_in": 43200}


@app.get("/briefing")
def briefing(db: Session = Depends(get_db), user: str = Depends(require_auth)):
    return build_ranked_briefing(db, user)


@app.post("/capture")
def capture(payload: CaptureRequest, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    suggested_updates, follow_ups, classification_source = _classify_capture_text(db, payload.text)
    if payload.confirm:
        try:
            _apply_approved_updates(db, payload.text, suggested_updates, classification_source)
        except SQLAlchemyError as error:
            db.rollback()
            raise HTTPException(status_code=500, detail="Capture could not be saved") from error
    return {
        "message": "Capture accepted",
        "suggested_updates": suggested_updates,
        "follow_ups": follow_ups,
        "classification_source": classification_source,
        "confirm": payload.confirm,
    }


@app.post("/capture/classify")
def classify_capture(payload: CaptureClassificationRequest, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    suggested_updates, follow_ups, classification_source = _classify_capture_text(db, payload.text, payload.image_inputs())
    return {
        "message": "Classification complete",
        "suggested_updates": suggested_updates,
        "follow_ups": follow_ups,
        "classification_source": classification_source,
        "confirm": payload.confirm,
    }


@app.post("/capture/confirm")
def confirm_capture(payload: CaptureConfirmationRequest, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    try:
        _apply_approved_updates(db, payload.text, payload.approved_updates, payload.classification_source)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=500, detail="Capture could not be saved") from error
    return {
        "message": "Approved updates saved",
        "saved_count": len(payload.approved_updates),
        "approved_updates": [update.model_dump() for update in payload.approved_updates],
    }


@app.get("/objects/{object_type}")
def list_objects(
    object_type: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    model = _model_for_object_type(object_type)
    query = db.query(model)
    total = query.count()
    items = query.order_by(model.id.desc()).offset(offset).limit(limit).all()
    return {"items": [_serialize_model(item) for item in items], "total": total, "limit": limit, "offset": offset}


@app.post("/objects/{object_type}")
def create_object(object_type: str, payload: CreateObjectRequest, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    model = _model_for_object_type(object_type)
    valid_fields = {column.name for column in model.__table__.columns} - {"id"}
    unknown_fields = sorted(set(payload.attributes) - valid_fields)
    if unknown_fields:
        raise HTTPException(status_code=422, detail=f"Unknown fields: {', '.join(unknown_fields)}")
    identity_field = "name" if "name" in valid_fields else "title"
    if not str(payload.attributes.get(identity_field) or "").strip():
        raise HTTPException(status_code=422, detail=f"Missing required field: {identity_field}")
    if model is Task:
        validate_task_attributes(payload.attributes)
    try:
        instance = model(**payload.attributes)
        db.add(instance)
        db.flush()
        if model is Meeting:
            ensure_tasks_for_meeting_action_items(db, instance)
        db.commit()
        db.refresh(instance)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An object with these unique values already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail="Object could not be created") from error
    return {"message": f"{object_type} created", "object": _serialize_model(instance)}


@app.patch("/objects/{object_type}/{object_id}")
def update_object(
    object_type: str,
    object_id: int,
    payload: UpdateObjectRequest,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    model = _model_for_object_type(object_type)
    valid_fields = {column.name for column in model.__table__.columns} - {"id"}
    unknown_fields = sorted(set(payload.attributes) - valid_fields)
    if unknown_fields:
        raise HTTPException(status_code=422, detail=f"Unknown fields: {', '.join(unknown_fields)}")
    identity_field = "name" if "name" in valid_fields else "title"
    if identity_field in payload.attributes and not str(payload.attributes.get(identity_field) or "").strip():
        raise HTTPException(status_code=422, detail=f"Missing required field: {identity_field}")
    if model is Task:
        validate_task_attributes(payload.attributes, partial=True)
    instance = db.get(model, object_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Object not found")
    try:
        for field, value in payload.attributes.items():
            setattr(instance, field, value)
        if model is Task and "status" in payload.attributes:
            if instance.status == "completed":
                complete_task(db, instance)
            elif instance.status in OPEN_TASK_STATUSES:
                instance.completed_at = None
        if model is Meeting:
            ensure_tasks_for_meeting_action_items(db, instance)
        db.commit()
        db.refresh(instance)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An object with these unique values already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail="Object could not be updated") from error
    return {"message": f"{object_type} updated", "object": _serialize_model(instance)}


@app.post("/tasks/{task_id}/complete")
def complete_task_endpoint(task_id: int, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        complete_task(db, task)
        db.commit()
        db.refresh(task)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail="Task could not be completed") from error
    return {"message": "Task completed", "task": _serialize_model(task)}


@app.post("/tasks/{task_id}/reopen")
def reopen_task_endpoint(task_id: int, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        reopen_task(db, task)
        db.commit()
        db.refresh(task)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail="Task could not be reopened") from error
    return {"message": "Task reopened", "task": _serialize_model(task)}


@app.delete("/objects/{object_type}/{object_id}")
def delete_object(
    object_type: str,
    object_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    model = _model_for_object_type(object_type)
    instance = db.get(model, object_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Object not found")
    try:
        db.delete(instance)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail="Object could not be deleted") from error
    return {"message": f"{object_type} deleted", "id": object_id}


@app.get("/captures")
def capture_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: str = Depends(require_auth),
):
    query = db.query(CaptureRecord)
    records = query.order_by(CaptureRecord.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "items": [_serialize_model(record) for record in records],
        "total": query.count(),
        "limit": limit,
        "offset": offset,
    }


@app.post("/meeting-prep")
def meeting_prep(payload: MeetingPrepRequest, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    meeting_title = payload.meeting or "Executive meeting"
    company_name = _company_in_query(meeting_title)
    company = db.query(Company).filter(Company.name.ilike(company_name)).first() if company_name else None
    topic_query = _meeting_topic_query(meeting_title, company_name) if company_name else ""
    context_query = topic_query or meeting_title

    def scoped_items(model: type[Any]) -> list[Any]:
        items = db.query(model).all()
        return [item for item in items if _belongs_to_company(item, company_name)] if company_name else items

    include_company_unmatched = bool(company_name and not topic_query)
    issues = _rank_for_context(scoped_items(StrategicIssue), SEARCH_CONFIG[StrategicIssue][1], context_query, include_unmatched=include_company_unmatched)
    decisions = _rank_for_context(scoped_items(Decision), SEARCH_CONFIG[Decision][1], context_query, include_unmatched=include_company_unmatched)
    people = _rank_for_context(scoped_items(Person), SEARCH_CONFIG[Person][1], context_query, include_unmatched=include_company_unmatched)
    meetings = _rank_for_context(scoped_items(Meeting), SEARCH_CONFIG[Meeting][1], context_query)[:5]
    metrics = _rank_for_context(scoped_items(Metric), SEARCH_CONFIG[Metric][1], context_query, include_unmatched=include_company_unmatched)
    projects = _rank_for_context(scoped_items(Project), SEARCH_CONFIG[Project][1], context_query, include_unmatched=include_company_unmatched)
    tasks = [
        task for task in _rank_for_context(
            scoped_items(Task),
            SEARCH_CONFIG[Task][1],
            context_query,
            include_unmatched=include_company_unmatched,
        )
        if task.status in OPEN_TASK_STATUSES
    ]
    capture_candidates = scoped_items(CaptureRecord)
    minimum_capture_score = 1 if company_name and not topic_query else 3 if company_name else 6
    captures = _unique_captures([
        capture for capture in _rank_for_context(capture_candidates, ["raw_text"], context_query)
        if _match_score(capture, ["raw_text"], context_query) >= minimum_capture_score
    ])
    capture_people = [
        person.name
        for person in db.query(Person).all()
        if any(re.search(rf"\b{re.escape(person.name)}\b", capture.raw_text, flags=re.IGNORECASE) for capture in captures)
    ]
    action_items = list(dict.fromkeys(
        [task.title for task in tasks] +
        [item for meeting in meetings for item in (meeting.action_items or [])]
    ))
    risks = list(dict.fromkeys(risk for item in [*issues, *projects] for risk in (item.risks or [])))

    def topical(labels: list[str]) -> list[str]:
        if not topic_query:
            return labels
        return [label for label in labels if _match_score(type("Label", (), {"value": label})(), ["value"], topic_query)]

    supplemental_people = topical(list(company.people or [] if company else []))
    supplemental_issues = topical(list(company.strategic_issues or [] if company else []))
    supplemental_projects = topical(list(company.projects or [] if company else []))
    supplemental_decisions = topical(list(company.decisions or [] if company else []))
    related_people = _merge_memory_labels(
        [person.name for person in people] + capture_people, supplemental_people, company_name
    )[:8]
    related_issues = _merge_memory_labels([issue.title for issue in issues], supplemental_issues, company_name)[:8]
    related_projects = _merge_memory_labels([project.title for project in projects], supplemental_projects, company_name)[:8]
    related_decisions = _merge_memory_labels([decision.title for decision in decisions], supplemental_decisions, company_name)[:8]
    metric_summaries = [f"{metric.title}: {metric.value} ({metric.trend})" for metric in metrics[:8]]
    metric_summaries = list(dict.fromkeys(metric_summaries + topical(list(company.kpis or [] if company else []))))[:8]
    agenda = [
        f"Review current context for {meeting_title}",
        f"Discuss open decisions: {', '.join(related_decisions[:2]) if related_decisions else 'No open decisions'}",
        f"Validate strategic issues: {', '.join(related_issues[:2]) if related_issues else 'No active strategic issues'}",
        f"Review active projects: {', '.join(related_projects[:2]) if related_projects else 'No active projects'}",
        "Confirm risks, action items, and follow-up owners",
    ]
    return {
        "meeting": meeting_title,
        "context_found": bool(company or issues or decisions or people or meetings or metrics or projects or tasks or captures),
        "agenda": agenda,
        "related_people": related_people,
        "related_strategic_issues": related_issues,
        "related_projects": related_projects,
        "open_decisions": related_decisions,
        "recent_meeting_context": [meeting.summary for meeting in meetings if meeting.summary][:3],
        "recent_capture_context": [_result_summary(capture) for capture in captures],
        "action_items": action_items[:8],
        "metrics": metric_summaries,
        "risks": risks[:5],
    }


@app.post("/search")
def search(payload: SearchRequest, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    ranked_results = []
    query_tokens = set(re.findall(r"[a-z0-9]+", payload.query.lower()))
    target_company = _company_in_query(payload.query)
    mentioned_people = [
        person for person in db.query(Person).all()
        if re.search(rf"\b{re.escape(person.name)}\b", payload.query, flags=re.IGNORECASE)
    ]
    transition_people = [
        person.name for person in mentioned_people
        if target_company and person.company.lower() != target_company.lower()
    ]
    risk_intent = bool(query_tokens & {"risk", "risks"})
    action_intent = bool(query_tokens & {"action", "actions"})
    question_intent = bool(query_tokens & {"question", "questions"})
    quantity_intent = {"how", "many"} <= query_tokens
    overdue_intent = "overdue" in query_tokens
    meetings_today_intent = "today" in query_tokens and bool(query_tokens & {"meeting", "meetings"})
    for model, (title_field, fields) in SEARCH_CONFIG.items():
        for item in db.query(model).all():
            if target_company and not _belongs_to_company(item, target_company):
                continue
            if quantity_intent and model is not Metric:
                continue
            if risk_intent and (model not in {StrategicIssue, Project} or not item.risks):
                continue
            if action_intent and (
                (model is Meeting and not item.action_items)
                or (model is Task and item.status in {"completed", "cancelled"})
                or model not in {Meeting, Task}
            ):
                continue
            if question_intent and (model is not Meeting or not item.open_questions):
                continue
            if overdue_intent and (
                (model is Decision and (not item.review_date or item.review_date >= date.today().isoformat()))
                or (model is Task and not task_is_overdue(item))
                or model not in {Decision, Task}
            ):
                continue
            if meetings_today_intent and (model is not Meeting or item.date != date.today().isoformat()):
                continue
            score = _match_score(item, fields, payload.query)
            intent_score = _search_intent_boost(model, payload.query)
            if not score and model is Decision and query_tokens & {"decision", "decisions"}:
                score = intent_score
            if not score and model in {StrategicIssue, Project} and query_tokens & {"risk", "risks"} and item.risks:
                score = 12
            if not score and model is Meeting and (action_intent or question_intent):
                score = 12
            if not score and model is Task and (action_intent or overdue_intent or query_tokens & {"task", "tasks", "commitment", "commitments"}):
                score = 12
            if not score and model is Decision and overdue_intent:
                score = 12
            if not score and model is Task and overdue_intent:
                score = 12
            if not score and model is Meeting and meetings_today_intent:
                score = 12
            if score:
                score += intent_score
                score += _entity_name_boost(item, title_field, payload.query)
                ranked_results.append((score, item.id or 0, item, {
                    "type": RESULT_TYPES[model],
                    "title": getattr(item, title_field),
                    "summary": _result_summary(item),
                }))

    for capture in db.query(CaptureRecord).all():
        if target_company and not _belongs_to_company(capture, target_company):
            continue
        score = _match_score(capture, ["raw_text"], payload.query)
        if score:
            capture_score = min(score, 8)
            if any(re.search(rf"\b{re.escape(name)}\b", capture.raw_text, flags=re.IGNORECASE) for name in transition_people):
                capture_score += 40
            ranked_results.append((capture_score, capture.id or 0, capture, {
                "type": "capture",
                "title": f"Captured update from {capture.created_at.date().isoformat()}",
                "summary": _result_summary(capture),
            }))

    ranked_results.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    if not ranked_results:
        return {"query": payload.query, "answer": "No matching executive memory found.", "results": []}
    # Keep close supporting matches while dropping weak records that happen to
    # share one generic word with the question.
    cutoff = max(1, ranked_results[0][0] - 6)
    included = []
    seen_results = set()
    for entry in ranked_results:
        if entry[0] < cutoff:
            continue
        result = entry[3]
        identity = (result["type"], result["title"], result["summary"])
        if identity in seen_results:
            continue
        seen_results.add(identity)
        included.append(entry)
        if len(included) == 10:
            break
    results = [entry[3] for entry in included]
    answer = _answer_for_ranked_items([entry[2] for entry in included], payload.query)
    return {"query": payload.query, "answer": answer, "results": results}
