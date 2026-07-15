# Capture Fidelity and Task Qualification — Codex Implementation Instructions

## Objective

Improve ExecutiveOS so natural-language and screenshot captures preserve the user's original intent, produce better-qualified tasks and notes, and make it possible to compare the original capture with the exact values written to durable memory.

The implementation must preserve the existing review-before-save workflow. AI suggestions must remain proposed changes until the user approves them.

## Core Problem

ExecutiveOS currently moves too quickly from an unstructured executive capture into clean database objects. This can lose important context such as:

- why the user raised the issue;
- whether the user was directing, considering, questioning, observing, or deciding;
- who is accountable versus who performs the work;
- who the task is waiting on;
- the required deliverable and definition of done;
- the consequence or importance of the item;
- whether the capture creates, updates, merges with, resolves, or supersedes existing memory;
- uncertainty, tone, urgency, hesitation, and confidence;
- supporting context that does not fit neatly into an existing object type.

Implement an intermediate capture-interpretation layer before durable object mutations.

---

## Required Architecture

Every capture must have three distinct durable layers.

### Layer 1 — Immutable Source Capture

Continue preserving the original typed text. Add durable capture metadata sufficient to reconstruct what was analyzed and approved.

Store, at minimum:

- original typed text;
- screenshot-derived text or visual evidence summary when screenshots are used;
- capture timestamp;
- classification source;
- AI model;
- prompt version;
- complete structured interpretation response;
- approved suggestions;
- rejected suggestions;
- saved record IDs;
- user edits made during review;
- processing errors or fallback events.

Do not overwrite the source capture when records are updated later.

### Layer 2 — Capture Interpretation

Create a new durable `capture_interpretations` model or equivalent linked structure.

Suggested fields:

- `capture_id`;
- `capture_summary`;
- `capture_purpose`;
- `executive_intent`;
- `primary_company`;
- `primary_subject`;
- `primary_topic`;
- `urgency`;
- `tone`;
- `temporal_context`;
- `confidence`;
- `model`;
- `prompt_version`;
- `people_roles` JSON;
- `statements` JSON;
- `open_questions` JSON;
- `ambiguities` JSON;
- `source_evidence` JSON;
- `created_at` and `updated_at`.

Each interpreted statement should include:

- source excerpt;
- statement type: fact, observation, concern, decision, directive, commitment, proposal, recommendation, assumption, question, or unverified information;
- company;
- people mentioned and their role in the statement;
- temporal meaning;
- confidence;
- whether the statement changes existing memory.

### Layer 3 — Proposed Record Mutations

Each suggested update must explicitly identify:

- object type;
- operation: `create`, `update`, `merge`, `resolve`, `supersede`, or `no_change`;
- matched existing record ID, when applicable;
- match confidence;
- evidence excerpt;
- field-level mutation semantics;
- missing material fields;
- uncertainty;
- user-visible explanation of why the mutation is proposed.

Field-level operations must support:

- `append`;
- `replace`;
- `remove`;
- `clear`;
- `no_change`.

Do not rely on ignoring empty strings to represent all update behavior. A user must be able to explicitly clear an owner, blocker, due date, next step, risk, or other outdated value after review.

---

## Task Data Quality Enhancements

Expand the task model while preserving compatibility with existing task records.

Add the following fields, using JSON where appropriate to minimize schema complexity:

- `expected_deliverable`;
- `definition_of_done`;
- `why_it_matters`;
- `delegated_by`;
- `assigned_to`;
- `waiting_on`;
- `stakeholders`;
- `dependencies`;
- `follow_up_date`;
- `recurrence`;
- `task_type`;
- `confidence`;
- `interpretation_notes`;
- `source_excerpt`;
- `parent_task_id`;
- `linked_project_ids`;
- `linked_decision_ids`;
- `linked_people`.

Preserve the current `owner` field for backward compatibility, but distinguish these meanings:

- `owner`: accountable for eventual completion;
- `assigned_to`: performs the work;
- `delegated_by`: requested or assigned the work;
- `waiting_on`: external person or party whose action is required.

### Task Qualification Rules

For every proposed task, attempt to populate:

1. concise action-oriented title;
2. accountable owner;
3. assigned person;
4. delegated-by person;
5. waiting-on person or party;
6. company;
7. task-specific description;
8. expected deliverable;
9. definition of done;
10. next action;
11. blocker;
12. dependencies;
13. due date;
14. follow-up date;
15. recurrence or standing-responsibility indicator;
16. priority;
17. why it matters;
18. source excerpt;
19. confidence;
20. missing material fields.

Do not use the entire capture as the task description unless the entire capture concerns only that task. Create a focused task note and keep the full capture separately linked through provenance.

When the capture describes an ongoing quality gate, standing expectation, recurring review, or continuing responsibility, do not force it into a one-time task. Use recurrence or a standing-responsibility task type.

---

## AI Prompt Changes

Update the capture prompt and structured schema so the model must:

