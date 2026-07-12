"""add leadership reviews

Revision ID: 0007_add_leadership_reviews
Revises: 0006_add_clarifications
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_add_leadership_reviews"
down_revision: Union[str, None] = "0006_add_clarifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "leadership_reviews" in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "leadership_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_type", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("capture_id", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executive_summary", sa.Text(), nullable=True),
        sa.Column("findings", sa.JSON(), nullable=True),
        sa.Column("strategic_questions", sa.JSON(), nullable=True),
        sa.Column("proposed_followups", sa.JSON(), nullable=True),
        sa.Column("missing_context", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("source_record_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for column in (
        "id",
        "review_type",
        "company",
        "capture_id",
        "generated_at",
        "period_start",
        "period_end",
        "prompt_version",
        "status",
        "idempotency_key",
        "created_at",
        "updated_at",
    ):
        op.create_index(op.f(f"ix_leadership_reviews_{column}"), "leadership_reviews", [column], unique=False)


def downgrade() -> None:
    for column in (
        "updated_at",
        "created_at",
        "idempotency_key",
        "status",
        "prompt_version",
        "period_end",
        "period_start",
        "generated_at",
        "capture_id",
        "company",
        "review_type",
        "id",
    ):
        op.drop_index(op.f(f"ix_leadership_reviews_{column}"), table_name="leadership_reviews")
    op.drop_table("leadership_reviews")
