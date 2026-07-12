import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.database import SessionLocal
from app.main import app
from app.models import LeadershipReview


client = TestClient(app)


def create_task(title="Leadership advisor missing owner task"):
    response = client.post("/objects/tasks", json={"attributes": {
        "title": title,
        "company": "PEC",
        "status": "open",
        "priority": "high",
    }})
    assert response.status_code == 200
    return response.json()["object"]


def test_capture_confirm_generates_nonblocking_leadership_review():
    saved = client.post("/capture/confirm", json={
        "text": "Avery owns the morning sales meeting follow-up.",
        "classification_source": "local_fallback",
        "approved_updates": [{
            "type": "task",
            "title": "Morning sales meeting follow-up needs owner confirmation",
            "company": "PEC",
            "status": "open",
            "priority": "high",
            "source_type": "capture_text",
        }],
    })

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["leadership_review"]
    assert payload["leadership_review"]["review_type"] == "capture"
    assert payload["leadership_review"]["findings"]


def test_capture_confirm_still_saves_when_leadership_review_fails(monkeypatch):
    def fail_review(*_args, **_kwargs):
        raise RuntimeError("advisor unavailable")

    monkeypatch.setattr("app.main.generate_capture_leadership_review", fail_review)
    saved = client.post("/capture/confirm", json={
        "text": "Sam will review the PEC closeout list.",
        "classification_source": "local_fallback",
        "approved_updates": [{
            "type": "task",
            "title": "Sam review PEC closeout list",
            "company": "PEC",
            "owner": "Sam",
            "status": "open",
            "priority": "medium",
        }],
    })

    assert saved.status_code == 200
    assert saved.json()["leadership_review"] is None
    assert "Leadership review could not be generated" in saved.json()["leadership_review_error"]
    tasks = client.get("/objects/tasks").json()["items"]
    assert any(task["title"] == "Sam review PEC closeout list" for task in tasks)


def test_nightly_leadership_review_is_idempotent_and_reaches_inbox():
    create_task()

    first = client.post("/leadership-reviews/generate", json={"review_type": "nightly"})
    second = client.post("/leadership-reviews/generate", json={"review_type": "nightly"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["review"]["id"] == second.json()["review"]["id"]

    inbox = client.get("/executive-inbox").json()
    assert any(item["source_type"] == "leadership_review" for item in inbox["items"])


def test_briefing_surfaces_latest_leadership_review():
    create_task("Leadership advisor briefing task lacks owner")
    generated = client.post("/leadership-reviews/generate", json={"review_type": "nightly"})
    assert generated.status_code == 200

    briefing = client.get("/briefing").json()
    assert briefing["leadership_advisor"]
    assert briefing["leadership_advisor"]["review_type"] == "nightly"
    assert briefing["leadership_advisor"]["findings"]


def test_leadership_review_lifecycle_and_task_proposals():
    create_task("Leadership advisor proposal task lacks owner")
    generated = client.post("/leadership-reviews/generate", json={"review_type": "manual"})
    review = generated.json()["review"]

    applied = client.post(f"/leadership-reviews/{review['id']}/proposals", json={"finding_indexes": []})
    assert applied.status_code == 200
    assert applied.json()["applied"]

    db = SessionLocal()
    try:
        stored = db.get(LeadershipReview, review["id"])
        assert stored.status == "reviewed"
    finally:
        db.close()

    reviewed = client.post(f"/leadership-reviews/{review['id']}/review")
    assert reviewed.status_code == 200
    dismissed = client.post(f"/leadership-reviews/{review['id']}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["review"]["status"] == "dismissed"
