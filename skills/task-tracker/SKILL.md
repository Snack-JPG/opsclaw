---
name: task_tracker
description: Task and project tracking for OpsClaw: create tasks from natural language, monitor deadlines, generate daily standups and weekly reports, and escalate overdue or blocked work through Linear, Notion, or Asana.
---

# Task Tracker Skill

Use this skill whenever the user asks to add, update, review, or summarize work items, inspect deadlines, generate standups, or produce weekly progress reports. It also applies to scheduled deadline sweeps, standup generation, and end-of-week reporting when task tracking is enabled.

## Load Order
1. Read `workspace/SOUL.md`, `workspace/USER.md`, `workspace/AGENTS.md`, `workspace/ops-state.json`, and `workspace/heartbeat-state.json`.
2. Read today's memory note in `workspace/memory/YYYY-MM-DD.md` and yesterday's note if active task context spans multiple days.
3. Read this skill's config before selecting a provider or project:
   - `config/tracker-config.json`
   - `config/report-template.md`
4. Use the bundled scripts for deterministic work:
   - `scripts/nl_parser.py`
   - `scripts/linear-client.py`
   - `scripts/notion-client.py`
   - `scripts/asana-client.py`
   - `scripts/standup.py`
   - `scripts/report-generator.py`

## Triggers
- `Cron`: daily standup summary at `8:30 AM` local timezone.
- `Cron`: weekly report every Friday at `4:00 PM` local timezone.
- `Heartbeat`: due-today scan, overdue scan, blocked-work scan, and provider health check.
- `Manual`: commands such as `Add task: review Q1 budget by Friday`, `What's overdue?`, `Standup`, `Weekly report`, `Mark launch checklist as done`, or `Block homepage copy - waiting on client`.

## Core Responsibilities
- Convert natural-language task requests into structured task payloads with title, due date, priority, assignee, labels, status, and optional block reason.
- Create, update, list, and search tasks through Linear, Notion, or Asana using the selected provider in `config/tracker-config.json`.
- Track due-today, due-this-week, overdue, and blocked work with deterministic status labels.
- Generate owner-facing daily standups from normalized task snapshots.
- Generate weekly reports with completed work, carried-over work, new-work volume, velocity trends, and actionable recommendations.
- Escalate overdue or blocked work clearly and record the result in state and memory.

## Natural Language Intake
Always run `scripts/nl_parser.py` before creating or updating a task from free text.

It should extract at minimum:
- `title`
- `dueDate`
- `priority`
- `assignee`
- `project`
- `labels`
- `status`
- `blockReason`

Examples:
- `Add task: Review Q1 budget, high priority, due next Tuesday`
- `Remind me to follow up with Sarah on Friday`
- `Block website launch - waiting on legal approval`
- `Mark onboarding checklist as done`

Rules:
- If a due date is ambiguous, return the parsed assumption and confidence instead of hiding the ambiguity.
- If the title is missing, ask for clarification before creating anything.
- `task_create` actions may execute immediately if the user's policy allows it.
- Task completion, blocking, and status changes should only target an unambiguous existing task.

## Standup Flow
At the daily standup time or when the user requests `Standup`:

1. Pull tasks completed yesterday.
2. Pull tasks currently in progress.
3. Pull blocked tasks and include the reason when present.
4. Pull tasks due today.
5. Run `scripts/standup.py` on the normalized task snapshot.
6. Return this structure:

```text
Standup
Date: <YYYY-MM-DD>

Done Yesterday
- <task>

In Progress
- <task>

Blocked
- <task> - <reason>

Due Today
- <task>
```

Rules:
- Keep the output concise and action-oriented.
- If no tasks exist in a section, say `None`.
- Surface overdue work separately if it is material to today's priorities.

## Weekly Report Flow
At Friday `4:00 PM` local time or on `Weekly report`:

1. Pull tasks completed this week.
2. Pull tasks still open from prior weeks.
3. Pull tasks created this week.
4. Compute weekly velocity and compare it against the trailing four-week average.
5. Run `scripts/report-generator.py` with `config/report-template.md`.
6. Return the report plus recommendations when the workload appears overloaded, blocked, or under-committed.

Expected sections:
- completed this week
- carried over
- newly created
- due next week
- velocity trend
- recommendations

## Deadline Tracking and Escalation
During heartbeat runs:

1. Query the selected provider for:
   - tasks due today
   - overdue tasks
   - blocked tasks
   - tasks with no assignee when assignment is required
2. Update `workspace/ops-state.json.tasks` with counts and the latest task snapshot metadata.
3. Update `workspace/heartbeat-state.json.lastChecks.tasks`.
4. Escalate when:
   - a task is overdue by more than the configured threshold
   - a high-priority task is due today and still not started
   - a blocked task has been blocked longer than the configured threshold
5. Record the escalation reason and recommended next action in memory.

Escalation output should include:
- task title
- current status
- due date or blocked-since date
- days overdue or blocked
- owner recommendation

## Manual Commands
- `Add task: <description>`
  - Parse the free text and create a task in the configured provider.
- `What's due today?`
  - List tasks due today, sorted by priority then due time.
- `What's due this week?`
  - List open tasks due within the configured lookahead window.
- `What's overdue?`
  - Return all overdue tasks with age and priority.
- `Mark <task> as done`
  - Resolve the task to an exact provider record and mark it complete.
- `Block <task> - <reason>`
  - Mark the task blocked and store the reason.
- `Standup`
  - Generate the current daily standup.
- `Weekly report`
  - Generate the current weekly report.

## Approval Policy
- Read-only task queries are `internal_query` and execute immediately.
- Standups, reports, and deadline briefings are `internal_brief` and execute immediately.
- Task creation is `task_create` and follows the configured owner approval policy.
- Task status updates that reflect an explicit user instruction may execute immediately when the target task is unambiguous.
- Do not silently edit or close a task when multiple matches exist.

## Reliability and Observability
- Use provider-specific scripts for all task API access.
- Keep provider responses normalized so reporting scripts stay provider-agnostic.
- Retry transient network failures and HTTP `429` / `5xx` responses with bounded exponential backoff.
- Return a degraded but explicit status if the provider is unavailable.
- Capture exhausted failures in `workspace/memory/dead-letters/YYYY-MM-DD.json`.
- Log provider, action, task identifiers, and sanitized context through the shared structured logger.

## Setup and References
- Human setup instructions live in `README.md`.
- Provider selection and defaults live in `config/tracker-config.json`.
- Weekly report formatting lives in `config/report-template.md`.

## Acceptance Standard
This skill is considered healthy when:
- `Add task: X by Friday` creates a task with the correct parsed due date.
- `Standup` includes completed, in-progress, blocked, and due-today work.
- `Weekly report` generates velocity metrics and recommendations without manual cleanup.
- Overdue and blocked work appear in heartbeat escalation output.
- `Mark <task> as done` updates the correct task when the match is unambiguous.
