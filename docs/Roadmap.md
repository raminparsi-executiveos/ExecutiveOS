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

### Enhancement Roadmap Priority 3: Provenance and Source History

- Added reusable provenance and revision-history records for durable memory.
- Added object history endpoints exposing source type, source identifier, excerpt, confidence, verification state, classification, supersession fields, and revisions.

### Enhancement Roadmap Priority 4: Contradiction and Stale-Memory Detection

- Added review-alert records and detection for overdue tasks, overdue decisions, stale metrics, conflicting roles, multiple active project owners, and possible reversing decisions.
- Added explicit alert resolution and dismissal flow.

### Enhancement Roadmap Priority 5: Dynamic Meeting Preparation

- Added meeting type, section exclusions, meeting objectives, desired outcomes, questions, open commitments, overdue tasks, metrics, risks, contradictions, sensitive people context, recent changes, follow-up actions, and inclusion reasons.

### Enhancement Roadmap Priority 6: Semantic and Conversational Search

- Added structured filters for company, record type, date range, status, owner, and priority.
- Added conversation IDs plus answer categories for directly supported facts, inferences, missing information, supporting records, and provenance.

### Enhancement Roadmap Priority 7: Company-Specific Dashboards

- Added configurable company dashboard modules, hidden/reordered module support, data freshness, and empty-data indicators.

### Enhancement Roadmap Priority 8: Integration Inbox

- Added reviewed-only inbox flow for Google Calendar event data and uploaded-document text.
- Added suggestion storage, duplicate source identifiers, rejected/approved statuses, source metadata, and approval through existing capture memory workflow.

### Enhancement Roadmap Priority 9: Improved Entity Resolution

- Added entity aliases and suggestion endpoints for possible duplicate people/company alias relationships without automatic merging.

### Enhancement Roadmap Priority 10: Memory Type and Verification Classification

- Added memory classification and verification state fields to capture suggestions and provenance records.
- Briefing/search/prep surfaces preserve classification/provenance context instead of treating every suggestion as an equally verified fact.

### Next Candidate: Memory Backup Import/Export

- Added versioned JSON backup export for durable memory, provenance, revisions, alerts, inbox records, dashboard configs, aliases, captures, briefing views, and search conversations.
- Added explicit backup import in merge or replace mode.
- Added Memory UI controls for exporting a backup file and importing a reviewed backup file.

### Next Candidate: Richer Linking Between Related Objects

- Added read-only related-memory graph endpoints for stored objects.
- Related-memory lookup combines explicit `linked_*` fields, reciprocal references, meeting-task source metadata, attendees, and same-company context.
- Added Memory UI controls to inspect related records grouped by object type.

### Next Candidate: Per-Company Filters and Memory Browsing

- Added company-scoped object listing through the `company` query parameter.
- Added Memory UI company filtering so stored objects can be browsed in a company context.

### Next Candidate: Capture Observability

- Added capture observability endpoint with classification-source counts, AI/fallback usage, fallback rate, image-unavailable count, saved-update totals, and recent capture previews.
- Added Capture UI quality panel so AI classification quality and fallback frequency can be monitored during normal use.

### Next Candidate: Clarification and Memory-Gap Engine

- Added durable clarification records with lifecycle statuses for open, answered, snoozed, dismissed, intentionally unknown, and suppressed questions.
- Added deterministic rules for material missing owners/due dates/next actions/reasoning/metric periods, stale active projects, active-project owner contradictions, ambiguous task language, and disconnected decisions.
- Added clarification endpoints for generation, listing, retrieval, answer preview, confirmation, snoozing, dismissal, intentionally unknown, suppression, and reopening.
- Added clarification cards to the normalized Executive Inbox, Morning Briefing, and relevant Meeting Prep questions.
- Added tests for deduplication, low-value field suppression, preview-before-write, stable-ID confirmation with revision history, lifecycle actions, contradictions, ambiguous language, stale records, briefing limits, inbox integration, and metadata availability.

## Next Candidates

- Review deployed usage and identify the next enhancement set.
