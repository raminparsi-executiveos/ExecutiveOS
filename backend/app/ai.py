import logging
import os
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
CAPTURE_PROMPT_VERSION = "capture-fidelity-v1"


def _openai_timeout_seconds() -> float:
    raw_timeout = os.getenv("OPENAI_TIMEOUT_SECONDS", "60")
    try:
        timeout = float(raw_timeout)
    except ValueError:
        logger.warning("Invalid OPENAI_TIMEOUT_SECONDS value %r; using 60 seconds", raw_timeout)
        return 60.0
    return max(10.0, timeout)


def _openai_image_detail() -> str:
    detail = os.getenv("OPENAI_IMAGE_DETAIL", "high").strip().lower()
    if detail not in {"low", "high", "original", "auto"}:
        logger.warning("Invalid OPENAI_IMAGE_DETAIL value %r; using high", detail)
        return "high"
    return detail


class SuggestedUpdate(BaseModel):
    type: Literal["person", "company", "strategic_issue", "project", "decision", "meeting", "sop", "document", "metric", "task"]
    name: str = ""
    title: str = ""
    company: str = ""
    description: str = ""
    details: str = ""
    role: str = ""
    owner: str = ""
    status: str = ""
    current_thinking: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    current_priorities: list[str] = Field(default_factory=list)
    performance_notes: list[str] = Field(default_factory=list)
    objective: str = ""
    milestones: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    context: str = ""
    options_considered: list[str] = Field(default_factory=list)
    final_decision: str = ""
    reasoning: str = ""
    expected_outcome: str = ""
    review_date: str = ""
    summary: str = ""
    attendees: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    purpose: str = ""
    current_process: str = ""
    escalation_rules: list[str] = Field(default_factory=list)
    source: str = ""
    value: str = ""
    date: str = ""
    trend: str = ""
    notes: str = ""
    related_strategic_issue: str = ""
    due_date: str = ""
    priority: str = ""
    source_type: str = ""
    source_id: str = ""
    source_summary: str = ""
    next_action: str = ""
    blocked_by: str = ""
    tags: list[str] = Field(default_factory=list)
    memory_classification: str = "confirmed_fact"
    verification_state: str = "ai_extracted_pending_review"
    operation: Literal["create", "update", "merge", "resolve", "supersede", "no_change"] = "create"
    matched_record_id: int | None = None
    match_confidence: str = ""
    evidence_excerpt: str = ""
    field_operations: dict[str, str] = Field(default_factory=dict)
    missing_material_fields: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    explanation: str = ""
    expected_deliverable: str = ""
    definition_of_done: str = ""
    why_it_matters: str = ""
    delegated_by: str = ""
    assigned_to: str = ""
    waiting_on: str = ""
    stakeholders: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    follow_up_date: str = ""
    recurrence: str = ""
    task_type: str = ""
    confidence: str = ""
    interpretation_notes: str = ""
    source_excerpt: str = ""
    parent_task_id: int | None = None
    linked_project_ids: list[int] = Field(default_factory=list)
    linked_decision_ids: list[int] = Field(default_factory=list)
    linked_people: list[str] = Field(default_factory=list)


class CaptureStatement(BaseModel):
    source_excerpt: str = ""
    statement_type: Literal[
        "fact",
        "observation",
        "concern",
        "decision",
        "directive",
        "commitment",
        "proposal",
        "recommendation",
        "assumption",
        "question",
        "unverified_information",
    ] = "observation"
    company: str = ""
    people: list[dict[str, str]] = Field(default_factory=list)
    temporal_meaning: str = ""
    confidence: str = ""
    changes_existing_memory: bool = False


class CaptureAnalysis(BaseModel):
    suggested_updates: list[SuggestedUpdate]
    follow_ups: list[str] = Field(default_factory=list)
    capture_summary: str = ""
    capture_purpose: str = ""
    executive_intent: str = ""
    primary_company: str = ""
    primary_subject: str = ""
    primary_topic: str = ""
    urgency: str = ""
    tone: str = ""
    temporal_context: str = ""
    confidence: str = ""
    people_roles: list[dict[str, str]] = Field(default_factory=list)
    statements: list[CaptureStatement] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    source_evidence: list[dict[str, str]] = Field(default_factory=list)


