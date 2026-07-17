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


def test_local_fallback_turns_sales_debrief_into_meeting_and_clarifications(monkeypatch):
    monkeypatch.setattr("app.capture_service.analyze_capture", lambda text, memory_context: None)
    capture = (
        "PEC sales meeting check-in debrief: Ryan, Catalina and I met today (07.16.2026) "
        "to discuss sales activities and outlook. I mentioned to the team that we need to focus "
        "on existing clients and come up with new strategy to get our year back on track."
    )

    classified = client.post("/capture/classify", json={"text": capture})

    assert classified.status_code == 200
    payload = classified.json()
    updates = payload["suggested_updates"]
    meeting = next(update for update in updates if update["type"] == "meeting")
    assert meeting["title"] == "PEC sales meeting debrief"
    assert set(meeting["attendees"]) >= {"Ryan", "Catalina"}
    assert any("business result" in follow_up for follow_up in payload["follow_ups"])
    assert any("sales activity target" in follow_up for follow_up in payload["follow_ups"])
    assert payload["diagnostics"]["classification_source"] == "local_fallback"
    assert payload["next_best_action"]
    task_titles = [update["title"] for update in updates if update["type"] == "task"]
    assert "Discuss sales activities and outlook" not in task_titles
    assert "Come up with new strategy" not in task_titles


def test_capture_task_quality_metadata_reaches_audit(monkeypatch):
    monkeypatch.setattr("app.capture_service.analyze_capture", lambda text, memory_context: None)
    classified = client.post("/capture/classify", json={
        "text": "Kyle will send the revised client-retention plan by Friday.",
    })
    assert classified.status_code == 200
    update = next(update for update in classified.json()["suggested_updates"] if update["type"] == "task")
    assert update["quality_score"] >= 70
    assert update["next_best_action"]

    saved = client.post("/capture/confirm", json={
        "capture_id": classified.json()["capture_id"],
        "text": "Kyle will send the revised client-retention plan by Friday.",
        "classification_source": "local_fallback",
        "approved_updates": [update],
    })
    assert saved.status_code == 200

    audit = client.get(f"/captures/{saved.json()['capture_id']}/audit")
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["diagnostics"]["average_task_quality"] >= 70
    assert payload["next_best_action"]
    approved_row = next(row for row in payload["comparison"] if row["approved_mutation"])
    assert approved_row["approved_mutation"]["quality_score"] >= 70


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


def test_local_fallback_does_not_invent_mina_from_minimum_or_passive_feedback(monkeypatch):
    monkeypatch.setattr("app.capture_service.analyze_capture", lambda text, memory_context: None)
    capture = (
        "Create qualified tasks and follow-ups from this capture:\n\n"
        "RYSE wellness leadership meeting prep : Review pip document for Grace and give veronica feedback. "
        "Get timeline from joe for implementing healthcare plan with medical staff on each shift. "
        "Admissions capability to med pass and QEEG and TMS. "
        "Go over plan for once per month contractor to come thru and fix or maintain the house. "
        "Modified binary admissions guideline to include well paying policy otherwise we can get stuck with a client that is not wanted by any other facility. "
        "Let’s see if we can get some Google reviews from Raul before discharge. "
        "When can we expect to eliminate guiding hands (the outsourced therapy group provider)? "
        "Amanda should be ready to take on groups prior to transition. "
        "Should we consider an amft that can work on case management and individual therapy instead of offering Grace a shift in role? "
        "Review Grace pip is owned by Ramin, Arghavan and Joe. "
        "Feedback will be provided during the leadership meeting tomorrow (July 15, 2026). "
        "Joe is the owner of the healthcare plan implantation. "
        "Let’s come up with a list of tasks for facility improvement and maintenance. "
        "The Facility maintenance provider will be selected by end of the week and the first set of tasks will be used to vet the contractor. "
        "Well-paying policy means a minimum of $1k per night. "
        "Raul is a current client so we would like to get the review from him. "
        "Joe is Joseph Licari. "
        "Let’s discuss what criteria and date Amanda will be ready to take over the group therapies."
    )

    classified = client.post("/capture/classify", json={"text": capture})

    assert classified.status_code == 200
    updates = classified.json()["suggested_updates"]
    labels = [update.get("name") or update.get("title") for update in updates]
    assert "Mina" not in labels
    assert "Mina promotion and pay increase" not in labels
    assert not any(update.get("owner") == "Feedback" for update in updates)
    task_titles = [update["title"] for update in updates if update["type"] == "task"]
    assert "Review pip document for Grace and give veronica feedback" in task_titles
    assert any(title.lower().startswith("get timeline from joe") for title in task_titles)
    assert any("facility improvement and maintenance" in title.lower() for title in task_titles)


