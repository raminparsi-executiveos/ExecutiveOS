# ExecutiveOS

ExecutiveOS is an AI-first executive memory and decision platform for founders, CEOs, and business owners. It captures messy context, turns it into structured executive memory, and generates briefing, meeting-prep, and search answers from that memory.

## Current MVP

The app ships the core executive-memory workflows plus roadmap support surfaces:

1. **Capture**: enter natural language or attach a PNG, JPEG, or WebP screenshot, review suggested structured updates, and save only the approved items.
2. **Capture Audit**: compare original input, screenshot evidence summaries, AI interpretation, approved mutations, rejected suggestions, and actual persisted values for any capture.
3. **Morning Briefing**: review a ranked command center with needs-attention, delegation, overdue, blocked/waiting, changed-since-last-briefing, and upcoming sections, plus supporting memory context.
4. **Meeting Prep**: generate an agenda and context pack from stored companies, people, projects, decisions, meetings, metrics, and recent captures, including unresolved company context for general leadership reviews.
5. **Search / Ask**: ask natural-language questions over executive memory and get a direct answer with supporting records.
6. **Memory**: browse stored objects, edit their fields, complete or reopen tasks, or delete incorrect records.
7. **Review Alerts**: inspect stale, overdue, contradictory, or duplicate-looking memory and resolve alerts explicitly.
8. **Company Dashboards**: view configurable company-specific modules with data freshness.
9. **Integration Inbox**: stage Google Calendar event data and uploaded-document text for review before approval.
10. **Clarifications Needed**: review high-value questions about missing owners, stale assumptions, contradictions, ambiguous action language, and disconnected records before confirming any memory changes.
11. **Leadership Advisor**: generate evidence-grounded leadership reviews after approved captures, on demand, or through a nightly run; review or approve proposed follow-ups before any durable memory change.
12. **Durable Resolution Tracking**: resolve and reopen risks, meeting actions, and other follow-up items by stable ID so completed items stay out of briefing and meeting prep.
13. **Memory Backup**: export durable memory to a JSON backup or import a reviewed backup in merge or replace mode.

## Tech Stack

- Backend: FastAPI, SQLAlchemy, Pydantic, SQLite locally, PostgreSQL on Render
- Frontend: Vite static app
- AI: OpenAI Responses API with structured output, optional in local development
- Tests: pytest

## Repository Layout

```text
backend/          FastAPI app, database models, auth, AI capture logic
frontend/         Vite browser app
docs/             Product, AI behavior, roadmap, and review docs
tests/            API and workflow regression tests
render.yaml       Render Blueprint for backend, frontend, and PostgreSQL
Makefile          Common local commands
```

## Getting Started

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. Health check:

```bash
curl http://127.0.0.1:8000/health
```

Local data is stored in `backend/executiveos.db` unless `DATABASE_URL` is set.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://127.0.0.1:8000` for API calls. Set `VITE_API_URL` when the backend is hosted elsewhere.

## Configuration

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | No locally, yes on Render | Defaults to local SQLite. Render wires this to PostgreSQL. |
| `OPENAI_API_KEY` | No | Enables AI capture classification and screenshot analysis. |
| `OPENAI_MODEL` | No | Defaults to `gpt-5.6`. Use a vision-capable model for screenshot capture. |
| `OPENAI_IMAGE_DETAIL` | No | Defaults to `high` to avoid GPT-5.6 original-detail screenshot latency. Use `low` for faster rough reads. |
| `OPENAI_TIMEOUT_SECONDS` | No | Defaults to `60`; Render defaults to `90` for slower screenshot analysis. |
| `LEADERSHIP_REVIEW_TIMEZONE` | No | Defaults to `America/Los_Angeles`; used to make nightly advisor reviews idempotent by local day. |
| `CORS_ORIGINS` | No | Comma-separated allowed origins. Defaults to `*`. |
| `EXECUTIVEOS_USERNAME` | Production | Defaults to `admin`. |
| `EXECUTIVEOS_PASSWORD` | Production | Required on Render; must be at least 12 characters. |
| `SESSION_SECRET` | Production | Required when auth is enabled; must be at least 32 characters. |

