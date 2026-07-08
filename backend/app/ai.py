import logging
import os

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SuggestedUpdate(BaseModel):
    type: str
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


class CaptureAnalysis(BaseModel):
    suggested_updates: list[SuggestedUpdate]
    follow_ups: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = """You organize executive memory from natural-language capture.
Extract only facts supported by the capture. Propose atomic updates using only these
types: person, company, strategic_issue, project, decision, meeting, sop, document,
metric. Preserve decision context, reasoning, tradeoffs, expected outcomes, and review
dates when present. Use ISO dates when the date is explicit. Do not create tasks or raw
notes. Put useful missing-context questions in follow_ups. Never invent facts.
"""


def analyze_capture(text: str, memory_context: str) -> CaptureAnalysis | None:
    """Return structured AI extraction, or None when AI is not configured/available."""
    if not os.getenv("OPENAI_API_KEY"):
        return None

    try:
        from openai import OpenAI

        response = OpenAI(timeout=20.0, max_retries=1).responses.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Known memory:\n{memory_context}\n\nCapture:\n{text}",
                },
            ],
            text_format=CaptureAnalysis,
        )
        return response.output_parsed
    except Exception as error:
        # Capture must remain usable if the provider is unavailable. The exception is
        # logged server-side without exposing credentials or provider details to users.
        logger.warning(
            "AI capture classification failed; using local fallback (%s)",
            type(error).__name__,
        )
        return None
