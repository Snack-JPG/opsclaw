---
name: crm_sync
description: CRM integration for OpsClaw: look up contacts and deals, auto-log email and call interactions, score client health, generate prioritized follow-ups, and automate onboarding through HubSpot, Pipedrive, or GoHighLevel.
---

# CRM Sync Skill

Use this skill whenever the user asks to look up a client, inspect or update pipeline context, log a client interaction, generate a health report, review overdue follow-ups, or start client onboarding. It also applies to email-triggered CRM logging, heartbeat checks for stale follow-ups, daily follow-up runs, and weekly client health reviews.

## Load Order
1. Read `workspace/SOUL.md`, `workspace/USER.md`, `workspace/AGENTS.md`, `workspace/ops-state.json`, and `workspace/heartbeat-state.json`.
2. Read today's note in `workspace/memory/YYYY-MM-DD.md` and the previous note if recent client context matters.
3. Read this skill's config before making CRM decisions:
   - `config/crm-config.json`
   - `config/health-rules.json`
   - onboarding template in `config/onboarding-templates/`
4. Use the bundled scripts for deterministic work:
   - `scripts/hubspot-client.py`
   - `scripts/pipedrive-client.py`
   - `scripts/gohighlevel-client.py`
   - `scripts/health-scorer.py`
   - `scripts/onboarding.py`
   - `scripts/follow_ups.py`

## Triggers
- `Webhook`: new deal created, deal stage changed, contact created, or CRM workflow event received from HubSpot, Pipedrive, or GoHighLevel.
- `Cron`: daily follow-up review at 9:00 AM local timezone.
- `Cron`: weekly client health review every Monday at 8:00 AM local timezone.
- `Heartbeat`: overdue follow-up scan, stale pipeline activity check, and CRM error/rate-limit review.
- `Manual`: commands such as `Look up Acme`, `Log call with Acme about renewal`, `Client health report`, `Start onboarding for Acme - consulting`, `Follow-up list`, or `Update Acme deal to Proposal Sent`.

## Core Responsibilities
- Resolve a person or company to CRM contacts, companies, and active deals.
- Auto-log email and call interactions to the relevant CRM timeline with a short summary and timestamp.
- Update client health scores using deterministic rules and clear factor breakdowns.
- Generate prioritized follow-up lists from upcoming and overdue reminders.
- Automate new-client onboarding plans across CRM, tasks, reminders, and kickoff scheduling.
- Maintain clear auditability in memory and `workspace/ops-state.json`.

## Auto-Logging Flow
When `email-intel` or a manual command identifies a client interaction:

1. Match the sender, attendee, or supplied client name to a CRM contact.
2. If no contact exists, search the company and active deals before concluding there is no match.
3. Create a CRM note with:
   - interaction type: `email`, `call`, `meeting`, or `manual_note`
   - UTC timestamp
   - concise summary
   - source identifiers if available
4. Update or compute `lastContactAt` in the normalized result.
5. If the client has an active deal, add the same note to the deal timeline.
6. Record the action in memory with sanitized details.

Rules:
- Logging CRM notes is allowed without approval when it records facts.
- Do not change deal stage, value, or close date without explicit approval.
- If matching is ambiguous, present candidate records instead of writing to the wrong client.

## Client Health Scoring
Weekly health reviews and on-demand health reports must use `scripts/health-scorer.py`.

Weighted factors:
- recency of last contact: `30%`
- deal stage momentum: `25%`
- email response rate: `20%`
- meeting attendance: `15%`
- open task completion: `10%`

Output:
- `healthy` for scores above `70`
- `at_risk` for scores from `40` to `70`
- `critical` for scores below `40`

Expectations:
- Always return the total score plus factor-level breakdown.
- If data is missing, mark the factor as inferred and reduce confidence instead of failing.
- Surface the worst drivers first in owner-facing summaries.

## Follow-Up Engine
Daily at 9:00 AM local timezone:

1. Query the CRM for deals and contacts with due or overdue follow-up dates.
2. Combine CRM results with recent interaction history and health status where available.
3. Prioritize by urgency:
   - overdue active deals
   - high-value opportunities due today
   - at-risk clients with no recent contact
   - upcoming follow-ups due within the configured lookahead window
4. Generate a concise owner-facing list with recommended next action.
5. Update `workspace/ops-state.json.crm.followUps` and `workspace/heartbeat-state.json.lastChecks.crm`.

## New Client Onboarding
When onboarding is triggered manually or from a CRM webhook:

1. Load the requested onboarding template from `config/onboarding-templates/`.
2. Create or upsert the contact, company, and deal in the selected CRM.
3. Prepare a welcome email draft for approval, never send automatically.
4. Produce a deterministic checklist payload for the task system.
5. Suggest kickoff scheduling details and reminder dates.
6. Write onboarding milestones to memory and return a structured action report.

## Commands
- `Look up [client name/company]`
  - Search contacts, companies, and active deals and summarize the current relationship state.
- `Log call with [client] about [topic]`
  - Create CRM notes for the contact and active deal with factual summaries only.
- `Client health report`
  - Score the requested client or all supplied clients and surface at-risk accounts first.
- `Start onboarding for [client] - [service type]`
  - Use the matching onboarding template, create the CRM records, and generate checklist output.
- `Follow-up list`
  - Produce today's prioritized follow-up queue.
- `Update [client] deal to [stage]`
  - Confirm the target deal and queue the change for explicit approval before any write.

## Approval Policy
- Read-only CRM queries are `internal_query` and execute immediately.
- Logging factual notes is `crm_note` and executes immediately.
- Health reports, onboarding plans, and follow-up briefings are `internal_brief` and execute immediately.
- Deal stage, value, close date, owner, or pipeline changes are `crm_deal_change` and require explicit owner approval.
- Welcome emails remain drafts until approved under the email skill's send policy.

## Reliability and Observability
- Use the provider-specific scripts for all CRM API access.
- For GoHighLevel webhook subscriptions, use the Marketplace app settings. The local helper returns the subscription payload because the referenced public docs do not expose a REST registration/list endpoint.
- Apply bounded retry with exponential backoff for transient network errors and HTTP `429` / `5xx` responses.
- Return normalized JSON so downstream steps stay provider-agnostic.
- Capture exhausted failures in `workspace/memory/dead-letters/YYYY-MM-DD.json`.
- On heartbeat, surface degraded CRM status plainly, including rate-limit windows and last successful sync.

## Setup and References
- Human setup instructions live in `README.md`.
- Connection details and provider selection live in `config/crm-config.json`.
- GoHighLevel-specific auth defaults and webhook templates live in `config/gohighlevel-config.json`.
- Health thresholds and factor rules live in `config/health-rules.json`.
- Template-specific onboarding flows live in `config/onboarding-templates/`.

## Acceptance Standard
This skill is considered healthy when:
- contact lookup returns the correct HubSpot, Pipedrive, or GoHighLevel records
- email or call interactions are logged to the contact and active deal timelines
- health scores calculate correctly with factor-level breakdown for test clients
- overdue follow-ups appear in the daily queue
- onboarding output contains all expected checklist items and CRM objects
- CRM rate limits degrade gracefully without crashing the workflow
