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

- Backend: FastAPI, SQLAlchemy, SQLite
- Frontend: React + Vite
- AI: OpenAI API (optional in local development)

## Getting Started

- Backend: `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload`
- Frontend: `cd frontend && npm install && npm run dev`
