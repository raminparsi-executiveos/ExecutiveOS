import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.ai import (
    CaptureAnalysis,
    _capture_model_candidates,
    _openai_image_detail,
    _openai_timeout_seconds,
    _parse_capture_analysis_json,
    analyze_capture,
    last_capture_ai_failure,
)


def test_openai_timeout_seconds_defaults_and_clamps(monkeypatch):
    monkeypatch.delenv('OPENAI_TIMEOUT_SECONDS', raising=False)
    assert _openai_timeout_seconds() == 60.0

    monkeypatch.setenv('OPENAI_TIMEOUT_SECONDS', '3')
    assert _openai_timeout_seconds() == 10.0

    monkeypatch.setenv('OPENAI_TIMEOUT_SECONDS', '90')
    assert _openai_timeout_seconds() == 90.0

    monkeypatch.setenv('OPENAI_TIMEOUT_SECONDS', 'not-a-number')
    assert _openai_timeout_seconds() == 60.0


def test_openai_image_detail_defaults_and_validates(monkeypatch):
    monkeypatch.delenv('OPENAI_IMAGE_DETAIL', raising=False)
    assert _openai_image_detail() == 'high'

    monkeypatch.setenv('OPENAI_IMAGE_DETAIL', 'LOW')
    assert _openai_image_detail() == 'low'

    monkeypatch.setenv('OPENAI_IMAGE_DETAIL', 'original')
    assert _openai_image_detail() == 'original'

    monkeypatch.setenv('OPENAI_IMAGE_DETAIL', 'massive')
    assert _openai_image_detail() == 'high'


def test_capture_model_candidates_try_configured_capture_model_then_fallback(monkeypatch):
    monkeypatch.setenv('OPENAI_CAPTURE_MODEL', 'gpt-capture')
    monkeypatch.setenv('OPENAI_MODEL', 'gpt-primary')
    monkeypatch.setenv('OPENAI_CAPTURE_FALLBACK_MODEL', 'gpt-fallback')

    candidates = _capture_model_candidates()

    assert candidates[:3] == ['gpt-capture', 'gpt-primary', 'gpt-fallback']
    assert 'gpt-4.1-mini' in candidates


def test_analyze_capture_records_missing_key_failure(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    assert analyze_capture('Kyle will send the update.', '') is None

    failure = last_capture_ai_failure()
    assert failure['reason'] == 'missing_openai_api_key'
    assert failure['attempted_models'] == []


def test_capture_analysis_schema_is_strict_for_openai_response_format():
    schema = CaptureAnalysis.model_json_schema()
    for definition in [schema, *schema.get('$defs', {}).values()]:
        properties = set(definition.get('properties', {}))
        if not properties:
            continue
        assert set(definition.get('required', [])) == properties
        assert definition.get('additionalProperties') is False


def test_parse_capture_analysis_json_accepts_json_object():
    analysis = _parse_capture_analysis_json('{"capture_summary":"Reviewed sales plan","suggested_updates":[]}')

    assert analysis.capture_summary == 'Reviewed sales plan'
    assert analysis.suggested_updates == []


def test_parse_capture_analysis_json_accepts_fenced_json():
    analysis = _parse_capture_analysis_json('```json\n{"suggested_updates":[],"follow_ups":["Who owns this?"]}\n```')

    assert analysis.follow_ups == ['Who owns this?']


def test_parse_capture_analysis_json_wraps_update_list():
    analysis = _parse_capture_analysis_json('[{"type":"task","title":"Review pricing"}]')

    assert len(analysis.suggested_updates) == 1
    assert analysis.suggested_updates[0].title == 'Review pricing'


def test_parse_capture_analysis_json_flattens_nested_details_object():
    analysis = _parse_capture_analysis_json('''{
      "suggested_updates": [{
        "type": "task",
        "details": {
          "title": "Ryan to focus outreach",
          "owner": "Ryan Labus",
          "next_action": "Confirm sales team focus this week"
        }
      }]
    }''')

    update = analysis.suggested_updates[0]
    assert update.title == 'Ryan to focus outreach'
    assert update.owner == 'Ryan Labus'
    assert update.next_action == 'Confirm sales team focus this week'
    assert isinstance(update.details, str)


def test_parse_capture_analysis_json_infers_missing_update_type():
    analysis = _parse_capture_analysis_json('''{
      "suggested_updates": [{
        "operation": "create",
        "title": "Daily outreach cadence",
        "owner": "Ryan",
        "status": "open",
        "field_operations": {"status": "replace"}
      }]
    }''')

    assert analysis.suggested_updates[0].type == 'task'
    assert analysis.suggested_updates[0].title == 'Daily outreach cadence'


def test_parse_capture_analysis_json_coerces_human_readable_ids():
    analysis = _parse_capture_analysis_json('''{
      "suggested_updates": [{
        "type": "task",
        "title": "Update existing pricing task",
        "matched_record_id": "task#70",
        "parent_task_id": "parent task 17",
        "linked_project_ids": ["project#8", 9],
        "linked_decision_ids": ["decision#3"]
      }]
    }''')

    update = analysis.suggested_updates[0]
    assert update.matched_record_id == 70
    assert update.parent_task_id == 17
    assert update.linked_project_ids == [8, 9]
    assert update.linked_decision_ids == [3]


def test_parse_capture_analysis_json_coerces_structured_followups():
    analysis = _parse_capture_analysis_json('''{
      "suggested_updates": [],
      "follow_ups": [
        {"question": "Who is the accountable owner?", "why": "Clarify the owner clearly."},
        {"question": "What is the target date?", "reason": "No milestone is provided."}
      ],
      "open_questions": [{"question": "Which company owns this?"}],
      "ambiguities": [{"ambiguity": "Owner unclear"}]
    }''')

    assert analysis.follow_ups == [
        "Who is the accountable owner? (Clarify the owner clearly.)",
        "What is the target date? (No milestone is provided.)",
    ]
    assert analysis.open_questions == ["Which company owns this?"]
    assert analysis.ambiguities == ["Owner unclear"]
