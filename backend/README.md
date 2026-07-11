# Backend

The backend is a FastAPI service that stores executive memory, classifies capture input, serves briefing and meeting-prep outputs, and answers search questions.

## Local Development

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The service runs at `http://127.0.0.1:8000`.

Useful checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/auth/status
```

Apply schema migrations from the repository root:

```bash
alembic upgrade head
```

## Environment Variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy database URL. Defaults to `sqlite:///./executiveos.db`. `postgres://` URLs are normalized to `postgresql://`. |
| `OPENAI_API_KEY` | Enables AI capture classification and screenshot extraction. |
| `OPENAI_MODEL` | Capture model. Defaults to `gpt-5.6`. |
| `OPENAI_IMAGE_DETAIL` | Screenshot image detail. Defaults to `high`; set `low` for faster rough reads. |
| `OPENAI_TIMEOUT_SECONDS` | OpenAI request timeout. Defaults to `60`; Render defaults to `90` for screenshot analysis. |
| `CORS_ORIGINS` | Comma-separated browser origins. Defaults to `*`. |
| `EXECUTIVEOS_USERNAME` | Login username. Defaults to `admin`. |
| `EXECUTIVEOS_PASSWORD` | Enables auth locally and is required on Render. Minimum 12 characters. |
| `SESSION_SECRET` | HMAC secret for bearer tokens. Minimum 32 characters. |

Authentication is required when `EXECUTIVEOS_PASSWORD` is set or when Render sets `RENDER=true`. Tokens expire after 12 hours. Failed login attempts are rate-limited per client.

## API Surface

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Checks API and database availability. |
| `GET` | `/auth/status` | Reports whether auth is required and configured. |
| `POST` | `/auth/login` | Issues a bearer token. |
| `GET` | `/briefing` | Returns ranked executive briefing sections and supporting memory context. |
| `POST` | `/capture` | Classifies text and optionally saves suggested updates immediately. |
| `POST` | `/capture/classify` | Classifies text and optional screenshot data for review. Supports `image_data` or up to 5 values in `image_data_list`. |
| `POST` | `/capture/confirm` | Saves approved capture updates. |
| `GET` | `/captures` | Lists confirmed capture records. |
| `GET` | `/objects/{object_type}` | Lists stored objects. |
| `POST` | `/objects/{object_type}` | Creates a stored object from validated attributes. |
| `PATCH` | `/objects/{object_type}/{object_id}` | Updates validated fields on a stored object. |
| `DELETE` | `/objects/{object_type}/{object_id}` | Deletes a stored object. |
| `GET` | `/objects/{object_type}/{object_id}/history` | Returns provenance and revision history for a stored object. |
| `GET` | `/review-alerts` | Generates and lists review alerts for stale, conflicting, overdue, or duplicate-looking memory. |
| `POST` | `/review-alerts/{alert_id}/resolve` | Confirms, updates, merges, supersedes, or dismisses a review alert. |
| `GET` | `/dashboards/{company}` | Returns a configurable company dashboard with data freshness. |
| `PUT` | `/dashboards/{company}/config` | Updates visible dashboard modules and order. |
| `GET` | `/integration-inbox` | Lists staged calendar/document inbox items. |
| `POST` | `/integration-inbox` | Creates an inbox item from Google Calendar event data or uploaded-document text. |
| `POST` | `/integration-inbox/{item_id}/approve` | Saves reviewed inbox suggestions through the approval workflow. |
| `GET` | `/executive-inbox` | Lists normalized executive inbox items, including clarification cards. |
| `POST` | `/clarifications/generate` | Runs deterministic clarification rules and deduplicates resulting cards. |
| `GET` | `/clarifications` | Lists clarification cards with status, company, type, target, and score filters. |
| `GET` | `/clarifications/{clarification_id}` | Retrieves one clarification with evidence and proposed update state. |
| `POST` | `/clarifications/{clarification_id}/answer` | Stores an answer and returns a proposed update preview without mutating memory. |
| `POST` | `/clarifications/{clarification_id}/confirm` | Applies the reviewed proposed update to stable target IDs and records revision history. |
| `POST` | `/clarifications/{clarification_id}/snooze` | Hides a clarification until an ISO datetime. |
| `POST` | `/clarifications/{clarification_id}/dismiss` | Dismisses a clarification while keeping it auditable. |
| `POST` | `/clarifications/{clarification_id}/intentionally-unknown` | Marks the answer intentionally unknown without changing target memory. |
| `POST` | `/clarifications/{clarification_id}/suppress` | Suppresses a clarification rule for the supplied scope. |
| `POST` | `/clarifications/{clarification_id}/reopen` | Reopens an answered, dismissed, snoozed, or suppressed clarification. |
| `POST` | `/entity-aliases` | Stores a confirmed alias for entity resolution. |
| `GET` | `/entity-resolution/suggestions` | Lists possible duplicate or alias relationships requiring confirmation. |
| `GET` | `/backup/export` | Exports a versioned JSON backup of durable memory, provenance, review state, aliases, inbox records, dashboards, captures, and conversations. |
| `POST` | `/backup/import` | Imports a backup in `merge` or explicit `replace` mode. |
| `GET` | `/objects/{object_type}/{object_id}/related` | Returns related memory grouped by object type using explicit links, reciprocal links, meeting/task source metadata, attendees, and company context. |
| `GET` | `/capture/observability` | Summarizes capture classification sources, fallback rate, image-unavailable count, saved updates, and recent capture previews. |
| `POST` | `/tasks/{task_id}/complete` | Marks a task complete and keeps it searchable. |
| `POST` | `/tasks/{task_id}/reopen` | Reopens a completed or cancelled task. |
| `POST` | `/meeting-prep` | Generates agenda and context for a meeting. |
| `POST` | `/search` | Answers a natural-language question over memory. |

