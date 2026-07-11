"""add memory timestamps

Revision ID: 0002_add_memory_timestamps
Revises: 0001_initial_schema
Create Date: 2026-07-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_add_memory_timestamps"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "companies",
    "people",
    "strategic_issues",
    "projects",
    "decisions",
    "meetings",
    "sops",
    "documents",
    "metrics",
]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "created_at" not in columns:
            op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
            op.create_index(op.f(f"ix_{table}_created_at"), table, ["created_at"], unique=False)
        if "updated_at" not in columns:
            op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
            op.create_index(op.f(f"ix_{table}_updated_at"), table, ["updated_at"], unique=False)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(op.f(f"ix_{table}_updated_at"), table_name=table)
        op.drop_index(op.f(f"ix_{table}_created_at"), table_name=table)
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
