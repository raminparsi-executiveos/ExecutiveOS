import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app

client = TestClient(app)


def test_people_can_be_created_and_listed():
    payload = {
        "attributes": {
            "name": "Mina",
            "role": "VP of Ops",
            "company": "PEC",
            "responsibilities": ["Operations"],
            "current_priorities": ["Scaling delivery"],
        }
    }

    create_response = client.post('/objects/people', json=payload)
    assert create_response.status_code == 200

    list_response = client.get('/objects/people')
    assert list_response.status_code == 200
    data = list_response.json()
    assert data['items']
    assert data['total'] >= len(data['items'])
    assert data['limit'] == 50
    assert any(item['name'] == 'Mina' for item in data['items'])


def test_objects_reject_unknown_fields():
    response = client.post('/objects/people', json={'attributes': {'name': 'Kai', 'admin': True}})
    assert response.status_code == 422
    assert response.json()['detail'] == 'Unknown fields: admin'


def test_objects_require_identity_fields():
    missing_name = client.post('/objects/people', json={'attributes': {'role': 'Ops'}})
    assert missing_name.status_code == 422
    assert missing_name.json()['detail'] == 'Missing required field: name'

    missing_title = client.post('/objects/projects', json={'attributes': {'company': 'PEC'}})
    assert missing_title.status_code == 422
    assert missing_title.json()['detail'] == 'Missing required field: title'


def test_objects_can_be_updated_and_deleted():
    created = client.post('/objects/projects', json={
        'attributes': {
            'title': 'Editable rollout',
            'company': 'PEC',
            'status': 'active',
        }
    })
    assert created.status_code == 200
    project_id = created.json()['object']['id']

    updated = client.patch(f'/objects/projects/{project_id}', json={
        'attributes': {
            'status': 'paused',
            'next_steps': ['Decide owner'],
        }
    })
    assert updated.status_code == 200
    assert updated.json()['object']['status'] == 'paused'
    assert updated.json()['object']['next_steps'] == ['Decide owner']

    rejected = client.patch(f'/objects/projects/{project_id}', json={'attributes': {'admin': True}})
    assert rejected.status_code == 422

    blank_title = client.patch(f'/objects/projects/{project_id}', json={'attributes': {'title': '  '}})
    assert blank_title.status_code == 422
    assert blank_title.json()['detail'] == 'Missing required field: title'

    deleted = client.delete(f'/objects/projects/{project_id}')
    assert deleted.status_code == 200
    assert deleted.json()['id'] == project_id

    missing = client.patch(f'/objects/projects/{project_id}', json={'attributes': {'status': 'active'}})
    assert missing.status_code == 404
