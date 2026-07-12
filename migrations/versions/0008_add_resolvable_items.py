"""add durable resolvable items

Revision ID: 0008_add_resolvable_items
Revises: 0007_add_leadership_reviews
Create Date: 2026-07-12
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_add_resolvable_items"
down_revision: Union[str, None] = "0007_add_leadership_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dedupe_key(parent_type: str, parent_id: int, item_type: str, text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{parent_type}:{parent_id}:{item_type}:{digest}"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "resolvable_items" not in inspector.get_table_names():
        op.create_table(
            "resolvable_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("parent_type", sa.String(), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=False),
            sa.Column("item_type", sa.String(), nullable=True),
            sa.Column("display_text", sa.Text(), nullable=False),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("company", sa.String(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by", sa.String(), nullable=True),
            sa.Column("resolution_source", sa.String(), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dedupe_key", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("dedupe_key"),
        )
        for column in (
            "id",
            "parent_type",
            "parent_id",
            "item_type",
            "status",
            "company",
            "resolved_at",
            "dedupe_key",
            "created_at",
            "updated_at",
        ):
            op.create_index(op.f(f"ix_resolvable_items_{column}"), "resolvable_items", [column], unique=False)

    metadata = sa.MetaData()
    resolvable = sa.Table("resolvable_items", metadata, autoload_with=bind)
    meetings = sa.Table("meetings", metadata, autoload_with=bind)
    projects = sa.Table("projects", metadata, autoload_with=bind)
    issues = sa.Table("strategic_issues", metadata, autoload_with=bind)
    now = datetime.now(timezone.utc)

    def exists(key: str) -> bool:
        return bool(bind.execute(sa.select(resolvable.c.id).where(resolvable.c.dedupe_key == key)).first())

    def insert(parent_type: str, parent_id: int, item_type: str, text: str, company: str) -> None:
        text = str(text or "").strip()
        if not text:
            return
        key = _dedupe_key(parent_type, parent_id, item_type, text)
        if exists(key):
            return
        bind.execute(resolvable.insert().values(
            parent_type=parent_type,
            parent_id=parent_id,
            item_type=item_type,
            display_text=text,
            status="open",
            company=company or "",
            dedupe_key=key,
            created_at=now,
            updated_at=now,
        ))

    for meeting in bind.execute(sa.select(meetings.c.id, meetings.c.company, meetings.c.action_items)):
        for action in meeting.action_items or []:
            insert("meeting", meeting.id, "meeting_action", action, meeting.company)
    for project in bind.execute(sa.select(projects.c.id, projects.c.company, projects.c.risks)):
        for risk in project.risks or []:
            insert("project", project.id, "risk", risk, project.company)
    for issue in bind.execute(sa.select(issues.c.id, issues.c.company, issues.c.risks)):
        for risk in issue.risks or []:
            insert("strategic_issue", issue.id, "risk", risk, issue.company)


def downgrade() -> None:
    bind = op.get_bind()
    if "resolvable_items" not in sa.inspect(bind).get_table_names():
        return
    for column in (
        "updated_at",
        "created_at",
        "dedupe_key",
        "resolved_at",
        "company",
        "status",
        "item_type",
        "parent_id",
        "parent_type",
        "id",
    ):
        op.drop_index(op.f(f"ix_resolvable_items_{column}"), table_name="resolvable_items")
    op.drop_table("resolvable_items")
