from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from .database import Base


class Company(Base):
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


class Person(Base):
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


class StrategicIssue(Base):
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


class Project(Base):
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


class Decision(Base):
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


class Meeting(Base):
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


class SOP(Base):
    __tablename__ = "sops"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    company = Column(String, default="")
    purpose = Column(Text, default="")
    owner = Column(String, default="")
    current_process = Column(Text, default="")
    escalation_rules = Column(JSON, default=list)
    related_projects = Column(JSON, default=list)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    type = Column(String, default="reference")
    source = Column(String, default="")
    summary = Column(Text, default="")
    linked_objects = Column(JSON, default=list)


class Metric(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    company = Column(String, default="")
    value = Column(String, default="")
    date = Column(String, default="")
    related_strategic_issue = Column(String, default="")
    trend = Column(String, default="stable")
    notes = Column(Text, default="")


class CaptureRecord(Base):
    __tablename__ = "capture_records"

    id = Column(Integer, primary_key=True, index=True)
    raw_text = Column(Text, nullable=False)
    classification_source = Column(String, default="unknown")
    saved_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
