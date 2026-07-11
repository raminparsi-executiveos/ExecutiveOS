"""add roadmap support tables

Revision ID: 0005_add_roadmap_support_tables
Revises: 0004_add_briefing_views
Create Date: 2026-07-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_add_roadmap_support_tables"
down_revision: Union[str, None] = "0004_add_briefing_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing_tables = _existing_tables()

    if "provenance_records" not in existing_tables:
        op.create_table(
            "provenance_records",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("object_type", sa.String(), nullable=False),
            sa.Column("object_id", sa.Integer(), nullable=False),
            sa.Column("original_source_type", sa.String(), nullable=True),
            sa.Column("original_source_id", sa.String(), nullable=True),
            sa.Column("source_title", sa.String(), nullable=True),
            sa.Column("source_date", sa.String(), nullable=True),
            sa.Column("capture_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("source_excerpt", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("confidence", sa.String(), nullable=True),
            sa.Column("verification_state", sa.String(), nullable=True),
            sa.Column("memory_classification", sa.String(), nullable=True),
            sa.Column("superseded_by_type", sa.String(), nullable=True),
            sa.Column("superseded_by_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("id", "object_type", "object_id", "original_source_type", "capture_date", "verification_state", "memory_classification", "created_at", "updated_at"):
            op.create_index(op.f(f"ix_provenance_records_{column}"), "provenance_records", [column], unique=False)

    if "revision_records" not in existing_tables:
        op.create_table(
            "revision_records",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("object_type", sa.String(), nullable=False),
            sa.Column("object_id", sa.Integer(), nullable=False),
            sa.Column("changed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("changed_by", sa.String(), nullable=True),
            sa.Column("change_type", sa.String(), nullable=True),
            sa.Column("before", sa.JSON(), nullable=True),
            sa.Column("after", sa.JSON(), nullable=True),
            sa.Column("source_type", sa.String(), nullable=True),
            sa.Column("source_id", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("id", "object_type", "object_id", "changed_at"):
            op.create_index(op.f(f"ix_revision_records_{column}"), "revision_records", [column], unique=False)

    if "review_alerts" not in existing_tables:
        op.create_table(
            "review_alerts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("alert_type", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("object_type", sa.String(), nullable=True),
            sa.Column("object_id", sa.Integer(), nullable=True),
            sa.Column("related_object_type", sa.String(), nullable=True),
            sa.Column("related_object_id", sa.Integer(), nullable=True),
            sa.Column("evidence", sa.JSON(), nullable=True),
            sa.Column("resolution", sa.Text(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("id", "alert_type", "title", "severity", "status", "resolved_at", "created_at", "updated_at"):
            op.create_index(op.f(f"ix_review_alerts_{column}"), "review_alerts", [column], unique=False)

    if "integration_inbox_items" not in existing_tables:
        op.create_table(
            "integration_inbox_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("source_type", sa.String(), nullable=False),
            sa.Column("source_identifier", sa.String(), nullable=True),
            sa.Column("source_title", sa.String(), nullable=True),
            sa.Column("source_date", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column("extracted_text", sa.Text(), nullable=True),
            sa.Column("suggested_updates", sa.JSON(), nullable=True),
            sa.Column("rejected_suggestions", sa.JSON(), nullable=True),
            sa.Column("confidence", sa.String(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("id", "source_type", "source_identifier", "status", "created_at", "updated_at"):
            op.create_index(op.f(f"ix_integration_inbox_items_{column}"), "integration_inbox_items", [column], unique=False)

    if "entity_aliases" not in existing_tables:
        op.create_table(
            "entity_aliases",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("entity_type", sa.String(), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("alias", sa.String(), nullable=False),
            sa.Column("confidence", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("id", "entity_type", "entity_id", "alias", "created_at", "updated_at"):
            op.create_index(op.f(f"ix_entity_aliases_{column}"), "entity_aliases", [column], unique=False)

    if "dashboard_configs" not in existing_tables:
        op.create_table(
            "dashboard_configs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company", sa.String(), nullable=False),
            sa.Column("modules", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company"),
        )
        op.create_index(op.f("ix_dashboard_configs_id"), "dashboard_configs", ["id"], unique=False)
        op.create_index(op.f("ix_dashboard_configs_company"), "dashboard_configs", ["company"], unique=False)
        op.create_index(op.f("ix_dashboard_configs_created_at"), "dashboard_configs", ["created_at"], unique=False)
        op.create_index(op.f("ix_dashboard_configs_updated_at"), "dashboard_configs", ["updated_at"], unique=False)

    if "search_conversations" not in existing_tables:
        op.create_table(
            "search_conversations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("conversation_id", sa.String(), nullable=False),
            sa.Column("last_query", sa.Text(), nullable=True),
            sa.Column("context", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("conversation_id"),
        )
        op.create_index(op.f("ix_search_conversations_id"), "search_conversations", ["id"], unique=False)
        op.create_index(op.f("ix_search_conversations_conversation_id"), "search_conversations", ["conversation_id"], unique=False)
        op.create_index(op.f("ix_search_conversations_created_at"), "search_conversations", ["created_at"], unique=False)
        op.create_index(op.f("ix_search_conversations_updated_at"), "search_conversations", ["updated_at"], unique=False)


def downgrade() -> None:
    for table, columns in [
        ("search_conversations", ["updated_at", "created_at", "conversation_id", "id"]),
        ("dashboard_configs", ["updated_at", "created_at", "company", "id"]),
        ("entity_aliases", ["updated_at", "created_at", "alias", "entity_id", "entity_type", "id"]),
        ("integration_inbox_items", ["updated_at", "created_at", "status", "source_identifier", "source_type", "id"]),
        ("review_alerts", ["updated_at", "created_at", "resolved_at", "status", "severity", "title", "alert_type", "id"]),
        ("revision_records", ["changed_at", "object_id", "object_type", "id"]),
        ("provenance_records", ["updated_at", "created_at", "memory_classification", "verification_state", "capture_date", "original_source_type", "object_id", "object_type", "id"]),
    ]:
        for column in columns:
            op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)
        op.drop_table(table)
