import os
import sys
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.database import SessionLocal
from app.main import app
from app.models import Clarification, Project


client = TestClient(app)


def create(object_type, attributes):
    response = client.post(f'/objects/{object_type}', json={'attributes': attributes})
    assert response.status_code == 200
    return response.json()['object']


def clarification_for_title(title, *, company='Clarico'):
    response = client.get(f'/clarifications?company={company}')
    assert response.status_code == 200
    return next(item for item in response.json()['items'] if title in item['question'])


def test_missing_owner_generates_ranked_deduped_clarification():
    project = create('projects', {
        'title': 'Clarico onboarding rebuild',
        'company': 'Clarico',
        'status': 'active',
        'objective': 'Rebuild onboarding because handoffs are creating delays.',
        'risks': ['Client launch timeline may slip'],
    })

    first = client.get('/clarifications?company=Clarico').json()['items']
    matches = [item for item in first if item['target_record_type'] == 'projects' and item['target_record_id'] == project['id']]
    assert len(matches) == 1
    assert matches[0]['subtype'] == 'project_owner'
    assert matches[0]['score'] >= 80
    assert 'missing owner' in matches[0]['score_reasons']

    second = client.get('/clarifications?company=Clarico').json()['items']
    repeated = [item for item in second if item['target_record_type'] == 'projects' and item['target_record_id'] == project['id']]
    assert len(repeated) == 1


def test_low_value_optional_empty_field_does_not_generate_clarification():
    task = create('tasks', {
        'title': 'Clarico low priority reference cleanup',
        'company': 'Clarico',
        'status': 'open',
        'priority': 'low',
    })

    response = client.get('/clarifications?company=Clarico').json()
    assert not any(item['target_record_type'] == 'tasks' and item['target_record_id'] == task['id'] for item in response['items'])


def test_answer_preview_then_confirm_updates_stable_record_and_revision_history():
    project = create('projects', {
        'title': 'Clarico owner preview workflow',
        'company': 'Clarico',
        'status': 'active',
    })
    clarification = clarification_for_title('Clarico owner preview workflow')

    preview = client.post(f"/clarifications/{clarification['id']}/answer", json={'answer': 'Avery'}).json()['clarification']
    assert preview['status'] == 'open'
    assert preview['proposed_update']['requires_confirmation'] is True
    assert preview['proposed_update']['updates'][0]['attributes']['owner'] == 'Avery'

    unchanged = next(item for item in client.get('/objects/projects').json()['items'] if item['id'] == project['id'])
    assert unchanged['owner'] == ''

    confirmed = client.post(f"/clarifications/{clarification['id']}/confirm", json={}).json()['clarification']
    assert confirmed['status'] == 'answered'

    updated = next(item for item in client.get('/objects/projects').json()['items'] if item['id'] == project['id'])
    assert updated['owner'] == 'Avery'

    history = client.get(f"/objects/projects/{project['id']}/history").json()
    assert any(revision['change_type'] == 'clarification_answer' for revision in history['revisions'])


def test_snooze_dismiss_intentionally_unknown_suppress_and_reopen_lifecycle():
    first = create('projects', {
        'title': 'Clarico lifecycle snooze',
        'company': 'Clarico',
        'status': 'active',
    })
    clarification = clarification_for_title(first['title'])
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    snoozed = client.post(f"/clarifications/{clarification['id']}/snooze", json={'snoozed_until': future}).json()['clarification']
    assert snoozed['status'] == 'snoozed'
    assert not any(item['id'] == clarification['id'] for item in client.get('/clarifications?company=Clarico').json()['items'])

    reopened = client.post(f"/clarifications/{clarification['id']}/reopen").json()['clarification']
    assert reopened['status'] == 'open'

    dismissed = client.post(f"/clarifications/{clarification['id']}/dismiss", json={'reason': 'Not material now'}).json()['clarification']
    assert dismissed['status'] == 'dismissed'

    second = create('projects', {
        'title': 'Clarico lifecycle unknown',
        'company': 'Clarico',
        'status': 'active',
    })
    unknown = clarification_for_title(second['title'])
    marked = client.post(f"/clarifications/{unknown['id']}/intentionally-unknown", json={'reason': 'Intentionally not assigned'}).json()['clarification']
    assert marked['status'] == 'intentionally_unknown'

    third = create('projects', {
        'title': 'Clarico lifecycle suppressed',
        'company': 'Clarico',
        'status': 'active',
    })
    suppressible = clarification_for_title(third['title'])
    suppressed = client.post(f"/clarifications/{suppressible['id']}/suppress", json={
        'scope': 'projects:owner',
        'reason': 'Handled elsewhere',
    }).json()['clarification']
    assert suppressed['status'] == 'suppressed'
    assert suppressed['suppression_scope'] == 'projects:owner'