1. Identify the user's primary intent.
2. Separate facts, observations, concerns, decisions, directives, commitments, proposals, recommendations, assumptions, questions, and unverified information.
3. Identify all explicit and implied action items.
4. For each action, determine:
   - accountable owner;
   - performer;
   - delegated-by person;
   - waiting-on person;
   - recipient;
   - timing;
   - trigger;
   - expected output;
   - definition of done;
   - blocker;
   - dependency;
   - rationale;
   - whether it is one-time or recurring.
5. Compare the capture against relevant existing memory.
6. State whether each proposal creates, updates, merges with, resolves, or supersedes an existing record.
7. Preserve a source excerpt supporting every material field.
8. Flag uncertainty rather than silently omitting weakly supported information.
9. Preserve meaningful context that does not fit a typed object in the capture interpretation.
10. Generate clarification questions only when missing information materially affects identity, ownership, execution, timing, or completion.
11. Never invent facts.
12. Never silently convert a suggestion or question into a confirmed decision.
13. Preserve corrections, superseded instructions, former ownership, and employment transitions.

The structured response schema must support the capture interpretation and field-level mutation operations described above.

---

## Relevant Memory Context

Replace the current shallow memory context with targeted retrieval.

For each capture, supply the AI with the most relevant existing records, including when applicable:

- open and recently completed tasks;
- active projects;
- current strategic issues;
- recent decisions;
- recent meetings;
- known people, roles, responsibilities, priorities, and aliases;
- blockers and waiting-on relationships;
- recent related captures;
- similar titles and likely duplicates;
- unresolved risks and meeting actions.

Do not dump the entire database into the prompt. Use deterministic or scored retrieval to select the most relevant records.

The AI must be given stable record IDs for candidate matches so it can propose an update to an existing record rather than creating a duplicate.

---

## Matching and Dedupe

Do not rely primarily on case-insensitive exact title matching.

Implement a layered matching strategy using:

- exact normalized identity;
- aliases;
- company;
- person and owner overlap;
- source links;
- token similarity;
- semantic similarity when available;
- record status;
- recent related captures;
- linked projects, meetings, and decisions.

Every create suggestion must include a duplicate check. When a likely match exists, display it during review and prefer `update` or `merge` unless the user confirms a new record.

Do not automatically merge ambiguous people or similar names.

---

## List Mutation Safety

For list fields such as risks, milestones, next steps, responsibilities, concerns, action items, and tags, require an explicit operation:

- append new values;
- replace the complete list;
- remove selected values;
- resolve selected values;
- preserve unchanged.

Do not replace a complete list merely because the AI returned one new item.

Do not indefinitely append stale values without offering a removal or supersession operation.

---

## Capture Review and Audit UI

Add a Capture Fidelity or Capture Audit view.

For each capture, show:

1. original typed input;
2. screenshot evidence summary when applicable;
3. AI capture interpretation;
4. proposed updates before approval;
5. user-approved updates;
6. actual saved database values;
7. linked record IDs;
8. rejected suggestions;
9. omitted or unresolved context;
10. processing source, model, prompt version, confidence, and fallback status.

Provide a comparison layout with columns similar to:

| Original input | AI interpretation | Approved mutation | Actual saved value | Omitted or unresolved context |
| --- | --- | --- | --- | --- |

The audit view must make it easy to identify:

- lost context;
- incorrect ownership;
- weak task titles;
- duplicate records;
- overwritten list values;
- missing dates or definitions of done;
- AI fields changed by the user before approval;
- differences between the approved preview and the final persisted row.

---

## Capture-Time Clarifications

Keep the existing clarification engine, but add high-value capture-time questions.

Examples:

- Is this person performing the task or only accountable for reviewing it?
- Is this a one-time task or an ongoing responsibility?
- What result would allow this task to be marked complete?
- Does this replace an existing direction or add to it?
- Should a relative date be tied to a known meeting or calendar date?
- What specifically is the waiting-on party expected to provide?
- Is this a decision, recommendation, or idea still under consideration?
- Should this update an existing project rather than create a new one?

Only generate a blocking clarification when the answer materially changes:

- record identity;
- owner or performer;
- timing;
- completion criteria;
- decision status;
- create-versus-update behavior.

Non-blocking missing context should be saved as an open qualification issue and surfaced in review or the Executive Inbox.

---

## Provenance and Classification

Keep the following concepts separate:

1. literal source content;
2. AI interpretation;
3. user-approved durable value.

Do not use a general `details` summary as a substitute for a durable final decision, objective, or process field unless the user explicitly approves that mapping.

Every material field written to durable memory should be traceable to:

- capture ID;
- interpretation ID;
- source excerpt;
- approved mutation ID;
- model and prompt version;
- user approval event.

Preserve `memory_classification` and `verification_state` per proposed statement or mutation, not only at the whole-record level when practical.

---

## Database and Migration Requirements

