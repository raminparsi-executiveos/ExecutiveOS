import os
import sys
from datetime import date, timedelta

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app
from app.database import SessionLocal
from app.models import CaptureRecord, Meeting


client = TestClient(app)


def test_tasks_can_be_created_completed_reopened_and_deleted():
    future_due_date = (date.today() + timedelta(days=7)).isoformat()
    created = client.post('/objects/tasks', json={'attributes': {
        'title': 'Kyle will send the revised client-retention plan',
        'description': 'Send revised client-retention plan.',
        'company': 'PEC',
        'owner': 'Kyle',
        'due_date': future_due_date,
        'status': 'open',
        'priority': 'high',
        'source_type': 'manual',
        'next_action': 'Review the revised plan',
        'tags': ['client-retention'],
    }})
    assert created.status_code == 200
    task = created.json()['object']
    assert task['owner'] == 'Kyle'
    assert task['status'] == 'open'
    assert task['is_overdue'] is False

    completed = client.post(f"/tasks/{task['id']}/complete")
    assert completed.status_code == 200
    assert completed.json()['task']['status'] == 'completed'
    assert completed.json()['task']['completed_at']

    briefing = client.get('/briefing').json()
    assert 'Kyle will send the revised client-retention plan' not in [
        item['label'] for item in briefing['open_tasks']
    ]

    reopened = client.post(f"/tasks/{task['id']}/reopen")
    assert reopened.status_code == 200
    assert reopened.json()['task']['status'] == 'open'
    assert reopened.json()['task']['completed_at'] is None

    deleted = client.delete(f"/objects/tasks/{task['id']}")
    assert deleted.status_code == 200


def test_task_validation_and_overdue_derivation():
    invalid_status = client.post('/objects/tasks', json={'attributes': {
        'title': 'Bad task',
        'status': 'done',
    }})
    assert invalid_status.status_code == 422

    overdue = client.post('/objects/tasks', json={'attributes': {
        'title': 'Overdue executive commitment',
        'company': 'PEC',
        'owner': 'Ramin',
        'due_date': '2020-01-01',
        'status': 'open',
        'priority': 'critical',
    }})
    assert overdue.status_code == 200
    assert overdue.json()['object']['is_overdue'] is True

    briefing = client.get('/briefing').json()
    assert 'Overdue executive commitment' in [item['label'] for item in briefing['overdue_tasks']]


def test_local_capture_suggests_and_saves_task_commitment(monkeypatch):
    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory_context: None)
    classified = client.post('/capture/classify', json={
        'text': 'Kyle will send the revised client-retention plan by Friday.',
    })
    assert classified.status_code == 200
    task_update = next(update for update in classified.json()['suggested_updates'] if update['type'] == 'task')
    assert task_update['owner'] == 'Kyle'
    assert task_update['due_date'] == 'Friday'

    saved = client.post('/capture/confirm', json={
        'text': 'Kyle will send the revised client-retention plan by Friday.',
        'classification_source': 'local_fallback',
        'approved_updates': [task_update],
    })
    assert saved.status_code == 200

    tasks = client.get('/objects/tasks').json()['items']
    assert any(task['title'] == 'Kyle will send the revised client-retention plan by Friday' for task in tasks)


def test_capture_confirm_normalizes_task_status_and_priority_values():
    saved = client.post('/capture/confirm', json={
        'text': 'Morning sales meeting: Avery owns follow-up on open prospects.',
        'classification_source': 'ai',
        'approved_updates': [{
            'type': 'task',
            'title': 'Avery follow up on open prospects',
            'company': 'PEC',
            'owner': 'Avery',
            'status': 'Open',
            'priority': 'Normal',
            'source_type': 'capture_text',
            'details': 'Captured from morning sales meeting.',
        }],
    })
    assert saved.status_code == 200

    tasks = client.get('/objects/tasks').json()['items']
    task = next(item for item in tasks if item['title'] == 'Avery follow up on open prospects')
    assert task['status'] == 'open'
    assert task['priority'] == 'medium'


