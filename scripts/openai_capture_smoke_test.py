#!/usr/bin/env python3
"""Smoke-test the backend OpenAI capture connection.

Run from the Render backend shell:
    python scripts/openai_capture_smoke_test.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ai import _capture_model_candidates, _openai_timeout_seconds


def main() -> None:
    key = os.getenv("OPENAI_API_KEY", "")
    print(f"OPENAI_API_KEY set: {bool(key)}")
    print(f"OPENAI_MODEL: {os.getenv('OPENAI_MODEL', '')!r}")
    print(f"OPENAI_CAPTURE_MODEL: {os.getenv('OPENAI_CAPTURE_MODEL', '')!r}")
    print(f"OPENAI_CAPTURE_FALLBACK_MODEL: {os.getenv('OPENAI_CAPTURE_FALLBACK_MODEL', '')!r}")
    print(f"Candidates: {_capture_model_candidates()}")
    print(f"Timeout: {_openai_timeout_seconds()}")
    if not key:
        raise SystemExit("OPENAI_API_KEY is not set.")

    from openai import OpenAI

    client = OpenAI(timeout=_openai_timeout_seconds(), max_retries=0)
    for model in _capture_model_candidates():
        print(f"\nTrying model: {model}")
        try:
            response = client.responses.create(
                model=model,
                input="Reply with exactly: ok",
                max_output_tokens=20,
            )
            print("SUCCESS")
            print(str(response.output_text)[:200])
            return
        except Exception as error:
            print(f"FAILED: {type(error).__name__}: {str(error)[:500]}")
    raise SystemExit("All candidate models failed.")


if __name__ == "__main__":
    main()
