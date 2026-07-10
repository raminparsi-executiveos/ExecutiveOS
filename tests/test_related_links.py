import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app


client = TestClient(app)


def test_related_endpoint_returns_explicit_and_company_links():
    person = client.post('/objects/people', json={'attributes': {
        'name': 'Priya Linktest',
        'company': 'PEC',
        'linked_projects': ['Link Graph Rollout'],
        'linked_decisions': ['Approve link graph'],
    }}).json()['object']
    client.post('/objects/projects', json={'attributes': {
        'title': 'Link Graph Rollout',
        'company': 'PEC',
        'linked_people': ['Priya Linktest'],
    }})
    client.post('/objects/decisions', json={'attributes': {
        'title': 'Approve link graph',
        'company': 'PEC',
        'linked_people': ['Priya Linktest'],
    }})

    response = client.get(f"/objects/people/{person['id']}/related")
    assert response.status_code == 200
    related = response.json()['related']
    assert any(item['label'] == 'Link Graph Rollout' for item in related['projects'])
    assert any(item['label'] == 'Approve link graph' for item in related['decisions'])
    assert any(item['label'] == 'PEC' for item in related['companies'])


def test_related_endpoint_links_meetings_and_tasks_by_source():
    meeting = client.post('/objects/meetings', json={'attributes': {
        'title': 'Link graph meeting',
        'company': 'PEC',
        'action_items': ['Priya: finish link graph'],
    }}).json()['object']
    tasks = client.get('/objects/tasks').json()['items']
    task = next(item for item in tasks if item['title'] == 'Priya: finish link graph')

    meeting_related = client.get(f"/objects/meetings/{meeting['id']}/related").json()['related']
    assert any(item['label'] == 'Priya: finish link graph' for item in meeting_related['tasks'])

    task_related = client.get(f"/objects/tasks/{task['id']}/related").json()['related']
    assert any(item['label'] == 'Link graph meeting' for item in task_related['meetings'])


def test_related_endpoint_404s_for_missing_object():
    response = client.get('/objects/people/999999/related')
    assert response.status_code == 404
