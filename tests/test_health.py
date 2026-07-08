import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_briefing_endpoint():
    response = client.get('/briefing')
    assert response.status_code == 200
    payload = response.json()
    assert 'top_priorities' in payload
    assert len(payload['top_priorities']) >= 3


def test_empty_search_is_rejected():
    response = client.post('/search', json={'query': ''})
    assert response.status_code == 422
