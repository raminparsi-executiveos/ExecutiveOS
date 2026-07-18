import logging
import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .leadership_lens import leadership_lens_summary

logger = logging.getLogger(__name__)
CAPTURE_PROMPT_VERSION = "capture-fidelity-v1"
_LAST_CAPTURE_AI_FAILURE: dict[str, object] = {}


def _set_last_capture_ai_failure(**values: object) -> None:
    _LAST_CAPTURE_AI_FAILURE.clear()
    _LAST_CAPTURE_AI_FAILURE.update(values)


def last_capture_ai_failure() -> dict[str, object]:
    return dict(_LAST_CAPTURE_AI_FAILURE)


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


def _capture_model_candidates() -> list[str]:
    configured = [
        os.getenv("OPENAI_CAPTURE_MODEL", ""),
        os.getenv("OPENAI_MODEL", ""),
        os.getenv("OPENAI_CAPTURE_FALLBACK_MODEL", ""),
        "gpt-4.1-mini",
    ]
    candidates: list[str] = []
    for model in configured:
        model = str(model or "").strip()
        if model and model not in candidates:
            candidates.append(model)
    return candidates


def _strict_json_schema(schema: dict[str, object], _model: type[BaseModel]) -> None:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties.keys())
    schema["additionalProperties"] = False


SUGGESTED_UPDATE_TYPES = {
    "person",
    "company",
    "strategic_issue",
    "project",
    "decision",
    "meeting",
    "sop",
    "document",
    "metric",
    "task",
}
SUGGESTED_UPDATE_STRING_FIELDS = {
    "name",
    "title",
    "company",
    "description",
    "details",
    "role",
    "owner",
    "status",
    "current_thinking",
    "objective",
    "context",
    "final_decision",
    "reasoning",
    "expected_outcome",
    "review_date",
    "summary",
    "purpose",
    "current_process",
    "source",
    "value",
    "date",
    "trend",
    "notes",
    "related_strategic_issue",
    "due_date",
    "priority",
    "source_type",
    "source_id",
    "source_summary",
    "next_action",
    "blocked_by",
    "memory_classification",
    "verification_state",
    "operation",
    "match_confidence",
    "evidence_excerpt",
    "uncertainty",
    "explanation",
    "expected_deliverable",
    "definition_of_done",
    "why_it_matters",
    "delegated_by",
    "assigned_to",
    "waiting_on",
    "follow_up_date",
    "recurrence",
    "task_type",
    "confidence",
    "interpretation_notes",
    "source_excerpt",
    "next_best_action",
}
SUGGESTED_UPDATE_LIST_FIELDS = {
    "responsibilities",
    "strengths",
    "concerns",
    "current_priorities",
    "performance_notes",
    "milestones",
    "risks",
    "next_steps",
    "options_considered",
    "attendees",
    "decisions_made",
    "action_items",
    "open_questions",
    "escalation_rules",
    "tags",
    "missing_material_fields",
    "stakeholders",
    "dependencies",
    "linked_project_ids",
    "linked_decision_ids",
    "linked_people",
    "quality_notes",
}


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def _coerce_int_list(value: Any) -> list[int]:
    ids: list[int] = []
    for item in _as_list(value):
        parsed = _coerce_int(item)
        if parsed is not None and parsed not in ids:
            ids.append(parsed)
    return ids


