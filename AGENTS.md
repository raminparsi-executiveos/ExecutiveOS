# ExecutiveOS Codex Implementation Instructions

## Purpose

Use these instructions when making changes in this repository. The current objective is to strengthen ExecutiveOS in five phases, implemented in the exact priority order below.

Do not begin a lower-priority phase until the higher-priority phase is complete, tested, and backward-compatible. Prefer small, reviewable changes, but keep the application usable at the end of every change.

## Repository Context

ExecutiveOS is an AI-first executive memory and decision platform with:

- FastAPI, SQLAlchemy, Pydantic, Alembic, SQLite locally, and PostgreSQL in production.
- A Vite-based browser frontend.
- Natural-language capture, morning briefing, meeting prep, search, memory objects, review alerts, company dashboards, and an integration inbox.
- Pytest regression tests under `tests/`.

Preserve the existing API and user workflows unless a phase below explicitly requires a change.

## General Engineering Requirements

For every phase:

1. Inspect the current implementation and relevant tests before editing.
2. Add or update Alembic migrations for schema changes. Never rely on implicit table recreation.
3. Keep SQLite and PostgreSQL behavior compatible.
4. Add backend regression tests and frontend tests where practical.
5. Run at minimum:
   - `python -m pytest -q`
   - `cd frontend && npm install && npm run build`
6. Do not hard-code company names, people, dates, or sample data into production logic.
7. Preserve provenance, revision history, and auditability.
8. Require explicit user confirmation before AI suggestions modify durable memory, except for direct deterministic user actions such as clicking Complete, Resolve, Delegate, Snooze, or Dismiss.
9. Use stable record IDs for mutations. Do not use fuzzy text matching as the final source of truth.
10. Maintain accessible controls, clear loading states, useful error messages, and keyboard support.
11. Update `README.md` and relevant files in `docs/` when behavior, configuration, APIs, or data models change.
12. Avoid broad refactors unrelated to the active phase.

---

# Priority 1: Durable Resolution Records

## Goal

Replace resolution behavior that depends on scanning recent capture text with durable, auditable records and stable IDs.

## Required Outcome

A risk, meeting action, task, strategic issue, project, alert, or other resolvable item must remain resolved permanently unless explicitly reopened. It must not reappear after additional captures are created.

## Required Data Model

Implement a durable model suitable for individually addressable action and risk items. Choose the cleanest design after reviewing the current models, but the resulting system must support:

- Stable item ID.
- Parent record type and parent record ID.
- Item type, such as `risk`, `meeting_action`, or another supported type.
- Display text.
- Status, including at least `open`, `resolved`, and where appropriate `completed`, `cancelled`, or `reopened`.
- `resolved_at` or `completed_at`.
- `resolved_by` or actor metadata when available.
- Resolution source, such as manual control, capture, API, or imported data.
- Optional resolution note.
- Created and updated timestamps.
- Provenance and revision history.

Existing array fields may remain temporarily for backward compatibility, but durable child records must become the source of truth for active/resolved state.

## Migration Requirements

- Create an Alembic migration.
- Backfill existing meeting action items and risks into durable child records.
- Make the migration idempotent and safe for existing production databases.
- Prevent duplicate child records during migration and subsequent synchronization.
- Preserve original parent arrays for audit compatibility unless removal is handled in a later explicit migration.

## API Requirements

Add deterministic endpoints or extend existing endpoints to support:

- Resolve by stable ID.
- Complete by stable ID where applicable.
- Reopen by stable ID.
- Optional resolution note.
- Retrieval of open and resolved items.

Do not implement Resolve by posting a synthetic sentence such as `Mark X as resolved` to `/capture/confirm` from the frontend.

Natural-language capture may still suggest resolving an existing item, but confirmation must resolve the matched stable ID. If the match is ambiguous, return candidates and require user selection.

## Briefing and Meeting Prep Requirements

- Query durable statuses directly.
- Remove the dependency on the 25 most recent captures for determining whether an item is resolved.
- Return stable IDs and action metadata to the frontend.
- Resolved items must stay hidden from open sections regardless of how many later captures exist.
- Provide a way to view recently resolved items and reopen them.

## Frontend Requirements

- Resolve and Complete controls must call stable-ID endpoints.
- Add Undo/Reopen after successful resolution or completion.
- Use optimistic updates only when rollback on failure is reliable.
- Display confirmation or a lightweight success state.
- Prevent duplicate submissions.

## Priority 1 Tests

Add tests covering at least:

