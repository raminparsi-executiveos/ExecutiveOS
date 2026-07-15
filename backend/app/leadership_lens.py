from __future__ import annotations

from typing import Any


LEADERSHIP_LENS_VERSION = "leadership-lens-v1"

LEADERSHIP_BOOK_LENSES = [
    {
        "key": "effective-executive",
        "title": "The Effective Executive",
        "author": "Peter Drucker",
        "lens": "define the executive contribution and the decision or outcome that matters",
    },
    {
        "key": "high-output-management",
        "title": "High Output Management",
        "author": "Andrew Grove",
        "lens": "turn work into an operating rhythm with measurable output and review cadence",
    },
    {
        "key": "good-to-great",
        "title": "Good to Great",
        "author": "Jim Collins",
        "lens": "name the brutal fact, ownership discipline, and focused priority",
    },
    {
        "key": "five-dysfunctions",
        "title": "The Five Dysfunctions of a Team",
        "author": "Patrick Lencioni",
        "lens": "make commitment and accountability explicit across the team",
    },
    {
        "key": "measure-what-matters",
        "title": "Measure What Matters",
        "author": "John Doerr",
        "lens": "connect the task to an observable result and success measure",
    },
]


def leadership_lens_summary() -> str:
    names = ", ".join(f"{book['title']} ({book['author']})" for book in LEADERSHIP_BOOK_LENSES)
    return f"Leadership lens ({LEADERSHIP_LENS_VERSION}): {names}."


def _append_unique(values: list[Any], additions: list[Any]) -> list[Any]:
    result = list(values or [])
    for value in additions:
        if value not in (None, "", []) and value not in result:
            result.append(value)
    return result


def _append_note(existing: str, note: str) -> str:
    existing = str(existing or "").strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}\n\n{note}"


def enrich_task_update_with_leadership_lens(update: dict[str, Any]) -> dict[str, Any]:
    if update.get("type") != "task":
        return update

    enriched = dict(update)
    title = str(enriched.get("title") or enriched.get("details") or "Task").strip()
    owner = str(enriched.get("owner") or "").strip()
    due_or_cadence = str(enriched.get("due_date") or enriched.get("follow_up_date") or enriched.get("recurrence") or "").strip()

    enriched["expected_deliverable"] = enriched.get("expected_deliverable") or f"Observable outcome for: {title}"
    enriched["definition_of_done"] = enriched.get("definition_of_done") or (
        "Done means the accountable owner confirms the outcome, supporting evidence, "
        "next review cadence, and any needed handoff."
    )
    enriched["why_it_matters"] = enriched.get("why_it_matters") or (
        "Leader lens: clarify the business result, owner, and operating cadence so this becomes managed work, not just activity."
    )
    enriched["next_action"] = enriched.get("next_action") or (
        "Name the accountable owner, expected result, and next review point."
    )
    enriched["interpretation_notes"] = _append_note(
        enriched.get("interpretation_notes") or "",
        (
            f"{leadership_lens_summary()} Applied lenses: executive contribution, output cadence, "
            "focused priority, team accountability, and measurable result."
        ),
    )
    enriched["tags"] = _append_unique(enriched.get("tags") or [], ["leadership-lens"])
    missing = list(enriched.get("missing_material_fields") or [])
    if not owner:
        missing = _append_unique(missing, ["accountable owner"])
    if not due_or_cadence:
        missing = _append_unique(missing, ["due date or review cadence"])
    if not enriched.get("expected_deliverable"):
        missing = _append_unique(missing, ["expected deliverable"])
    enriched["missing_material_fields"] = missing
    return enriched


def enrich_updates_with_leadership_lens(updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_task_update_with_leadership_lens(update) for update in updates]
