import re
import os
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

from .ai import SuggestedUpdate, analyze_capture
from .auth import auth_configuration_checks, auth_configured, auth_required, authenticate, require_auth
from .database import Base, engine, get_db
from .models import CaptureRecord, Company, Decision, Document, Meeting, Metric, Person, Project, SOP, StrategicIssue
from .schemas import (
    CaptureClassificationRequest,
    CaptureConfirmationRequest,
    CaptureRequest,
    CreateObjectRequest,
    LoginRequest,
    MeetingPrepRequest,
    SearchRequest,
)
from .seed import seed_data

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

OBJECT_MODEL_MAP = {
    "companies": Company,
    "people": Person,
    "strategic-issues": StrategicIssue,
    "projects": Project,
    "decisions": Decision,
    "meetings": Meeting,
    "sops": SOP,
    "documents": Document,
    "metrics": Metric,
}


def _model_for_object_type(object_type: str):
    model = OBJECT_MODEL_MAP.get(object_type)
    if not model:
        raise HTTPException(status_code=404, detail="Object type not found")
    return model


def _serialize_model(instance: Any) -> dict[str, Any]:
    return {
        column.name: getattr(instance, column.name)
        for column in instance.__table__.columns
    }


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    return str(value)


def _matches_query(record: Any, fields: list[str], query: str) -> bool:
    return _match_score(record, fields, query) > 0


def _match_score(record: Any, fields: list[str], query: str) -> int:
    haystack = " ".join(_stringify_value(getattr(record, field, "")) for field in fields).lower()
    if not query:
        return 0
    if query.lower() in haystack:
        return 20

    normalized_query = query.lower()
    stop_words = {"a", "an", "and", "are", "did", "do", "does", "for", "from", "in", "is", "me", "my", "of", "on", "the", "to", "we", "what", "why", "with"}
    tokens = set(re.findall(r"[a-z0-9]+", normalized_query)) - stop_words
    synonyms = {
        "promote": ["promotion", "promoted"],
        "promoted": ["promotion", "promote"],
        "what": ["title", "summary", "context"],
        "happening": ["status", "active", "current", "issue", "project"],
    }
    score = 0
    for token in tokens:
        if token in haystack:
            score += 3
            continue
        for synonym in synonyms.get(token, []):
            if synonym in haystack:
                score += 3
                break
    return score


def _search_intent_boost(model: type[Any], query: str) -> int:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if tokens & {"why", "decide", "decided", "decision", "promote", "promoted", "promotion"}:
        return 12 if model is Decision else 0
    if tokens & {"meeting", "agenda", "prep"}:
        return 8 if model is Meeting else 0
    if tokens & {"metric", "metrics", "kpi", "trend"}:
        return 8 if model is Metric else 0
    if tokens & {"project", "projects", "initiative"}:
        return 8 if model is Project else 0
    if tokens & {"who", "person", "role"}:
        return 8 if model is Person else 0
    if "company" in tokens:
        return 8 if model in {Person, Company} else 0
    return 0


SEARCH_CONFIG = {
    Company: ("name", ["name", "description", "strategic_issues", "projects", "people"]),
    Person: ("name", ["name", "role", "company", "responsibilities", "concerns", "current_priorities", "performance_notes"]),
    StrategicIssue: ("title", ["title", "company", "owner", "status", "current_thinking", "risks"]),
    Project: ("title", ["title", "company", "objective", "status", "owner", "milestones", "risks", "next_steps"]),
    Decision: ("title", ["title", "company", "context", "options_considered", "final_decision", "reasoning", "expected_outcome"]),
    Meeting: ("title", ["title", "company", "attendees", "summary", "decisions_made", "action_items", "open_questions"]),
    SOP: ("title", ["title", "company", "purpose", "owner", "current_process", "escalation_rules"]),
    Document: ("title", ["title", "type", "source", "summary", "linked_objects"]),
    Metric: ("title", ["title", "company", "value", "related_strategic_issue", "trend", "notes"]),
}

RESULT_TYPES = {
    Company: "company", Person: "person", StrategicIssue: "strategic_issue",
    Project: "project", Decision: "decision", Meeting: "meeting", SOP: "sop",
    Document: "document", Metric: "metric",
}


def _rank_for_context(items: list[Any], fields: list[str], query: str) -> list[Any]:
    scored = [(_match_score(item, fields, query), item.id or 0, item) for item in items]
    relevant = [entry for entry in scored if entry[0] > 0]
    pool = relevant or scored
    return [entry[2] for entry in sorted(pool, key=lambda entry: (entry[0], entry[1]), reverse=True)]


