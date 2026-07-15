from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from .database import Base


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        index=True,
    )


class Company(TimestampMixin, Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text, default="")
    leadership = Column(JSON, default=list)
    strategic_issues = Column(JSON, default=list)
    projects = Column(JSON, default=list)
    people = Column(JSON, default=list)
    kpis = Column(JSON, default=list)
    decisions = Column(JSON, default=list)
    meetings = Column(JSON, default=list)


class Person(TimestampMixin, Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    role = Column(String, default="")
    company = Column(String, default="")
    responsibilities = Column(JSON, default=list)
    strengths = Column(JSON, default=list)
    concerns = Column(JSON, default=list)
    current_priorities = Column(JSON, default=list)
    performance_notes = Column(JSON, default=list)
    linked_projects = Column(JSON, default=list)
    linked_decisions = Column(JSON, default=list)
    linked_meetings = Column(JSON, default=list)


class StrategicIssue(TimestampMixin, Base):
    __tablename__ = "strategic_issues"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    company = Column(String, default="")
    owner = Column(String, default="")
    status = Column(String, default="active")
    current_thinking = Column(Text, default="")
    risks = Column(JSON, default=list)
    linked_projects = Column(JSON, default=list)
    linked_decisions = Column(JSON, default=list)
    linked_metrics = Column(JSON, default=list)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    company = Column(String, default="")
    objective = Column(Text, default="")
    status = Column(String, default="active")
    owner = Column(String, default="")
    milestones = Column(JSON, default=list)
    risks = Column(JSON, default=list)
    next_steps = Column(JSON, default=list)
    linked_people = Column(JSON, default=list)
    linked_decisions = Column(JSON, default=list)


class Decision(TimestampMixin, Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    date = Column(String, default="")
    company = Column(String, default="")
    context = Column(Text, default="")
    options_considered = Column(JSON, default=list)
    final_decision = Column(Text, default="")
    reasoning = Column(Text, default="")
    expected_outcome = Column(Text, default="")
    review_date = Column(String, default="")
    linked_people = Column(JSON, default=list)
    linked_projects = Column(JSON, default=list)
    linked_strategic_issues = Column(JSON, default=list)


class Meeting(TimestampMixin, Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    date = Column(String, default="")
    company = Column(String, default="")
    attendees = Column(JSON, default=list)
    summary = Column(Text, default="")
    decisions_made = Column(JSON, default=list)
    action_items = Column(JSON, default=list)
    open_questions = Column(JSON, default=list)
    linked_people = Column(JSON, default=list)
    linked_projects = Column(JSON, default=list)
    linked_strategic_issues = Column(JSON, default=list)


class SOP(TimestampMixin, Base):
    __tablename__ = "sops"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    company = Column(String, default="")
    purpose = Column(Text, default="")
    owner = Column(String, default="")
    current_process = Column(Text, default="")
    escalation_rules = Column(JSON, default=list)
    related_projects = Column(JSON, default=list)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    type = Column(String, default="reference")
    source = Column(String, default="")
    summary = Column(Text, default="")
    linked_objects = Column(JSON, default=list)


class Metric(TimestampMixin, Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    company = Column(String, default="")
    value = Column(String, default="")
    date = Column(String, default="")
    related_strategic_issue = Column(String, default="")
    trend = Column(String, default="stable")
    notes = Column(Text, default="")


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, default="")
    company = Column(String, default="")
    owner = Column(String, default="")
    due_date = Column(String, default="")
    status = Column(String, default="open", index=True)
    priority = Column(String, default="medium", index=True)
    source_type = Column(String, default="manual")
    source_id = Column(String, default="")
    source_summary = Column(Text, default="")
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    next_action = Column(Text, default="")
    blocked_by = Column(Text, default="")
    tags = Column(JSON, default=list)
    expected_deliverable = Column(Text, default="")
    definition_of_done = Column(Text, default="")
    why_it_matters = Column(Text, default="")
    delegated_by = Column(String, default="")
    assigned_to = Column(String, default="")
    waiting_on = Column(String, default="")
    stakeholders = Column(JSON, default=list)
    dependencies = Column(JSON, default=list)
    follow_up_date = Column(String, default="")
    recurrence = Column(String, default="")
    task_type = Column(String, default="")
    confidence = Column(String, default="")
    interpretation_notes = Column(Text, default="")
    source_excerpt = Column(Text, default="")
    parent_task_id = Column(Integer, nullable=True, index=True)
    linked_project_ids = Column(JSON, default=list)
    linked_decision_ids = Column(JSON, default=list)
    linked_people = Column(JSON, default=list)


class CaptureRecord(Base):
    __tablename__ = "capture_records"

    id = Column(Integer, primary_key=True, index=True)
    raw_text = Column(Text, nullable=False)
    classification_source = Column(String, default="unknown")
    saved_count = Column(Integer, default=0)
    screenshot_summary = Column(Text, default="")
    ai_model = Column(String, default="")
    prompt_version = Column(String, default="")
    structured_interpretation = Column(JSON, default=dict)
    approved_suggestions = Column(JSON, default=list)
    rejected_suggestions = Column(JSON, default=list)
    saved_record_ids = Column(JSON, default=list)
    user_edits = Column(JSON, default=list)
    processing_events = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class CaptureInterpretation(TimestampMixin, Base):
    __tablename__ = "capture_interpretations"

    id = Column(Integer, primary_key=True, index=True)
    capture_id = Column(Integer, index=True, nullable=False)
    capture_summary = Column(Text, default="")
    capture_purpose = Column(String, default="")
    executive_intent = Column(String, default="")
    primary_company = Column(String, default="", index=True)
    primary_subject = Column(String, default="")
    primary_topic = Column(String, default="")
    urgency = Column(String, default="")
    tone = Column(String, default="")
    temporal_context = Column(String, default="")
    confidence = Column(String, default="")
    model = Column(String, default="")
    prompt_version = Column(String, default="", index=True)
    people_roles = Column(JSON, default=list)
    statements = Column(JSON, default=list)
    open_questions = Column(JSON, default=list)
    ambiguities = Column(JSON, default=list)
    source_evidence = Column(JSON, default=list)
    raw_response = Column(JSON, default=dict)


class CaptureMutation(TimestampMixin, Base):
    __tablename__ = "capture_mutations"

    id = Column(Integer, primary_key=True, index=True)
    capture_id = Column(Integer, index=True, nullable=False)
    interpretation_id = Column(Integer, nullable=True, index=True)
    suggestion_index = Column(Integer, default=0, index=True)
    object_type = Column(String, index=True, nullable=False)
    operation = Column(String, default="create", index=True)
    status = Column(String, default="proposed", index=True)
    matched_record_type = Column(String, default="", index=True)
    matched_record_id = Column(Integer, nullable=True, index=True)
    match_confidence = Column(String, default="")
    evidence_excerpt = Column(Text, default="")
    field_operations = Column(JSON, default=dict)
    proposed_values = Column(JSON, default=dict)
    approved_values = Column(JSON, default=dict)
    persisted_values = Column(JSON, default=dict)
    saved_record_type = Column(String, default="", index=True)
    saved_record_id = Column(Integer, nullable=True, index=True)
    missing_material_fields = Column(JSON, default=list)
    uncertainty = Column(Text, default="")
    explanation = Column(Text, default="")
    user_edits = Column(JSON, default=list)
    applied_at = Column(DateTime(timezone=True), nullable=True, index=True)


class BriefingView(Base):
    __tablename__ = "briefing_views"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    last_viewed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class ProvenanceRecord(TimestampMixin, Base):
    __tablename__ = "provenance_records"

    id = Column(Integer, primary_key=True, index=True)
    object_type = Column(String, index=True, nullable=False)
    object_id = Column(Integer, index=True, nullable=False)
    original_source_type = Column(String, default="manual_entry", index=True)
    original_source_id = Column(String, default="")
    source_title = Column(String, default="")
    source_date = Column(String, default="")
    capture_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    source_excerpt = Column(Text, default="")
    created_by = Column(String, default="user")
    confidence = Column(String, default="user_confirmed")
    verification_state = Column(String, default="user_confirmed", index=True)
    memory_classification = Column(String, default="confirmed_fact", index=True)
    superseded_by_type = Column(String, default="")
    superseded_by_id = Column(Integer, nullable=True)


class RevisionRecord(Base):
    __tablename__ = "revision_records"

    id = Column(Integer, primary_key=True, index=True)
    object_type = Column(String, index=True, nullable=False)
    object_id = Column(Integer, index=True, nullable=False)
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    changed_by = Column(String, default="user")
    change_type = Column(String, default="update")
    before = Column(JSON, default=dict)
    after = Column(JSON, default=dict)
    source_type = Column(String, default="")
    source_id = Column(String, default="")


class ReviewAlert(TimestampMixin, Base):
    __tablename__ = "review_alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(String, index=True, nullable=False)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, default="")
    severity = Column(String, default="medium", index=True)
    status = Column(String, default="open", index=True)
    object_type = Column(String, default="")
    object_id = Column(Integer, nullable=True)
    related_object_type = Column(String, default="")
    related_object_id = Column(Integer, nullable=True)
    evidence = Column(JSON, default=list)
    resolution = Column(Text, default="")
    resolved_at = Column(DateTime(timezone=True), nullable=True, index=True)


class ResolvableItem(TimestampMixin, Base):
    __tablename__ = "resolvable_items"

    id = Column(Integer, primary_key=True, index=True)
    parent_type = Column(String, index=True, nullable=False)
    parent_id = Column(Integer, index=True, nullable=False)
    item_type = Column(String, default="action", index=True)
    display_text = Column(Text, nullable=False)
    status = Column(String, default="open", index=True)
    company = Column(String, default="", index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True, index=True)
    resolved_by = Column(String, default="")
    resolution_source = Column(String, default="")
    resolution_note = Column(Text, default="")
    reopened_at = Column(DateTime(timezone=True), nullable=True, index=True)
    dedupe_key = Column(String, unique=True, index=True, nullable=False)


class LeadershipReview(TimestampMixin, Base):
    __tablename__ = "leadership_reviews"

    id = Column(Integer, primary_key=True, index=True)
    review_type = Column(String, default="manual", index=True)
    company = Column(String, default="", index=True)
    capture_id = Column(Integer, nullable=True, index=True)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    period_start = Column(DateTime(timezone=True), nullable=True, index=True)
    period_end = Column(DateTime(timezone=True), nullable=True, index=True)
    executive_summary = Column(Text, default="")
    findings = Column(JSON, default=list)
    strategic_questions = Column(JSON, default=list)
    proposed_followups = Column(JSON, default=list)
    missing_context = Column(JSON, default=list)
    confidence = Column(String, default="0.0")
    model = Column(String, default="deterministic")
    prompt_version = Column(String, default="leadership-advisor-v1", index=True)
    status = Column(String, default="new", index=True)
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    source_record_ids = Column(JSON, default=list)


class IntegrationInboxItem(TimestampMixin, Base):
    __tablename__ = "integration_inbox_items"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(String, index=True, nullable=False)
    source_identifier = Column(String, default="", index=True)
    source_title = Column(String, default="")
    source_date = Column(String, default="")
    status = Column(String, default="new", index=True)
    source_metadata = Column("metadata", JSON, key="source_metadata", default=dict)
    extracted_text = Column(Text, default="")
    suggested_updates = Column(JSON, default=list)
    rejected_suggestions = Column(JSON, default=list)
    confidence = Column(String, default="unverified")
    error = Column(Text, default="")


class Clarification(TimestampMixin, Base):
    __tablename__ = "clarifications"

    id = Column(Integer, primary_key=True, index=True)
    clarification_type = Column(String, index=True, nullable=False)
    subtype = Column(String, default="", index=True)
    status = Column(String, default="open", index=True)
    question = Column(Text, nullable=False)
    why_it_matters = Column(Text, default="")
    target_record_type = Column(String, default="", index=True)
    target_record_id = Column(Integer, nullable=True, index=True)
    company = Column(String, default="", index=True)
    evidence = Column(JSON, default=list)
    score = Column(Integer, default=0, index=True)
    score_reasons = Column(JSON, default=list)
    suggested_answers = Column(JSON, default=list)
    proposed_update = Column(JSON, default=dict)
    confidence = Column(String, default="deterministic")
    uncertainty = Column(Text, default="")
    user_response = Column(Text, default="")
    note = Column(Text, default="")
    answered_at = Column(DateTime(timezone=True), nullable=True, index=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=True, index=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    suppression_scope = Column(String, default="")
    suppression_reason = Column(Text, default="")
    dedupe_key = Column(String, unique=True, index=True, nullable=False)
    evidence_fingerprint = Column(String, default="")
    generation_rule_version = Column(String, default="clarification-rules-v1", index=True)


class EntityAlias(TimestampMixin, Base):
    __tablename__ = "entity_aliases"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, index=True, nullable=False)
    entity_id = Column(Integer, index=True, nullable=False)
    alias = Column(String, index=True, nullable=False)
    confidence = Column(String, default="user_confirmed")


class DashboardConfig(TimestampMixin, Base):
    __tablename__ = "dashboard_configs"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String, unique=True, index=True, nullable=False)
    modules = Column(JSON, default=list)


class SearchConversation(TimestampMixin, Base):
    __tablename__ = "search_conversations"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, unique=True, index=True, nullable=False)
    last_query = Column(Text, default="")
    context = Column(JSON, default=dict)
