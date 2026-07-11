# ExecutiveOS Codex Implementation Instructions

## Purpose

Use these instructions when making changes in this repository. The current objective is to strengthen ExecutiveOS in six phases, implemented in the exact priority order below.

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

The user can process captures, integration suggestions, review alerts, unresolved risks, tasks requiring attention, decision requests, and later clarification questions from one inbox.

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

# Priority 3: Clarification and Memory-Gap Engine

## Goal

Proactively identify material gaps, stale assumptions, contradictions, ambiguous language, and disconnected records in existing memory, then ask a small number of high-value questions that improve executive decisions and follow-through.

## Product Principle

ExecutiveOS must not ask questions merely to make the database more complete. Ask only when the answer is likely to improve a decision, delegation, deadline, risk response, meeting, briefing, or company-level understanding.

The system must behave as a controlled clarification workflow, not a conversational interrogation loop.

## Required Outcome

ExecutiveOS produces a ranked clarification queue. Each clarification card explains:

- What is unclear or missing.
- Why the clarification matters.
- Which records and evidence caused the question.
- Any likely answers supported by existing memory.
- The exact proposed memory changes that would follow an answer.
- Available actions: answer, select a suggested answer, ask later, dismiss, intentionally unknown, or suppress this clarification type for the relevant scope.

No answer may modify durable memory until the user reviews and confirms the proposed update.

## Clarification Types

Support at least the following categories:

### Missing Material Context

Examples include:

- Active project without an owner.
- Important task without a due date or next action.
- Decision without reasoning, effective date, or responsible owner.
- Metric without a reporting period, unit, target, or freshness expectation.
- Risk without an owner, mitigation, status, or related project.
- Waiting or blocked task without a follow-up date.

Do not generate a question for every optional empty field. Use materiality rules by record type and status.

### Stale Information

Examples include:

- Active project with no meaningful update within its expected cadence.
- Waiting task with no follow-up activity.
- Metric older than its configured reporting frequency.
- Person priority or responsibility that may no longer be current.
- Decision or risk still marked open after related work appears complete.

Staleness thresholds must be configurable globally and overridable by company, record type, or individual record.

### Contradictions

Examples include:

- Different owners for the same initiative.
- Conflicting statuses, deadlines, metric values, or decision outcomes.
- A project marked active while directly related evidence says it was completed.
- A person assigned to incompatible roles in overlapping contexts.

A contradiction question must show both sides and their provenance. Never silently choose one.

### Ambiguous Language

Detect material phrases such as:

- `soon`
- `almost complete`
- `Kyle is handling it`
- `waiting on them`
- `follow up later`
- `pricing looks good`

Generate a clarification only when the ambiguity affects an actionable field such as owner, due date, status, blocker, amount, or decision.

### Disconnected Information

Examples include:

- Decision with no linked project, issue, or company.
- Meeting action without a task, owner, or parent meeting link.
- Risk without a durable parent.
- Frequently mentioned person without a resolved person record.
- Capture or document containing an apparent commitment that is not represented by a task.

## Data Model Requirements

Create a durable clarification model or equivalent auditable structure supporting:

- Stable clarification ID.
- Clarification type and subtype.
- Status: at least `open`, `answered`, `snoozed`, `dismissed`, `intentionally_unknown`, and `suppressed`.
- Question text.
- Explanation of why the question matters.
- Target record type and stable ID.
- Related evidence records with source type, source ID, revision or capture ID, and concise evidence text.
- Deterministic score and score reasons.
- Suggested answers or candidate records where applicable.
- Proposed update payload, without applying it.
- Confidence and uncertainty metadata.
- Created, updated, answered, snoozed-until, and dismissed timestamps.
- User response and optional note.
- Suppression scope and reason.
- Generation rule version so clarifications can be regenerated safely after logic changes.

Use uniqueness or deduplication keys so the same unresolved gap is not recreated repeatedly. Reopen or refresh the existing clarification when supporting evidence materially changes.

## Detection Architecture

Implement a deterministic rules engine first. Optional AI may improve wording, consolidate related gaps, or suggest likely answers, but it must not be the sole detector for core clarification types.

Recommended service boundaries:

- `clarification_rules`: record-type-specific deterministic checks.
- `clarification_service`: generation, deduplication, ranking, lifecycle, and proposed updates.
- `clarification_evidence`: evidence collection and provenance formatting.
- `clarification_ai`: optional question rewording or answer suggestions with strict structured validation.

Avoid running a full database scan on every page request. Support incremental generation triggered by relevant record mutations plus a safe scheduled or on-demand reconciliation pass.

## Ranking and Daily Limits

Rank clarifications using auditable deterministic factors:

- Record priority and business importance.
- Urgency and deadline proximity.
- Whether work is blocked or awaiting the executive.
- Number of downstream records affected.
- Confidence that a genuine gap exists.
- Age and freshness.
- Company weighting.
- Whether clarification would unlock a decision or commitment.
- Repetition or prior snoozes.

