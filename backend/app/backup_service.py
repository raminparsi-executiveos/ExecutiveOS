from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.orm import Session

from .models import (
    BriefingView,
    CaptureRecord,
    Company,
    DashboardConfig,
    Decision,
    Document,
    EntityAlias,
    IntegrationInboxItem,
    Meeting,
    Metric,
    Person,
    Project,
    ProvenanceRecord,
    RevisionRecord,
    ReviewAlert,
    SOP,
    SearchConversation,
    StrategicIssue,
    Task,
)


BACKUP_SCHEMA_VERSION = 1
BACKUP_MODELS = [
    Company,
    Person,
    StrategicIssue,
    Project,
    Decision,
    Meeting,
    SOP,
    Document,
    Metric,
    Task,
    CaptureRecord,
    BriefingView,
    ProvenanceRecord,
    RevisionRecord,
    ReviewAlert,
    IntegrationInboxItem,
    EntityAlias,
    DashboardConfig,
    SearchConversation,
]
BACKUP_MODEL_BY_TABLE = {model.__tablename__: model for model in BACKUP_MODELS}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_instance(instance: Any) -> dict[str, Any]:
    return {
        column.name: _serialize_value(getattr(instance, column.key))
        for column in instance.__table__.columns
    }


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _deserialize_record(model: type[Any], record: dict[str, Any]) -> dict[str, Any]:
    columns = {column.name: column for column in model.__table__.columns}
    unknown = sorted(set(record) - set(columns))
    if unknown:
        raise ValueError(f"{model.__tablename__} contains unknown fields: {', '.join(unknown)}")
    values: dict[str, Any] = {}
    for name, column in columns.items():
        if name not in record:
            continue
        value = record[name]
        if isinstance(column.type, DateTime):
            value = _parse_datetime(value)
        values[column.key] = value
    return values


def export_backup(db: Session) -> dict[str, Any]:
    records = {
        model.__tablename__: [
            _serialize_instance(item)
            for item in db.query(model).order_by(model.id.asc()).all()
        ]
        for model in BACKUP_MODELS
    }
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "application": "ExecutiveOS",
        "records": records,
    }


def import_backup(db: Session, backup: dict[str, Any], mode: str = "merge") -> dict[str, Any]:
    if mode not in {"merge", "replace"}:
        raise ValueError("Import mode must be merge or replace")
    if backup.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise ValueError(f"Unsupported backup schema version: {backup.get('schema_version')}")
    records = backup.get("records")
    if not isinstance(records, dict):
        raise ValueError("Backup records must be an object")
    unknown_tables = sorted(set(records) - set(BACKUP_MODEL_BY_TABLE))
    if unknown_tables:
        raise ValueError(f"Backup contains unsupported tables: {', '.join(unknown_tables)}")

    counts = {model.__tablename__: 0 for model in BACKUP_MODELS}
    if mode == "replace":
        for model in reversed(BACKUP_MODELS):
            db.query(model).delete()
        db.flush()

    for table_name, table_records in records.items():
        if not isinstance(table_records, list):
            raise ValueError(f"{table_name} records must be a list")
        model = BACKUP_MODEL_BY_TABLE[table_name]
        for raw_record in table_records:
            if not isinstance(raw_record, dict):
                raise ValueError(f"{table_name} record must be an object")
            values = _deserialize_record(model, raw_record)
            record_id = values.get("id")
            instance = db.get(model, record_id) if record_id is not None else None
            if instance is None:
                instance = model(**values)
            else:
                for field, value in values.items():
                    setattr(instance, field, value)
            db.add(instance)
            counts[table_name] += 1
    db.flush()
    return {
        "mode": mode,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "imported_counts": {table: count for table, count in counts.items() if count},
        "total_imported": sum(counts.values()),
    }