def test_capture_confirm_treats_unknown_ai_task_priority_as_medium():
    saved = client.post('/capture/confirm', json={
        'text': 'Screenshot capture from sales follow-up.',
        'classification_source': 'ai',
        'approved_updates': [{
            'type': 'task',
            'title': 'Prepare reporting period follow-up',
            'company': 'PEC',
            'owner': 'Avery',
            'status': 'open',
            'priority': 'next_reporting_period',
            'source_type': 'capture_text',
        }],
    })
    assert saved.status_code == 200

    tasks = client.get('/objects/tasks').json()['items']
    task = next(item for item in tasks if item['title'] == 'Prepare reporting period follow-up')
    assert task['priority'] == 'medium'


def test_capture_confirm_normalizes_ai_proposed_pending_status():
    saved = client.post('/capture/confirm', json={
        'text': 'Screenshot capture with a proposed task pending approval.',
        'classification_source': 'ai',
        'approved_updates': [{
            'type': 'task',
            'title': 'Review proposed leadership approval item',
            'company': 'PEC',
            'owner': 'Avery',
            'status': 'proposed; pending leadership approval',
            'priority': 'medium',
            'source_type': 'capture_text',
        }],
    })
    assert saved.status_code == 200

    tasks = client.get('/objects/tasks').json()['items']
    task = next(item for item in tasks if item['title'] == 'Review proposed leadership approval item')
    assert task['status'] == 'waiting'


def test_local_fallback_filters_weak_context_tasks(monkeypatch):
    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory_context: None)

    classified = client.post('/capture/classify', json={
        'text': 'PEC sales meeting check-in debrief: Ryan, Catalina and I met today to discuss sales activities and outlook. We need to get our year back on track.',
    })

    assert classified.status_code == 200
    payload = classified.json()
    task_titles = [update['title'] for update in payload['suggested_updates'] if update['type'] == 'task']
    assert 'Discuss sales activities and outlook' not in task_titles
    assert 'Get our year back on track' not in task_titles


def test_capture_confirm_clears_invalid_task_owner_and_reopens_non_resolution_completion():
    saved = client.post('/capture/confirm', json={
        'text': 'RYSE leadership notes: This will require Veronica to build a group therapy curriculum.',
        'classification_source': 'ai',
        'approved_updates': [{
            'type': 'task',
            'title': 'Veronica build a group therapy curriculum',
            'company': 'RYSE Wellness',
            'owner': 'This',
            'status': 'completed',
            'priority': 'medium',
            'source_type': 'capture_text',
            'source_excerpt': 'This will require Veronica to build a group therapy curriculum.',
        }],
    })

    assert saved.status_code == 200
    tasks = client.get('/objects/tasks').json()['items']
    task = next(item for item in tasks if item['title'] == 'Veronica build a group therapy curriculum')
    assert task['owner'] == ''
    assert task['status'] == 'open'


def test_capture_confirm_skips_weak_local_fallback_task_from_old_review():
    saved = client.post('/capture/confirm', json={
        'text': 'PEC sales meeting check-in debrief: Ryan, Catalina and I met today to discuss sales activities and outlook.',
        'classification_source': 'local_fallback',
        'approved_updates': [{
            'type': 'task',
            'title': 'Discuss sales activities and outlook',
            'company': 'PEC',
            'status': 'open',
            'priority': 'medium',
            'source_type': 'capture_text',
            'source_excerpt': 'Ryan, Catalina and I met today to discuss sales activities and outlook.',
        }],
    })

    assert saved.status_code == 200
    assert saved.json()['saved_count'] == 0
    tasks = client.get('/objects/tasks').json()['items']
    assert not any(task['title'] == 'Discuss sales activities and outlook' for task in tasks)


