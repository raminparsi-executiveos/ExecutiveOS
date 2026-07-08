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
    create('metrics', {
        'title': 'Distributor count', 'company': 'EverPole', 'value': '17', 'trend': 'up 3',
    })
    count = client.post('/search', json={'query': 'How many distributors does EverPole have?'}).json()
    assert count['answer'] == '17'

    questions = client.post('/search', json={'query': 'What are all open questions?'}).json()
    assert 'Should PEC accelerate volume hiring?' in questions['answer']
    assert 'Can RYSE add volume weekend intake?' in questions['answer']
