from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import CaptureRecord


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
