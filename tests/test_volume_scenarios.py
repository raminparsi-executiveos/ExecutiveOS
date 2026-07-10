import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app

client = TestClient(app)


def create(object_type, attributes):
    response = client.post(f'/objects/{object_type}', json={'attributes': attributes})
    assert response.status_code == 200


def test_rich_memory_questions_return_the_requested_fields():
    create('projects', {
        'title': 'Volume Northstar rollout', 'company': 'PEC', 'owner': 'Avery Chen',
        'status': 'active', 'objective': 'Replace the legacy ERP',
        'risks': ['Volume data migration delay'], 'next_steps': ['Complete volume vendor mapping'],
    })
    create('decisions', {
        'title': 'Volume Atlas selection', 'company': 'PEC', 'final_decision': 'Choose Atlas',
        'reasoning': 'Best field workflow', 'review_date': '2026-09-01',
    })
    create('metrics', {
        'title': 'Volume project margin', 'company': 'PEC', 'value': '31%', 'trend': 'down 2 points',
    })

    assert client.post('/search', json={'query': 'Who owns Volume Northstar rollout?'}).json()['answer'] == 'Avery Chen'
    assert client.post('/search', json={'query': 'What are the risks for Volume Northstar rollout?'}).json()['answer'] == 'Volume data migration delay'
    assert client.post('/search', json={'query': 'What is the next step for Volume Northstar rollout?'}).json()['answer'] == 'Complete volume vendor mapping'
    assert client.post('/search', json={'query': 'Why did we make the Volume Atlas selection?'}).json()['answer'] == 'Best field workflow'
    assert client.post('/search', json={'query': 'When should we review Volume Atlas selection?'}).json()['answer'] == '2026-09-01'
    assert client.post('/search', json={'query': 'How is Volume project margin trending?'}).json()['answer'] == 'down 2 points'


def test_company_meeting_actions_and_search_stay_isolated():
    create('meetings', {
        'title': 'Volume PEC operating review', 'company': 'PEC',
        'action_items': ['Avery: complete the volume ERP map'],
        'open_questions': ['Should PEC accelerate volume hiring?'],
    })
    create('meetings', {
        'title': 'Volume RYSE census review', 'company': 'RYSE Wellness',
        'action_items': ['Sam: call volume referral partners'],
        'open_questions': ['Can RYSE add volume weekend intake?'],
    })

    pec = client.post('/meeting-prep', json={'meeting': 'PEC leadership review'}).json()
    assert 'Avery: complete the volume ERP map' in pec['action_items']
    assert 'Sam: call volume referral partners' not in pec['action_items']

    ryse_actions = client.post('/search', json={'query': 'What action items are open at RYSE?'}).json()
    assert 'Sam: call volume referral partners' in ryse_actions['answer']
    assert 'Avery: complete the volume ERP map' not in ryse_actions['answer']


def test_plural_quantity_and_aggregate_questions():
    create('meetings', {
        'title': 'Volume PEC operating review', 'company': 'PEC',
        'action_items': ['Avery: complete the volume ERP map'],
        'open_questions': ['Should PEC accelerate volume hiring?'],
    })
    create('meetings', {
        'title': 'Volume RYSE census review', 'company': 'RYSE Wellness',
        'action_items': ['Sam: call volume referral partners'],
        'open_questions': ['Can RYSE add volume weekend intake?'],
    })
    create('metrics', {
        'title': 'Distributor count', 'company': 'EverPole', 'value': '17', 'trend': 'up 3',
    })
    count = client.post('/search', json={'query': 'How many distributors does EverPole have?'}).json()
    assert count['answer'] == '17'

    questions = client.post('/search', json={'query': 'What are all open questions?'}).json()
    assert 'Should PEC accelerate volume hiring?' in questions['answer']
    assert 'Can RYSE add volume weekend intake?' in questions['answer']


