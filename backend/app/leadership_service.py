import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    CaptureRecord,
    Clarification,
    Decision,
    LeadershipReview,
    Meeting,
    Metric,
    Project,
    ReviewAlert,
    SOP,
    StrategicIssue,
    Task,
)
from .tasks import OPEN_TASK_STATUSES, upsert_task_from_update


LEADERSHIP_PROMPT_VERSION = "leadership-advisor-v1"
LEADERSHIP_MODEL = "deterministic-leadership-framework-v1"
SEVERITY_SCORE = {"critical": 100, "high": 80, "medium": 55, "low": 30}


def leadership_timezone_name() -> str:
    return os.getenv("LEADERSHIP_REVIEW_TIMEZONE", "America/Los_Angeles")


def leadership_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(leadership_timezone_name())
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Los_Angeles")


def _aware(timestamp: datetime | None) -> datetime | None:
    if timestamp and timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp


def _serialize_review(review: LeadershipReview) -> dict[str, Any]:
    return {
        "id": review.id,
        "review_type": review.review_type,
        "company": review.company or "",
        "capture_id": review.capture_id,
        "generated_at": review.generated_at.isoformat() if review.generated_at else "",
        "period_start": review.period_start.isoformat() if review.period_start else "",
        "period_end": review.period_end.isoformat() if review.period_end else "",
        "executive_summary": review.executive_summary,
        "leadership_signals": review.findings or [],
        "findings": review.findings or [],
        "strategic_questions": review.strategic_questions or [],
        "proposed_followups": review.proposed_followups or [],
        "missing_context": review.missing_context or [],
        "confidence": float(review.confidence or 0),
        "model": review.model,
        "prompt_version": review.prompt_version,
        "status": review.status,
        "source_record_ids": review.source_record_ids or [],
    }


def serialize_leadership_review(review: LeadershipReview) -> dict[str, Any]:
    return _serialize_review(review)


def _evidence(record_type: str, item: Any, label: str = "") -> dict[str, Any]:
    return {
        "object_type": record_type,
        "object_id": str(getattr(item, "id", "") or ""),
        "label": label or getattr(item, "title", None) or getattr(item, "name", None) or str(item),
        "company": getattr(item, "company", "") or "",
    }


def _finding(
    *,
    category: str,
    severity: str,
    finding: str,
    evidence: list[dict[str, Any]],
    principles: list[str],
    recommended_action: str,
    suggested_owner: str = "",
    suggested_due_date: str | None = None,
    success_measure: str = "",
    facts: list[str] | None = None,
    inferences: list[str] | None = None,
    missing_context: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "finding": finding,
        "evidence": evidence,
        "leadership_principles": principles,
        "recommended_action": recommended_action,
        "suggested_owner": suggested_owner,
        "suggested_due_date": suggested_due_date,
        "success_measure": success_measure,
        "supported_facts": facts or [],
        "inferences": inferences or [],
        "missing_context": missing_context or [],
        "proposal": _proposal_for(category, finding, recommended_action, suggested_owner, suggested_due_date),
    }


def _proposal_for(category: str, finding: str, action: str, owner: str, due_date: str | None) -> dict[str, Any]:
    if category in {"execution", "accountability", "measurement", "process", "risk"}:
        return {
            "type": "task",
            "title": action[:180],
            "owner": owner,
            "due_date": due_date or "",
            "priority": "high" if "urgent" in finding.lower() else "medium",
            "next_action": action,
            "source_type": "leadership_review",
        }
    if category in {"strategy", "opportunity"}:
        return {
            "type": "strategic_issue",
            "title": finding[:180],
            "current_thinking": action,
            "owner": owner,
            "status": "active",
        }
    return {
        "type": "clarification",
        "question": action,
        "why_it_matters": finding,
    }


def _filter_company(items: list[Any], company: str) -> list[Any]:
    if not company:
        return items
    return [item for item in items if str(getattr(item, "company", "") or "").lower() == company.lower()]


