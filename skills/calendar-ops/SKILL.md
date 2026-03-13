---
name: calendar_ops
description: Calendar management for OpsClaw using Google Calendar: morning schedule briefings, meeting prep generation, availability checks, conflict detection, and approval-gated event changes.
---

# Calendar Operations Skill

Use this skill whenever the user asks to review the calendar, summarize a day or week, check availability, prepare for a meeting, detect double-bookings, or create/update/cancel calendar events. It also applies to heartbeat checks, morning briefings, and pre-meeting prep automation when calendar monitoring is enabled.

## Load Order
1. Read `workspace/SOUL.md`, `workspace/USER.md`, `workspace/AGENTS.md`, `workspace/ops-state.json`, and `workspace/heartbeat-state.json`.
2. Read today's note in `workspace/memory/YYYY-MM-DD.md` and yesterday's note when recent context matters.
3. Read this skill's config before making decisions:
   - `config/calendars.json`
   - `config/prep-rules.json`
4. Use the bundled scripts for deterministic work:
   - `scripts/gcal-auth.py`
   - `scripts/gcal-client.py`
   - `scripts/briefing.py`
   - `scripts/prep-generator.py`

## Triggers
- `Cron`: morning schedule briefing at the owner's configured briefing time.
- `Cron`: pre-meeting prep sweep every 15 minutes during active hours.
- `Heartbeat`: upcoming-meeting scan, stale prep detection, and conflict checks.
- `Manual`: commands such as `What's next?`, `What's my schedule today?`, `Am I free Friday at 3pm?`, `Prep for my client call`, `Move <meeting> to <time>`, or `Cancel <meeting>`.

## Core Responsibilities
- Fetch events from the configured Google calendars for the requested window.
- Maintain `workspace/ops-state.json` calendar state:
  - `calendar.todayEvents`
  - `calendar.nextMeeting`
  - `calendar.prepStatus`
  - `calendar.lastChecked`
- Produce concise schedule briefings with gaps, prep status, and conflicts.
- Detect double-bookings and low-buffer transitions between meetings.
- Generate meeting prep documents before important meetings.
- Treat calendar writes as `calendar_write` actions that require explicit approval.

## Morning Briefing Flow
1. Read `config/calendars.json` to determine which calendars count toward the briefing.
2. Use `scripts/gcal-client.py list-events` to fetch today's events across all monitored calendars.
3. Run `scripts/gcal-client.py conflicts` on the same set.
4. Run `scripts/briefing.py` to generate the owner-facing schedule briefing.
5. Update `workspace/ops-state.json` with today's events, next meeting, prep status, and timestamps.
6. Deliver the briefing via the configured channel.

The morning briefing must include:
- ordered timeline for the day
- free blocks or major gaps
- prep status for meetings that require prep
- travel or handoff warnings when meetings are tightly stacked
- conflict warnings when overlaps exist

## Pre-Meeting Prep Flow
When a meeting starts within 30 minutes:

1. Check `config/prep-rules.json` to determine whether prep is required.
2. Gather available context:
   - attendee details from the event itself
   - recent notes from workspace memory
   - recent email thread summaries if `email-intel` is active
   - client context if `crm-sync` is active
3. Run `scripts/prep-generator.py`.
4. Save or deliver the prep document and mark the result in `workspace/ops-state.json.calendar.prepStatus`.
5. If required context is missing, still generate a prep doc that clearly labels the missing sections rather than failing silently.

The prep document should cover:
- meeting objective
- attendee context
- recent interactions
- open decisions or blockers
- suggested talking points
- recommended owner outcome for the meeting

## Heartbeat Checks
During heartbeat runs:

1. Check for meetings starting in the next 2 hours.
2. Flag meetings that require prep but do not have a generated prep doc.
3. Detect conflicts or impossible transitions in the monitored calendars.
4. Update `workspace/heartbeat-state.json.lastChecks.calendar` and error counters.
5. Respect quiet hours for owner-facing notifications unless the conflict is critical.

## Manual Commands
- `What's next?`
  - Return the next event, countdown, calendar, attendees, and prep status.
- `What's my schedule today|tomorrow|this week?`
  - Generate a schedule summary for the requested window.
- `Am I free <day> at <time>?`
  - Check overlapping events and configured buffers before answering.
- `Prep for my <meeting name> meeting`
  - Generate or refresh a prep doc on demand.
- `Move my <meeting> to <time>`
  - Propose the change, check availability, and queue for explicit approval before any write.
- `Cancel <meeting>`
  - Summarize the target event and queue the cancellation for explicit approval.

## Approval Policy
- Read-only calendar queries are `internal_query` and execute immediately.
- Briefings and prep docs are `internal_brief` and execute immediately.
- Event creation, updates, and deletion are `calendar_write` and require explicit approval.
- Never change or delete an event unless the approving instruction is clear and the target event is unambiguous.

## Reliability and Observability
- Use `scripts/gcal-auth.py` to manage OAuth tokens instead of hand-editing credentials.
- Use `scripts/gcal-client.py` for all Google Calendar API access.
- Apply retry-with-backoff on transient API failures.
- Log structured results with sanitized calendar and attendee data.
- Capture exhausted failures in `workspace/memory/dead-letters/YYYY-MM-DD.json`.
- If Google Calendar dependencies are missing, fail with an actionable install message.

## Setup and References
- Human setup instructions live in `README.md`.
- Calendar selection lives in `config/calendars.json`.
- Prep policy lives in `config/prep-rules.json`.

## Acceptance Standard
This skill is considered healthy when:
- today's events are fetched correctly from Google Calendar
- the morning briefing includes all events with correct times
- a prep doc can be generated 30 minutes before a test meeting
- `What's next?` returns the correct next event
- `Am I free Friday 3pm?` returns correct availability
- calendar conflicts are surfaced when overlaps exist
