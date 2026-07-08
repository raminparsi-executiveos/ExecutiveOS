import re
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import Company, Decision, Document, Meeting, Metric, Person, Project, SOP, StrategicIssue
from .schemas import (
    CaptureClassificationRequest,
    CaptureConfirmationRequest,
    CaptureRequest,
    CreateObjectRequest,
    MeetingPrepRequest,
    SearchRequest,
)
from .seed import seed_data

Base.metadata.create_all(bind=engine)

app = FastAPI(title="ExecutiveOS API")

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
    haystack = " ".join(_stringify_value(getattr(record, field, "")) for field in fields).lower()
    if not query:
        return False
    if query.lower() in haystack:
        return True

    normalized_query = query.lower()
    tokens = set(re.findall(r"[a-z0-9]+", normalized_query))
    synonyms = {
        "promote": ["promotion", "promoted", "raise", "increase", "pay"],
        "promoted": ["promotion", "promoted", "raise", "increase", "pay"],
        "why": ["reason", "context", "decision"],
        "what": ["title", "summary", "context"],
        "happening": ["status", "active", "current", "issue", "project"],
    }
    for token in tokens:
        if token in haystack:
            return True
        for synonym in synonyms.get(token, []):
            if synonym in haystack:
                return True
    return False


def _upsert_company(db: Session, name: str) -> Company:
    company = db.query(Company).filter(Company.name.ilike(name)).first()
    if not company:
        company = Company(name=name)
    db.add(company)
    db.commit()
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
    db.commit()
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
    db.commit()
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
    decision.date = decision.date or "2026-07-07"
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def _classify_capture_text(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    updates: list[dict[str, Any]] = []
    detected_name = ""
    for candidate in ["Julio", "Mina"]:
        if candidate.lower() in lowered:
            detected_name = candidate
            break

    detected_company = ""
    for candidate in ["PEC", "RYSE Wellness", "EverPole", "MyndLog"]:
        if candidate.lower() in lowered:
            detected_company = candidate
            break

    if detected_name:
        updates.append({
            "type": "person",
            "name": detected_name,
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


def _apply_approved_updates(db: Session, text: str, approved_updates: list[dict[str, Any]]) -> None:
    lowered = text.lower()
    detected_name = ""
    for candidate in ["Julio", "Mina"]:
        if candidate.lower() in lowered:
            detected_name = candidate
            break

    detected_company = ""
    for candidate in ["PEC", "RYSE Wellness", "EverPole", "MyndLog"]:
        if candidate.lower() in lowered:
            detected_company = candidate
            break

    for update in approved_updates:
        update_type = update.get("type")
        if update_type == "person" and detected_name:
            _upsert_person(db, name=detected_name, company=detected_company, responsibilities=["PM quality"] if "pm quality" in lowered else [], current_priorities=["Improve PM quality"] if "pm quality" in lowered else [])
        elif update_type == "strategic_issue":
            _upsert_strategic_issue(db, update.get("title") or "Improve PM quality", company=detected_company or "PEC", owner=detected_name or "CEO")
        elif update_type == "company" and detected_company:
            _upsert_company(db, detected_company)
        elif update_type == "decision" and detected_name:
            _upsert_decision(db, update.get("title") or f"{detected_name} promotion and pay increase", company=detected_company or "PEC", context=text, final_decision="Compensation adjustment and expanded responsibilities.", reasoning="Recognize growth and align incentives with expanded ownership.")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    db = next(get_db())
    seed_data(db)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/briefing")
def briefing(db: Session = Depends(get_db)):
    issues = db.query(StrategicIssue).all()
    people = db.query(Person).all()
    decisions = db.query(Decision).all()
    return {
        "top_priorities": [issue.title for issue in issues[:3]] or ["Increase PEC sales", "Improve PM quality", "Reduce RYSE overtime"],
        "strategic_issues": [issue.title for issue in issues[:3]] or ["Buyer diligence", "Admissions improvement"],
        "meetings_today": [],
        "open_decisions": [decision.title for decision in decisions[:3]] or ["Julio pay review", "EverPole distributor strategy"],
        "people_needing_attention": [person.name for person in people[:3]] or ["Julio", "RYSE admissions lead"],
        "waiting_on_items": ["Sales pipeline review"],
        "risks": ["Staffing capacity"],
        "recommended_focus": "Focus on PM quality and sales conversion."
    }


@app.post("/capture")
def capture(payload: CaptureRequest, db: Session = Depends(get_db)):
    suggested_updates = _classify_capture_text(payload.text)
    if payload.confirm:
        _apply_approved_updates(db, payload.text, suggested_updates)
    return {
        "message": "Capture accepted",
        "suggested_updates": suggested_updates,
        "confirm": payload.confirm,
    }


@app.post("/capture/classify")
def classify_capture(payload: CaptureClassificationRequest):
    return {
        "message": "Classification complete",
        "suggested_updates": _classify_capture_text(payload.text),
        "confirm": payload.confirm,
    }


@app.post("/capture/confirm")
def confirm_capture(payload: CaptureConfirmationRequest, db: Session = Depends(get_db)):
    _apply_approved_updates(db, payload.text, payload.approved_updates)
    return {
        "message": "Approved updates saved",
        "approved_updates": payload.approved_updates,
    }


@app.get("/objects/{object_type}")
def list_objects(object_type: str, db: Session = Depends(get_db)):
    model = _model_for_object_type(object_type)
    items = db.query(model).all()
    return {"items": [_serialize_model(item) for item in items]}


@app.post("/objects/{object_type}")
def create_object(object_type: str, payload: CreateObjectRequest, db: Session = Depends(get_db)):
    model = _model_for_object_type(object_type)
    instance = model(**payload.attributes)
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return {"message": f"{object_type} created", "object": _serialize_model(instance)}


@app.post("/meeting-prep")
def meeting_prep(payload: MeetingPrepRequest, db: Session = Depends(get_db)):
    meeting_title = payload.meeting or "Executive meeting"
    issues = db.query(StrategicIssue).all()
    decisions = db.query(Decision).all()
    people = db.query(Person).all()
    agenda = [
        f"Review current context for {meeting_title}",
        f"Discuss open decisions: {', '.join(decision.title for decision in decisions[:2]) if decisions else 'No open decisions'}",
        f"Validate strategic issues: {', '.join(issue.title for issue in issues[:2]) if issues else 'No active strategic issues'}",
        "Confirm risks, action items, and follow-up owners",
    ]
    return {
        "meeting": meeting_title,
        "agenda": agenda,
        "related_people": [person.name for person in people[:3]],
        "related_strategic_issues": [issue.title for issue in issues[:3]],
        "open_decisions": [decision.title for decision in decisions[:3]],
    }


@app.post("/search")
def search(payload: SearchRequest, db: Session = Depends(get_db)):
    query = payload.query.lower()
    results = []

    for decision in db.query(Decision).all():
        if _matches_query(decision, ["title", "context", "final_decision"], query):
            results.append({"type": "decision", "title": decision.title, "summary": decision.final_decision or decision.context})

    for issue in db.query(StrategicIssue).all():
        if _matches_query(issue, ["title", "current_thinking", "owner"], query):
            results.append({"type": "strategic_issue", "title": issue.title, "summary": issue.current_thinking or "Active strategic issue"})

    if not results:
        for person in db.query(Person).all():
            if _matches_query(person, ["name", "role", "company", "responsibilities", "current_priorities"], query):
                results.append({"type": "person", "title": person.name, "summary": person.role or "Executive context"})

    return {"query": payload.query, "results": results[:5]}