def test_contradiction_shows_both_evidence_sources_without_mutating_records():
    left = create('projects', {
        'title': 'Clarico pricing launch',
        'company': 'Clarico',
        'status': 'active',
        'owner': 'Mina',
    })
    right = create('projects', {
        'title': 'Clarico pricing launch',
        'company': 'Clarico',
        'status': 'active',
        'owner': 'Sam',
    })

    items = client.get('/clarifications?company=Clarico&clarification_type=contradiction').json()['items']
    conflict = next(item for item in items if item['target_record_id'] == left['id'])
    assert conflict['subtype'] == 'project_owner_conflict'
    assert {entry['text'] for entry in conflict['evidence']} == {'Owner: Mina', 'Owner: Sam'}

    projects = client.get('/objects/projects').json()['items']
    assert next(item for item in projects if item['id'] == left['id'])['owner'] == 'Mina'
    assert next(item for item in projects if item['id'] == right['id'])['owner'] == 'Sam'


def test_ambiguous_actionable_language_and_stale_project_rules():
    task = create('tasks', {
        'title': 'Clarico ambiguity follow-up',
        'company': 'Clarico',
        'status': 'open',
        'priority': 'medium',
        'description': 'Sam will follow up later on the pricing cleanup.',
    })
    project = create('projects', {
        'title': 'Clarico stale project',
        'company': 'Clarico',
        'status': 'active',
        'owner': 'Avery',
    })
    db = SessionLocal()
    try:
        instance = db.get(Project, project['id'])
        instance.updated_at = datetime.now(timezone.utc) - timedelta(days=45)
        db.add(instance)
        db.commit()
    finally:
        db.close()

    items = client.get('/clarifications?company=Clarico').json()['items']
    ambiguous = next(item for item in items if item['target_record_type'] == 'tasks' and item['target_record_id'] == task['id'])
    stale = next(item for item in items if item['target_record_type'] == 'projects' and item['target_record_id'] == project['id'])
    assert ambiguous['clarification_type'] == 'ambiguous_language'
    assert stale['clarification_type'] == 'stale_information'


def test_clarifications_appear_in_inbox_briefing_and_meeting_prep_with_limits():
    for index in range(7):
        create('projects', {
            'title': f'Clarico briefing project {index}',
            'company': 'Clarico',
            'status': 'active',
        })

    inbox = client.get('/executive-inbox?company=Clarico&source_type=clarification').json()
    assert inbox['total'] >= 7
    assert all(item['source_type'] == 'clarification' for item in inbox['items'])

    briefing = client.get('/briefing').json()
    assert len(briefing['clarifications_needed']) <= 5
    assert any(item['record_type'] == 'clarification' for item in briefing['clarifications_needed'])

    prep = client.post('/meeting-prep', json={'meeting': 'Clarico leadership meeting'}).json()
    assert prep['clarifications_needed']
    assert any('Clarico briefing project' in question for question in prep['questions_to_ask'])


def test_material_evidence_change_reopens_answered_clarification():
    project = create('projects', {
        'title': 'Clarico reopen on evidence',
        'company': 'Clarico',
        'status': 'active',
    })
    clarification = clarification_for_title(project['title'])
    client.post(f"/clarifications/{clarification['id']}/answer", json={'answer': 'Avery'})
    client.post(f"/clarifications/{clarification['id']}/confirm", json={})

    db = SessionLocal()
    try:
        stored = db.get(Project, project['id'])
        stored.owner = ''
        stored.risks = ['New risk changed the materiality']
        db.add(stored)
        db.commit()
    finally:
        db.close()

    regenerated = client.get('/clarifications?company=Clarico').json()['items']
    reopened = next(item for item in regenerated if item['target_record_type'] == 'projects' and item['target_record_id'] == project['id'])
    assert reopened['status'] == 'open'
    assert 'explicit risk' in reopened['score_reasons']


def test_clarification_table_is_available_to_migrations_and_metadata():
    db = SessionLocal()
    try:
        assert Clarification.__tablename__ in Clarification.metadata.tables
        db.query(Clarification).count()
    finally:
        db.close()