def _memory_snapshot(db: Session, *, company: str = "") -> dict[str, list[Any]]:
    return {
        "tasks": _filter_company(db.query(Task).order_by(Task.id.desc()).limit(200).all(), company),
        "projects": _filter_company(db.query(Project).order_by(Project.id.desc()).limit(100).all(), company),
        "issues": _filter_company(db.query(StrategicIssue).order_by(StrategicIssue.id.desc()).limit(100).all(), company),
        "decisions": _filter_company(db.query(Decision).order_by(Decision.id.desc()).limit(100).all(), company),
        "meetings": _filter_company(db.query(Meeting).order_by(Meeting.id.desc()).limit(100).all(), company),
        "metrics": _filter_company(db.query(Metric).order_by(Metric.id.desc()).limit(100).all(), company),
        "sops": _filter_company(db.query(SOP).order_by(SOP.id.desc()).limit(100).all(), company),
        "clarifications": _filter_company(db.query(Clarification).filter(Clarification.status == "open").order_by(Clarification.score.desc()).limit(100).all(), company),
        "alerts": _filter_company(db.query(ReviewAlert).filter(ReviewAlert.status == "open").order_by(ReviewAlert.id.desc()).limit(100).all(), company),
    }


def _recently_changed(item: Any, since: datetime | None) -> bool:
    if not since:
        return True
    changed_at = _aware(getattr(item, "updated_at", None) or getattr(item, "created_at", None))
    return bool(changed_at and changed_at >= since)