def test_meeting_action_items_create_linked_tasks_and_preserve_meeting_actions():
    meeting = client.post('/objects/meetings', json={'attributes': {
        'title': 'PEC client retention review',
        'company': 'PEC',
        'action_items': ['Kyle: send revised client-retention plan'],
    }})
    assert meeting.status_code == 200
    meeting_id = meeting.json()['object']['id']

    tasks = client.get('/objects/tasks').json()['items']
    linked = next(task for task in tasks if task['title'] == 'Kyle: send revised client-retention plan')
    assert linked['source_type'] == 'meeting'
    assert linked['source_id'] == str(meeting_id)
    assert linked['source_summary'] == 'PEC client retention review'

    prep = client.post('/meeting-prep', json={'meeting': 'PEC client retention review'}).json()
    assert 'Kyle: send revised client-retention plan' in prep['action_items']

    completed = client.post(f"/tasks/{linked['id']}/complete")
    assert completed.status_code == 200
    refreshed_meeting = client.get('/objects/meetings').json()['items']
    stored = next(item for item in refreshed_meeting if item['id'] == meeting_id)
    assert stored['action_items'] == ['Kyle: send revised client-retention plan']

    briefing = client.get('/briefing').json()
    assert 'Kyle: send revised client-retention plan' not in [
        item['label'] for item in briefing['open_tasks']
    ]


def test_briefing_and_meeting_prep_expose_completable_task_metadata():
    task_response = client.post('/objects/tasks', json={'attributes': {
        'title': 'Ramin review PEC rework list',
        'company': 'PEC',
        'owner': 'Ramin',
        'status': 'open',
        'priority': 'high',
    }})
    assert task_response.status_code == 200
    task_id = task_response.json()['object']['id']

    briefing = client.get('/briefing').json()
    briefing_item = next(item for item in briefing['needs_your_attention'] if item['title'] == 'Ramin review PEC rework list')
    assert briefing_item['record_type'] == 'task'
    assert briefing_item['record_id'] == task_id

    legacy_task_item = next(item for item in briefing['open_tasks'] if item['label'] == 'Ramin review PEC rework list')
    assert legacy_task_item['record_type'] == 'task'
    assert legacy_task_item['task_id'] == task_id

    prep = client.post('/meeting-prep', json={'meeting': 'PEC rework meeting'}).json()
    detail = next(item for item in prep['action_items_detail'] if item['label'] == 'Ramin review PEC rework list')
    assert detail['task_id'] == task_id
    assert detail['status'] == 'open'

    completed = client.post(f'/tasks/{task_id}/complete')
    assert completed.status_code == 200

    refreshed = client.post('/meeting-prep', json={'meeting': 'PEC rework meeting'}).json()
    assert 'Ramin review PEC rework list' not in [
        item['label'] for item in refreshed['action_items_detail']
    ]


def test_meeting_prep_exposes_resolve_metadata_for_non_task_items():
    db = SessionLocal()
    try:
        db.add(Meeting(
            title='PEC legacy prep review',
            company='PEC',
            action_items=['Confirm legacy worksheet cleanup'],
        ))
        db.commit()
    finally:
        db.close()

    issue = client.post('/objects/strategic-issues', json={'attributes': {
        'title': 'PEC prep risk cleanup',
        'company': 'PEC',
        'owner': 'Ramin',
        'status': 'active',
        'current_thinking': 'Risk should be visible before it is resolved.',
        'risks': ['Legacy worksheet rework'],
    }})
    assert issue.status_code == 200

    prep = client.post('/meeting-prep', json={'meeting': 'PEC legacy prep review'}).json()
    legacy_action = next(item for item in prep['action_items_detail'] if item['label'] == 'Confirm legacy worksheet cleanup')
    assert legacy_action['record_type'] == 'meeting_action'
    assert legacy_action['resolvable'] is True

    risk = next(item for item in prep['risks_detail'] if item['label'] == 'Legacy worksheet rework')
    assert risk['record_type'] == 'risk'
    assert risk['resolvable'] is True

    resolved = client.post('/capture/confirm', json={
        'text': 'Mark Legacy worksheet rework as resolved',
        'approved_updates': [],
        'classification_source': 'manual',
    })
    assert resolved.status_code == 200

    refreshed = client.post('/meeting-prep', json={'meeting': 'PEC legacy prep review'}).json()
    assert 'Legacy worksheet rework' not in [item['label'] for item in refreshed['risks_detail']]


