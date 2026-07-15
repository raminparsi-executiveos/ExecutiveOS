from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import CaptureInterpretation, CaptureMutation, CaptureRecord, Task


client = TestClient(app)


def test_capture_classification_persists_interpretation_and_mutations(monkeypatch):
    monkeypatch.setattr("app.capture_service.analyze_capture", lambda text, memory_context: None)

    classified = client.post("/capture/classify", json={
        "text": "Kyle will send the revised client-retention plan by Friday.",
    })

    assert classified.status_code == 200
    payload = classified.json()
    assert payload["capture_id"]
    assert payload["interpretation_id"]
    assert payload["mutation_ids"]
    assert payload["capture_interpretation"]["capture_summary"].startswith("Kyle will send")

    db = SessionLocal()
    try:
        capture = db.get(CaptureRecord, payload["capture_id"])
        interpretation = db.get(CaptureInterpretation, payload["interpretation_id"])
        mutations = db.query(CaptureMutation).filter(CaptureMutation.capture_id == capture.id).all()
        assert capture.raw_text.startswith("Kyle will send")
        assert capture.prompt_version == "capture-fidelity-v1"
        assert interpretation.raw_response["follow_ups"] == payload["follow_ups"]
        assert mutations
        assert mutations[0].status == "proposed"
        assert mutations[0].field_operations
    finally:
        db.close()


def test_capture_confirm_links_approved_mutation_to_persisted_task():
    classified = client.post("/capture/classify", json={
        "text": "Kyle should review Julio's work on critical projects before anything is sent to the client.",
    })
    assert classified.status_code == 200
    capture_id = classified.json()["capture_id"]
    update = {
        "type": "task",
        "title": "Kyle review Julio's critical project work before client release",
        "company": "PEC",
        "owner": "Kyle",
        "assigned_to": "Kyle",
        "stakeholders": ["Julio"],
        "task_type": "standing_responsibility",
        "recurrence": "before client release",
        "expected_deliverable": "Reviewed critical project work before it is sent to the client.",
        "definition_of_done": "Kyle has reviewed Julio's work and cleared it for client release.",
        "source_excerpt": "Kyle should review Julio's work on critical projects before anything is sent to the client.",
        "missing_material_fields": ["whether this is one-time or recurring"],
        "operation": "create",
    }

    saved = client.post("/capture/confirm", json={
        "capture_id": capture_id,
        "text": "Kyle should review Julio's work on critical projects before anything is sent to the client.",
        "classification_source": "local_fallback",
        "approved_updates": [update],
    })

    assert saved.status_code == 200
    saved_payload = saved.json()
    assert saved_payload["capture_id"] == capture_id
    assert saved_payload["saved_record_ids"][0]["type"] == "task"

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.title.ilike(update["title"])).one()
        assert task.owner == "Kyle"
        assert task.assigned_to == "Kyle"
        assert task.stakeholders == ["Julio"]
        assert task.expected_deliverable.startswith("Reviewed critical")
        assert task.definition_of_done.startswith("Kyle has reviewed")

        mutation = (
            db.query(CaptureMutation)
            .filter(CaptureMutation.capture_id == capture_id, CaptureMutation.status == "approved_applied")
            .one()
        )
        assert mutation.status == "approved_applied"
        assert mutation.saved_record_type == "task"
        assert mutation.saved_record_id == task.id
        assert mutation.persisted_values["expected_deliverable"] == update["expected_deliverable"]
    finally:
        db.close()


def test_capture_audit_endpoint_compares_original_approved_and_persisted_values():
    saved = client.post("/capture/confirm", json={
        "text": "Joseph is waiting for Veronica to confirm the staffing plan before scheduling interviews.",
        "classification_source": "ai",
        "approved_updates": [{
            "type": "task",
            "title": "Joseph schedule interviews after staffing plan confirmation",
            "company": "PEC",
            "owner": "Joseph",
            "assigned_to": "Joseph",
            "waiting_on": "Veronica",
            "dependencies": ["Veronica confirms the staffing plan"],
            "next_action": "Schedule interviews after confirmation.",
            "source_excerpt": "Joseph is waiting for Veronica to confirm the staffing plan before scheduling interviews.",
        }],
    })
    assert saved.status_code == 200

    audit = client.get(f"/captures/{saved.json()['capture_id']}/audit")
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["capture"]["raw_text"].startswith("Joseph is waiting")
    assert payload["comparison"]
    row = payload["comparison"][0]
    assert row["approved_mutation"]["waiting_on"] == "Veronica"
    assert row["actual_saved_value"]["waiting_on"] == "Veronica"
    assert row["linked_record"]["type"] == "task"


