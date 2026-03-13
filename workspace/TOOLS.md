# TOOLS.md — Integration Inventory And Use Policy

This file defines how OpsClaw should treat each integration class in Phase 1. Update it when enabling or disabling systems.

## Core Runtime Tools
### OpenClaw Gateway
- Purpose: owner messaging, inbound commands, heartbeat execution
- Access level: read/write to internal channels only
- Risk level: medium
- Notes: protect with a gateway token and allowlisted users

### Workspace State Files
- Purpose: source of truth for queues, health, and client context
- Access level: read/write
- Risk level: low
- Notes: writes must be atomic and timestamped

### Structured Logger
- Purpose: machine-readable audit trail
- Access level: write
- Risk level: low
- Notes: redact secrets and regulated data before logging

## Planned Skills
### Email Intel
- Systems: Gmail API, Outlook API, webhook ingress
- Default access: read + draft only
- Write policy: sending external email requires approval
- Safety notes: use idempotency on webhook events and log failures to dead letters

### Calendar Ops
- Systems: Google Calendar API, Microsoft 365 Calendar
- Default access: read
- Write policy: any calendar mutation requires approval
- Safety notes: meeting prep may be generated automatically; event changes may not

### CRM Sync
- Systems: HubSpot, Pipedrive
- Default access: read + notes
- Write policy: notes allowed if configured; stage/value changes require approval
- Safety notes: protect contact data and avoid logging sensitive customer information

### Task Tracker
- Systems: Linear, Notion, Asana
- Default access: read/write internal tasks
- Write policy: routine internal task creation allowed if configured
- Safety notes: blocked tasks should reference the missing dependency or approval

### Ops Reporting
- Systems: owner messaging channel, internal memory, state files
- Default access: read/write
- Write policy: owner-facing reports only
- Safety notes: summarize risk clearly and avoid exposing secrets

## Secret Handling
- Store credentials in environment variables or external secret stores.
- Never commit tokens, OAuth refresh tokens, webhook secrets, or passwords.
- Rotate webhook and gateway tokens when onboarding, offboarding, or after suspected exposure.

## Observability Requirements
- Every tool action should emit structured logs with a correlation ID.
- Consecutive subsystem failures should be reflected in `heartbeat-state.json`.
- Exhausted retries should create a dead-letter record for manual review.

## Rate Limit Guidance
- Respect provider quotas.
- Retry transient failures with exponential backoff and jitter.
- Escalate when a provider is degraded long enough to threaten SLA targets.