Return score reasons with each item.

Default behavior should surface no more than 3 to 5 high-value clarification questions per daily briefing or focused session. The full queue may remain accessible in the Executive Inbox.

Do not let low-value missing fields crowd out material contradictions or blockers.

## API Requirements

Add endpoints or extend the unified inbox API to support:

- Generate or reconcile clarifications on demand.
- List clarifications with filters for company, type, status, score, and target record.
- Retrieve one clarification with full evidence.
- Preview the proposed update for a selected or written answer.
- Confirm the proposed update using stable IDs and normal validation.
- Snooze until a date/time.
- Dismiss with optional reason.
- Mark intentionally unknown.
- Suppress a clarification rule for a record, company, field, or global scope when authorized.
- Reopen a dismissed, answered, or suppressed clarification.

Answer submission and update confirmation should be separate operations. A free-text answer must first produce a reviewable proposed change.

All mutations must be idempotent and auditable.

## Answer Processing Requirements

Support:

- Single-choice suggested answers.
- Existing-record selection, such as choosing a person as owner.
- Date, number, currency, status, and text answers.
- Open-ended answers converted into proposed structured updates.
- `I do not know` and `intentionally unknown` without forcing a value.
- `Not important` or dismissal without modifying the target record.

When suggesting a likely answer, clearly label it as an inference and show the supporting evidence. Never present an inference as known fact.

If an answer could update multiple records, show each proposed mutation independently and allow partial approval.

## Integration Requirements

### Executive Inbox

- Clarifications must appear as a normalized inbox source type.
- Support answer, snooze, dismiss, intentionally unknown, and open evidence actions.
- Inbox ranking must use the clarification score and reasons.

### Morning Briefing

- Show at most the configured daily limit.
- Prefer questions that unblock current priorities.
- Do not repeat dismissed, suppressed, answered, or currently snoozed questions.

### Meeting Prep

- Surface relevant open clarifications for the meeting company, people, projects, or agenda topics.
- Phrase them as proposed questions to resolve during the meeting.
- Allow meeting notes to answer them through the normal review workflow.

### Search and Memory

- Search results may state that a fact is unknown or contradictory and link to the open clarification.
- Memory detail pages should display related open and answered clarifications.
- Answered clarifications must link to the resulting revision history.

## Frontend Requirements

Add a `Clarifications Needed` or `Help ExecutiveOS Learn` section within the Executive Inbox.

Each card must show:

- Question.
- Materiality explanation.
- Target record and company.
- Evidence summary with expandable sources.
- Suggested answers, when supported.
- Confidence or uncertainty wording appropriate for nontechnical users.
- Preview of proposed changes before confirmation.
- Answer, Ask Later, Intentionally Unknown, Dismiss, and suppression controls.

Provide:

- Keyboard-accessible focused question mode.
- Progress indication without gamifying low-value data completion.
- Clear distinction between answering a question and confirming a database update.
- Undo or reopen where safe.
- Responsive desktop and mobile layouts.

Do not display raw model prompts, unformatted JSON, internal scores without explanation, or unsupported certainty.

## Privacy and Safety Requirements

- Do not send more memory context to an AI provider than required for the specific clarification.
- Redact secrets and sensitive fields from AI prompts where possible.
- Log AI source, model, latency, and failure state without storing sensitive prompt contents unnecessarily.
- The deterministic engine must remain functional when no OpenAI key is configured.
- Clarification generation must respect authentication and company-level access controls if introduced.

## Priority 3 Tests

Add tests covering at least:

1. High-value missing owner generates one clarification.
2. Low-value optional empty field does not generate a clarification.
3. Duplicate generation reuses the same clarification rather than creating another.
4. Material evidence change refreshes or reopens the clarification correctly.
5. Contradictory values show both evidence sources and do not mutate either record.
6. Stale-record thresholds respect configuration and a fixed test clock.
7. Ambiguous language generates a question only when it affects an actionable field.
8. Suggested answers are labeled as inferred and include evidence.
9. Free-text answer produces a preview but does not mutate memory.
10. Confirming the preview updates the stable target ID and creates revision history.
11. Partial approval works when an answer proposes multiple updates.
12. Snoozed questions disappear and return at the correct time.
13. Dismissed and intentionally unknown questions stay hidden but remain auditable.
14. Suppression scope prevents the applicable rule without disabling unrelated rules.
15. Daily briefing respects the 3-to-5 default limit and prioritization.
16. Executive Inbox normalization and cross-surface status consistency.
17. No clarification is generated from already resolved or completed items unless a real contradiction exists.
18. AI failure falls back to deterministic question wording.
19. Authorization and validation prevent arbitrary record mutation through answer payloads.
20. SQLite and PostgreSQL-compatible migration behavior.

## Priority 3 Acceptance Criteria

Priority 3 is complete only when ExecutiveOS can identify, rank, explain, and safely resolve material memory gaps without overwhelming the user or silently changing durable memory.