Object types: `companies`, `people`, `strategic-issues`, `projects`, `decisions`, `meetings`, `sops`, `documents`, `metrics`, and `tasks`.

Object listing accepts an optional `company` query parameter for company-scoped memory browsing. For `companies`, the filter applies to company name; for other objects with a `company` field, it applies to that field.

Tasks use statuses `open`, `in_progress`, `waiting`, `blocked`, `completed`, and `cancelled`, with priorities `critical`, `high`, `medium`, and `low`. Approved capture task suggestions and meeting action items create task records without deleting the original meeting action-item text.

The briefing endpoint ranks tasks, decisions, risks, meetings, captures, and active memory into Needs Your Attention, Delegate or Follow Up, Overdue, Blocked or Waiting, Changed Since Last Briefing, and Upcoming. Each ranked item includes score reasons, owner, company, status, due date, recommended next action, and compact source information.

Clarifications are deterministic, durable questions about material missing context, stale records, contradictions, ambiguous action language, and disconnected decisions. They appear in `/executive-inbox`, the `clarifications_needed` briefing section, and relevant meeting prep questions. Answering a clarification creates a preview; confirming it is the separate operation that updates stable target records and creates revision history.

Capture-approved records, manual object edits, and inbox approvals create provenance/revision records. Search supports company, record type, date, status, owner, priority, and conversation filters and returns directly supported facts, inferences, missing information, and supporting records.

Backup import/export is intentionally explicit and user-initiated. Merge mode upserts records by backup id; replace mode clears supported memory tables before restoring the uploaded backup.

Related-memory lookup is read-only. It does not create inferred links; it exposes the current graph from stored structured fields and source metadata.

Capture observability is read-only and derived from `capture_records`; it does not inspect prompts, screenshots, or model internals.

## Docker

Build from the repository root:

```bash
docker build -t executiveos-backend -f Dockerfile .
```

Run locally:

```bash
docker run --rm -p 8000:8000 -e PORT=8000 executiveos-backend
```

For the alternate backend Dockerfile:

```bash
docker build -t executiveos-backend-dev -f backend/Dockerfile .
```

## Render

The root `render.yaml` is the source of truth for deployment. It creates the backend service, frontend static site, and PostgreSQL database. Render injects `DATABASE_URL`; add `EXECUTIVEOS_PASSWORD` and `OPENAI_API_KEY` manually as secret environment variables.

The Docker startup command runs `python -m app.migrate` before starting the API, so pending Alembic migrations are applied during deploy. Existing databases created before Alembic are stamped at the matching baseline and then upgraded.