Authentication is optional for local development unless `EXECUTIVEOS_PASSWORD` is set. Render sets `RENDER=true`, so authentication is required there. The Blueprint generates `SESSION_SECRET`, but `EXECUTIVEOS_PASSWORD` must be added manually as a secret environment variable.

## Capture Behavior

Capture uses OpenAI structured output when `OPENAI_API_KEY` is configured. Suggested updates are not saved until the user approves them. Screenshots are analyzed through the same review workflow and are not stored as images.

Without an OpenAI key, text capture still works through a visibly labeled local preview classifier. Screenshot classification requires a configured AI connection.

Every classification now creates an auditable source capture and interpretation before durable memory is changed. Confirmation links approved updates to capture mutation rows, saved record IDs, and the exact persisted values. The Capture Audit tab and `GET /captures/{capture_id}/audit` endpoint expose this comparison so lost context, user edits, rejected suggestions, duplicate-looking creates, and approved-vs-saved mismatches can be reviewed later.

Capture accepts:

- Text up to 20,000 characters
- Up to 5 PNG, JPEG, or WebP screenshots up to 5 MB each
- Up to 50 approved updates per confirmation

## API Overview

Important endpoints:

- `GET /health`
- `GET /auth/status`
- `POST /auth/login`
- `GET /briefing`
- `POST /capture`
- `POST /capture/classify`
- `POST /capture/confirm`
- `GET /capture/observability`
- `GET /captures/{capture_id}/audit`
- `GET /backup/export`
- `POST /backup/import`
- `GET /captures`
- `GET /objects/{object_type}`
- `POST /objects/{object_type}`
- `PATCH /objects/{object_type}/{object_id}`
- `DELETE /objects/{object_type}/{object_id}`
- `GET /objects/{object_type}/{object_id}/history`
- `GET /objects/{object_type}/{object_id}/related`
- `GET /review-alerts`
- `POST /review-alerts/{alert_id}/resolve`
- `GET /dashboards/{company}`
- `PUT /dashboards/{company}/config`
- `GET /integration-inbox`
- `POST /integration-inbox`
- `POST /integration-inbox/{item_id}/approve`
- `GET /executive-inbox`
- `GET /resolvable-items`
- `POST /resolvable-items/{item_id}/resolve`
- `POST /resolvable-items/{item_id}/reopen`
- `GET /leadership-reviews`
- `GET /leadership-reviews/{review_id}`
- `POST /leadership-reviews/generate`
- `POST /leadership-reviews/nightly/run`
- `POST /leadership-reviews/{review_id}/review`
- `POST /leadership-reviews/{review_id}/dismiss`
- `POST /leadership-reviews/{review_id}/proposals`
- `POST /clarifications/generate`
- `GET /clarifications`
- `GET /clarifications/{clarification_id}`
- `POST /clarifications/{clarification_id}/answer`
- `POST /clarifications/{clarification_id}/confirm`
- `POST /clarifications/{clarification_id}/snooze`
- `POST /clarifications/{clarification_id}/dismiss`
- `POST /clarifications/{clarification_id}/intentionally-unknown`
- `POST /clarifications/{clarification_id}/suppress`
- `POST /clarifications/{clarification_id}/reopen`
- `POST /entity-aliases`
- `GET /entity-resolution/suggestions`
- `POST /meeting-prep`
- `POST /search`

Supported object types are `companies`, `people`, `strategic-issues`, `projects`, `decisions`, `meetings`, `sops`, `documents`, `metrics`, and `tasks`.