At least one end-to-end test must demonstrate:

1. A material gap is detected.
2. The clarification appears in the Executive Inbox.
3. The user answers it.
4. ExecutiveOS previews the exact proposed update.
5. The user confirms.
6. The stable target record and revision history are updated.
7. The clarification is marked answered and disappears from open surfaces.

---

# Priority 4: Smarter Capture and Date Normalization

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

## Clarification Integration

- When capture confidence is below a documented threshold, create or associate a Priority 3 clarification rather than silently guessing.
- Do not create duplicate clarification questions when the capture preview already exposes the ambiguity for immediate confirmation.
- Confirmed capture answers may resolve an existing clarification using its stable ID.

## AI and Fallback Requirements

- Keep the local fallback functional without an OpenAI key.
- Make fallback rules generic and data-driven.
- Validate AI structured output strictly.
- Do not allow AI output to bypass authorization, validation, or confirmation.
- Add graceful handling for AI timeout, malformed output, and partial suggestions.

## Priority 4 Tests

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
11. Low-confidence capture integrating correctly with Priority 3 clarifications.

## Priority 4 Acceptance Criteria

Capture previews must be more accurate, transparent, and actionable than the current rule-based flow, while remaining safe without AI access.

---

# Priority 5: Interactive Briefing and Meeting Workspaces

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
- Answer or snooze a clarification.
- Open source and revision history.
- Select and process multiple compatible items.

Ensure all actions use stable IDs and update every relevant surface.

## Meeting Prep Requirements

Add:

- Editable agenda ordering.
- Time allocation per agenda item.
- Presenter or owner.
- Decision-required indicator.
- Relevant unresolved clarification questions.
- Ability to exclude or include sections.
- Meeting note capture during the meeting.
- Conversion of notes into reviewed tasks, decisions, risks, follow-ups, and clarification answers.
- A post-meeting review step before durable updates are saved.
- Meeting completion status and follow-up summary.

Persist user edits so regenerated meeting prep does not overwrite them without warning.

## UX Requirements

- Support autosave with visible state.
- Provide undo for important changes.
- Maintain mobile and desktop usability.
- Use semantic buttons, labels, focus management, and keyboard navigation.
- Avoid presenting dense raw JSON or developer terminology to end users.

## Priority 5 Tests

Cover:

1. Inline edits persist and appear across surfaces.
2. Agenda ordering persists across regeneration.
3. Meeting notes produce reviewable suggestions rather than immediate uncontrolled writes.
4. Meeting notes can answer a linked clarification through preview and confirmation.
5. Bulk action validation.
6. Undo/reopen behavior.
7. Accessibility-critical controls and labels.
8. Concurrent edit conflict behavior.

## Priority 5 Acceptance Criteria

A user must be able to run a morning review and a leadership meeting without leaving the corresponding workspace for routine actions.

---

# Priority 6: Executive Outcome Tracking and Scoreboard

## Goal

Show whether commitments, decisions, risks, projects, delegation, and clarification quality are producing measurable progress.

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
- Open clarification count by company and type.
- Average clarification age.
- Clarifications answered, dismissed, snoozed, and marked intentionally unknown.
- Clarifications that led to a material record update.
- Repeated clarification rules that may indicate poor capture quality.

Clarification metrics must not encourage generating unnecessary questions. Measure usefulness and resolution, not raw question volume.

## Data Integrity Requirements

- Define every metric in documentation.
- Use stable event timestamps and revision history.
- Make date ranges and timezone explicit.
- Exclude deleted, cancelled, or test records according to documented rules.
- Provide supporting record drill-down for every aggregate.
- Clearly distinguish measured facts from AI-generated observations.

## Frontend Requirements

Add an `Executive Scoreboard` with:

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
- Number of high-priority clarification questions.

## Priority 6 Tests

Cover:

1. Metric calculations against fixed fixtures.
2. Date-range boundaries and timezone behavior.
3. Cancelled/deleted record exclusions.
4. Reopened task and risk treatment.
5. Drill-down totals matching aggregate values.
6. Data freshness calculations.
7. Clarification usefulness metrics excluding suppressed or duplicate generation noise.
8. No unsupported AI claim being presented as a measured fact.

## Priority 6 Acceptance Criteria

Every displayed executive metric must be reproducible from stored records and linked to supporting detail.

---

# Implementation Sequence

Follow this sequence strictly:

1. Priority 1 schema design and migration.
2. Priority 1 backend services and endpoints.
3. Priority 1 frontend migration away from synthetic capture commands.
4. Priority 1 tests, documentation, and cleanup of obsolete resolution logic.
5. Priority 2 implementation and tests.
6. Priority 3 clarification schema, deterministic rules, and deduplication.
7. Priority 3 APIs, inbox integration, answer preview/confirmation, and tests.
8. Priority 4 implementation and tests.
9. Priority 5 implementation and tests.
10. Priority 6 implementation and tests.

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