def test_search_includes_open_tasks_and_excludes_completed_actions():
    created = client.post('/objects/tasks', json={'attributes': {
        'title': 'Sam call volume referral partners',
        'company': 'RYSE Wellness',
        'owner': 'Sam',
        'status': 'open',
        'priority': 'medium',
    }})
    assert created.status_code == 200
    task_id = created.json()['object']['id']

    search = client.post('/search', json={'query': 'What action items are open at RYSE?'}).json()
    assert 'Sam call volume referral partners' in search['answer']

    client.post(f'/tasks/{task_id}/complete')
    completed_search = client.post('/search', json={'query': 'What action items are open at RYSE?'}).json()
    assert 'Sam call volume referral partners' not in completed_search['answer']


def test_capture_can_mark_existing_pricing_issue_resolved(monkeypatch):
    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory_context: None)
    issue = client.post('/objects/strategic-issues', json={'attributes': {
        'title': 'Quote generator pricing issues',
        'company': 'PEC',
        'owner': 'Ramin',
        'status': 'active',
        'current_thinking': 'Pricing logic needs review.',
    }})
    assert issue.status_code == 200

    before = client.get('/briefing').json()
    assert 'Quote generator pricing issues' in [
        item['title'] for section in ('needs_your_attention', 'top_priorities') for item in before[section]
    ]

    classified = client.post('/capture/classify', json={
        'text': 'Mark quote generator pricing issues as resolved',
    })
    assert classified.status_code == 200
    update = next(update for update in classified.json()['suggested_updates'] if update['type'] == 'strategic_issue')
    assert update['title'] == 'Quote generator pricing issues'
    assert update['status'] == 'resolved'

    saved = client.post('/capture/confirm', json={
        'text': 'Mark quote generator pricing issues as resolved',
        'approved_updates': [update],
        'classification_source': 'local_fallback',
    })
    assert saved.status_code == 200

    after = client.get('/briefing').json()
    visible_titles = [
        item['title'] for section in ('needs_your_attention', 'top_priorities') for item in after[section]
    ]
    assert 'Quote generator pricing issues' not in visible_titles

    stored = next(item for item in client.get('/objects/strategic-issues').json()['items'] if item['title'] == 'Quote generator pricing issues')
    assert stored['status'] == 'resolved'


def test_capture_can_remove_resolved_pricing_risk_from_morning_briefing(monkeypatch):
    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory_context: None)
    created = client.post('/objects/strategic-issues', json={'attributes': {
        'title': 'Quote generator rollout validation',
        'company': 'PEC',
        'owner': 'Ramin',
        'status': 'active',
        'current_thinking': 'Keep validating the pricing workflow.',
        'risks': ['Potential pricing inaccuracies', 'Slow estimator adoption'],
    }})
    assert created.status_code == 200

    before = client.get('/briefing').json()
    assert 'Potential pricing inaccuracies' in [
        item['title'] for item in before['needs_your_attention']
    ]

    classified = client.post('/capture/classify', json={
        'text': 'Mark potential pricing inaccuracies as resolved',
    })
    assert classified.status_code == 200
    update = next(update for update in classified.json()['suggested_updates'] if update['type'] == 'strategic_issue')
    assert update['title'] == 'Quote generator rollout validation'
    assert update['risks'] == ['Slow estimator adoption']
    assert update.get('status') != 'resolved'

    saved = client.post('/capture/confirm', json={
        'text': 'Mark potential pricing inaccuracies as resolved',
        'approved_updates': [update],
        'classification_source': 'local_fallback',
    })
    assert saved.status_code == 200

    after = client.get('/briefing').json()
    visible_titles = [
        item['title'] for section in ('needs_your_attention', 'top_priorities') for item in after[section]
    ]
    assert 'Potential pricing inaccuracies' not in visible_titles

    stored = next(
        item for item in client.get('/objects/strategic-issues').json()['items']
        if item['title'] == 'Quote generator rollout validation'
    )
    assert stored['status'] == 'active'
    assert stored['risks'] == ['Slow estimator adoption']