def _coerce_text_list(value: Any) -> list[str]:
    output: list[str] = []
    for item in _as_list(value):
        if item in (None, "", []):
            continue
        if isinstance(item, dict):
            text = (
                item.get("question")
                or item.get("text")
                or item.get("title")
                or item.get("summary")
                or item.get("description")
                or item.get("ambiguity")
                or item.get("follow_up")
                or _compact_json_value(item)
            )
            why = item.get("why") or item.get("why_it_matters") or item.get("reason")
            if why and text and str(why) not in str(text):
                text = f"{text} ({why})"
        else:
            text = item
        text = str(text or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def _compact_json_value(value: Any) -> str:
    if value in (None, "", []):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _as_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    return value if isinstance(value, list) else [value]


def _infer_suggested_update_type(update: dict[str, Any]) -> str:
    update_type = str(update.get("type") or "").strip().lower()
    if update_type in SUGGESTED_UPDATE_TYPES:
        return update_type
    if update.get("attendees") or update.get("action_items") or update.get("open_questions"):
        return "meeting"
    if update.get("final_decision") or update.get("options_considered") or update.get("review_date"):
        return "decision"
    if update.get("value") or update.get("trend") or update.get("related_strategic_issue"):
        return "metric"
    if update.get("objective") or update.get("milestones"):
        return "project"
    if update.get("current_thinking") or update.get("risks"):
        return "strategic_issue"
    if update.get("role") or update.get("responsibilities") or (update.get("name") and not update.get("title")):
        return "person"
    return "task"


def _normalize_suggested_update_payload(raw_update: Any) -> dict[str, Any]:
    if not isinstance(raw_update, dict):
        return {"type": "task", "title": str(raw_update or ""), "details": str(raw_update or "")}
    update = dict(raw_update)
    nested_details = update.get("details")
    if isinstance(nested_details, dict):
        for key, value in nested_details.items():
            if key not in update or update.get(key) in (None, "", []):
                update[key] = value
        update["details"] = (
            nested_details.get("details")
            or nested_details.get("summary")
            or nested_details.get("description")
            or nested_details.get("title")
            or _compact_json_value(nested_details)
        )
    update["type"] = _infer_suggested_update_type(update)
    for field in SUGGESTED_UPDATE_STRING_FIELDS:
        if field in update and not isinstance(update[field], str) and update[field] is not None:
            update[field] = _compact_json_value(update[field])
    for field in SUGGESTED_UPDATE_LIST_FIELDS:
        if field in update:
            update[field] = _as_list(update[field])
    for field in ("matched_record_id", "parent_task_id", "quality_score"):
        if field in update:
            parsed = _coerce_int(update[field])
            update[field] = parsed if parsed is not None else (0 if field == "quality_score" else None)
    for field in ("linked_project_ids", "linked_decision_ids"):
        if field in update:
            update[field] = _coerce_int_list(update[field])
    if not update.get("title") and update["type"] != "person" and update.get("name"):
        update["title"] = update["name"]
    if not update.get("name") and update["type"] in {"person", "company"} and update.get("title"):
        update["name"] = update["title"]
    return update


def _normalize_capture_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    updates = normalized.get("suggested_updates") or normalized.get("updates") or normalized.get("items") or []
    normalized["suggested_updates"] = [
        _normalize_suggested_update_payload(update)
        for update in _as_list(updates)
    ]
    for field in ("follow_ups", "open_questions", "ambiguities"):
        if field in normalized:
            normalized[field] = _coerce_text_list(normalized[field])
    for field in ("people_roles", "statements", "source_evidence"):
        if field in normalized:
            normalized[field] = _as_list(normalized[field])
    return normalized


def _parse_capture_analysis_json(raw_text: str) -> "CaptureAnalysis":
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    payload = json.loads(text)
    if isinstance(payload, list):
        payload = {"suggested_updates": payload}
    if not isinstance(payload, dict):
        raise ValueError("Capture analysis JSON must be an object.")
    payload.setdefault("suggested_updates", [])
    return CaptureAnalysis.model_validate(_normalize_capture_analysis_payload(payload))


class SuggestedUpdate(BaseModel):
    model_config = ConfigDict(json_schema_extra=_strict_json_schema)

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
    quality_score: int = 0
    quality_notes: list[str] = Field(default_factory=list)
    next_best_action: str = ""


class CaptureStatement(BaseModel):
    model_config = ConfigDict(json_schema_extra=_strict_json_schema)

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
    model_config = ConfigDict(json_schema_extra=_strict_json_schema)

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
Return only valid JSON. The JSON must be an object compatible with the CaptureAnalysis
shape, with suggested_updates as an array. Use empty strings or empty arrays when a
field is unknown.
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
Enrich task proposals from a leader perspective using these management lenses:
The Effective Executive, High Output Management, Good to Great,
The Five Dysfunctions of a Team, and Measure What Matters. Use them to clarify
executive contribution, output cadence, focused priorities, team accountability,
and measurable results. Put this framing in why_it_matters, definition_of_done,
expected_deliverable, next_action, missing_material_fields, and interpretation_notes.
Do not claim the capture mentioned a book unless it did.
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
        _set_last_capture_ai_failure(
            reason="missing_openai_api_key",
            attempted_models=[],
            last_error_type="",
            last_error="OPENAI_API_KEY is not configured.",
        )
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

        client = OpenAI(timeout=_openai_timeout_seconds(), max_retries=2)
        last_error: Exception | None = None
        attempted_models: list[str] = []
        for model in _capture_model_candidates():
            attempted_models.append(model)
            try:
                response = client.responses.create(
                    model=model,
                    input=[
                        {"role": "system", "content": f"{SYSTEM_PROMPT}\n{leadership_lens_summary()}\nPrompt version: {CAPTURE_PROMPT_VERSION}"},
                        {
                            "role": "user",
                            "content": user_content,
                        },
                    ],
                    text={"format": {"type": "json_object"}},
                )
                parsed = _parse_capture_analysis_json(response.output_text)
                _set_last_capture_ai_failure(
                    reason="",
                    attempted_models=attempted_models,
                    last_successful_model=model,
                    last_error_type="",
                    last_error="",
                )
                return parsed
            except Exception as error:
                last_error = error
                logger.warning(
                    "AI capture classification attempt failed (model=%s, images=%s, error_type=%s, error=%s)",
                    model,
                    len(image_data) if isinstance(image_data, list) else int(bool(image_data)),
                    type(error).__name__,
                    str(error)[:500],
                )
        if last_error:
            raise last_error
        return None
    except Exception as error:
        # Capture must remain usable if the provider is unavailable. The exception is
        # logged server-side without exposing credentials or provider details to users.
        logger.warning(
            "AI capture classification failed across configured models; using local fallback (models=%s, images=%s, error_type=%s, error=%s)",
            ",".join(_capture_model_candidates()),
            len(image_data) if isinstance(image_data, list) else int(bool(image_data)),
            type(error).__name__,
            str(error)[:500],
        )
        _set_last_capture_ai_failure(
            reason="openai_call_failed",
            attempted_models=_capture_model_candidates(),
            last_error_type=type(error).__name__,
            last_error=str(error)[:500],
        )
        return None
