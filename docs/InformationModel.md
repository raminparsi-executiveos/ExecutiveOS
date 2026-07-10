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
| `Task` | Action item or commitment with owner, due date, status, priority, source metadata, blocker, next action, tags, completion history, and review timestamp. |
| `CaptureRecord` | Raw confirmed capture text, classification source, saved count, and timestamp. |
| `BriefingView` | Per-user last briefing view timestamp used to compute changed-since-last-briefing sections. |
| `ProvenanceRecord` | Source traceability for memory records, including source type, identifier, excerpt, verification, classification, and supersession fields. |
| `RevisionRecord` | Auditable before/after snapshots for creates, edits, deletes, capture approvals, and inbox approvals. |
| `ReviewAlert` | User-resolved alert for stale, conflicting, overdue, duplicate-looking, or superseded memory. |
| `IntegrationInboxItem` | Reviewed-only staging area for Google Calendar event data and uploaded-document text. |
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
- Completed and cancelled tasks remain stored, searchable, and auditable.
- Overdue is derived from an ISO `due_date` when the task status is not completed or cancelled.
- Meeting `action_items` are preserved on the meeting record, with linked task records created for workflow tracking.
- Fuzzy text matching may suggest that a task should be reviewed, but linked tasks are cleared from open/waiting views only through explicit completion.

## Capture Rules

- Suggestions must map to one of the supported object types.
- Raw notes are not stored as first-class memory objects.
- Capture records preserve the confirmed input as audit and search context.
- Screenshots are not persisted as images.
- Approved structured values are authoritative when they conflict with heuristic text detection.
- Approved commitments and action items may create task records after user review.

## Generated Outputs

Briefings, meeting prep, and search answers are generated on demand from stored objects and capture history. They should not be treated as durable source-of-truth records.

Morning Briefing ranked items include title, company, owner, why it matters, status, due date, recommended next action, supporting source, score, and score reasons. Scores are transparent derived values based on priority, due date, overdue duration, status, risks, missing owner, executive ownership, recent changes, and blocked/waiting state.

Search answers separate directly supported facts, inferences, and missing information. Integration Inbox records never modify memory until suggestions are approved. Review alerts are durable records with explicit resolution timestamps so dismissed issues do not repeatedly interrupt unless materially new evidence creates a new alert.