SYSTEM_PROMPT = """You organize executive memory from natural-language capture.
Extract only facts supported by the capture. Propose atomic updates using only these
types: person, company, strategic_issue, project, decision, meeting, sop, document,
metric, task. Create task suggestions for commitments, owners, blockers, and action
items. Preserve decision context, reasoning, tradeoffs, expected outcomes, and review
dates when present. Use ISO dates when the date is explicit. Do not create raw notes.
Put useful missing-context questions in follow_ups. Never invent facts.
First preserve the user's intent in the capture interpretation fields. Separate facts,
observations, concerns, decisions, directives, commitments, proposals, recommendations,
assumptions, questions, and unverified information. Never silently convert a proposal,
question, or recommendation into a confirmed decision.
When both typed text and screenshots are supplied, analyze them together as one capture:
use the text as user-provided context for the screenshots, and use screenshots as evidence
for the typed request. Do not ignore either source.
For every suggested update, set operation to create, update, merge, resolve, supersede,
or no_change. Include matched_record_id when Known memory provides a stable ID. Preserve
a short evidence_excerpt for every material update and use field_operations to describe
append, replace, remove, clear, resolve, supersede, or no_change behavior for fields.
Do not replace complete lists when the capture only adds one item.
For tasks, qualify ownership carefully: owner is accountable, assigned_to performs work,
delegated_by requested it, and waiting_on is the external person or party blocking it.
Populate expected_deliverable, definition_of_done, next_action, dependencies,
follow_up_date, recurrence or task_type, why_it_matters, source_excerpt, confidence,
and missing_material_fields when supported. Do not use the whole capture as task
description unless the entire capture concerns only that task.
Classify each suggestion as one of confirmed_fact, decision, commitment, proposal,
concern, assumption, recommendation, or unverified_information. Set verification_state
to ai_extracted_pending_review unless the capture explicitly says the user confirmed it.
Treat explicit corrections as authoritative. In phrases such as "X, not Y", never
assign Y. A person update that changes employment must include the corrected company.
Treat similar names as distinct identities unless the user explicitly says they are
aliases. Never expand a short name (for example, Juli) into another name (Juliana or
Julio). When the user distinguishes two people, create/update the exact stated name.
For employment transitions, preserve the former company, new company, timing, and any
continuing part-time or advisory relationship in the person's performance_notes. Set
company to the person's new primary company only when the capture makes that clear.
Use details as a concise human-readable summary, but also populate the durable typed
fields because details may be used only as supporting context.
"""


def analyze_capture(text: str, memory_context: str, image_data: str | list[str] = "") -> CaptureAnalysis | None:
    """Return structured AI extraction, or None when AI is not configured/available."""
    if not os.getenv("OPENAI_API_KEY"):
        return None

    try:
        from openai import OpenAI

        capture_prompt = text.strip() or "Extract the executive-memory facts visible in this screenshot."
        user_content = [{
            "type": "input_text",
            "text": f"Known memory:\n{memory_context}\n\nTyped capture context:\n{capture_prompt}\n\nIf screenshots are attached, analyze the typed context and screenshots together.",
        }]
        image_inputs = image_data if isinstance(image_data, list) else ([image_data] if image_data else [])
        image_detail = _openai_image_detail()
        for image in image_inputs:
            user_content.append({"type": "input_image", "image_url": image, "detail": image_detail})

        model = os.getenv("OPENAI_MODEL", "gpt-5.6")
        response = OpenAI(timeout=_openai_timeout_seconds(), max_retries=2).responses.parse(
            model=model,
            input=[
                {"role": "system", "content": f"{SYSTEM_PROMPT}\nPrompt version: {CAPTURE_PROMPT_VERSION}"},
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            text_format=CaptureAnalysis,
        )
        return response.output_parsed
    except Exception as error:
        # Capture must remain usable if the provider is unavailable. The exception is
        # logged server-side without exposing credentials or provider details to users.
        logger.warning(
            "AI capture classification failed; using local fallback (model=%s, images=%s, error_type=%s, error=%s)",
            os.getenv("OPENAI_MODEL", "gpt-5.6"),
            len(image_data) if isinstance(image_data, list) else int(bool(image_data)),
            type(error).__name__,
            str(error)[:500],
        )
        return None