def test_local_fallback_preserves_sales_meeting_task_context(monkeypatch):
    monkeypatch.setattr("app.capture_service.analyze_capture", lambda text, memory_context: None)
    capture = (
        "Pec sales meeting prep for tomorrow. "
        "Federico to transition to full quote creation on ownership, full site visit coordination ownership, and follow up program ownership by July 21. "
        "Catalina and Ryan to own the task of getting him there. "
        "Outreach must be logged in gohighlevel and also in activity spreadsheet. "
        "Populate every day so that we can review prior to each sales check in. "
        "We need to be more competitive on pricing. Especially on large jobs. "
        "We need to start landing those jobs to get our year back on track. "
        "Structural engineering is able to take on new projects. "
        "We will leverage Yeison until we are able to train or hire his replacement. "
        "The outreach and re-connection with old clients is what will get us to our numbers. "
        "Offer discounts on proposals. "
        "Let’s try to close as many quotes this week as possible."
    )

    classified = client.post("/capture/classify", json={"text": capture})

    assert classified.status_code == 200
    tasks = [update for update in classified.json()["suggested_updates"] if update["type"] == "task"]
    titles = [task["title"] for task in tasks]
    assert "Review prior to each sales check in" not in titles
    outreach = next(task for task in tasks if task["title"] == "Log outreach daily in GoHighLevel and activity spreadsheet")
    assert outreach["recurrence"] == "daily"
    assert outreach["task_type"] == "standing_responsibility"
    assert "leadership-lens" in outreach["tags"]
    assert "The Effective Executive" in outreach["interpretation_notes"]
    assert "High Output Management" in outreach["interpretation_notes"]
    assert "review before each sales check-in" in outreach["definition_of_done"]
    assert "old clients" in outreach["why_it_matters"]
    transition = next(task for task in tasks if task["title"].startswith("Transition Federico"))
    assert transition["assigned_to"] == "Federico"
    assert transition["due_date"] == "July 21"
    assert "quote creation" in transition["expected_deliverable"]
    enablement = next(task for task in tasks if task["title"].startswith("Catalina and Ryan get Federico ready"))
    assert enablement["owner"] == "Catalina and Ryan"
    assert "Federico" in enablement["stakeholders"]
    assert any(task["title"] == "Offer discounts on proposals for competitive pricing" for task in tasks)
    assert any(task["title"] == "Close as many quotes as possible this week" for task in tasks)


def test_leadership_lens_enriches_ai_task_suggestions_and_saved_tasks():
    saved = client.post("/capture/confirm", json={
        "text": "Avery should tighten the PEC quote follow-up process.",
        "classification_source": "ai",
        "approved_updates": [{
            "type": "task",
            "title": "Tighten PEC quote follow-up process",
            "company": "PEC",
            "owner": "Avery",
            "status": "open",
            "priority": "high",
            "source_type": "capture_text",
        }],
    })

    assert saved.status_code == 200
    tasks = client.get("/objects/tasks").json()["items"]
    task = next(item for item in tasks if item["title"] == "Tighten PEC quote follow-up process")
    assert "leadership-lens" in task["tags"]
    assert "measurable result" in task["interpretation_notes"]
    assert task["expected_deliverable"].startswith("Observable outcome")
    assert "accountable owner confirms" in task["definition_of_done"]