1. A resolved risk remains resolved after more than 25 new captures.
2. Two items with similar text do not resolve each other.
3. Resolving one risk does not resolve its parent strategic issue unless explicitly requested.
4. Reopening restores the item to briefing and meeting prep.
5. Existing meeting action arrays are preserved for audit while child status drives visibility.
6. Migration backfill does not create duplicates.
7. Natural-language resolution with one exact match targets the stable ID.
8. Ambiguous natural-language resolution does not mutate records without confirmation.
9. Resolution provenance and revision history are stored.
10. Frontend Resolve no longer posts a synthetic capture command.

## Priority 1 Acceptance Criteria

Priority 1 is complete only when recent-capture scanning is no longer the source of truth for item resolution and all existing regression tests pass.

---

# Priority 2: Unified Executive Inbox

## Goal

Create one prioritized processing surface for new information and items requiring executive action.

## Required Outcome

The user can process captures, integration suggestions, review alerts, unresolved risks, tasks requiring attention, and decision requests from one inbox.

## Inbox Item Contract

Create a normalized inbox response shape containing at least:

- Stable item ID.
- Source type and source ID.
- Company.
- Title and summary.
- Priority and ranking explanation.
- Created date and freshness.
- Suggested action.
- Available actions.
- Status.
- Owner and due date when applicable.
- Supporting source/provenance links.

Prefer a service layer that normalizes existing records rather than duplicating all source data into a new table. Persist inbox-specific state such as snoozed-until, dismissed, processed, and user ranking overrides.

## Required Actions

Support:

- Accept or approve.
- Delegate.
- Snooze until a date/time.
- Dismiss or archive.
- Open supporting source.
- Convert to task or decision where applicable.
- Bulk processing for compatible actions.

## Ranking Requirements

Rank inbox items using deterministic factors before optional AI assistance:

- Overdue status.
- Critical/high priority.
- Explicitly awaiting the user.
- Blocked work.
- Decision deadlines.
- Staleness.
- Company importance or user-configured weighting.
- Recent material changes.

Return score reasons in the API.

## Frontend Requirements

- Add an `Executive Inbox` primary navigation item.
- Provide filters for company, source type, priority, owner, and status.
- Provide a focused processing mode with keyboard navigation.
- Reflect actions immediately across briefing, meeting prep, memory, alerts, and dashboards.
- Clearly separate destructive dismissal from reversible snoozing.

## Priority 2 Tests

Add tests for:

1. Normalization of each supported source type.
2. Ranking and score reasons.
3. Snoozed items disappearing and returning at the correct time.
4. Dismissed items staying out while remaining auditable.
5. Delegation updating or creating the correct durable record.
6. Approving an integration item updates memory exactly once.
7. Bulk actions reject incompatible item combinations safely.
8. Cross-surface consistency after processing.

## Priority 2 Acceptance Criteria

The inbox must allow the user to process the majority of incoming executive work without visiting separate review surfaces.

---

# Priority 3: Smarter Capture and Date Normalization

## Goal

Improve capture quality, entity matching, date interpretation, duplicate prevention, and confidence handling.

## Required Outcome

Natural-language capture should reliably turn messy input into proposed structured updates while explaining uncertainty and requiring confirmation.

## Date Requirements

- Convert relative dates such as `Friday`, `tomorrow`, `next week`, and `end of month` into ISO dates.
- Interpret dates using the user-configured timezone.
- Return both original text and interpreted date in the preview.
- Require confirmation when a date is materially ambiguous.
- Store normalized dates, not unresolved relative strings, in durable date fields.

## Entity Resolution Requirements

- Match people and companies dynamically from stored memory and aliases.
- Do not hard-code names such as Julio or Mina, or a fixed list of companies, in production classification logic.
- Return match confidence and candidate IDs.
- Avoid silently creating duplicate people, companies, projects, issues, and tasks.
- Use stable IDs in approved updates whenever an existing entity is matched.

## Multi-Item Capture Requirements

Split a single capture into independently reviewable suggestions for:

- Tasks and commitments.
- Decisions.
- Risks.
- Projects.
- People and role changes.
- Metrics.
- Meeting notes and action items.
- Confirmed facts and documents.

Each suggestion must include:

- Suggested operation: create, update, resolve, complete, or link.
- Target record ID when matched.
- Confidence.
- Evidence span from the source text.
- Assumptions or ambiguity warnings.
- Fields to be changed.

## AI and Fallback Requirements

- Keep the local fallback functional without an OpenAI key.
- Make fallback rules generic and data-driven.
- Validate AI structured output strictly.
- Do not allow AI output to bypass authorization, validation, or confirmation.
- Add graceful handling for AI timeout, malformed output, and partial suggestions.

## Priority 3 Tests

Cover at least:

1. Relative date normalization using a fixed test clock and timezone.
2. Ambiguous date preview and confirmation behavior.
3. Existing person and company matching by alias.
4. Duplicate prevention.
5. Multi-item capture splitting.
6. Evidence spans and confidence fields.
7. Generic fallback behavior with no hard-coded personal names.
8. AI failure fallback.
9. Stable-ID updates to existing records.
10. Capture resolution targeting Priority 1 durable items.