def _result_summary(item: Any) -> str:
    if isinstance(item, Person):
        role = item.role or "Person"
        return f"{role} at {item.company}" if item.company else role
    for field in ("final_decision", "summary", "current_thinking", "objective", "description", "role", "purpose", "value", "notes"):
        value = getattr(item, field, None)
        if value:
            return _stringify_value(value)
    return f"{item.__class__.__name__.replace('StrategicIssue', 'Strategic issue')} memory"


COMPANY_ALIASES = {
    "pro engineering consulting": "PEC",
    "pro engineering": "PEC",
    "pec": "PEC",
    "ryse wellness": "RYSE Wellness",
    "ryse": "RYSE Wellness",
    "everpole": "EverPole",
    "myndlog": "MyndLog",
}


def _company_mentions(text: str, alias: str) -> list[re.Match[str]]:
    return list(re.finditer(rf"\b{re.escape(alias)}\b", text, flags=re.IGNORECASE))


def _mention_is_negated(text: str, match: re.Match[str]) -> bool:
    prefix = text[max(0, match.start() - 20):match.start()]
    return bool(re.search(r"\bnot(?:\s+(?:with|at|part of))?\s*$", prefix, flags=re.IGNORECASE))


def _detect_positive_company(text: str) -> str:
    for alias in sorted(COMPANY_ALIASES, key=len, reverse=True):
        for match in _company_mentions(text, alias):
            if not _mention_is_negated(text, match):
                return COMPANY_ALIASES[alias]
    return ""


def _normalize_company(company: str) -> str:
    return COMPANY_ALIASES.get(company.strip().lower(), company.strip())


