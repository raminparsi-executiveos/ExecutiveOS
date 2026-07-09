# Roadmap

## Completed

### Phase 1: Product Foundation

- Created project structure.
- Added product docs for vision, requirements, AI behavior, information model, and review.

### Phase 2: Memory Model

- Added SQLAlchemy models and local SQLite persistence.
- Added PostgreSQL support for hosted deployment.
- Seeded representative development data.

### Phase 3: Core API

- Added routes for health, auth, capture, briefing, meeting prep, search, object creation, object listing, and capture history.
- Added scoped search and meeting-prep ranking.
- Added regression tests for cross-company memory behavior and workflow edge cases.

### Phase 4: Frontend Workflows

- Added Vite frontend for Capture, Morning Briefing, Meeting Prep, and Search / Ask.
- Added authentication UI, API error states, empty states, and approval controls.
- Added responsive layout and reproducible frontend lockfile.

### Phase 5: AI-Assisted Capture

- Added OpenAI structured-output classification.
- Added screenshot capture through vision-capable model input.
- Added local fallback classification for text-only development.
- Added explicit AI-versus-local-preview labeling.

### Phase 6: Deployment and Operational Basics

- Added Render Blueprint for backend, frontend, and PostgreSQL.
- Added production authentication requirements.
- Added operational response headers, health checks, and CORS configuration.
- Added Alembic migration scaffolding and an initial schema migration.

## Next Candidates

- Move hosted deployments fully onto explicit migration execution instead of startup table creation.
- Add first-class object editing in the frontend.
- Add import/export for memory backup.
- Add richer linking between related objects.
- Add calendar and email integrations for meeting context.
- Add per-company filters and memory browsing views.
- Add observability for AI classification quality and fallback frequency.
