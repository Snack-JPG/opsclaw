# HEARTBEAT.md — Autonomous Operations Checklist

Use this document for scheduled sweeps, webhook catch-up runs, and manual health checks. A heartbeat should be fast, repeatable, and mostly read-only unless explicitly allowed by policy.

## Default Cadence
- Standard interval: every `30m`
- Quiet hours: `22:00-07:00` local time
- Reconciliation run: `02:00` daily

## Every Heartbeat
1. Load `ops-state.json` and `heartbeat-state.json`.
2. Check approval queue age and any items awaiting owner response.
3. Check urgent email queue and unread counts if email is active.
4. Check meetings within the next two hours if calendar is active.
5. Check tasks due today, overdue items, and blocked items if task tracking is active.
6. Check CRM follow-ups and at-risk accounts if CRM is active.
7. Check reporting freshness, dead-letter volume, and consecutive error counters.
8. Write updated timestamps and counters back to `heartbeat-state.json`.

## Escalation Rules
- Urgent message from a VIP contact: alert owner immediately.
- Meeting in under 30 minutes with missing prep: generate prep note or alert owner.
- Overdue task older than 24 hours: alert owner in next permitted message window.
- CRM account health below threshold: include in next brief, escalate immediately if revenue-critical.
- Dead letters above 5 in 24 hours: alert owner with source breakdown.
- Skill error count above 3 in one hour: alert owner and mark subsystem degraded.

## Quiet-Hours Policy
- Work silently during quiet hours unless the issue is critical.
- Queue non-urgent updates for the morning briefing.
- Critical means: VIP escalation, security event, imminent meeting failure, or severe system outage.

## Health Dashboard Format
Use this structure when reporting runtime health:

```text
Skills Health
Email      OK / WARN / FAIL
Calendar   OK / WARN / FAIL
CRM        OK / WARN / FAIL
Tasks      OK / WARN / FAIL
Reporting  OK / WARN / FAIL
```

Attach last-check age, error counts, and next action when available.

## Reconciliation Run
At 02:00 local time:
- Compare processed email/event counts against source systems where possible.
- Look for stale approvals, orphaned tasks, missing CRM follow-ups, and unclosed dead letters.
- Write discrepancies to memory and dead-letter storage.
- Do not auto-resolve anything that could alter external state without approval.

## Failure Handling
- Use exponential backoff for transient API errors.
- Increment consecutive error counters per subsystem.
- Send events to dead-letter storage when retries are exhausted.
- Reset the subsystem counter after a successful check.

## Completion Standard
A heartbeat is complete only when:
- timestamps are updated,
- any failures are recorded,
- owner alerts are queued or sent according to policy,
- no silent errors remain.
