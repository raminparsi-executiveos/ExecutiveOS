# Information Model

ExecutiveOS stores executive memory as typed objects plus immutable capture history. Generated outputs are disposable views over the stored memory.

## Core Objects

| Object | Purpose |
| --- | --- |
| `Company` | Business context, leadership, issues, projects, people, KPIs, decisions, and meetings. |
| `Person` | Role, company, responsibilities, strengths, concerns, priorities, performance notes, and links. |
| `StrategicIssue` | Active or historical strategic concern with owner, current thinking, risks, and links. |
| `Project` | Initiative with objective, status, owner, milestones, risks, next steps, and links. |
| `Decision` | Decision record with context, options, final decision, reasoning, outcome, review date, and links. |
| `Meeting` | Meeting memory with attendees, summary, decisions, action items, questions, and links. |
| `SOP` | Operating process with purpose, owner, process details, escalation rules, and related projects. |
| `Document` | Reference document metadata and summary. |
| `Metric` | KPI or measurement with value, date, trend, and related issue. |
| `Task` | Action item, commitment, or standing responsibility with accountable owner, assigned performer, delegated-by person, waiting-on party, deliverable, definition of done, dependencies, due/follow-up dates, recurrence, source excerpt, status, priority, source metadata, blocker, next action, tags, completion history, and review timestamp. |
| `CaptureRecord` | Immutable source capture with raw text, screenshot evidence summary, classification source, model, prompt version, structured interpretation response, approved/rejected suggestions, saved record IDs, user edits, processing events, saved count, and timestamp. |
| `CaptureInterpretation` | AI or fallback interpretation linked to a capture, including summary, purpose, executive intent, primary company/subject/topic, urgency, tone, temporal context, confidence, people roles, typed statements, questions, ambiguities, source evidence, model, and prompt version. |
| `CaptureMutation` | Reviewable proposed record mutation linked to a capture and interpretation, including object type, create/update/merge/resolve/supersede/no-change operation, matched record ID, field-level operations, evidence excerpt, missing material fields, uncertainty, approval status, persisted values, and saved record ID. |
| `BriefingView` | Per-user last briefing view timestamp used to compute changed-since-last-briefing sections. |
| `ProvenanceRecord` | Source traceability for memory records, including source type, identifier, excerpt, verification, classification, and supersession fields. |
| `RevisionRecord` | Auditable before/after snapshots for creates, edits, deletes, capture approvals, and inbox approvals. |
| `ReviewAlert` | User-resolved alert for stale, conflicting, overdue, duplicate-looking, or superseded memory. |
| `IntegrationInboxItem` | Reviewed-only staging area for Google Calendar event data and uploaded-document text. |
| `Clarification` | Durable question about material missing context, stale information, contradictions, ambiguous action language, or disconnected records, with evidence, score reasons, lifecycle status, answer preview, and confirmation state. |
| `EntityAlias` | Confirmed alias for dynamic entity resolution without automatic merging. |
| `DashboardConfig` | Configurable company dashboard module definitions. |

## API Object Types

The object listing and creation endpoints use these path names:

- `companies`
- `people`
- `strategic-issues`
- `projects`
- `decisions`
- `meetings`
- `sops`
- `documents`
- `metrics`
- `tasks`

## Task Rules

- Supported statuses are `open`, `in_progress`, `waiting`, `blocked`, `completed`, and `cancelled`.
- Supported priorities are `critical`, `high`, `medium`, and `low`.
- `owner` means accountable for eventual completion. `assigned_to` means the person performing the work. `delegated_by` means the person who requested it. `waiting_on` means the external person or party blocking progress.
- Capture-created tasks should preserve expected deliverable, definition of done, why it matters, source excerpt, confidence, and material missing fields when available.
- Completed and cancelled tasks remain stored, searchable, and auditable.
- Overdue is derived from an ISO `due_date` when the task status is not completed or cancelled.
- Meeting `action_items` are preserved on the meeting record, with linked task records created for workflow tracking.
- Fuzzy text matching may suggest that a task should be reviewed, but linked tasks are cleared from open/waiting views only through explicit completion.

## Capture Rules

- Suggestions must map to one of the supported object types.
- Raw notes are not stored as first-class memory objects.
- Capture records preserve the original input separately from AI interpretation and approved durable values.
- Capture interpretations and mutations are stored before approval so rejected suggestions, user edits, and omitted context remain auditable.
- Proposed mutations must describe field-level behavior such as append, replace, remove, clear, resolve, supersede, or no-change rather than relying on blank values.
- Screenshots are not persisted as images.
- Approved structured values are authoritative when they conflict with heuristic text detection.
- Approved commitments and action items may create task records after user review.
- `GET /captures/{capture_id}/audit` compares original input, AI interpretation, approved mutation, actual saved values, linked record IDs, and unresolved context.

## Generated Outputs

Briefings, meeting prep, and search answers are generated on demand from stored objects and capture history. They should not be treated as durable source-of-truth records.

Morning Briefing ranked items include title, company, owner, why it matters, status, due date, recommended next action, supporting source, score, and score reasons. Scores are transparent derived values based on priority, due date, overdue duration, status, risks, missing owner, executive ownership, recent changes, and blocked/waiting state.

Search answers separate directly supported facts, inferences, and missing information. Integration Inbox records never modify memory until suggestions are approved. Review alerts are durable records with explicit resolution timestamps so dismissed issues do not repeatedly interrupt unless materially new evidence creates a new alert.

Clarification cards are durable generated records, not facts. They use stable target record IDs and evidence snippets to explain why a question matters. Answers are stored as reviewable proposed updates first; confirming the preview applies validated field changes to the target record and writes revision history. Snoozed, dismissed, intentionally unknown, and suppressed clarifications remain auditable and stay out of open briefing/inbox sections.