def test_briefing_hides_longer_risk_resolved_by_recent_capture():
    created = client.post('/objects/strategic-issues', json={'attributes': {
        'title': 'Quote generator rollout validation',
        'company': 'PEC',
        'owner': 'Ramin',
        'status': 'active',
        'current_thinking': 'Keep validating the pricing workflow.',
        'risks': ['Potential pricing inaccuracies if logic is not fully validated'],
    }})
    assert created.status_code == 200

    db = SessionLocal()
    try:
        db.add(CaptureRecord(raw_text='Mark potential pricing inaccuracies as resolved'))
        db.commit()
    finally:
        db.close()

    briefing = client.get('/briefing').json()
    visible_titles = [
        item['title'] for section in ('needs_your_attention', 'top_priorities') for item in briefing[section]
    ]
    assert 'Potential pricing inaccuracies if logic is not fully validated' not in visible_titles


def test_briefing_hides_risk_resolved_by_mark_as_resolved_capture_variants():
    for raw_text in (
        'Potential pricing inaccuracies if logic is not fully validated - mark as resolved',
        'Mark as resolved: potential pricing inaccuracies',
    ):
        created = client.post('/objects/strategic-issues', json={'attributes': {
            'title': f'Quote generator validation {raw_text[:8]}',
            'company': 'PEC',
            'owner': 'Ramin',
            'status': 'active',
            'current_thinking': 'Keep validating the pricing workflow.',
            'risks': ['Potential pricing inaccuracies if logic is not fully validated'],
        }})
        assert created.status_code == 200

        db = SessionLocal()
        try:
            db.add(CaptureRecord(raw_text=raw_text))
            db.commit()
        finally:
            db.close()

        briefing = client.get('/briefing').json()
        visible_titles = [
            item['title'] for section in ('needs_your_attention', 'top_priorities') for item in briefing[section]
        ]
        assert 'Potential pricing inaccuracies if logic is not fully validated' not in visible_titles


def test_capture_can_resolve_single_word_rework_item(monkeypatch):
    monkeypatch.setattr('app.capture_service.analyze_capture', lambda text, memory_context: None)
    created = client.post('/objects/strategic-issues', json={'attributes': {
        'title': 'Quote generator cleanup',
        'company': 'PEC',
        'owner': 'Ramin',
        'status': 'active',
        'current_thinking': 'Cleanup after pricing review.',
        'risks': ['Rework'],
    }})
    assert created.status_code == 200

    before = client.get('/briefing').json()
    assert 'Rework' in [item['title'] for item in before['needs_your_attention']]

    classified = client.post('/capture/classify', json={'text': 'mark Rework as resolved'})
    assert classified.status_code == 200
    update = next(update for update in classified.json()['suggested_updates'] if update['type'] == 'strategic_issue')
    assert update['title'] == 'Quote generator cleanup'
    assert update['risks'] == []

    saved = client.post('/capture/confirm', json={
        'text': 'mark Rework as resolved',
        'approved_updates': [update],
        'classification_source': 'local_fallback',
    })
    assert saved.status_code == 200

    after = client.get('/briefing').json()
    visible_titles = [
        item['title'] for section in ('needs_your_attention', 'top_priorities') for item in after[section]
    ]
    assert 'Rework' not in visible_titles