def _company_is_explicitly_negated(text: str, company: str) -> bool:
    normalized = _normalize_company(company)
    aliases = [alias for alias, canonical in COMPANY_ALIASES.items() if canonical == normalized]
    return any(_mention_is_negated(text, match) for alias in aliases for match in _company_mentions(text, alias))


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

    if detected_name:
        updates.append({
            "type": "person",
            "name": detected_name,
            "company": detected_company,
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

    if not updates:
        updates.append({"type": "note", "details": "No structured update detected."})

    return updates


def _memory_context(db: Session) -> str:
    companies = ", ".join(company.name for company in db.query(Company).all()) or "None"
    people = ", ".join(
        f"{person.name} ({person.role or 'no role'}; {person.company or 'no company'})"
        for person in db.query(Person).all()
    ) or "None"
    issues = ", ".join(issue.title for issue in db.query(StrategicIssue).all()) or "None"
    return f"Companies: {companies}\nPeople: {people}\nStrategic issues: {issues}"


def _classify_capture_text(db: Session, text: str) -> tuple[list[dict[str, Any]], list[str], str]:
    analysis = analyze_capture(text, _memory_context(db))
    if analysis:
        return (
            [update.model_dump() for update in analysis.suggested_updates],
            analysis.follow_ups,
            "ai",
        )
    return _fallback_classify_capture_text(text), [], "local_fallback"


def _apply_generic_update(db: Session, update: dict[str, Any]) -> bool:
    model = {
        "project": Project,
        "meeting": Meeting,
        "sop": SOP,
        "document": Document,
        "metric": Metric,
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
    return True


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
        update_name = update.get("name") or detected_name
        proposed_company = _normalize_company(update.get("company") or "")
        if proposed_company and _company_is_explicitly_negated(text, proposed_company):
            proposed_company = ""
        update_company = explicit_company or proposed_company
        if update_type == "person" and update_name:
            _upsert_person(
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
                db.flush()
        elif update_type == "strategic_issue":
            title = update.get("title") or ("Improve PM quality" if "pm quality" in lowered else "")
            if title:
                issue = _upsert_strategic_issue(db, title, company=update_company, owner=update.get("owner") or update_name)
                issue.current_thinking = update.get("current_thinking") or issue.current_thinking
                issue.status = update.get("status") or issue.status
                db.flush()
        elif update_type == "company" and update_name:
            company = _upsert_company(db, update_name)
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
        else:
            _apply_generic_update(db, update)

    db.add(CaptureRecord(
        raw_text=text,
        classification_source=classification_source,
        saved_count=len(approved_updates),
    ))
    db.commit()


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
def briefing(db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    today = date.today().isoformat()
    issues = db.query(StrategicIssue).filter(StrategicIssue.status == "active").order_by(StrategicIssue.id.desc()).all()
    people = db.query(Person).order_by(Person.id.desc()).all()
    decisions = db.query(Decision).order_by(Decision.id.desc()).all()
    meetings = db.query(Meeting).filter(Meeting.date == today).order_by(Meeting.id.desc()).all()
    projects = db.query(Project).order_by(Project.id.desc()).all()
    risks = [risk for item in [*issues, *projects] for risk in (item.risks or [])]
    waiting_on = [action for meeting in db.query(Meeting).all() for action in (meeting.action_items or [])]
    priorities = [project.title for project in projects if project.status == "active"] + [issue.title for issue in issues]
    focus = priorities[0] if priorities else (decisions[0].title if decisions else "Capture the most important current context")
    return {
        "top_priorities": priorities[:3],
        "strategic_issues": [issue.title for issue in issues[:3]],
        "meetings_today": [meeting.title for meeting in meetings],
        "open_decisions": [decision.title for decision in decisions if not decision.review_date or decision.review_date >= today][:3],
        "people_needing_attention": [person.name for person in people if person.concerns][:3],
        "waiting_on_items": waiting_on[:5],
        "risks": risks[:5],
        "recommended_focus": f"Focus first on {focus}."
    }


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
    suggested_updates, follow_ups, classification_source = _classify_capture_text(db, payload.text)
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
    try:
        instance = model(**payload.attributes)
        db.add(instance)
        db.commit()
        db.refresh(instance)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An object with these unique values already exists") from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail="Object could not be created") from error
    return {"message": f"{object_type} created", "object": _serialize_model(instance)}


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
    issues = _rank_for_context(db.query(StrategicIssue).all(), SEARCH_CONFIG[StrategicIssue][1], meeting_title)
    decisions = _rank_for_context(db.query(Decision).all(), SEARCH_CONFIG[Decision][1], meeting_title)
    people = _rank_for_context(db.query(Person).all(), SEARCH_CONFIG[Person][1], meeting_title)
    meetings = _rank_for_context(db.query(Meeting).all(), SEARCH_CONFIG[Meeting][1], meeting_title)[:5]
    metrics = _rank_for_context(db.query(Metric).all(), SEARCH_CONFIG[Metric][1], meeting_title)
    projects = _rank_for_context(db.query(Project).all(), SEARCH_CONFIG[Project][1], meeting_title)
    action_items = [item for meeting in meetings for item in (meeting.action_items or [])]
    risks = [risk for item in [*issues, *projects] for risk in (item.risks or [])]
    agenda = [
        f"Review current context for {meeting_title}",
        f"Discuss open decisions: {', '.join(decision.title for decision in decisions[:2]) if decisions else 'No open decisions'}",
        f"Validate strategic issues: {', '.join(issue.title for issue in issues[:2]) if issues else 'No active strategic issues'}",
        f"Review active projects: {', '.join(project.title for project in projects[:2]) if projects else 'No active projects'}",
        "Confirm risks, action items, and follow-up owners",
    ]
    return {
        "meeting": meeting_title,
        "agenda": agenda,
        "related_people": [person.name for person in people[:3]],
        "related_strategic_issues": [issue.title for issue in issues[:3]],
        "related_projects": [project.title for project in projects[:3]],
        "open_decisions": [decision.title for decision in decisions[:3]],
        "recent_meeting_context": [meeting.summary for meeting in meetings if meeting.summary][:3],
        "action_items": action_items[:5],
        "metrics": [f"{metric.title}: {metric.value} ({metric.trend})" for metric in metrics[:5]],
        "risks": risks[:5],
    }


@app.post("/search")
def search(payload: SearchRequest, db: Session = Depends(get_db), _user: str = Depends(require_auth)):
    ranked_results = []
    for model, (title_field, fields) in SEARCH_CONFIG.items():
        for item in db.query(model).all():
            score = _match_score(item, fields, payload.query)
            if score:
                score += _search_intent_boost(model, payload.query)
                ranked_results.append((score, item.id or 0, {
                    "type": RESULT_TYPES[model],
                    "title": getattr(item, title_field),
                    "summary": _result_summary(item),
                }))

    ranked_results.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    if not ranked_results:
        return {"query": payload.query, "answer": "No matching executive memory found.", "results": []}
    # Keep close supporting matches while dropping weak records that happen to
    # share one generic word with the question.
    cutoff = max(1, ranked_results[0][0] - 6)
    results = [entry[2] for entry in ranked_results if entry[0] >= cutoff][:10]
    return {"query": payload.query, "answer": results[0]["summary"], "results": results}