- Use Alembic migrations for all schema changes.
- Migrations must work for both SQLite development databases and PostgreSQL production databases.
- Preserve all existing capture and task data.
- Backfill safe defaults for new fields.
- Do not delete or rewrite historical raw capture text.
- Include new interpretation and mutation data in backup export/import.
- Add indexes for capture ID, matched record ID, operation, status, company, and created date where useful.

---

## API Requirements

Add or extend endpoints to support:

- retrieving a full capture audit package;
- retrieving the interpretation linked to a capture;
- retrieving proposed, approved, rejected, and applied mutations;
- editing a proposed mutation before approval;
- comparing approved mutations to actual persisted values;
- rerunning interpretation with a newer prompt version without silently changing durable memory;
- explicitly applying append, replace, remove, clear, resolve, and supersede operations.

Existing capture endpoints must remain backward-compatible where reasonable.

---

## Observability

Extend capture observability with:

- percentage of captures with no saved updates;
- number of records created versus updated;
- likely duplicate-create rate;
- average tasks per capture;
- percentage of tasks missing owner, due date, next action, definition of done, or expected deliverable;
- number of user edits made before approval;
- number of rejected AI suggestions;
- number of approved-versus-persisted mismatches;
- AI fallback frequency;
- screenshot-unavailable rate;
- prompt-version performance comparisons.

Do not log secrets or full sensitive capture text in server logs.

---

## Tests and Acceptance Criteria

Add backend and frontend tests covering at least the following scenarios.

### Intent Preservation

A multi-topic capture preserves a structured interpretation even when only some proposed objects are approved.

### Qualified Task

A capture such as:

> Kyle should review Julio's work on critical projects before anything is sent to the client.

must produce a proposed task or standing responsibility that preserves:

- Kyle as accountable reviewer;
- Julio as the delivery subject or participant, not automatically the owner;
- critical projects as scope;
- review-before-client-release as the trigger;
- an expected deliverable;
- a definition of done;
- the relevant source excerpt;
- ambiguity about one-time versus recurring responsibility, when not explicit.

### Waiting-On Distinction

A capture such as:

> Joseph is waiting for Veronica to confirm the staffing plan before scheduling interviews.

must distinguish:

- Joseph as accountable or assigned person;
- Veronica as `waiting_on`;
- confirmation of the staffing plan as the dependency;
- scheduling interviews as the next action after the dependency is satisfied.

### Suggestion Versus Decision

A statement such as:

> We may want to use Julio for more critical projects.

must not be stored as a confirmed decision unless the user approves a decision-classified mutation.

### Explicit Clear

A capture such as:

> Kyle is no longer the owner of this project. Leave the owner open for now.

must propose clearing the owner rather than retaining the old owner.

### List Mutation

Adding one project risk must not replace existing risks unless the proposed operation is explicitly `replace` and approved.

### Existing Record Match

A capture referring to an existing initiative with different wording must show the likely existing record and propose update or merge rather than silently creating a duplicate.

### Audit Accuracy

The audit endpoint and UI must show the exact approved values and the exact final persisted values. A test must fail if those values diverge unexpectedly.

### Backward Compatibility

Existing captures, tasks, backup import/export, briefing, search, meeting prep, and clarification workflows must continue to pass regression tests.

---

## Recommended Implementation Order

### Phase 1 — Preserve Interpretation

- Add capture interpretation and mutation models.
- Store the complete structured AI interpretation.
- Add migrations, serialization, backup support, and backend tests.

### Phase 2 — Improve Task Quality

- Add task qualification fields.
- Update the AI schema and prompt.
- Update task review and detail UI.
- Add task qualification tests.

### Phase 3 — Relevant Memory Retrieval and Matching

- Build targeted memory context retrieval.
- Include stable candidate record IDs.
- Add create/update/merge/supersede operations.
- Add duplicate review behavior.

### Phase 4 — Mutation Semantics

- Implement append, replace, remove, clear, no-change, resolve, and supersede operations.
- Add list mutation safeguards.

### Phase 5 — Capture Audit UI

- Add full capture comparison endpoint and interface.
- Display omitted context and persisted-value comparisons.

### Phase 6 — Observability and Refinement

- Add fidelity and task-completeness metrics.
- Use production audit results to improve prompts and deterministic qualification rules.

---

## Implementation Constraints

- Do not silently mutate durable memory during classification or reinterpretation.
- Do not delete original capture evidence.
- Do not infer identities from similar names.
- Do not silently turn proposals into decisions.
- Do not create duplicate records when a likely existing match is available for review.
- Do not overwrite list fields without explicit mutation semantics.
- Do not require every missing optional field before a capture can be saved.
- Keep the workflow fast enough for routine executive use.
- Prefer incremental, reviewable commits with migrations and tests included in each phase.

## Definition of Complete

This initiative is complete when ExecutiveOS can show, for any capture:

1. what the user originally entered;
2. what the AI understood the user to mean;
3. what records and field changes were proposed;
4. what the user approved, edited, or rejected;
5. what was actually written to the database;
6. what material context remains unresolved;
7. how each resulting task is qualified for ownership, execution, follow-up, and completion.
