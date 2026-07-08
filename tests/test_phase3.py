import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app

client = TestClient(app)


def test_capture_creates_person_and_decision_updates():
    response = client.post(
        '/capture',
        json={
            'text': 'Julio is now responsible for PM quality and high-priority clients. His pay is increasing from $14.42/hr to $17.50/hr.',
            'confirm': True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload['confirm'] is True
    assert payload['suggested_updates']

    people_response = client.get('/objects/people')
    people = people_response.json()['items']
    assert any(item['name'] == 'Julio' and 'PM quality' in item['current_priorities'] for item in people)

    decisions_response = client.get('/objects/decisions')
    decisions = decisions_response.json()['items']
    assert any('Julio' in item['title'] for item in decisions)


def test_briefing_and_meeting_prep_and_search_work():
    briefing = client.get('/briefing').json()
    assert 'top_priorities' in briefing
    assert len(briefing['top_priorities']) >= 3

    prep = client.post('/meeting-prep', json={'meeting': 'RYSE leadership meeting'}).json()
    assert 'agenda' in prep
    assert prep['agenda']

    search = client.post('/search', json={'query': 'Why did we promote Julio?'}).json()
    assert search['results']
    assert search['results'][0]['title'] == 'Julio promotion and pay increase'
    assert 'Increase census' not in [result['title'] for result in search['results']]
    assert 'RYSE Wellness' not in [result['title'] for result in search['results']]
    assert search['answer'] == search['results'][0]['summary']
