from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import CaptureMutation, CaptureRecord, Task


def capture_observability(db: Session, days: int = 30) -> dict[str, Any]:
    days = max(1, min(days, 365))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    captures = (
        db.query(CaptureRecord)
        .filter(CaptureRecord.created_at >= since)
        .order_by(CaptureRecord.created_at.desc())
        .all()
    )
    source_counts = Counter(capture.classification_source or "unknown" for capture in captures)
    total = len(captures)
    saved_total = sum(capture.saved_count or 0 for capture in captures)
    fallback_total = sum(source_counts[source] for source in ("local_fallback", "image_unavailable", "unknown"))
    mutations = (
        db.query(CaptureMutation)
        .filter(CaptureMutation.created_at >= since)
        .all()
    )
    mutation_operations = Counter(mutation.operation or "unknown" for mutation in mutations)
    rejected_total = sum(1 for mutation in mutations if mutation.status == "rejected")
    edited_total = sum(len(mutation.user_edits or []) for mutation in mutations)
    mismatches = sum(
        1
        for mutation in mutations
        if mutation.status == "approved_applied"
        and mutation.approved_values
        and mutation.persisted_values
        and any(
            mutation.approved_values.get(field) not in (None, "", [])
            and mutation.persisted_values.get(field) != mutation.approved_values.get(field)
            for field in mutation.approved_values
            if field not in {"type", "operation", "matched_record_id", "match_confidence", "field_operations", "explanation"}
        )
    )
    tasks = db.query(Task).filter(Task.created_at >= since).all()
    task_missing = {
        "owner": sum(1 for task in tasks if not task.owner),
        "due_date": sum(1 for task in tasks if not task.due_date),
        "next_action": sum(1 for task in tasks if not task.next_action),
        "definition_of_done": sum(1 for task in tasks if not task.definition_of_done),
        "expected_deliverable": sum(1 for task in tasks if not task.expected_deliverable),
    }
    return {
        "window_days": days,
        "total_captures": total,
        "saved_updates": saved_total,
        "average_saved_updates": round(saved_total / total, 2) if total else 0,
        "classification_sources": dict(sorted(source_counts.items())),
        "ai_captures": source_counts.get("ai", 0),
        "fallback_captures": fallback_total,
        "fallback_rate": round(fallback_total / total, 3) if total else 0,
        "image_unavailable": source_counts.get("image_unavailable", 0),
        "no_saved_update_captures": sum(1 for capture in captures if not capture.saved_count),
        "no_saved_update_rate": round(sum(1 for capture in captures if not capture.saved_count) / total, 3) if total else 0,
        "records_created": mutation_operations.get("create", 0),
        "records_updated": mutation_operations.get("update", 0) + mutation_operations.get("merge", 0),
        "likely_duplicate_create_rate": round(
            sum(1 for mutation in mutations if mutation.operation == "create" and mutation.matched_record_id) / max(1, mutation_operations.get("create", 0)),
            3,
        ) if mutations else 0,
        "average_tasks_per_capture": round(len(tasks) / total, 2) if total else 0,
        "task_missing_fields": task_missing,
        "user_edits_before_approval": edited_total,
        "rejected_suggestions": rejected_total,
        "approved_persisted_mismatches": mismatches,
        "screenshot_unavailable_rate": round(source_counts.get("image_unavailable", 0) / total, 3) if total else 0,
        "prompt_versions": dict(Counter(capture.prompt_version or "unknown" for capture in captures)),
        "recent": [
            {
                "id": capture.id,
                "classification_source": capture.classification_source or "unknown",
                "saved_count": capture.saved_count or 0,
                "created_at": capture.created_at.isoformat() if capture.created_at else "",
                "preview": capture.raw_text[:120],
            }
            for capture in captures[:10]
        ],
    }
