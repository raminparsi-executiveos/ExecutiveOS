import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app

client = TestClient(app)


def test_login_protects_memory_endpoints(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('EXECUTIVEOS_USERNAME', 'owner')
    monkeypatch.setenv('EXECUTIVEOS_PASSWORD', 'correct horse battery staple')
    monkeypatch.setenv('SESSION_SECRET', 'test-secret-that-is-long-and-random')

    status = client.get('/auth/status')
    status_payload = status.json()
    assert status_payload['required'] is True
    assert status_payload['configured'] is True
    assert all(status_payload['checks'].values())
    assert status_payload['ai']['openai_configured'] is False
    assert status_payload['ai']['model']
    assert client.get('/briefing').status_code == 401

    rejected = client.post('/auth/login', json={'username': 'owner', 'password': 'wrong'})
    assert rejected.status_code == 401

    login = client.post(
        '/auth/login',
        json={'username': 'owner', 'password': 'correct horse battery staple'},
    )
    assert login.status_code == 200
    token = login.json()['access_token']
    authorized = client.get('/briefing', headers={'Authorization': f'Bearer {token}'})
    assert authorized.status_code == 200
    assert client.get('/briefing', headers={'Authorization': 'Bearer malformed'}).status_code == 401


def test_render_fails_closed_without_credentials(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.delenv('EXECUTIVEOS_PASSWORD', raising=False)
    monkeypatch.delenv('SESSION_SECRET', raising=False)
    status_payload = client.get('/auth/status').json()
    assert status_payload['required'] is True
    assert status_payload['configured'] is False
    assert status_payload['checks']['password_present'] is False
    assert status_payload['checks']['session_secret_present'] is False
    assert client.get('/briefing').status_code == 503
