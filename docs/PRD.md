# Product Requirements Document

## Product Goal

ExecutiveOS helps leaders preserve important company context as structured memory, then use that memory for decisions, briefings, meeting preparation, and direct questions.

## MVP Scope

- Capture natural-language updates and screenshots.
- Suggest structured memory updates for user approval.
- Store approved updates as durable executive objects.
- Generate a morning briefing from current memory.
- Generate meeting prep from relevant company, project, people, decision, metric, meeting, and recent capture context.
- Answer natural-language search questions with a direct answer and supporting records.
- Browse, edit, and delete stored memory objects.
- Support local development without an OpenAI key through a clearly labeled limited preview classifier.
- Require authentication in hosted production.

## Core Workflows

### Capture

The user enters text or attaches a screenshot. The system extracts supported facts into suggested updates, shows them for review, and saves only selected updates.

### Morning Briefing

The system summarizes top priorities, active strategic issues, meetings today, open decisions, people needing attention, waiting-on items, risks, recent updates, and a recommended focus.

### Meeting Prep

The user enters a meeting name or context. The system returns a proposed agenda, related people, strategic issues, projects, decisions, recent context, action items, metrics, and risks.

### Search / Ask

The user asks a question about executive memory. The system returns a direct answer and ranked supporting records.

### Memory

The user browses stored memory by object type, opens a record, edits its fields, or deletes incorrect memory.

## Non-Goals

- Full task manager
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
