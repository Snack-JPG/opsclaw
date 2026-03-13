# API Integrations

OpsClaw ships with a provider-oriented integration layer so the same operating model can work across common business systems. This document summarizes the supported APIs, what each integration does, how it authenticates, and the operational constraints that matter in production.

## Integration Summary

| Integration | Skill | Auth model | Read/Write profile |
| --- | --- | --- | --- |
| Gmail | `email-intel` | Google Workspace CLI (`gws`) shared auth | Reads messages and drafts responses; sending remains approval-gated |
| Google Calendar | `calendar-ops` | Google Workspace CLI (`gws`) shared auth | Reads events and availability; event changes require approval |
| Google Drive / Docs | `drive-docs` | Google Workspace CLI (`gws`) shared auth | Reads and updates files/docs; external edits should remain approval-gated |
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

Run `gws auth setup --login`, then use [gws-auth-setup.sh](/Users/austin/Desktop/opsclaw/skills/email-intel/scripts/gws-auth-setup.sh) if you want a repo-local wrapper around the same auth flow.

### Authentication and components

- Shared `gws` auth state
- Gmail API access through `gws gmail`
- Optional OpenClaw polling or hook workflow, depending on deployment

### Notes

- This integration is `gws`-driven.
- Draft creation is allowed; message sending should remain approval-gated.
- If you add webhook or watch infrastructure around Gmail, monitor it separately from `gws` auth health.

## Google Calendar

### Purpose

- fetch daily schedule
- check availability
- detect conflicts
- generate meeting prep

### Setup path

Run `gws auth setup --login`, then test read operations with [skills/calendar-ops/scripts/gcal-client.py](/Users/austin/Desktop/opsclaw/skills/calendar-ops/scripts/gcal-client.py).

### Authentication

- Shared `gws` auth state managed by `gws auth`

### Notes

- Read operations are safe by default.
- Calendar modifications should remain explicitly approval-gated.
- Failed `gws auth status` should be treated as degraded service, not silent failure.

## Google Drive / Docs

### Purpose

- search Drive folders and shared docs
- download or upload files
- create Google Docs
- read or update document content

### Setup path

Run `gws auth setup --login`, then use:

- [skills/drive-docs/scripts/drive-client.py](/Users/austin/Desktop/opsclaw/skills/drive-docs/scripts/drive-client.py)
- [skills/drive-docs/scripts/docs-client.py](/Users/austin/Desktop/opsclaw/skills/drive-docs/scripts/docs-client.py)

### Notes

- Treat shared document edits as approval-gated unless the user was explicit.
- Keep monitored folder IDs in [drive-config.json](/Users/austin/Desktop/opsclaw/skills/drive-docs/config/drive-config.json).

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