## Priority 3 Acceptance Criteria

Capture previews must be more accurate, transparent, and actionable than the current rule-based flow, while remaining safe without AI access.

---

# Priority 4: Interactive Briefing and Meeting Workspaces

## Goal

Turn generated briefing and meeting-prep output into interactive operating workspaces.

## Morning Briefing Requirements

Allow inline actions for supported items:

- Complete or resolve.
- Reopen.
- Edit owner.
- Edit due date.
- Delegate.
- Add note.
- Snooze.
- Convert a risk into a task.
- Create a decision request.
- Open source and revision history.
- Select and process multiple compatible items.

Ensure all actions use stable IDs and update every relevant surface.

## Meeting Prep Requirements

Add:

- Editable agenda ordering.
- Time allocation per agenda item.
- Presenter or owner.
- Decision-required indicator.
- Ability to exclude or include sections.
- Meeting note capture during the meeting.
- Conversion of notes into reviewed tasks, decisions, risks, and follow-ups.
- A post-meeting review step before durable updates are saved.
- Meeting completion status and follow-up summary.

Persist user edits so regenerated meeting prep does not overwrite them without warning.

## UX Requirements

- Support autosave with visible state.
- Provide undo for important changes.
- Maintain mobile and desktop usability.
- Use semantic buttons, labels, focus management, and keyboard navigation.
- Avoid presenting dense raw JSON or developer terminology to end users.

## Priority 4 Tests

Cover:

1. Inline edits persist and appear across surfaces.
2. Agenda ordering persists across regeneration.
3. Meeting notes produce reviewable suggestions rather than immediate uncontrolled writes.
4. Bulk action validation.
5. Undo/reopen behavior.
6. Accessibility-critical controls and labels.
7. Concurrent edit conflict behavior.

## Priority 4 Acceptance Criteria

A user must be able to run a morning review and a leadership meeting without leaving the corresponding workspace for routine actions.

---

# Priority 5: Executive Outcome Tracking and Scoreboard

## Goal

Show whether commitments, decisions, risks, projects, and delegation are producing measurable progress.

## Required Metrics

Implement auditable calculations for:

- Commitments created versus completed.
- Completion rate by owner and company.
- Overdue trend.
- Average time to complete tasks.
- Average time to resolve risks.
- Open decisions and decision age.
- Decisions revisited or reversed.
- Projects without recent updates.
- Meetings with no assigned follow-up.
- Delegated work repeatedly returned to the executive.
- Executive attention distribution by company and category.

## Data Integrity Requirements

- Define every metric in documentation.
- Use stable event timestamps and revision history.
- Make date ranges and timezone explicit.
- Exclude deleted, cancelled, or test records according to documented rules.
- Provide supporting record drill-down for every aggregate.
- Clearly distinguish measured facts from AI-generated observations.

## Frontend Requirements

Add an `Executive Scoreboard` with:

- Company and date-range filters.
- Trend views.
- Owner-level drill-down.
- Data freshness indicators.
- Explanations of metric definitions.
- Links to the records behind each number.

Enhance the morning briefing with concise, deterministic observations, for example:

- Number of open commitments.
- Number overdue.
- Number without owners.
- Old unresolved decisions.
- Companies or projects lacking recent updates.

## Priority 5 Tests

Cover:

1. Metric calculations against fixed fixtures.
2. Date-range boundaries and timezone behavior.
3. Cancelled/deleted record exclusions.
4. Reopened task and risk treatment.
5. Drill-down totals matching aggregate values.
6. Data freshness calculations.
7. No unsupported AI claim being presented as a measured fact.

## Priority 5 Acceptance Criteria

Every displayed executive metric must be reproducible from stored records and linked to supporting detail.

---

# Implementation Sequence

Follow this sequence strictly:

1. Priority 1 schema design and migration.
2. Priority 1 backend services and endpoints.
3. Priority 1 frontend migration away from synthetic capture commands.
4. Priority 1 tests, documentation, and cleanup of obsolete resolution logic.
5. Priority 2 implementation and tests.
6. Priority 3 implementation and tests.
7. Priority 4 implementation and tests.
8. Priority 5 implementation and tests.

At the end of each priority, document:

- What changed.
- Database migrations added.
- API changes.
- Tests added and their results.
- Known limitations.
- Any follow-up work intentionally deferred to the next priority.

## Definition of Done

A priority is complete only when:

- Its acceptance criteria are met.
- Existing tests pass.
- New regression tests pass.
- The frontend production build succeeds.
- Database migrations work on a populated database.
- Documentation is updated.
- No unresolved high-severity regression remains.