def _candidate_findings(snapshot: dict[str, list[Any]], *, since: datetime | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    tasks = snapshot["tasks"]
    projects = snapshot["projects"]
    issues = snapshot["issues"]
    decisions = snapshot["decisions"]
    metrics = snapshot["metrics"]
    clarifications = snapshot["clarifications"]

    open_tasks = [task for task in tasks if task.status in OPEN_TASK_STATUSES]
    blocked = [task for task in open_tasks if task.status == "blocked" or task.blocked_by]
    missing_owner = [task for task in open_tasks if not task.owner]
    missing_due = [task for task in open_tasks if not task.due_date]
    if blocked:
        task = blocked[0]
        findings.append(_finding(
            category="execution",
            severity="high",
            finding=f"{len(blocked)} open commitment{'s are' if len(blocked) != 1 else ' is'} blocked or waiting on a dependency.",
            evidence=[_evidence("task", task)],
            principles=["high-output-management", "effective-executive"],
            recommended_action="Name the unblock owner and define the next measurable step for the blocked commitment.",
            suggested_owner=task.owner or "",
            success_measure="Blocked task has an unblock owner, next action, and review date.",
            facts=[f"{task.title} is {task.status}."],
            inferences=["A bottleneck may be limiting output."],
            missing_context=["Who can remove the blocker and by when?"] if not task.blocked_by else [],
        ))
    if missing_owner:
        task = missing_owner[0]
        findings.append(_finding(
            category="accountability",
            severity="high",
            finding=f"{len(missing_owner)} open commitment{'s lack' if len(missing_owner) != 1 else ' lacks'} a clear accountable owner.",
            evidence=[_evidence("task", task)],
            principles=["five-dysfunctions", "measure-what-matters"],
            recommended_action="Assign a single accountable owner and expected outcome for the commitment.",
            success_measure="Every open commitment has one owner and an observable completion condition.",
            facts=[f"{task.title} has no owner."],
            missing_context=["Who is accountable for this outcome?"],
        ))
    if missing_due:
        task = missing_due[0]
        findings.append(_finding(
            category="measurement",
            severity="medium",
            finding=f"{len(missing_due)} open commitment{'s have' if len(missing_due) != 1 else ' has'} no due date or review cadence.",
            evidence=[_evidence("task", task)],
            principles=["measure-what-matters", "high-output-management"],
            recommended_action="Add due dates or review cadences to commitments that matter this week.",
            suggested_owner=task.owner or "",
            success_measure="Priority commitments have due dates or review dates.",
            facts=[f"{task.title} has no due date."],
            missing_context=["When should this be reviewed?"],
        ))

    risky_projects = [project for project in projects if project.status == "active" and (project.risks or not project.owner)]
    if risky_projects:
        project = risky_projects[0]
        findings.append(_finding(
            category="risk",
            severity="high" if project.risks else "medium",
            finding=f"Active project '{project.title}' needs stronger operating control.",
            evidence=[_evidence("project", project)],
            principles=["good-to-great", "high-output-management"],
            recommended_action="Confirm owner, current risk, next milestone, and review cadence for this active project.",
            suggested_owner=project.owner or "",
            success_measure="Project has owner, next milestone, risk owner, and review cadence.",
            facts=[f"Project status is {project.status}."] + ([f"Risks: {', '.join(project.risks[:3])}."] if project.risks else []),
            inferences=["The project may be relying on attention instead of a repeatable operating rhythm."],
            missing_context=[] if project.owner else ["Who owns this project?"],
        ))

    active_issues = [issue for issue in issues if issue.status == "active" and (issue.risks or not issue.owner)]
    if active_issues:
        issue = active_issues[0]
        findings.append(_finding(
            category="strategy",
            severity="high" if issue.risks else "medium",
            finding=f"Strategic issue '{issue.title}' needs a clearer owner, decision path, or measurable target.",
            evidence=[_evidence("strategic_issue", issue)],
            principles=["effective-executive", "good-to-great", "measure-what-matters"],
            recommended_action="Turn the strategic issue into an explicit decision, owner, and measurable outcome.",
            suggested_owner=issue.owner or "",
            success_measure="Issue has owner, target outcome, and next decision date.",
            facts=[f"Issue status is {issue.status}."],
            missing_context=[] if issue.owner else ["Who owns this strategic issue?"],
        ))

    review_overdue = [decision for decision in decisions if decision.review_date and decision.review_date < datetime.now(timezone.utc).date().isoformat()]
    if review_overdue:
        decision = review_overdue[0]
        findings.append(_finding(
            category="strategy",
            severity="medium",
            finding=f"Decision '{decision.title}' is past its review date.",
            evidence=[_evidence("decision", decision)],
            principles=["effective-executive", "measure-what-matters"],
            recommended_action="Review whether the expected outcome occurred and whether the decision should be reaffirmed, changed, or retired.",
            success_measure="Decision has reviewed outcome and updated next review date.",
            facts=[f"Review date was {decision.review_date}."],
            missing_context=["What evidence shows whether this decision worked?"],
        ))

    weak_metrics = [metric for metric in metrics if not metric.value or not metric.date or str(metric.trend or "").lower() in {"down", "declining", "negative"}]
    if weak_metrics:
        metric = weak_metrics[0]
        findings.append(_finding(
            category="measurement",
            severity="medium",
            finding=f"Metric '{metric.title}' needs clearer evidence or a response plan.",
            evidence=[_evidence("metric", metric)],
            principles=["measure-what-matters", "high-output-management"],
            recommended_action="Define the current value, owner, review cadence, and response threshold for this metric.",
            success_measure="Metric has current value, date, owner, and action threshold.",
            facts=[f"Metric value: {metric.value or 'missing'}."],
            missing_context=["What threshold should trigger action?"],
        ))

    if clarifications:
        clarification = clarifications[0]
        findings.append(_finding(
            category="opportunity",
            severity="medium",
            finding="Executive Inbox has unresolved clarification questions that could improve decision quality.",
            evidence=[_evidence("clarification", clarification, clarification.question)],
            principles=["effective-executive", "five-dysfunctions"],
            recommended_action="Answer the highest-value clarification before the next briefing cycle.",
            success_measure="Top clarification is answered, snoozed with a date, or intentionally marked unknown.",
            facts=[clarification.question],
        ))

    return [
        finding for finding in findings
        if not since or any(
            _recently_changed(item, since)
            for evidence in finding["evidence"]
            for collection in snapshot.values()
            for item in collection
            if str(getattr(item, "id", "")) == str(evidence.get("object_id"))
        ) or finding["severity"] in {"high", "critical"}
    ]


def _prioritize(findings: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda finding: (
            SEVERITY_SCORE.get(finding.get("severity", "low"), 0),
            len(finding.get("evidence") or []),
            finding.get("category", ""),
        ),
        reverse=True,
    )[:limit]


def _questions(findings: list[dict[str, Any]]) -> list[str]:
    questions = []
    for finding in findings:
        if finding.get("missing_context"):
            questions.append(str(finding["missing_context"][0]))
        elif finding.get("category") == "strategy":
            questions.append("What decision would most improve strategic clarity this week?")
        elif finding.get("category") == "execution":
            questions.append("Which bottleneck would most improve team output if removed?")
        else:
            questions.append("What measurable outcome would make this item clearly resolved?")
    return list(dict.fromkeys(questions))[:5]


def _summary(review_type: str, findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No material leadership risks were detected from the available memory. Capture more current context to improve recommendations."
    top = findings[0]
    prefix = "Capture leadership review" if review_type == "capture" else "Leadership review"
    return f"{prefix}: {top['finding']} Recommended focus: {top['recommended_action']}"


def _source_ids(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen = []
    for finding in findings:
        for evidence in finding.get("evidence", []):
            item = {"type": evidence.get("object_type", ""), "id": str(evidence.get("object_id", ""))}
            if item not in seen:
                seen.append(item)
    return seen


def _save_review(
    db: Session,
    *,
    review_type: str,
    idempotency_key: str,
    company: str = "",
    capture_id: int | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    findings: list[dict[str, Any]],
) -> LeadershipReview:
    existing = db.query(LeadershipReview).filter(LeadershipReview.idempotency_key == idempotency_key).first()
    if existing:
        return existing
    prioritized = _prioritize(findings)
    review = LeadershipReview(
        review_type=review_type,
        company=company,
        capture_id=capture_id,
        generated_at=datetime.now(timezone.utc),
        period_start=period_start,
        period_end=period_end,
        executive_summary=_summary(review_type, prioritized),
        findings=prioritized,
        strategic_questions=_questions(prioritized),
        proposed_followups=[finding["recommended_action"] for finding in prioritized],
        missing_context=list(dict.fromkeys(
            context for finding in prioritized for context in (finding.get("missing_context") or [])
        )),
        confidence="0.72" if prioritized else "0.35",
        model=LEADERSHIP_MODEL,
        prompt_version=LEADERSHIP_PROMPT_VERSION,
        status="new",
        idempotency_key=idempotency_key,
        source_record_ids=_source_ids(prioritized),
    )
    db.add(review)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return db.query(LeadershipReview).filter(LeadershipReview.idempotency_key == idempotency_key).one()
    db.refresh(review)
    return review


def generate_capture_leadership_review(db: Session, capture: CaptureRecord, *, company: str = "") -> LeadershipReview:
    snapshot = _memory_snapshot(db, company=company)
    capture_created_at = _aware(capture.created_at)
    since = capture_created_at - timedelta(minutes=5) if capture_created_at else None
    findings = _candidate_findings(snapshot, since=since)
    return _save_review(
        db,
        review_type="capture",
        idempotency_key=f"capture:{capture.id}:leadership:{LEADERSHIP_PROMPT_VERSION}",
        company=company,
        capture_id=capture.id,
        period_start=since,
        period_end=datetime.now(timezone.utc),
        findings=findings,
    )


def nightly_period(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    tz = leadership_timezone()
    local_now = (now or datetime.now(timezone.utc)).astimezone(tz)
    period_end_local = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    if local_now.time() >= time.min:
        period_end_local = datetime.combine(local_now.date(), time.min, tzinfo=tz)
    period_start_local = period_end_local - timedelta(days=1)
    key_date = period_end_local.date().isoformat()
    return period_start_local.astimezone(timezone.utc), period_end_local.astimezone(timezone.utc), key_date


def generate_nightly_leadership_review(
    db: Session,
    *,
    now: datetime | None = None,
    company: str = "",
    force: bool = False,
) -> LeadershipReview:
    period_start, period_end, key_date = nightly_period(now)
    idempotency_key = f"nightly:{company or 'all'}:{leadership_timezone_name()}:{key_date}:{LEADERSHIP_PROMPT_VERSION}"
    existing = db.query(LeadershipReview).filter(LeadershipReview.idempotency_key == idempotency_key).first()
    if existing and not force:
        return existing
    snapshot = _memory_snapshot(db, company=company)
    findings = _candidate_findings(snapshot, since=period_start)
    if existing and force:
        existing.status = "dismissed"
        db.add(existing)
        db.flush()
        idempotency_key = f"{idempotency_key}:retry:{int(datetime.now(timezone.utc).timestamp())}"
    return _save_review(
        db,
        review_type="nightly",
        idempotency_key=idempotency_key,
        company=company,
        period_start=period_start,
        period_end=period_end,
        findings=findings,
    )


def generate_manual_leadership_review(db: Session, *, company: str = "") -> LeadershipReview:
    snapshot = _memory_snapshot(db, company=company)
    findings = _candidate_findings(snapshot)
    return _save_review(
        db,
        review_type="manual",
        idempotency_key=f"manual:{company or 'all'}:{int(datetime.now(timezone.utc).timestamp())}",
        company=company,
        period_end=datetime.now(timezone.utc),
        findings=findings,
    )


def list_leadership_reviews(
    db: Session,
    *,
    review_type: str = "",
    status: str = "",
    company: str = "",
    limit: int = 20,
) -> list[LeadershipReview]:
    query = db.query(LeadershipReview)
    if review_type:
        query = query.filter(LeadershipReview.review_type == review_type)
    if status:
        query = query.filter(LeadershipReview.status == status)
    if company:
        query = query.filter(LeadershipReview.company == company)
    return query.order_by(LeadershipReview.generated_at.desc(), LeadershipReview.id.desc()).limit(limit).all()


def latest_leadership_review(db: Session, *, review_type: str = "", company: str = "") -> LeadershipReview | None:
    reviews = list_leadership_reviews(db, review_type=review_type, company=company, limit=1)
    return reviews[0] if reviews else None


def review_leadership_review(db: Session, review: LeadershipReview) -> LeadershipReview:
    review.status = "reviewed"
    db.add(review)
    db.flush()
    db.refresh(review)
    return review


def dismiss_leadership_review(db: Session, review: LeadershipReview) -> LeadershipReview:
    review.status = "dismissed"
    db.add(review)
    db.flush()
    db.refresh(review)
    return review


def proposal_payloads(review: LeadershipReview, indexes: list[int] | None = None) -> list[dict[str, Any]]:
    findings = review.findings or []
    if indexes:
        selected = [findings[index] for index in indexes if 0 <= index < len(findings)]
    else:
        selected = findings
    return [
        proposal for finding in selected
        if (proposal := finding.get("proposal"))
    ]


def apply_review_proposals(db: Session, review: LeadershipReview, indexes: list[int] | None = None) -> list[dict[str, Any]]:
    applied = []
    findings = review.findings or []
    selected = (
        [(index, findings[index]) for index in indexes if 0 <= index < len(findings)]
        if indexes else list(enumerate(findings))
    )
    for index, finding in selected:
        proposal = finding.get("proposal") or {}
        proposal_type = proposal.get("type")
        if proposal_type == "task":
            task = upsert_task_from_update(
                db,
                proposal,
                default_source_type="leadership_review",
                default_source_summary=review.executive_summary,
            )
            if task:
                applied.append({"type": "task", "id": task.id, "title": task.title})
        elif proposal_type == "strategic_issue":
            title = str(proposal.get("title") or finding.get("finding") or "").strip()
            if not title:
                continue
            issue = db.query(StrategicIssue).filter(StrategicIssue.title.ilike(title)).first() or StrategicIssue(title=title)
            issue.company = review.company or issue.company
            issue.owner = proposal.get("owner") or issue.owner
            issue.current_thinking = proposal.get("current_thinking") or issue.current_thinking
            issue.status = proposal.get("status") or issue.status or "active"
            db.add(issue)
            db.flush()
            db.refresh(issue)
            applied.append({"type": "strategic_issue", "id": issue.id, "title": issue.title})
        elif proposal_type == "clarification":
            question = str(proposal.get("question") or finding.get("recommended_action") or "").strip()
            if not question:
                continue
            dedupe_key = f"leadership_review:{review.id}:finding:{index}:clarification"
            clarification = db.query(Clarification).filter(Clarification.dedupe_key == dedupe_key).first()
            if not clarification:
                clarification = Clarification(status="open", dedupe_key=dedupe_key)
            clarification.clarification_type = "leadership_review"
            clarification.subtype = "advisor_follow_up"
            clarification.question = question
            clarification.why_it_matters = proposal.get("why_it_matters") or finding.get("finding") or ""
            clarification.target_record_type = "leadership_reviews"
            clarification.target_record_id = review.id
            clarification.company = review.company or ""
            clarification.evidence = finding.get("evidence") or []
            clarification.score = SEVERITY_SCORE.get(finding.get("severity", "medium"), 50)
            clarification.score_reasons = ["leadership advisor", finding.get("category", "follow up")]
            clarification.confidence = "advisor_proposed"
            clarification.uncertainty = "Created from a reviewed Leadership Advisor proposal."
            clarification.evidence_fingerprint = dedupe_key
            clarification.generation_rule_version = LEADERSHIP_PROMPT_VERSION
            db.add(clarification)
            db.flush()
            db.refresh(clarification)
            applied.append({"type": "clarification", "id": clarification.id, "title": clarification.question})
        else:
            raise HTTPException(status_code=422, detail=f"Unsupported proposal type: {proposal_type}")
    review.status = "reviewed"
    review.proposed_followups = (review.proposed_followups or []) + [{"applied": applied}]
    db.add(review)
    db.flush()
    return applied


def leadership_inbox_items(db: Session, *, status: str = "new", company: str = "", limit: int = 50) -> list[dict[str, Any]]:
    reviews = list_leadership_reviews(db, status=status, company=company, limit=limit)
    items = []
    for review in reviews:
        findings = review.findings or []
        top = findings[0] if findings else {}
        priority = top.get("severity", "medium")
        items.append({
            "id": f"leadership_review:{review.id}",
            "source_type": "leadership_review",
            "source_id": review.id,
            "company": review.company or "",
            "title": top.get("finding") or review.executive_summary or "Leadership review ready",
            "summary": review.executive_summary,
            "priority": priority,
            "score": SEVERITY_SCORE.get(priority, 50),
            "score_reasons": [top.get("category", "leadership advisor")] if top else ["leadership advisor"],
            "created_at": review.generated_at.isoformat() if review.generated_at else "",
            "freshness": review.status,
            "suggested_action": "Review leadership implications and approve any follow-up proposals.",
            "available_actions": ["review", "dismiss", "create_proposals"],
            "status": review.status,
            "owner": "",
            "due_date": "",
            "supporting_sources": top.get("evidence", []) if top else [],
            "strategic_questions": review.strategic_questions or [],
        })
    return sorted(items, key=lambda item: item["score"], reverse=True)
