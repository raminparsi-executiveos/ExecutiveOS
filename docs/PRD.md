# Product Requirements Document

## Product Goal

ExecutiveOS helps leaders preserve important company context as structured memory, then use that memory for decisions, briefings, meeting preparation, and direct questions.

## MVP Scope

- Capture natural-language updates and one or more screenshots.
- Suggest structured memory updates for user approval.
- Store approved updates as durable executive objects.
- Track approved commitments and action items as first-class task records.
- Generate a morning briefing from current memory.
- Generate meeting prep from relevant company, project, people, decision, metric, meeting, and recent capture context.
- Answer natural-language search questions with a direct answer and supporting records.
- Browse, edit, and delete stored memory objects.
- Support local development without an OpenAI key through a clearly labeled limited preview classifier.
- Require authentication in hosted production.

## Core Workflows

### Capture

The user enters text or attaches one or more screenshots. The system extracts supported facts into suggested updates, shows them for review, and saves only selected updates.

### Morning Briefing

The system ranks current executive memory into Needs Your Attention, Delegate or Follow Up, Overdue, Blocked or Waiting, Changed Since Last Briefing, and Upcoming. Each ranked item explains why it matters, owner, status, due date, next action, source, and score reasons.

### Meeting Prep

The user enters a meeting name or context. The system returns a proposed agenda, related people, strategic issues, projects, decisions, recent context, action items, metrics, and risks.

### Search / Ask

The user asks a question about executive memory. The system returns a direct answer and ranked supporting records.

### Memory

The user browses stored memory by object type, opens a record, edits its fields, completes or reopens tasks, or deletes incorrect memory.

## Non-Goals

- Full project-management suite beyond executive action tracking
- CRM replacement
- Calendar replacement
- Enterprise permissions
- Long-form document repository
- Automatic external data sync

## Acceptance Criteria

- Capture suggestions remain disposable until explicit approval.
- Screenshots are analyzed but not stored as image files.
- Local preview mode is visibly distinguished from AI extraction.
- Meeting prep avoids pulling unrelated company context into unmatched sections.
- Search scopes named-company queries to that company.
- Auth misconfiguration is visible instead of failing silently.
- Approved meeting action items create linked task records while preserving original meeting history.
- Completed tasks no longer appear as open or waiting items but remain searchable and auditable.
- Morning briefing does not simply sort by newest records; top recommendations expose ranking reasons and the next action.
