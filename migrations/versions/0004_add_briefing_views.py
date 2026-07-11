"""add briefing views

Revision ID: 0004_add_briefing_views
Revises: 0003_add_tasks
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_add_briefing_views"
down_revision: Union[str, None] = "0003_add_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "briefing_views" in sa.inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "briefing_views",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(op.f("ix_briefing_views_id"), "briefing_views", ["id"], unique=False)
    op.create_index(op.f("ix_briefing_views_username"), "briefing_views", ["username"], unique=False)
    op.create_index(op.f("ix_briefing_views_last_viewed_at"), "briefing_views", ["last_viewed_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_briefing_views_last_viewed_at"), table_name="briefing_views")
    op.drop_index(op.f("ix_briefing_views_username"), table_name="briefing_views")
    op.drop_index(op.f("ix_briefing_views_id"), table_name="briefing_views")
    op.drop_table("briefing_views")
