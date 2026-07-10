import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app


client = TestClient(app)


def test_backup_export_contains_memory_and_metadata():
    response = client.get('/backup/export')
    assert response.status_code == 200
    backup = response.json()
    assert backup['schema_version'] == 1
    assert backup['application'] == 'ExecutiveOS'
    assert 'exported_at' in backup
    assert 'people' in backup['records']
    assert any(person['name'] == 'Julio' for person in backup['records']['people'])
    assert 'tasks' in backup['records']
    assert 'provenance_records' in backup['records']


def test_backup_merge_import_adds_records():
    backup = client.get('/backup/export').json()
    backup['records']['people'].append({
        'id': 9999,
        'name': 'Backup Person',
        'role': 'Advisor',
        'company': 'PEC',
        'responsibilities': [],
        'strengths': [],
        'concerns': [],
        'current_priorities': [],
        'performance_notes': [],
        'linked_projects': [],
        'linked_decisions': [],
        'linked_meetings': [],
        'created_at': '2026-07-10T12:00:00+00:00',
        'updated_at': '2026-07-10T12:00:00+00:00',
    })

    imported = client.post('/backup/import', json={'backup': backup, 'mode': 'merge'})
    assert imported.status_code == 200
    assert imported.json()['total_imported'] >= 1

    people = client.get('/objects/people').json()['items']
    assert any(person['name'] == 'Backup Person' for person in people)


def test_backup_replace_restores_exported_state():
    backup = client.get('/backup/export').json()
    created = client.post('/objects/people', json={'attributes': {
        'name': 'Temporary Import Test',
        'company': 'PEC',
    }})
    assert created.status_code == 200

    replaced = client.post('/backup/import', json={'backup': backup, 'mode': 'replace'})
    assert replaced.status_code == 200

    people = client.get('/objects/people').json()['items']
    assert not any(person['name'] == 'Temporary Import Test' for person in people)
    assert any(person['name'] == 'Julio' for person in people)


def test_backup_import_rejects_invalid_payloads():
    bad_version = client.post('/backup/import', json={
        'backup': {'schema_version': 999, 'records': {}},
        'mode': 'merge',
    })
    assert bad_version.status_code == 422

    bad_table = client.post('/backup/import', json={
        'backup': {'schema_version': 1, 'records': {'unknown_table': []}},
        'mode': 'merge',
    })
    assert bad_table.status_code == 422

    bad_mode = client.post('/backup/import', json={
        'backup': {'schema_version': 1, 'records': {}},
        'mode': 'overwrite',
    })
    assert bad_mode.status_code == 422
