import re
from typing import Any

from fastapi import HTTPException

from .models import CaptureRecord, Company, Decision, Document, Meeting, Metric, Person, Project, SOP, StrategicIssue

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
    normalized_haystack = " ".join(re.findall(r"[a-z0-9]+", haystack))
    normalized_phrase = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
    if normalized_phrase and re.search(rf"(?:^| ){re.escape(normalized_phrase)}(?: |$)", normalized_haystack):
        return 20

    normalized_query = query.lower()
    stop_words = {
        "a", "an", "and", "are", "company", "did", "do", "does", "for", "from",
        "in", "is", "me", "meeting", "metric", "my", "of", "on", "person", "project",
        "completely", "new", "role", "s", "the", "to", "topic", "we", "what", "why", "with",
    }
    tokens = set(re.findall(r"[a-z0-9]+", normalized_query)) - stop_words
    haystack_tokens = set(re.findall(r"[a-z0-9]+", haystack))
    synonyms = {
        "promote": ["promotion", "promoted"],
        "promoted": ["promotion", "promote"],
        "what": ["title", "summary", "context"],
        "happening": ["status", "active", "current", "issue", "project"],
    }
    score = 0
    for token in tokens:
        comparable_tokens = {token}
        if token.endswith("ies") and len(token) > 3:
            comparable_tokens.add(f"{token[:-3]}y")
        elif token.endswith("s") and len(token) > 3:
            comparable_tokens.add(token[:-1])
        if comparable_tokens & haystack_tokens:
            score += 3
            continue
        for synonym in synonyms.get(token, []):
            if synonym in haystack_tokens:
                score += 3
                break
    return score


def _search_intent_boost(model: type[Any], query: str) -> int:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if tokens & {"why", "decide", "decided", "decision", "decisions", "promote", "promoted", "promotion"}:
        return 30 if model is Decision else 0
    if tokens & {"meeting", "agenda", "prep"}:
        return 8 if model is Meeting else 0
    if tokens & {"metric", "metrics", "kpi", "trend"}:
        return 8 if model is Metric else 0
    if tokens & {"risk", "risks"}:
        return 12 if model in {StrategicIssue, Project} else 0
    if tokens & {"action", "actions", "question", "questions"}:
        return 12 if model is Meeting else 0
    if "happening" in tokens:
        return 20 if model is Company else 0
    if tokens & {"project", "projects", "initiative"}:
        return 8 if model is Project else 0
    if "role" in tokens or "person" in tokens:
        return 8 if model is Person else 0
    if tokens & {"who", "owner", "owns"}:
        return 8 if model in {Person, StrategicIssue, Project, SOP} else 0
    if "company" in tokens:
        if model is Person:
            return 12
        return 4 if model is Company else 0
    return 0


def _entity_name_boost(item: Any, title_field: str, query: str) -> int:
    entity_name = str(getattr(item, title_field, "")).strip().lower()
    if not entity_name:
        return 0
    return 20 if re.search(rf"\b{re.escape(entity_name)}\b", query.lower()) else 0


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


def _rank_for_context(
    items: list[Any], fields: list[str], query: str, *, include_unmatched: bool = False
) -> list[Any]:
    scored = [(_match_score(item, fields, query), item.id or 0, item) for item in items]
    relevant = [entry for entry in scored if entry[0] > 0]
    pool = relevant or (scored if include_unmatched else [])
    return [entry[2] for entry in sorted(pool, key=lambda entry: (entry[0], entry[1]), reverse=True)]


def _result_summary(item: Any) -> str:
    if isinstance(item, Person):
        role = item.role or "Person"
        summary = f"{role} at {item.company}" if item.company else role
        if item.performance_notes:
            summary += f" — {item.performance_notes[-1]}"
        return summary
    if isinstance(item, CaptureRecord):
        text_value = " ".join(item.raw_text.split())
        return text_value if len(text_value) <= 500 else f"{text_value[:497]}..."
    if isinstance(item, StrategicIssue):
        details = [item.status.capitalize() if item.status else "Strategic issue"]
        if item.owner:
            details.append(f"owned by {item.owner}")
        if item.company:
            details.append(item.company)
        return " — ".join(details)
    if isinstance(item, Project):
        details = [item.objective or item.status.capitalize() or "Project"]
        if item.owner:
            details.append(f"owned by {item.owner}")
        if item.company:
            details.append(item.company)
        return " — ".join(details)
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


def _company_in_query(query: str) -> str:
    return _detect_positive_company(query)


def _belongs_to_company(item: Any, company: str) -> bool:
    if isinstance(item, Company):
        return item.name.lower() == company.lower()
    if isinstance(item, CaptureRecord):
        aliases = [alias for alias, canonical in COMPANY_ALIASES.items() if canonical == company]
        return any(_company_mentions(item.raw_text, alias) for alias in aliases)
    return str(getattr(item, "company", "")).lower() == company.lower()


