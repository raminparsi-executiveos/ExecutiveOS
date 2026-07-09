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
| `OPENAI_MODEL` | Capture model. Defaults to `gpt-5.4-mini`. |
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
| `GET` | `/briefing` | Returns current executive briefing sections. |
| `POST` | `/capture` | Classifies text and optionally saves suggested updates immediately. |
| `POST` | `/capture/classify` | Classifies text and optional screenshot data for review. |
| `POST` | `/capture/confirm` | Saves approved capture updates. |
| `GET` | `/captures` | Lists confirmed capture records. |
| `GET` | `/objects/{object_type}` | Lists stored objects. |
| `POST` | `/objects/{object_type}` | Creates a stored object from validated attributes. |
| `PATCH` | `/objects/{object_type}/{object_id}` | Updates validated fields on a stored object. |
| `DELETE` | `/objects/{object_type}/{object_id}` | Deletes a stored object. |
| `POST` | `/meeting-prep` | Generates agenda and context for a meeting. |
| `POST` | `/search` | Answers a natural-language question over memory. |

Object types: `companies`, `people`, `strategic-issues`, `projects`, `decisions`, `meetings`, `sops`, `documents`, and `metrics`.

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
