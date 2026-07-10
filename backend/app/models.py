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


class CaptureRecord(Base):
    __tablename__ = "capture_records"

    id = Column(Integer, primary_key=True, index=True)
    raw_text = Column(Text, nullable=False)
    classification_source = Column(String, default="unknown")
    saved_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


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
