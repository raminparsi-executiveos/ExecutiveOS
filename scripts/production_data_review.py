#!/usr/bin/env python3
"""Read-only production data quality review for ExecutiveOS.

Run from the Render backend shell where DATABASE_URL is already set:
    python scripts/production_data_review.py
"""

from __future__ import annotations

import os
import textwrap
from collections.abc import Iterable

from sqlalchemy import create_engine, inspect, text


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is not set.")
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def section(title: str) -> None:
    print(f"\n{'=' * 88}\n{title}\n{'=' * 88}")


def run(conn, sql: str, params: dict | None = None):
    return conn.execute(text(sql), params or {}).mappings().all()


def print_rows(rows: Iterable[dict], empty: str = "No rows.") -> None:
    rows = list(rows)
    if not rows:
        print(empty)
        return
    for row in rows:
        print(" | ".join(f"{key}={value}" for key, value in row.items()))


def table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def columns(inspector, table_name: str) -> set[str]:
    if not table_exists(inspector, table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def optional_count_sql(table_name: str, inspector) -> str:
    if table_exists(inspector, table_name):
        return f"select '{table_name}' as table_name, count(*) as count from {table_name}"
    return f"select '{table_name}' as table_name, null as count"


def main() -> None:
    engine = create_engine(database_url(), pool_pre_ping=True)

    with engine.connect() as conn:
        inspector = inspect(conn)

        section("Schema Snapshot")
        if table_exists(inspector, "alembic_version"):
            print_rows(run(conn, "select version_num from alembic_version"))
        else:
            print("alembic_version table is missing.")

        expected = [
            "capture_records",
            "capture_interpretations",
            "capture_mutations",
            "tasks",
            "resolvable_items",
            "companies",
            "people",
            "projects",
            "decisions",
            "meetings",
            "strategic_issues",
        ]
        print_rows({"table": name, "exists": table_exists(inspector, name)} for name in expected)

        section("Record Counts")
        count_sql = "\nunion all\n".join(optional_count_sql(name, inspector) for name in expected)
        print_rows(run(conn, count_sql))

        section("Latest Captures")
        capture_cols = columns(inspector, "capture_records")
        if capture_cols:
            screenshot_expr = "left(coalesce(screenshot_summary, ''), 90)" if "screenshot_summary" in capture_cols else "''"
            prompt_expr = "coalesce(prompt_version, '')" if "prompt_version" in capture_cols else "''"
            model_expr = "coalesce(ai_model, '')" if "ai_model" in capture_cols else "''"
            print_rows(run(conn, f"""
                select
                    id,
                    created_at,
                    coalesce(classification_source, '') as source,
                    coalesce(saved_count, 0) as saved_count,
                    {model_expr} as model,
                    {prompt_expr} as prompt,
                    left(replace(coalesce(raw_text, ''), chr(10), ' '), 180) as raw_text,
                    {screenshot_expr} as screenshot_summary
                from capture_records
                order by id desc
                limit 20
            """))

            section("Repeated Raw Captures")
            print_rows(run(conn, """
                select
                    left(replace(coalesce(raw_text, ''), chr(10), ' '), 180) as raw_text,
                    count(*) as count,
                    min(id) as first_id,
                    max(id) as last_id
                from capture_records
                group by raw_text
                having count(*) > 1
                order by count desc
                limit 20
            """))

        section("Capture Audit Coverage")
        if table_exists(inspector, "capture_records") and table_exists(inspector, "capture_interpretations"):
            print_rows(run(conn, """
                select
                    count(*) as captures,
                    count(ci.id) as captures_with_interpretation,
                    count(*) - count(ci.id) as captures_without_interpretation
                from capture_records cr
                left join capture_interpretations ci on ci.capture_id = cr.id
            """))
        else:
            print("Capture audit coverage cannot be checked because audit tables are missing.")

        if table_exists(inspector, "capture_mutations"):
            print_rows(run(conn, """
                select object_type, operation, status, count(*) as count
                from capture_mutations
                group by object_type, operation, status
                order by count desc
                limit 40
            """))

            section("Latest Capture Mutations")
            print_rows(run(conn, """
                select
                    id,
                    capture_id,
                    object_type,
                    operation,
                    status,
                    match_confidence,
                    left(coalesce(evidence_excerpt, ''), 120) as evidence,
                    left(coalesce(explanation, ''), 120) as explanation,
                    saved_record_type,
                    saved_record_id
                from capture_mutations
                order by id desc
                limit 30
            """))

        section("Task Quality")
        task_cols = columns(inspector, "tasks")
        if task_cols:
            checks = [
                ("missing_owner", "coalesce(owner, '') = '' and coalesce(assigned_to, '') = ''" if "assigned_to" in task_cols else "coalesce(owner, '') = ''"),
                ("missing_company", "coalesce(company, '') = ''"),
                ("missing_source_excerpt", "coalesce(source_excerpt, '') = ''" if "source_excerpt" in task_cols else "true"),
                ("missing_next_action", "coalesce(next_action, '') = ''"),
                ("missing_definition_of_done", "coalesce(definition_of_done, '') = ''" if "definition_of_done" in task_cols else "true"),
                ("missing_why_it_matters", "coalesce(why_it_matters, '') = ''" if "why_it_matters" in task_cols else "true"),
                ("open_or_blank_status", "coalesce(status, '') in ('', 'open')"),
            ]
            quality_sql = "\nunion all\n".join(
                f"select '{label}' as check_name, count(*) as count from tasks where {predicate}"
                for label, predicate in checks
            )
            print_rows(run(conn, quality_sql))

            print("\nLatest tasks:")
            fields = [
                "id",
                "title",
                "company",
                "owner",
                "status",
                "priority",
                "due_date",
                "left(coalesce(next_action, ''), 100) as next_action",
            ]
            for optional in ("definition_of_done", "why_it_matters", "source_excerpt", "confidence"):
                if optional in task_cols:
                    fields.append(f"left(coalesce({optional}, ''), 100) as {optional}")
            print_rows(run(conn, f"""
                select {', '.join(fields)}
                from tasks
                order by id desc
                limit 30
            """))
        else:
            print("tasks table is missing.")

        section("Duplicate Created Records")
        duplicate_queries = []
        for table_name, title_col, company_col in [
            ("people", "name", "company"),
            ("projects", "title", "company"),
            ("decisions", "title", "company"),
            ("meetings", "title", "company"),
            ("strategic_issues", "title", "company"),
            ("tasks", "title", "company"),
        ]:
            if table_exists(inspector, table_name):
                duplicate_queries.append(f"""
                    select
                        '{table_name}' as table_name,
                        lower(coalesce({title_col}, '')) as normalized_title,
                        lower(coalesce({company_col}, '')) as normalized_company,
                        count(*) as count,
                        string_agg(id::text, ',' order by id) as ids
                    from {table_name}
                    group by lower(coalesce({title_col}, '')), lower(coalesce({company_col}, ''))
                    having count(*) > 1
                """)
        if duplicate_queries:
            print_rows(run(conn, "\nunion all\n".join(duplicate_queries) + "\norder by count desc limit 50"))

        section("Resolvable Items")
        if table_exists(inspector, "resolvable_items"):
            print_rows(run(conn, """
                select parent_type, item_type, status, count(*) as count
                from resolvable_items
                group by parent_type, item_type, status
                order by count desc
            """))
            print("\nLatest open resolvable items:")
            print_rows(run(conn, """
                select
                    id,
                    parent_type,
                    parent_id,
                    item_type,
                    company,
                    status,
                    left(coalesce(display_text, ''), 160) as display_text
                from resolvable_items
                where coalesce(status, '') <> 'resolved'
                order by id desc
                limit 30
            """))
        else:
            print("resolvable_items table is missing.")

    print(textwrap.dedent("""

        Review complete. This script only read from the database.
        Paste the output back into Codex for interpretation and recommendations.
    """).strip())


if __name__ == "__main__":
    main()
