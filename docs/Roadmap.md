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

### Enhancement Roadmap Priority 1: Formal Task and Action Model

- Added first-class task memory with explicit statuses, priorities, owners, due dates, source metadata, blockers, next actions, tags, review timestamps, and completion history.
- Added task creation, editing, deletion, completion, and reopening through the API and Memory UI.
- Converted approved capture commitments and meeting action items into task records while preserving original meeting action-item text.
- Updated briefing, meeting prep, and search to include open task context and hide completed tasks from open/waiting views without deleting task history.

### Enhancement Roadmap Priority 2: Ranked Today Dashboard

- Reworked Morning Briefing into ranked Needs Your Attention, Delegate or Follow Up, Overdue, Blocked or Waiting, Changed Since Last Briefing, and Upcoming sections.
- Added transparent score reasons, source summaries, owners, due dates, statuses, why-it-matters copy, and recommended next actions for ranked items.
- Added per-user briefing-view tracking so meaningful records changed after the prior briefing can be surfaced.
- Updated the frontend briefing view into a compact executive command-center layout while preserving supporting memory sections.

## Next Candidates

- Continue Enhancement Roadmap Priority 3: provenance and source history.
- Add import/export for memory backup.
- Add richer linking between related objects.
- Add calendar and uploaded-document ingestion through the approved Integration Inbox scope.
- Add per-company filters and memory browsing views.
- Add observability for AI classification quality and fallback frequency.