Task records support owners, assigned performers, delegators, waiting-on parties, expected deliverables, definitions of done, why-it-matters notes, dependencies, follow-up dates, recurrence, task type, source excerpts, confidence, due dates, status, priority, source metadata, blockers, next actions, tags, completion history, and overdue derivation. Meeting `action_items` and risk arrays remain on parent records for audit, while durable `resolvable_items` child records drive open/resolved visibility in briefing and meeting prep. Briefing rankings explain why each command-center item appears through score reasons, source summaries, owners, due dates, and recommended next actions.

Object listing supports `?company=...` for company-scoped memory browsing. The Memory screen includes the same filter so related company context can be reviewed without switching to company dashboards.

Provenance and revision history are stored separately from memory objects. Search responses distinguish directly supported facts, inferences, and missing information. Meeting prep supports meeting type and section exclusions. Integration Inbox suggestions never modify durable memory until approved.

Clarifications are durable review cards generated by deterministic rules. They surface in the Executive Inbox, Morning Briefing, and relevant Meeting Prep output, but answers only create a proposed update. Durable memory changes happen only after confirming the preview against the stable target record ID.

Leadership Advisor reviews are durable, evidence-linked review cards inspired by practical executive operating principles. Capture reviews run after approved capture saves and do not block the save if generation fails. Nightly reviews are idempotent by local date and can be triggered from Render Cron with `POST /leadership-reviews/nightly/run`; manual reviews use `POST /leadership-reviews/generate`. Advisor proposals are staged until the user explicitly applies them from Executive Inbox or the API.

Memory backups use a versioned JSON envelope containing durable memory tables, provenance, revision history, review alerts, integration inbox records, clarifications, dashboard configuration, aliases, captures, capture interpretations, capture mutations, and conversations. Import defaults to merge mode; replace mode intentionally clears supported memory tables before restoring the backup.

Related memory views combine explicit `linked_*` fields, reciprocal links, task/meeting source links, attendees, and same-company context so related records can be inspected without duplicating memory.

Capture observability summarizes recent classification sources, fallback frequency, image-unavailable events, saved-update rates, no-save captures, created-vs-updated mutation counts, task qualification gaps, rejected suggestions, user edits, approved-vs-persisted mismatches, and prompt-version performance so AI quality and local fallback usage can be monitored.

## Release Checklist

- Run `python -m pytest -q`.
- Run `cd frontend && npm run build` or at least the bundled `esbuild` check when Node is unavailable.
- Apply migrations with `alembic upgrade head` or deploy through the backend Docker startup command.
- Verify `/health`, `/auth/status`, `/briefing`, `/executive-inbox`, and `/capture/observability` on the deployed backend.
- Confirm Render has `EXECUTIVEOS_PASSWORD`, `SESSION_SECRET`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_IMAGE_DETAIL`, `DATABASE_URL`, and production `CORS_ORIGINS`.
- Confirm frontend `VITE_API_URL` points to the backend, not the static frontend URL.
- Trigger or schedule the nightly Leadership Advisor endpoint after auth is configured.

## Testing and Build

Run backend tests:

```bash
python -m pytest -q
```

Apply database migrations:

```bash
alembic upgrade head
```

Build the frontend:

```bash
cd frontend
npm run build
```

Makefile shortcuts:

```bash
make test
make build-frontend
make build-backend
make start-frontend
```

## Render Deployment

The root `render.yaml` provisions:

- `executiveos-backend`: Docker web service
- `executiveos-frontend`: static Vite site
- `executiveos-db`: PostgreSQL database

During Blueprint deployment, Render wires `DATABASE_URL` into the backend and `VITE_API_URL` into the frontend. Add `EXECUTIVEOS_PASSWORD` and `OPENAI_API_KEY` manually in Render's Environment page. Data stored in local SQLite is for development only and is not migrated to Render.

The backend Docker container runs pending Alembic migrations before starting the API. Existing databases created before Alembic are stamped at the matching baseline and then upgraded.