def _answer_for_result(item: Any, query: str) -> str:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if isinstance(item, Decision):
        if "why" in tokens and item.reasoning:
            return item.reasoning
        if tokens & {"when", "date"} and item.date:
            return item.date
        if "review" in tokens and item.review_date:
            return item.review_date
    if isinstance(item, Person):
        if "company" in tokens and item.company:
            return item.company
        if "role" in tokens and item.role:
            return item.role
        if tokens & {"responsible", "responsibility", "responsibilities"} and item.responsibilities:
            return "; ".join(item.responsibilities)
        if tokens & {"working", "priority", "priorities"} and item.current_priorities:
            return "; ".join(item.current_priorities)
    if isinstance(item, Company) and "happening" in tokens:
        parts = []
        if item.strategic_issues:
            parts.append(f"Strategic issues: {', '.join(item.strategic_issues[:3])}")
        if item.projects:
            parts.append(f"Projects: {', '.join(item.projects[:3])}")
        return ". ".join(parts) or _result_summary(item)
    if isinstance(item, (StrategicIssue, Project, SOP)) and tokens & {"who", "owner", "owns"}:
        if item.owner:
            return item.owner
    if isinstance(item, (StrategicIssue, Project)) and tokens & {"risk", "risks"} and item.risks:
        return "; ".join(item.risks)
    if isinstance(item, Project) and ({"next", "step", "steps"} & tokens) and item.next_steps:
        return "; ".join(item.next_steps)
    if isinstance(item, Metric):
        if tokens & {"trend", "trending"} and item.trend:
            return item.trend
        if tokens & {"up", "down"} and item.trend:
            return f"{item.title}: {item.trend}"
        return item.value or _result_summary(item)
    if isinstance(item, Meeting):
        if tokens & {"action", "actions", "item", "items"} and item.action_items:
            return "; ".join(item.action_items)
        if tokens & {"question", "questions"} and item.open_questions:
            return "; ".join(item.open_questions)
    if isinstance(item, CaptureRecord):
        return item.raw_text
    return _result_summary(item)


def _answer_for_ranked_items(items: list[Any], query: str) -> str:
    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if tokens & {"risk", "risks"}:
        values = [risk for item in items if isinstance(item, (StrategicIssue, Project)) for risk in (item.risks or [])]
        if values:
            return "; ".join(dict.fromkeys(values))
    if tokens & {"action", "actions"}:
        values = [action for item in items if isinstance(item, Meeting) for action in (item.action_items or [])]
        if values:
            return "; ".join(dict.fromkeys(values))
    if tokens & {"question", "questions"}:
        values = [question for item in items if isinstance(item, Meeting) for question in (item.open_questions or [])]
        if values:
            return "; ".join(dict.fromkeys(values))
    if "decisions" in tokens:
        values = [
            f"{item.title} (review {item.review_date})" if item.review_date else item.title
            for item in items if isinstance(item, Decision)
        ]
        if values:
            return "; ".join(values)
    if tokens & {"metrics"} or tokens & {"up", "down"}:
        values = [
            f"{item.title}: {item.trend or item.value}"
            for item in items if isinstance(item, Metric)
        ]
        if values:
            return "; ".join(values)
    return _answer_for_result(items[0], query)


def _merge_memory_labels(primary: list[str], supplemental: list[str], company: str = "") -> list[str]:
    """Keep richer normalized labels while dropping shorthand aliases from company indexes."""
    company_tokens = set(re.findall(r"[a-z0-9]+", company.lower()))
    merged: list[str] = []
    token_sets: list[set[str]] = []
    for label in [*primary, *supplemental]:
        tokens = set(re.findall(r"[a-z0-9]+", label.lower())) - company_tokens
        if not tokens or any(tokens <= existing or existing <= tokens for existing in token_sets):
            continue
        merged.append(label)
        token_sets.append(tokens)
    return merged


def _unique_captures(captures: list[CaptureRecord], limit: int = 5) -> list[CaptureRecord]:
    unique: list[CaptureRecord] = []
    seen: set[str] = set()
    for capture in captures:
        normalized = " ".join(capture.raw_text.lower().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(capture)
        if len(unique) == limit:
            break
    return unique


def _meeting_topic_query(meeting_title: str, company: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", meeting_title.lower())
    company_tokens = set(re.findall(r"[a-z0-9]+", company.lower()))
    for alias, canonical in COMPANY_ALIASES.items():
        if canonical == company:
            company_tokens.update(re.findall(r"[a-z0-9]+", alias))
    generic = {
        "agenda", "company", "leadership", "meeting", "monthly", "pec", "prep",
        "prepare", "review", "session", "team", "weekly",
    }
    topic_tokens = [token for token in tokens if token not in company_tokens | generic]
    if "management" in topic_tokens and "project" in topic_tokens:
        topic_tokens.append("pm")
    return " ".join(dict.fromkeys(topic_tokens))


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


