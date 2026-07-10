import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.database import SessionLocal
from app.main import app
from app.models import CaptureRecord


client = TestClient(app)


def test_capture_observability_counts_sources_and_saved_updates():
    db = SessionLocal()
    try:
        db.add(CaptureRecord(raw_text='AI classified capture', classification_source='ai', saved_count=2))
        db.add(CaptureRecord(raw_text='Fallback capture', classification_source='local_fallback', saved_count=1))
        db.add(CaptureRecord(raw_text='Image unavailable capture', classification_source='image_unavailable', saved_count=0))
        db.commit()
    finally:
        db.close()

    response = client.get('/capture/observability?days=30')
    assert response.status_code == 200
    payload = response.json()
    assert payload['total_captures'] >= 3
    assert payload['classification_sources']['ai'] >= 1
    assert payload['classification_sources']['local_fallback'] >= 1
    assert payload['classification_sources']['image_unavailable'] >= 1
    assert payload['saved_updates'] >= 3
    assert payload['fallback_captures'] >= 2
    assert payload['recent']
