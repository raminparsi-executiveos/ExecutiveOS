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
    assert any(item['name'] == 'Mina' for item in data['items'])
