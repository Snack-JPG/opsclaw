# Calendar Operations Skill

This skill adds Google Calendar-backed scheduling, daily briefings, meeting prep generation, availability checks, and approval-gated calendar changes to OpsClaw.

## Files
- `SKILL.md`: agent operating instructions
- `scripts/gcal-auth.py`: OAuth2 bootstrap, refresh, and token inspection
- `scripts/gcal-client.py`: Google Calendar client and CLI for read/write operations
- `scripts/briefing.py`: owner-facing schedule briefing generator
- `scripts/prep-generator.py`: meeting prep generator
- `config/calendars.json`: monitored calendar list and scheduling defaults
- `config/prep-rules.json`: prep-generation policy and heuristics

## Prerequisites
- A Google account with Google Calendar access
- A Google Cloud project you can administer
- OAuth client credentials for a desktop app or installed app flow
- `python3` installed locally
- These Python packages installed:

```bash
python3 -m pip install google-api-python-client google-auth google-auth-oauthlib
```

## Quick Start
1. Create a Google Cloud project or reuse an existing one.
2. Enable the Google Calendar API.
3. Create an OAuth client credential for a desktop app.
4. Download the JSON credential file.
5. Run:

```bash
python3 skills/calendar-ops/scripts/gcal-auth.py auth \
  --credentials /path/to/client-secret.json \
  --token-path skills/calendar-ops/config/google-token.json
```

6. Inspect token status:

```bash
python3 skills/calendar-ops/scripts/gcal-auth.py status \
  --token-path skills/calendar-ops/config/google-token.json
```

7. Configure calendars:

```bash
$EDITOR skills/calendar-ops/config/calendars.json
```

8. Test connectivity:

```bash
python3 skills/calendar-ops/scripts/gcal-client.py list-events \
  --token-path skills/calendar-ops/config/google-token.json \
  --calendars-path skills/calendar-ops/config/calendars.json \
  --window today
```

## Recommended OpenClaw Scheduling Jobs
Add or merge jobs like:

```json5
[
  {
    name: "Morning Schedule",
    schedule: { kind: "cron", expr: "0 7 * * 1-5", tz: "Europe/London" },
    payload: {
      kind: "agentTurn",
      message: "Generate today's schedule briefing. Include all calendar events, flag conflicts, and note which meetings need prep docs."
    },
    sessionTarget: "isolated",
    delivery: { mode: "announce" }
  },
  {
    name: "Meeting Prep Check",
    schedule: { kind: "cron", expr: "*/15 8-18 * * 1-5", tz: "Europe/London" },
    payload: {
      kind: "agentTurn",
      message: "Check calendar for meetings starting in the next 30 minutes that need prep docs. Generate prep for any that do not have one yet."
    },
    sessionTarget: "isolated",
    delivery: { mode: "announce" }
  }
]
```

## Local Script Usage

### List Events
```bash
python3 skills/calendar-ops/scripts/gcal-client.py list-events \
  --token-path skills/calendar-ops/config/google-token.json \
  --calendars-path skills/calendar-ops/config/calendars.json \
  --window today
```

### Check Availability
```bash
python3 skills/calendar-ops/scripts/gcal-client.py availability \
  --token-path skills/calendar-ops/config/google-token.json \
  --calendars-path skills/calendar-ops/config/calendars.json \
  --start 2026-03-20T15:00:00+00:00 \
  --end 2026-03-20T16:00:00+00:00
```

### Detect Conflicts
```bash
python3 skills/calendar-ops/scripts/gcal-client.py conflicts \
  --events-path /tmp/events.json
```

### Generate a Briefing
```bash
python3 skills/calendar-ops/scripts/briefing.py \
  --events-path /tmp/events.json \
  --ops-state workspace/ops-state.json \
  --prep-rules skills/calendar-ops/config/prep-rules.json
```

### Generate Meeting Prep
```bash
python3 skills/calendar-ops/scripts/prep-generator.py \
  --event-path /tmp/event.json \
  --prep-rules skills/calendar-ops/config/prep-rules.json \
  --recent-interactions /tmp/interactions.json \
  --attendee-context /tmp/attendees.json \
  --crm-context /tmp/crm.json
```

## Configuration

### `config/calendars.json`
- Lists which Google calendars should be monitored.
- Controls the display timezone, default lookahead windows, and minimum meeting buffer.
- Marks which calendars count for conflict detection and availability checks.

### `config/prep-rules.json`
- Defines when prep is required based on event keywords, attendee domains, or organizers.
- Controls auto-generation lead time and output location.
- Lets you always require prep for high-value contacts or specific meeting types.

## Operational Notes
- Read operations run immediately.
- Event changes must be queued for explicit owner approval before execution.
- Conflicts should be surfaced in both heartbeat checks and the morning briefing.
- Missing Google libraries or expired credentials should be treated as degraded-service conditions, not silent failures.

## Verification Checklist
- Fetch today's events and confirm times match Google Calendar.
- Check an occupied slot with `availability` and confirm the response is blocked.
- Check a free slot and confirm the response is available.
- Create a synthetic overlapping event set and confirm `conflicts` reports it.
- Generate a briefing and confirm it highlights prep-needed meetings and major free blocks.
- Generate a prep doc for a test client meeting and confirm attendee context and talking points appear.