def test_employment_transition_context_reaches_every_generated_output():
    transition = (
        'Yeison is transitioning to Northwind as his primary company on August 1. '
        'He will remain part-time at PEC for 15 hours per week through September, '
        'finishing the Meridian handoff and supporting Julio on client escalations.'
    )
    saved = client.post('/capture/confirm', json={
        'text': transition,
        'classification_source': 'ai',
        'approved_updates': [{
            'type': 'person',
            'name': 'Yeison',
            'company': 'Northwind',
            'role': 'Part-time PEC transition support',
            'responsibilities': ['Finish the Meridian handoff', 'Support Julio on client escalations'],
            'current_priorities': ['Transition to Northwind', 'Complete PEC handoff'],
            'details': transition,
        }],
    })
    assert saved.status_code == 200

    yeison = next(
        person for person in client.get('/objects/people').json()['items']
        if person['name'] == 'Yeison'
    )
    assert transition in yeison['performance_notes']
    assert yeison['company'] == 'Northwind'

    search = client.post('/search', json={'query': 'What is Yeison doing part-time at PEC?'}).json()
    assert '15 hours per week' in search['answer']
    assert 'Meridian handoff' in search['answer']

    prep = client.post('/meeting-prep', json={'meeting': 'PEC Yeison transition review'}).json()
    assert 'Yeison' in prep['related_people']
    assert any('15 hours per week' in context for context in prep['recent_capture_context'])

    morning = client.get('/briefing').json()
    assert any('Yeison is transitioning' in update['label'] for update in morning['recent_updates'])


def test_capture_resolves_matching_waiting_on_item():
    create('meetings', {
        'title': 'PEC staffing review',
        'company': 'PEC',
        'action_items': [
            'Confirm Yeison working hours',
            'Ask Avery for ERP timeline',
        ],
    })

    before = client.get('/briefing').json()
    before_waiting = [item['label'] for item in before['waiting_on_items']]
    assert 'Confirm Yeison working hours' in before_waiting

    classified = client.post('/capture/classify', json={
        'text': 'Yeison will work 15 hours per week at PEC through September.',
    })
    assert classified.status_code == 200
    assert any('Confirm Yeison working hours' in follow_up for follow_up in classified.json()['follow_ups'])

    saved = client.post('/capture/confirm', json={
        'text': 'Yeison will work 15 hours per week at PEC through September.',
        'classification_source': 'ai',
        'approved_updates': [{
            'type': 'person',
            'name': 'Yeison',
            'company': 'PEC',
            'current_priorities': ['15 hours per week at PEC through September'],
        }],
    })
    assert saved.status_code == 200

    likely_resolved_waiting = [item['label'] for item in client.get('/briefing').json()['waiting_on_items']]
    assert 'Confirm Yeison working hours' not in likely_resolved_waiting

    tasks = client.get('/objects/tasks').json()['items']
    linked = next(task for task in tasks if task['title'] == 'Confirm Yeison working hours')
    assert linked['status'] == 'waiting'
    completed = client.post(f"/tasks/{linked['id']}/complete")
    assert completed.status_code == 200

    after_waiting = [item['label'] for item in client.get('/briefing').json()['waiting_on_items']]
    assert 'Confirm Yeison working hours' not in after_waiting
    assert 'Ask Avery for ERP timeline' in after_waiting


def test_briefing_hides_waiting_item_resolved_by_existing_memory():
    create('meetings', {
        'title': 'PEC staffing review',
        'company': 'PEC',
        'action_items': [
            'Confirm Yeison working hours',
            'Ask Avery for ERP timeline',
        ],
    })
    tasks = client.get('/objects/tasks').json()['items']
    linked = next(task for task in tasks if task['title'] == 'Confirm Yeison working hours')
    assert client.post(f"/tasks/{linked['id']}/complete").status_code == 200

    briefing = client.get('/briefing').json()
    waiting = [item['label'] for item in briefing['waiting_on_items']]
    assert 'Confirm Yeison working hours' not in waiting
    assert 'Ask Avery for ERP timeline' in waiting


def test_company_meeting_prep_is_driven_by_the_requested_topic():
    pm = client.post('/meeting-prep', json={'meeting': 'PEC PM meeting'}).json()
    sales = client.post('/meeting-prep', json={'meeting': 'PEC sales meeting'}).json()

    assert 'Improve PM quality' in pm['related_strategic_issues']
    assert 'Increase PEC sales' not in pm['related_strategic_issues']
    assert 'PM Quality Initiative' in pm['related_projects']
    assert 'PM quality score' in pm['metrics']
    assert 'Sales pipeline' not in pm['metrics']

    assert 'Increase PEC sales' in sales['related_strategic_issues']
    assert 'Improve PM quality' not in sales['related_strategic_issues']
    assert 'Sales pipeline' in sales['metrics']
    assert 'PM quality score' not in sales['metrics']

    assert pm['related_strategic_issues'] != sales['related_strategic_issues']
    assert pm['metrics'] != sales['metrics']
