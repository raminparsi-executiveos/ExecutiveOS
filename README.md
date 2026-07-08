# ExecutiveOS

ExecutiveOS is an AI-first operating system for founders, CEOs, and business owners.

## Overview

This MVP focuses on four screens:

1. Capture
2. Morning Briefing
3. Meeting Prep
4. Search / Ask

The system stores executive memory as structured objects and generates outputs on demand.

## Tech Stack

- Backend: FastAPI, SQLAlchemy, SQLite locally / PostgreSQL on Render
- Frontend: React + Vite
- AI: OpenAI API (optional in local development)

## Getting Started

- Backend: `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload`
- Frontend: `cd frontend && npm install && npm run dev`

Set `OPENAI_API_KEY` to enable AI classification. `OPENAI_MODEL` defaults to `gpt-5.4-mini`. Without a key, Capture uses a limited local preview classifier so development remains usable; production should configure the key.

Capture accepts text and PNG, JPEG, or WebP screenshots up to 5 MB. Screenshot extraction uses the configured vision-capable OpenAI model, returns structured suggestions for review, and does not store the image itself. Text-only capture retains its limited local fallback when AI is unavailable.

Authentication is optional for local development and required on Render. Configure `EXECUTIVEOS_USERNAME` (defaults to `admin`), an `EXECUTIVEOS_PASSWORD` of at least 12 characters, and a random `SESSION_SECRET` of at least 32 characters. The Blueprint generates the session secret, but existing Render services require adding the password manually in the service's Environment page.

## Render deployment

The root `render.yaml` provisions the API, static frontend, and PostgreSQL database. The frontend API URL and backend database URL are wired automatically during Blueprint deployment. Data stored in local SQLite is for development only and is not migrated to Render.
