"""add clarifications

Revision ID: 0006_add_clarifications
Revises: 0005_add_roadmap_support_tables
Create Date: 2026-07-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_clarifications"
down_revision: Union[str, None] = "0005_add_roadmap_support_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clarifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clarification_type", sa.String(), nullable=False),
        sa.Column("subtype", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=True),
        sa.Column("target_record_type", sa.String(), nullable=True),
        sa.Column("target_record_id", sa.Integer(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_reasons", sa.JSON(), nullable=True),
        sa.Column("suggested_answers", sa.JSON(), nullable=True),
        sa.Column("proposed_update", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.String(), nullable=True),
        sa.Column("uncertainty", sa.Text(), nullable=True),
        sa.Column("user_response", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suppression_scope", sa.String(), nullable=True),
        sa.Column("suppression_reason", sa.Text(), nullable=True),
        sa.Column("dedupe_key", sa.String(), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(), nullable=True),
        sa.Column("generation_rule_version", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    for column in (
        "id",
        "clarification_type",
        "subtype",
        "status",
        "target_record_type",
        "target_record_id",
        "company",
        "score",
        "answered_at",
        "snoozed_until",
        "dismissed_at",
        "dedupe_key",
        "generation_rule_version",
        "created_at",
        "updated_at",
    ):
        op.create_index(op.f(f"ix_clarifications_{column}"), "clarifications", [column], unique=False)


def downgrade() -> None:
    for column in (
        "updated_at",
        "created_at",
        "generation_rule_version",
        "dedupe_key",
        "dismissed_at",
        "snoozed_until",
        "answered_at",
        "score",
        "company",
        "target_record_id",
        "target_record_type",
        "status",
        "subtype",
        "clarification_type",
        "id",
    ):
        op.drop_index(op.f(f"ix_clarifications_{column}"), table_name="clarifications")
    op.drop_table("clarifications")
