# API Integrations

OpsClaw ships with a provider-oriented integration layer so the same operating model can work across common business systems. This document summarizes the supported APIs, what each integration does, how it authenticates, and the operational constraints that matter in production.

## Integration Summary

| Integration | Skill | Auth model | Read/Write profile |
| --- | --- | --- | --- |
| Gmail | `email-intel` | Google Cloud + Gmail API + Pub/Sub | Reads messages and drafts responses; sending remains approval-gated |
| Google Calendar | `calendar-ops` | OAuth 2.0 desktop or installed-app flow | Reads events and availability; event changes require approval |
| HubSpot | `crm-sync` | Private app token | Reads CRM objects and can add notes; deal changes require approval |
| Pipedrive | `crm-sync` | API token | Reads CRM objects and can add notes; deal changes require approval |
| Linear | `task-tracker` | Personal API key | Reads and writes issues/tasks |
| Notion | `task-tracker` | Internal integration token | Reads and writes tasks in a database |
| Asana | `task-tracker` | Personal access token | Reads and writes tasks/projects |

## Gmail

### Purpose

- receive inbox change notifications
- classify messages
- escalate VIP or urgent items
- generate briefings
- create approval-safe draft responses

### Setup path

Use [skills/email-intel/scripts/gmail-setup.sh](/Users/austin/Desktop/opsclaw/skills/email-intel/scripts/gmail-setup.sh) to bootstrap the Google Cloud and Pub/Sub side of the integration.

### Authentication and components

- Google Cloud project
- Gmail API enabled
- Pub/Sub topic and push subscription
- Gmail watch registration
- OpenClaw hook preset for `gmail`

### Notes

- This integration is event-driven.
- Draft creation is allowed; message sending should remain approval-gated.
- Watch registrations can expire and should be monitored.

## Google Calendar

### Purpose

- fetch daily schedule
- check availability
- detect conflicts
- generate meeting prep

### Setup path

Use the auth helper in [skills/calendar-ops/scripts/gcal-auth.py](/Users/austin/Desktop/opsclaw/skills/calendar-ops/scripts/gcal-auth.py), then test read operations with [skills/calendar-ops/scripts/gcal-client.py](/Users/austin/Desktop/opsclaw/skills/calendar-ops/scripts/gcal-client.py).

### Authentication

- OAuth 2.0 client credentials
- refresh token stored locally in config

### Notes

- Read operations are safe by default.
- Calendar modifications should remain explicitly approval-gated.
- Expired tokens should be treated as degraded service, not silent failure.

## HubSpot

### Purpose

- contact, company, and deal lookup
- timeline notes
- onboarding workflows
- follow-up prioritisation
- health scoring inputs

### Authentication

- private app token via `HUBSPOT_ACCESS_TOKEN`

### Notes

- Use minimal scopes.
- Notes can be logged automatically if your policy permits.
- Deal-stage changes should require approval.

## Pipedrive

### Purpose

- contact and deal lookup
- notes
- onboarding and follow-up workflows
- CRM context for daily reporting

### Authentication

- API token via `PIPEDRIVE_API_TOKEN`

### Notes

- The company-specific API base URL must be correct.
- Keep the token out of `crm-config.json`; use environment variables only.

## Linear

### Purpose

- list, create, search, and update issues
- normalized task export for standups and reports

### Authentication

- `LINEAR_API_KEY`

### Notes

- Linear uses GraphQL; the wrapper normalizes output for the rest of OpsClaw.
- Task creation is typically safe, but you should still align it with the client’s workflow expectations.

## Notion

### Purpose

- query a task database
- create and update tasks
- supply normalized task data for reporting

### Authentication

- `NOTION_API_TOKEN`

### Notes

- The integration requires the target database to be shared with the integration.
- Property mapping must be accurate in the tracker config.

## Asana

### Purpose

- list tasks and sections
- create new tasks
- feed standup and weekly reporting

### Authentication

- `ASANA_ACCESS_TOKEN`

### Notes

- Confirm workspace, project, and section defaults in config before enabling write paths.

## Cross-Integration Principles

- Keep credentials in environment variables or a secret manager.
- Normalize provider output before it reaches cross-skill reporting.
- Preserve approval gates for external or high-impact writes.
- Design for degraded mode: missing one provider should not stop the rest of the system.
- Use [scripts/health-check.sh](/Users/austin/Desktop/opsclaw/scripts/health-check.sh) to catch missing dependencies, missing env vars, and basic connectivity drift.

## Recommended Validation Flow

1. Test provider authentication with the provider-specific CLI.
2. Confirm config files under `skills/<name>/config/` match the target environment.
3. Run sample read operations first.
4. Verify approval behavior before enabling any write path.
5. Capture one known-good output sample for future regression checks.
