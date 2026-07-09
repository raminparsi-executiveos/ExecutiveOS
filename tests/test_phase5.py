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

    monkeypatch.setattr('app.capture_service.analyze_capture', fake_analysis)
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


def test_screenshot_capture_uses_vision_and_keeps_review_flow(monkeypatch):
    image_data = 'data:image/png;base64,iVBORw0KGgo='

    def fake_vision_analysis(text, memory_context, supplied_image):
        assert text == 'Extract the revenue update from this dashboard.'
        assert 'Companies:' in memory_context
        assert supplied_image == image_data
        return CaptureAnalysis(suggested_updates=[
            SuggestedUpdate(
                type='metric', title='Screenshot revenue', company='PEC',
                value='$3.1M', trend='up 8%', source='Dashboard screenshot',
            )
        ])

    monkeypatch.setattr('app.capture_service.analyze_capture', fake_vision_analysis)
    response = client.post('/capture/classify', json={
        'text': 'Extract the revenue update from this dashboard.',
        'image_data': image_data,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload['classification_source'] == 'ai'
    assert payload['suggested_updates'][0]['title'] == 'Screenshot revenue'
    assert payload['suggested_updates'][0]['value'] == '$3.1M'


def test_screenshot_capture_validates_input_and_reports_missing_ai(monkeypatch):
    assert client.post('/capture/classify', json={'text': ''}).status_code == 422
    assert client.post('/capture/classify', json={
        'image_data': 'data:image/svg+xml;base64,PHN2Zz4=',
    }).status_code == 422

    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory, image: None)
    unavailable = client.post('/capture/classify', json={
        'image_data': 'data:image/jpeg;base64,/9j/2Q==',
    })
    assert unavailable.status_code == 200
    assert unavailable.json()['classification_source'] == 'image_unavailable'
    assert unavailable.json()['suggested_updates'] == []
    assert unavailable.json()['follow_ups']


def test_text_only_capture_accepts_explicit_empty_image_field(monkeypatch):
    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory: CaptureAnalysis(
        suggested_updates=[SuggestedUpdate(type='person', name='Brandon', company='RYSE Wellness')]
    ))
    response = client.post('/capture/classify', json={
        'text': 'RYSE - Brandon is going to another company. Should we look to per diem workers?',
        'image_data': '',
        'confirm': True,
    })
    assert response.status_code == 200
    assert response.json()['suggested_updates'][0]['name'] == 'Brandon'


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


def test_meeting_prep_does_not_include_unrelated_company_memory():
    prep = client.post('/meeting-prep', json={'meeting': 'RYSE leadership meeting'}).json()
    assert prep['context_found'] is True
    assert 'Admissions workflow' in prep['related_projects']
    assert 'Census' in prep['metrics']
    assert 'Julio promotion and pay increase' not in prep['open_decisions']
    assert 'Improve PM quality' not in prep['related_strategic_issues']

    pec = client.post('/meeting-prep', json={'meeting': 'PEC leadership review'}).json()
    assert 'Julio promotion and pay increase' in pec['open_decisions']
    assert 'Add weekend intake coverage' not in pec['open_decisions']
    assert 'Increase sales' not in pec['related_strategic_issues']


def test_unknown_meeting_context_returns_clean_empty_sections():
    prep = client.post('/meeting-prep', json={'meeting': 'Completely New Topic'}).json()
    assert prep['context_found'] is False
    assert prep['related_people'] == []
    assert prep['related_strategic_issues'] == []
    assert prep['related_projects'] == []
    assert prep['open_decisions'] == []


def test_search_answers_the_question_and_scopes_named_companies():
    why = client.post('/search', json={'query': 'Why did we promote Julio?'}).json()
    assert 'align incentives' in why['answer']

    company = client.post('/search', json={'query': "What is Julio's company?"}).json()
    assert company['answer'] == 'PEC'

    owner = client.post('/search', json={'query': 'Who owns PM quality?'}).json()
    assert owner['answer'] == 'Julio'

    ryse = client.post('/search', json={'query': 'What is happening at RYSE?'}).json()
    assert ryse['results']
    assert all(result['title'] not in {'GTM strategy', 'Improve PM quality', 'Julio'} for result in ryse['results'])

    decisions = client.post('/search', json={'query': 'What decisions need review?'}).json()
    assert decisions['results'][0]['type'] == 'decision'


def test_local_fallback_extracts_safe_common_updates(monkeypatch):
    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory_context: None)

    project = client.post('/capture/classify', json={
        'text': 'Morgan owns the Zephyr expansion. The main risk is distributor capacity.'
    }).json()['suggested_updates'][0]
    assert project['type'] == 'project'
    assert project['owner'] == 'Morgan'
    assert project['risks'] == ['distributor capacity']

    metric = client.post('/capture/classify', json={
        'text': 'Revenue is $2.4M, up 12% this quarter.'
    }).json()['suggested_updates'][0]
    assert metric['value'] == '$2.4M'
    assert metric['trend'] == 'up 12% this quarter'

    decision = client.post('/capture/classify', json={
        'text': 'We decided to pause the Atlas launch because compliance is not ready.'
    }).json()['suggested_updates'][0]
    assert decision['final_decision'] == 'pause the Atlas launch'
    assert decision['reasoning'] == 'compliance is not ready'

    unstructured = client.post('/capture/classify', json={'text': 'Just thinking out loud today.'}).json()
    assert unstructured['suggested_updates'] == []
    assert unstructured['follow_ups']


def test_capture_rejects_unsupported_update_types():
    response = client.post('/capture/confirm', json={
        'text': 'This must not report a fake save.',
        'approved_updates': [{'type': 'note', 'details': 'Not a supported object.'}],
    })
    assert response.status_code == 422


def test_capture_confirmation_rolls_back_partial_updates(monkeypatch):
    company_name = 'Atomic Rollback Company'

    def fail_generic_update(db, update):
        raise SQLAlchemyError('forced failure')

    monkeypatch.setattr('app.capture_service._apply_generic_update', fail_generic_update)
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


def test_company_correction_respects_negation_and_aliases(monkeypatch):
    client.post(
        '/capture/confirm',
        json={
            'text': 'Julio is with RYSE.',
            'approved_updates': [SuggestedUpdate(type='person', name='Julio', company='RYSE Wellness').model_dump()],
        },
    )

    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory_context: None)
    correction = 'Julio is with Pro Engineering, not RYSE.'
    classified = client.post('/capture/classify', json={'text': correction}).json()
    person_update = next(update for update in classified['suggested_updates'] if update['type'] == 'person')
    assert person_update['company'] == 'PEC'

    saved = client.post(
        '/capture/confirm',
        json={'text': correction, 'approved_updates': classified['suggested_updates']},
    )
    assert saved.status_code == 200

    people = client.get('/objects/people').json()['items']
    julio = next(person for person in people if person['name'] == 'Julio')
    assert julio['company'] == 'PEC'

    results = client.post('/search', json={'query': 'Julio company'}).json()['results']
    julio_result = next(result for result in results if result['type'] == 'person' and result['title'] == 'Julio')
    assert 'at PEC' in julio_result['summary']
