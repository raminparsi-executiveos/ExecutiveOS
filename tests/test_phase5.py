import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app
from app.ai import CaptureAnalysis, SuggestedUpdate
from app.models import Company
from app.database import SessionLocal
from sqlalchemy.exc import SQLAlchemyError

client = TestClient(app)


def test_capture_classify_and_confirm_flow():
    classify_response = client.post(
        '/capture/classify',
        json={
            'text': 'Julio is now responsible for PM quality and high-priority clients. His pay is increasing from $14.42/hr to $17.50/hr.',
            'confirm': False,
        },
    )
    assert classify_response.status_code == 200
    payload = classify_response.json()
    assert payload['suggested_updates']
    assert any(update['type'] == 'person' for update in payload['suggested_updates'])

    confirm_response = client.post(
        '/capture/confirm',
        json={
            'text': 'Julio is now responsible for PM quality and high-priority clients. His pay is increasing from $14.42/hr to $17.50/hr.',
            'approved_updates': payload['suggested_updates'],
        },
    )
    assert confirm_response.status_code == 200

    people_response = client.get('/objects/people')
    people = people_response.json()['items']
    assert any(item['name'] == 'Julio' for item in people)


def test_ai_classification_handles_arbitrary_executive_memory(monkeypatch):
    def fake_analysis(text, memory_context):
        assert 'Companies:' in memory_context
        return CaptureAnalysis(
            suggested_updates=[
                SuggestedUpdate(
                    type='project',
                    title='Northstar launch',
                    company='Acme',
                    owner='Priya',
                    status='active',
                    details='Launch the new operating model.',
                )
            ],
            follow_ups=['What date should the launch be reviewed?'],
        )

    monkeypatch.setattr('app.main.analyze_capture', fake_analysis)
    classified = client.post('/capture/classify', json={'text': 'Priya owns the Northstar launch.'})
    assert classified.status_code == 200
    payload = classified.json()
    assert payload['classification_source'] == 'ai'
    assert payload['suggested_updates'][0]['title'] == 'Northstar launch'
    assert payload['follow_ups']

    confirmed = client.post(
        '/capture/confirm',
        json={'text': 'Priya owns the Northstar launch.', 'approved_updates': payload['suggested_updates']},
    )
    assert confirmed.status_code == 200
    projects = client.get('/objects/projects').json()['items']
    assert any(project['title'] == 'Northstar launch' and project['owner'] == 'Priya' for project in projects)


def test_saved_memory_feeds_briefing_prep_and_search():
    update = SuggestedUpdate(
        type='project',
        title='Zephyr expansion',
        company='Acme',
        owner='Morgan',
        status='active',
        objective='Expand Zephyr into the northwest region.',
        risks=['Distributor capacity'],
    )
    saved = client.post(
        '/capture/confirm',
        json={'text': 'Morgan owns the Zephyr northwest expansion.', 'approved_updates': [update.model_dump()]},
    )
    assert saved.status_code == 200
    assert saved.json()['saved_count'] == 1

    briefing = client.get('/briefing').json()
    assert 'Zephyr expansion' in briefing['top_priorities']

    prep = client.post('/meeting-prep', json={'meeting': 'Zephyr leadership review'}).json()
    assert 'Zephyr expansion' in prep['related_projects']
    assert 'Distributor capacity' in prep['risks']

    search = client.post('/search', json={'query': 'Zephyr northwest'}).json()
    assert any(result['type'] == 'project' and result['title'] == 'Zephyr expansion' for result in search['results'])

    history = client.get('/captures?limit=1').json()
    assert history['total'] >= 1
    assert history['items'][0]['saved_count'] >= 1


def test_capture_confirmation_rolls_back_partial_updates(monkeypatch):
    company_name = 'Atomic Rollback Company'

    def fail_generic_update(db, update):
        raise SQLAlchemyError('forced failure')

    monkeypatch.setattr('app.main._apply_generic_update', fail_generic_update)
    response = client.post(
        '/capture/confirm',
        json={
            'text': 'Create two linked records.',
            'approved_updates': [
                SuggestedUpdate(type='company', name=company_name).model_dump(),
                SuggestedUpdate(type='project', title='Should not persist').model_dump(),
            ],
        },
    )
    assert response.status_code == 500
    with SessionLocal() as db:
        assert db.query(Company).filter(Company.name == company_name).first() is None
