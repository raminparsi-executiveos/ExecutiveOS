import os
import sys
import time
from datetime import date, timedelta

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.main import app


client = TestClient(app)


def create_task(title, **attributes):
    response = client.post('/objects/tasks', json={'attributes': {
        'title': title,
        **attributes,
    }})
    assert response.status_code == 200
    return response.json()['object']


def test_ranked_briefing_sections_explain_the_top_item():
    create_task(
        'Approve PEC retention rescue plan',
        company='PEC',
        owner='Ramin',
        due_date='2020-01-01',
        status='open',
        priority='critical',
        next_action='Approve or delegate the rescue plan',
    )
    create_task(
        'Review EverPole distributor notes',
        company='EverPole',
        owner='Mina',
        status='open',
        priority='medium',
    )

    briefing = client.get('/briefing').json()

    for section in [
        'needs_your_attention',
        'delegate_or_follow_up',
        'overdue',
        'blocked_or_waiting',
        'changed_since_last_briefing',
        'upcoming',
    ]:
        assert section in briefing

    top = briefing['needs_your_attention'][0]
    assert top['title'] == 'Approve PEC retention rescue plan'
    assert top['company'] == 'PEC'
    assert top['owner'] == 'Ramin'
    assert top['why_it_matters']
    assert top['recommended_next_action'] == 'Approve or delegate the rescue plan'
    assert top['score'] > 0
    assert 'critical priority' in top['score_reasons']
    assert any('overdue' in reason for reason in top['score_reasons'])
    assert top['source']['type'] == 'manual'

    delegate_titles = [item['title'] for item in briefing['delegate_or_follow_up']]
    assert 'Review EverPole distributor notes' in delegate_titles


def test_briefing_tracks_blocked_waiting_and_upcoming_items():
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    review_date = (date.today() + timedelta(days=3)).isoformat()

    create_task(
        'Unblock RYSE staffing coverage',
        company='RYSE Wellness',
        owner='Sam',
        status='blocked',
        priority='high',
        blocked_by='Need staffing numbers',
    )
    create_task(
        'Send MyndLog backup plan',
        company='MyndLog',
        owner='Ari',
        due_date=tomorrow,
        status='open',
        priority='medium',
    )
    decision = client.post('/objects/decisions', json={'attributes': {
        'title': 'Review EverPole pricing',
        'company': 'EverPole',
        'review_date': review_date,
        'final_decision': 'Use current pricing for initial distributor conversations.',
    }})
    assert decision.status_code == 200

    briefing = client.get('/briefing').json()

    blocked = next(item for item in briefing['blocked_or_waiting'] if item['title'] == 'Unblock RYSE staffing coverage')
    assert blocked['status'] == 'blocked'
    assert 'blocked dependency' in blocked['score_reasons']
    assert 'Need staffing numbers' in blocked['why_it_matters']

    visible_follow_up_titles = [
        item['title']
        for section in ('delegate_or_follow_up', 'upcoming')
        for item in briefing[section]
    ]
    assert 'Send MyndLog backup plan' in visible_follow_up_titles
    upcoming_titles = [item['title'] for item in briefing['upcoming']]
    assert 'Review EverPole pricing' in upcoming_titles


def test_changed_since_last_briefing_uses_previous_view_timestamp():
    first = client.get('/briefing').json()
    assert first['previous_viewed_at'] == ''

    time.sleep(0.01)
    create_task(
        'New PEC dashboard follow-up',
        company='PEC',
        owner='Kyle',
        status='open',
        priority='high',
    )

    second = client.get('/briefing').json()
    assert second['previous_viewed_at']
    visible_titles = [
        item['title']
        for section in ('needs_your_attention', 'delegate_or_follow_up', 'changed_since_last_briefing')
        for item in second[section]
    ]
    assert 'New PEC dashboard follow-up' in visible_titles
