"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("leadership", sa.JSON(), nullable=True),
        sa.Column("strategic_issues", sa.JSON(), nullable=True),
        sa.Column("projects", sa.JSON(), nullable=True),
        sa.Column("people", sa.JSON(), nullable=True),
        sa.Column("kpis", sa.JSON(), nullable=True),
        sa.Column("decisions", sa.JSON(), nullable=True),
        sa.Column("meetings", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_companies_id"), "companies", ["id"], unique=False)
    op.create_index(op.f("ix_companies_name"), "companies", ["name"], unique=False)

    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("responsibilities", sa.JSON(), nullable=True),
        sa.Column("strengths", sa.JSON(), nullable=True),
        sa.Column("concerns", sa.JSON(), nullable=True),
        sa.Column("current_priorities", sa.JSON(), nullable=True),
        sa.Column("performance_notes", sa.JSON(), nullable=True),
        sa.Column("linked_projects", sa.JSON(), nullable=True),
        sa.Column("linked_decisions", sa.JSON(), nullable=True),
        sa.Column("linked_meetings", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_people_id"), "people", ["id"], unique=False)
    op.create_index(op.f("ix_people_name"), "people", ["name"], unique=False)

    op.create_table(
        "strategic_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("current_thinking", sa.Text(), nullable=True),
        sa.Column("risks", sa.JSON(), nullable=True),
        sa.Column("linked_projects", sa.JSON(), nullable=True),
        sa.Column("linked_decisions", sa.JSON(), nullable=True),
        sa.Column("linked_metrics", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_strategic_issues_id"), "strategic_issues", ["id"], unique=False)
    op.create_index(op.f("ix_strategic_issues_title"), "strategic_issues", ["title"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("milestones", sa.JSON(), nullable=True),
        sa.Column("risks", sa.JSON(), nullable=True),
        sa.Column("next_steps", sa.JSON(), nullable=True),
        sa.Column("linked_people", sa.JSON(), nullable=True),
        sa.Column("linked_decisions", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)
    op.create_index(op.f("ix_projects_title"), "projects", ["title"], unique=False)

    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("date", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("options_considered", sa.JSON(), nullable=True),
        sa.Column("final_decision", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("review_date", sa.String(), nullable=True),
        sa.Column("linked_people", sa.JSON(), nullable=True),
        sa.Column("linked_projects", sa.JSON(), nullable=True),
        sa.Column("linked_strategic_issues", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_decisions_id"), "decisions", ["id"], unique=False)
    op.create_index(op.f("ix_decisions_title"), "decisions", ["title"], unique=False)

    op.create_table(
        "meetings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("date", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("attendees", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("decisions_made", sa.JSON(), nullable=True),
        sa.Column("action_items", sa.JSON(), nullable=True),
        sa.Column("open_questions", sa.JSON(), nullable=True),
        sa.Column("linked_people", sa.JSON(), nullable=True),
        sa.Column("linked_projects", sa.JSON(), nullable=True),
        sa.Column("linked_strategic_issues", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meetings_id"), "meetings", ["id"], unique=False)
    op.create_index(op.f("ix_meetings_title"), "meetings", ["title"], unique=False)

    op.create_table(
        "sops",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("current_process", sa.Text(), nullable=True),
        sa.Column("escalation_rules", sa.JSON(), nullable=True),
        sa.Column("related_projects", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_sops_id"), "sops", ["id"], unique=False)
    op.create_index(op.f("ix_sops_title"), "sops", ["title"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("linked_objects", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index(op.f("ix_documents_title"), "documents", ["title"], unique=False)

    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("value", sa.String(), nullable=True),
        sa.Column("date", sa.String(), nullable=True),
        sa.Column("related_strategic_issue", sa.String(), nullable=True),
        sa.Column("trend", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metrics_id"), "metrics", ["id"], unique=False)
    op.create_index(op.f("ix_metrics_title"), "metrics", ["title"], unique=False)

    op.create_table(
        "capture_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("classification_source", sa.String(), nullable=True),
        sa.Column("saved_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_capture_records_id"), "capture_records", ["id"], unique=False)
    op.create_index(op.f("ix_capture_records_created_at"), "capture_records", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_capture_records_created_at"), table_name="capture_records")
    op.drop_index(op.f("ix_capture_records_id"), table_name="capture_records")
    op.drop_table("capture_records")
    op.drop_index(op.f("ix_metrics_title"), table_name="metrics")
    op.drop_index(op.f("ix_metrics_id"), table_name="metrics")
    op.drop_table("metrics")
    op.drop_index(op.f("ix_documents_title"), table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_sops_title"), table_name="sops")
    op.drop_index(op.f("ix_sops_id"), table_name="sops")
    op.drop_table("sops")
    op.drop_index(op.f("ix_meetings_title"), table_name="meetings")
    op.drop_index(op.f("ix_meetings_id"), table_name="meetings")
    op.drop_table("meetings")
    op.drop_index(op.f("ix_decisions_title"), table_name="decisions")
    op.drop_index(op.f("ix_decisions_id"), table_name="decisions")
    op.drop_table("decisions")
    op.drop_index(op.f("ix_projects_title"), table_name="projects")
    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_strategic_issues_title"), table_name="strategic_issues")
    op.drop_index(op.f("ix_strategic_issues_id"), table_name="strategic_issues")
    op.drop_table("strategic_issues")
    op.drop_index(op.f("ix_people_name"), table_name="people")
    op.drop_index(op.f("ix_people_id"), table_name="people")
    op.drop_table("people")
    op.drop_index(op.f("ix_companies_name"), table_name="companies")
    op.drop_index(op.f("ix_companies_id"), table_name="companies")
    op.drop_table("companies")
