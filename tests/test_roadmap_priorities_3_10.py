import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app


client = TestClient(app)


def create(object_type, attributes):
    response = client.post(f'/objects/{object_type}', json={'attributes': attributes})
    assert response.status_code == 200
    return response.json()['object']


def test_provenance_revision_and_classification_are_stored_for_approved_capture():
    saved = client.post('/capture/confirm', json={
        'text': 'Kyle will send the PEC client recovery plan.',
        'classification_source': 'ai',
        'approved_updates': [{
            'type': 'task',
            'title': 'Kyle will send the PEC client recovery plan',
            'company': 'PEC',
            'owner': 'Kyle',
            'status': 'open',
            'priority': 'high',
            'memory_classification': 'commitment',
            'verification_state': 'user_confirmed',
        }],
    })
    assert saved.status_code == 200

    task = next(item for item in client.get('/objects/tasks').json()['items'] if item['title'] == 'Kyle will send the PEC client recovery plan')
    history = client.get(f"/objects/task/{task['id']}/history").json()
    assert history['provenance']
    assert history['provenance'][0]['memory_classification'] == 'commitment'
    assert history['provenance'][0]['verification_state'] == 'user_confirmed'
    assert history['revisions']


def test_review_alert_generation_and_resolution():
    task = create('tasks', {
        'title': 'Overdue PEC review alert task',
        'company': 'PEC',
        'status': 'open',
        'priority': 'critical',
        'due_date': '2020-01-01',
    })

    alerts = client.get('/review-alerts?refresh=true').json()['items']
    overdue = next(alert for alert in alerts if alert['object_type'] == 'tasks' and alert['object_id'] == task['id'])
    assert overdue['alert_type'] == 'task_overdue'

    resolved = client.post(f"/review-alerts/{overdue['id']}/resolve", json={
        'action': 'dismiss',
        'resolution': 'Handled outside ExecutiveOS.',
    })
    assert resolved.status_code == 200
    assert resolved.json()['alert']['status'] == 'dismissed'


def test_dynamic_meeting_prep_supports_type_and_section_exclusion():
    create('tasks', {
        'title': 'PEC overdue client recovery commitment',
        'company': 'PEC',
        'owner': 'Kyle',
        'status': 'open',
        'priority': 'high',
        'due_date': '2020-01-01',
    })
    prep = client.post('/meeting-prep', json={
        'meeting': 'PEC client recovery meeting',
        'meeting_type': 'client recovery',
        'excluded_sections': ['sensitive_people_context'],
    }).json()
    assert prep['meeting_type'] == 'client recovery'
    assert prep['meeting_objective']
    assert 'PEC overdue client recovery commitment' in prep['overdue_tasks']
    assert prep['sensitive_people_context'] == []
    assert prep['inclusion_reasons']['tasks']


def test_search_filters_categories_and_conversation_context():
    create('tasks', {
        'title': 'RYSE admissions follow-up',
        'company': 'RYSE Wellness',
        'owner': 'Sam',
        'status': 'open',
        'priority': 'high',
    })
    create('tasks', {
        'title': 'PEC sales follow-up',
        'company': 'PEC',
        'owner': 'Avery',
        'status': 'open',
        'priority': 'low',
    })

    response = client.post('/search', json={
        'query': 'What follow-up tasks are open?',
        'company': 'RYSE Wellness',
        'record_types': ['task'],
        'status': 'open',
    }).json()
    assert response['conversation_id']
    assert response['directly_supported_facts']
    assert 'missing_information' in response
    assert any(result['title'] == 'RYSE admissions follow-up' for result in response['results'])
    assert all(result['title'] != 'PEC sales follow-up' for result in response['results'])


def test_company_dashboard_config_and_data_freshness():
    create('metrics', {
        'title': 'Census',
        'company': 'RYSE Wellness',
        'value': '18',
        'trend': 'up',
    })
    dashboard = client.get('/dashboards/RYSE Wellness').json()
    assert dashboard['company'] == 'RYSE Wellness'
    assert dashboard['modules']
    assert dashboard['data_freshness']

    updated = client.put('/dashboards/RYSE Wellness/config', json={'modules': [
        {'name': 'Census', 'visible': True, 'order': 0},
        {'name': 'Hidden', 'visible': False, 'order': 1},
    ]})
    assert updated.status_code == 200
    refreshed = client.get('/dashboards/RYSE Wellness').json()
    assert [module['name'] for module in refreshed['modules']] == ['Census']


def test_integration_inbox_preserves_source_and_requires_review_before_save():
    item = client.post('/integration-inbox', json={
        'source_type': 'uploaded_document',
        'source_identifier': 'doc-1',
        'source_title': 'PEC recovery notes',
        'source_date': '2026-07-09',
        'extracted_text': 'PEC: Kyle will follow up on the recovery notes.',
    })
    assert item.status_code == 200
    payload = item.json()['item']
    assert payload['status'] == 'new'
    assert payload['suggested_updates']

    before = client.get('/objects/tasks').json()['total']
    approved = client.post(f"/integration-inbox/{payload['id']}/approve", json={'suggestion_indexes': [0]})
    assert approved.status_code == 200
    after = client.get('/objects/tasks').json()['total']
    assert after >= before


def test_entity_aliases_and_resolution_suggestions():
    company = next(item for item in client.get('/objects/companies').json()['items'] if item['name'] == 'PEC')
    alias = client.post('/entity-aliases', json={
        'entity_type': 'companies',
        'entity_id': company['id'],
        'alias': 'Pro Engineering Consulting',
    })
    assert alias.status_code == 200

    suggestions = client.get('/entity-resolution/suggestions').json()['items']
    assert any('Pro Engineering Consulting' in suggestion['names'] for suggestion in suggestions)
