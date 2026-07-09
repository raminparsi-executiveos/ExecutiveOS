from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .database import engine


MEMORY_TABLES = {
    "companies",
    "people",
    "strategic_issues",
    "projects",
    "decisions",
    "meetings",
    "sops",
    "documents",
    "metrics",
    "capture_records",
}


def alembic_config() -> Config:
    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    return Config(str(config_path))


def stamp_existing_schema_if_needed(config: Config) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "alembic_version" in tables or not (tables & MEMORY_TABLES):
        return

    company_columns = {
        column["name"]
        for column in inspector.get_columns("companies")
    } if "companies" in tables else set()
    revision = (
        "0002_add_memory_timestamps"
        if {"created_at", "updated_at"} <= company_columns
        else "0001_initial_schema"
    )
    command.stamp(config, revision)


def main() -> None:
    config = alembic_config()
    stamp_existing_schema_if_needed(config)
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
