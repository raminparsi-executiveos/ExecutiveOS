import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app
from app.ai import CaptureAnalysis, SuggestedUpdate

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