def test_capture_audit_synthesizes_rows_for_legacy_capture_without_mutations():
    db = SessionLocal()
    try:
        task = Task(title="Review Grace PIP document", company="RYSE Wellness", owner="Ramin")
        db.add(task)
        db.flush()
        task_id = task.id
        capture = CaptureRecord(
            raw_text="Review pip document for Grace and give Veronica feedback.",
            classification_source="local_fallback",
            saved_count=1,
            approved_suggestions=[{
                "type": "task",
                "title": "Review Grace PIP document",
                "details": "Review PIP document and provide feedback.",
            }],
            saved_record_ids=[{"type": "task", "id": task_id, "suggestion_index": 0}],
        )
        db.add(capture)
        db.commit()
        capture_id = capture.id
    finally:
        db.close()

    audit = client.get(f"/captures/{capture_id}/audit")

    assert audit.status_code == 200
    payload = audit.json()
    assert payload["comparison"]
    assert payload["comparison"][0]["linked_record"] == {"type": "task", "id": task_id}
    assert payload["comparison"][0]["omitted_or_unresolved_context"]["status"] == "approved_legacy"
    assert {action["key"] for action in payload["available_actions"]} >= {"review_again", "create_tasks"}


def test_capture_fidelity_records_are_included_in_backup():
    saved = client.post("/capture/confirm", json={
        "text": "Mina will prepare the weekly margin review.",
        "classification_source": "ai",
        "approved_updates": [{
            "type": "task",
            "title": "Mina prepare weekly margin review",
            "company": "PEC",
            "owner": "Mina",
            "recurrence": "weekly",
            "expected_deliverable": "Weekly margin review prepared.",
        }],
    })
    assert saved.status_code == 200

    backup = client.get("/backup/export")
    assert backup.status_code == 200
    records = backup.json()["records"]
    assert "capture_interpretations" in records
    assert "capture_mutations" in records
    assert any(record["capture_id"] == saved.json()["capture_id"] for record in records["capture_mutations"])


def test_capture_list_mutation_appends_risk_without_replacing_existing_values():
    created = client.post("/objects/projects", json={"attributes": {
        "title": "Quote generator rollout",
        "company": "PEC",
        "status": "active",
        "risks": ["Slow estimator adoption"],
    }})
    assert created.status_code == 200

    saved = client.post("/capture/confirm", json={
        "text": "Add a risk to Quote generator rollout: pricing validation gap.",
        "classification_source": "ai",
        "approved_updates": [{
            "type": "project",
            "title": "Quote generator rollout",
            "risks": ["Pricing validation gap"],
            "field_operations": {"risks": "append"},
        }],
    })
    assert saved.status_code == 200

    projects = client.get("/objects/projects").json()["items"]
    project = next(item for item in projects if item["title"] == "Quote generator rollout")
    assert project["risks"] == ["Slow estimator adoption", "Pricing validation gap"]


def test_capture_explicit_clear_can_remove_task_owner_after_review():
    created = client.post("/objects/tasks", json={"attributes": {
        "title": "Reassign Meridian handoff owner",
        "company": "PEC",
        "owner": "Kyle",
        "status": "open",
    }})
    assert created.status_code == 200

    saved = client.post("/capture/confirm", json={
        "text": "Kyle is no longer the owner of the Meridian handoff. Leave the owner open for now.",
        "classification_source": "ai",
        "approved_updates": [{
            "type": "task",
            "title": "Reassign Meridian handoff owner",
            "field_operations": {"owner": "clear"},
            "operation": "update",
        }],
    })
    assert saved.status_code == 200

    tasks = client.get("/objects/tasks").json()["items"]
    task = next(item for item in tasks if item["title"] == "Reassign Meridian handoff owner")
    assert task["owner"] == ""
