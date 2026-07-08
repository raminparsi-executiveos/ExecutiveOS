import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app

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
