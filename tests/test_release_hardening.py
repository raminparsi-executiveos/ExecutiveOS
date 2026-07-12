import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.main import app


client = TestClient(app)


def create(object_type, attributes):
    response = client.post(f"/objects/{object_type}", json={"attributes": attributes})
    assert response.status_code == 200
    return response.json()["object"]


def test_resolved_risk_stays_resolved_after_many_later_captures_and_can_reopen():
    create("strategic-issues", {
        "title": "PEC release risk",
        "company": "PEC",
        "status": "active",
        "risks": ["Release blocker remains unresolved"],
    })
    risk = next(item for item in client.get("/resolvable-items?item_type=risk").json()["items"] if item["label"] == "Release blocker remains unresolved")

    resolved = client.post(f"/resolvable-items/{risk['id']}/resolve", json={"note": "Done"})
    assert resolved.status_code == 200

    for index in range(30):
        saved = client.post("/capture/confirm", json={
            "text": f"Later unrelated capture {index}",
            "classification_source": "manual",
            "approved_updates": [],
        })
        assert saved.status_code == 200

    briefing = client.get("/briefing").json()
    visible = [item["title"] for section in ("needs_your_attention", "top_priorities") for item in briefing[section]]
    assert "Release blocker remains unresolved" not in visible

    reopened = client.post(f"/resolvable-items/{risk['id']}/reopen", json={"note": "Needs another look"})
    assert reopened.status_code == 200
    assert reopened.json()["item"]["status"] == "reopened"
    refreshed = client.get("/briefing").json()
    visible_after_reopen = [item["title"] for item in refreshed["needs_your_attention"]]
    assert "Release blocker remains unresolved" in visible_after_reopen


def test_similar_resolvable_items_do_not_resolve_each_other_by_stable_id():
    create("strategic-issues", {
        "title": "PEC pricing risks",
        "company": "PEC",
        "status": "active",
        "risks": ["Pricing logic validation", "Pricing logic training"],
    })
    items = client.get("/resolvable-items?item_type=risk").json()["items"]
    validation = next(item for item in items if item["label"] == "Pricing logic validation")
    training = next(item for item in items if item["label"] == "Pricing logic training")

    resolved = client.post(f"/resolvable-items/{validation['id']}/resolve", json={})
    assert resolved.status_code == 200

    remaining = client.get("/resolvable-items?item_type=risk").json()["items"]
    assert not any(item["id"] == validation["id"] for item in remaining)
    assert any(item["id"] == training["id"] for item in remaining)


def test_executive_inbox_normalizes_tasks_alerts_integration_and_resolvable_items():
    create("tasks", {
        "title": "Release inbox task",
        "company": "PEC",
        "status": "open",
        "priority": "high",
        "due_date": "2020-01-01",
    })
    create("strategic-issues", {
        "title": "Release inbox risk source",
        "company": "PEC",
        "status": "active",
        "risks": ["Release inbox risk"],
    })
    alert = client.get("/review-alerts").json()
    assert alert["items"]
    integration = client.post("/integration-inbox", json={
        "source_type": "uploaded_document",
        "source_identifier": "release-note",
        "source_title": "Release note",
        "extracted_text": "Task: release inbox integration review",
    })
    assert integration.status_code == 200

    inbox = client.get("/executive-inbox").json()["items"]
    source_types = {item["source_type"] for item in inbox}
    assert {"task", "review_alert", "integration_inbox", "resolvable_item"} <= source_types
    assert all("score_reasons" in item for item in inbox)
