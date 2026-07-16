import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.ai import _capture_model_candidates, _openai_image_detail, _openai_timeout_seconds


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
