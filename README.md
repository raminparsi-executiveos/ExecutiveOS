# ExecutiveOS

ExecutiveOS is an AI-first executive memory and decision platform for founders, CEOs, and business owners. It captures messy context, turns it into structured executive memory, and generates briefing, meeting-prep, and search answers from that memory.

## Current MVP

The app ships five working workflows:

1. **Capture**: enter natural language or attach a PNG, JPEG, or WebP screenshot, review suggested structured updates, and save only the approved items.
2. **Morning Briefing**: review active priorities, strategic issues, meetings today, open decisions, risks, waiting-on items, and recent captures with company labels, including unresolved context beyond only the newest records.
3. **Meeting Prep**: generate an agenda and context pack from stored companies, people, projects, decisions, meetings, metrics, and recent captures, including unresolved company context for general leadership reviews.
4. **Search / Ask**: ask natural-language questions over executive memory and get a direct answer with supporting records.
5. **Memory**: browse stored objects, edit their fields, or delete incorrect records.

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
| `OPENAI_MODEL` | No | Defaults to `gpt-5.4-mini`. Use a vision-capable model for screenshot capture. |
| `CORS_ORIGINS` | No | Comma-separated allowed origins. Defaults to `*`. |
| `EXECUTIVEOS_USERNAME` | Production | Defaults to `admin`. |
| `EXECUTIVEOS_PASSWORD` | Production | Required on Render; must be at least 12 characters. |
| `SESSION_SECRET` | Production | Required when auth is enabled; must be at least 32 characters. |

Authentication is optional for local development unless `EXECUTIVEOS_PASSWORD` is set. Render sets `RENDER=true`, so authentication is required there. The Blueprint generates `SESSION_SECRET`, but `EXECUTIVEOS_PASSWORD` must be added manually as a secret environment variable.

## Capture Behavior

Capture uses OpenAI structured output when `OPENAI_API_KEY` is configured. Suggested updates are not saved until the user approves them. Screenshots are analyzed through the same review workflow and are not stored as images.

Without an OpenAI key, text capture still works through a visibly labeled local preview classifier. Screenshot classification requires a configured AI connection.

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
- `GET /captures`
- `GET /objects/{object_type}`
- `POST /objects/{object_type}`
- `PATCH /objects/{object_type}/{object_id}`
- `DELETE /objects/{object_type}/{object_id}`
- `POST /meeting-prep`
- `POST /search`

Supported object types are `companies`, `people`, `strategic-issues`, `projects`, `decisions`, `meetings`, `sops`, `documents`, and `metrics`.

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
