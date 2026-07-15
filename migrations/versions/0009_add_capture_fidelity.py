"""add capture fidelity audit records

Revision ID: 0009_add_capture_fidelity
Revises: 0008_add_resolvable_items
Create Date: 2026-07-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_add_capture_fidelity"
down_revision: Union[str, None] = "0008_add_resolvable_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TASK_COLUMNS = (
    ("expected_deliverable", sa.Text(), ""),
    ("definition_of_done", sa.Text(), ""),
    ("why_it_matters", sa.Text(), ""),
    ("delegated_by", sa.String(), ""),
    ("assigned_to", sa.String(), ""),
    ("waiting_on", sa.String(), ""),
    ("stakeholders", sa.JSON(), []),
    ("dependencies", sa.JSON(), []),
    ("follow_up_date", sa.String(), ""),
    ("recurrence", sa.String(), ""),
    ("task_type", sa.String(), ""),
    ("confidence", sa.String(), ""),
    ("interpretation_notes", sa.Text(), ""),
    ("source_excerpt", sa.Text(), ""),
    ("parent_task_id", sa.Integer(), None),
    ("linked_project_ids", sa.JSON(), []),
    ("linked_decision_ids", sa.JSON(), []),
    ("linked_people", sa.JSON(), []),
)

CAPTURE_COLUMNS = (
    ("screenshot_summary", sa.Text(), ""),
    ("ai_model", sa.String(), ""),
    ("prompt_version", sa.String(), ""),
    ("structured_interpretation", sa.JSON(), {}),
    ("approved_suggestions", sa.JSON(), []),
    ("rejected_suggestions", sa.JSON(), []),
    ("saved_record_ids", sa.JSON(), []),
    ("user_edits", sa.JSON(), []),
    ("processing_events", sa.JSON(), []),
)


def _add_column_if_missing(table: str, name: str, column_type: sa.types.TypeEngine, default: object) -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in sa.inspect(bind).get_columns(table)}
    if name in existing:
        return
    op.add_column(table, sa.Column(name, column_type, nullable=True))
    if default is not None and not isinstance(default, (list, dict)):
        table_ref = sa.table(table, sa.column(name))
        bind.execute(table_ref.update().where(sa.column(name).is_(None)).values({name: default}))


def _create_index_if_missing(table: str, column: str) -> None:
    bind = op.get_bind()
    index_name = op.f(f"ix_{table}_{column}")
    existing = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
    if index_name not in existing:
        op.create_index(index_name, table, [column], unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for name, column_type, default in TASK_COLUMNS:
        _add_column_if_missing("tasks", name, column_type, default)
    for name, column_type, default in CAPTURE_COLUMNS:
        _add_column_if_missing("capture_records", name, column_type, default)
    _create_index_if_missing("tasks", "parent_task_id")

    if "capture_interpretations" not in inspector.get_table_names():
        op.create_table(
            "capture_interpretations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("capture_id", sa.Integer(), nullable=False),
            sa.Column("capture_summary", sa.Text(), nullable=True),
            sa.Column("capture_purpose", sa.String(), nullable=True),
            sa.Column("executive_intent", sa.String(), nullable=True),
            sa.Column("primary_company", sa.String(), nullable=True),
            sa.Column("primary_subject", sa.String(), nullable=True),
            sa.Column("primary_topic", sa.String(), nullable=True),
            sa.Column("urgency", sa.String(), nullable=True),
            sa.Column("tone", sa.String(), nullable=True),
            sa.Column("temporal_context", sa.String(), nullable=True),
            sa.Column("confidence", sa.String(), nullable=True),
            sa.Column("model", sa.String(), nullable=True),
            sa.Column("prompt_version", sa.String(), nullable=True),
            sa.Column("people_roles", sa.JSON(), nullable=True),
            sa.Column("statements", sa.JSON(), nullable=True),
            sa.Column("open_questions", sa.JSON(), nullable=True),
            sa.Column("ambiguities", sa.JSON(), nullable=True),
            sa.Column("source_evidence", sa.JSON(), nullable=True),
            sa.Column("raw_response", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("id", "capture_id", "primary_company", "prompt_version", "created_at", "updated_at"):
            op.create_index(op.f(f"ix_capture_interpretations_{column}"), "capture_interpretations", [column], unique=False)

    if "capture_mutations" not in inspector.get_table_names():
        op.create_table(
            "capture_mutations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("capture_id", sa.Integer(), nullable=False),
            sa.Column("interpretation_id", sa.Integer(), nullable=True),
            sa.Column("suggestion_index", sa.Integer(), nullable=True),
            sa.Column("object_type", sa.String(), nullable=False),
            sa.Column("operation", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("matched_record_type", sa.String(), nullable=True),
            sa.Column("matched_record_id", sa.Integer(), nullable=True),
            sa.Column("match_confidence", sa.String(), nullable=True),
            sa.Column("evidence_excerpt", sa.Text(), nullable=True),
            sa.Column("field_operations", sa.JSON(), nullable=True),
            sa.Column("proposed_values", sa.JSON(), nullable=True),
            sa.Column("approved_values", sa.JSON(), nullable=True),
            sa.Column("persisted_values", sa.JSON(), nullable=True),
            sa.Column("saved_record_type", sa.String(), nullable=True),
            sa.Column("saved_record_id", sa.Integer(), nullable=True),
            sa.Column("missing_material_fields", sa.JSON(), nullable=True),
            sa.Column("uncertainty", sa.Text(), nullable=True),
            sa.Column("explanation", sa.Text(), nullable=True),
            sa.Column("user_edits", sa.JSON(), nullable=True),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in (
            "id",
            "capture_id",
            "interpretation_id",
            "suggestion_index",
            "object_type",
            "operation",
            "status",
            "matched_record_type",
            "matched_record_id",
            "saved_record_type",
            "saved_record_id",
            "applied_at",
            "created_at",
            "updated_at",
        ):
            op.create_index(op.f(f"ix_capture_mutations_{column}"), "capture_mutations", [column], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "capture_mutations" in tables:
        op.drop_table("capture_mutations")
    if "capture_interpretations" in tables:
        op.drop_table("capture_interpretations")

    existing_task_columns = {column["name"] for column in sa.inspect(bind).get_columns("tasks")}
    for name, _, _ in reversed(TASK_COLUMNS):
        if name in existing_task_columns:
            if name == "parent_task_id":
                indexes = {index["name"] for index in sa.inspect(bind).get_indexes("tasks")}
                index_name = op.f("ix_tasks_parent_task_id")
                if index_name in indexes:
                    op.drop_index(index_name, table_name="tasks")
            op.drop_column("tasks", name)

    existing_capture_columns = {column["name"] for column in sa.inspect(bind).get_columns("capture_records")}
    for name, _, _ in reversed(CAPTURE_COLUMNS):
        if name in existing_capture_columns:
            op.drop_column("capture_records", name)
