# CRM Sync Skill

This skill adds CRM-backed client lookup, interaction logging, health scoring, follow-up generation, and onboarding automation to OpsClaw using either HubSpot or Pipedrive.

## Files
- `SKILL.md`: agent operating instructions
- `scripts/hubspot-client.py`: HubSpot CRM API wrapper and CLI
- `scripts/pipedrive-client.py`: Pipedrive API wrapper and CLI
- `scripts/health-scorer.py`: deterministic client health scoring engine
- `scripts/onboarding.py`: onboarding checklist and CRM upsert orchestrator
- `scripts/follow_ups.py`: follow-up prioritisation engine
- `config/crm-config.json`: provider selection and connection template
- `config/health-rules.json`: factor thresholds and score weights
- `config/onboarding-templates/*.json`: onboarding checklist templates

## Prerequisites
- A HubSpot or Pipedrive account with API access
- `python3` installed locally
- For HubSpot:
  - a private app token with CRM object read/write scopes
- For Pipedrive:
  - an API token and your company domain, for example `acme`

These scripts use the Python standard library only, so no extra package install is required.

## Quick Start
1. Copy and edit the CRM config template:

```bash
$EDITOR skills/crm-sync/config/crm-config.json
```

2. Set the provider:
   - HubSpot: `"provider": "hubspot"`
   - Pipedrive: `"provider": "pipedrive"`

3. Add credentials:
   - HubSpot: set `hubspot.baseUrl` and export `HUBSPOT_ACCESS_TOKEN`
   - Pipedrive: set `pipedrive.baseUrl` and export `PIPEDRIVE_API_TOKEN`

4. Test connectivity.

### HubSpot Test
```bash
python3 skills/crm-sync/scripts/hubspot-client.py search-contacts \
  --config skills/crm-sync/config/crm-config.json \
  --query "Acme"
```

### Pipedrive Test
```bash
python3 skills/crm-sync/scripts/pipedrive-client.py search-contacts \
  --config skills/crm-sync/config/crm-config.json \
  --query "Acme"
```

## HubSpot Setup
1. In HubSpot, create a private app with CRM scopes for contacts, companies, deals, notes, and tasks.
2. Copy the access token.
3. Export it:

```bash
export HUBSPOT_ACCESS_TOKEN="pat-na1-..."
```

4. Set `hubspot.baseUrl` to the default unless you have a regional requirement:

```json
"hubspot": {
  "baseUrl": "https://api.hubapi.com",
  "tokenEnv": "HUBSPOT_ACCESS_TOKEN"
}
```

### Common HubSpot Commands
```bash
python3 skills/crm-sync/scripts/hubspot-client.py lookup \
  --config skills/crm-sync/config/crm-config.json \
  --query "Acme"
```

```bash
python3 skills/crm-sync/scripts/hubspot-client.py add-note \
  --config skills/crm-sync/config/crm-config.json \
  --contact-id 123456 \
  --body "Call summary: reviewed renewal timing and next steps." \
  --deal-id 78910
```

## Pipedrive Setup
1. In Pipedrive, open `Settings -> Personal preferences -> API`.
2. Copy the API token.
3. Export it:

```bash
export PIPEDRIVE_API_TOKEN="..."
```

4. Set `pipedrive.baseUrl` using your company domain:

```json
"pipedrive": {
  "baseUrl": "https://acme.pipedrive.com/api/v1",
  "tokenEnv": "PIPEDRIVE_API_TOKEN"
}
```

### Common Pipedrive Commands
```bash
python3 skills/crm-sync/scripts/pipedrive-client.py lookup \
  --config skills/crm-sync/config/crm-config.json \
  --query "Acme"
```

```bash
python3 skills/crm-sync/scripts/pipedrive-client.py add-note \
  --config skills/crm-sync/config/crm-config.json \
  --person-id 123 \
  --content "Email summary: sent proposal recap and confirmed procurement timeline." \
  --deal-id 456
```

## Health Scoring
Score one or more clients from a metrics payload:

```bash
python3 skills/crm-sync/scripts/health-scorer.py \
  --rules skills/crm-sync/config/health-rules.json \
  --input /tmp/client-metrics.json
```

Expected input shape:

```json
{
  "clients": [
    {
      "clientId": "acme",
      "name": "Acme Corp",
      "lastContactAt": "2026-03-10T10:00:00Z",
      "dealStage": "proposal_sent",
      "daysInStage": 6,
      "responseRate": 0.82,
      "meetingAttendanceRate": 0.9,
      "openTasks": 5,
      "completedTasks": 4
    }
  ]
}
```

## Onboarding Automation
Run onboarding with a selected template:

```bash
python3 skills/crm-sync/scripts/onboarding.py \
  --template skills/crm-sync/config/onboarding-templates/consulting.json \
  --client /tmp/new-client.json \
  --provider hubspot
```

The output is a structured checklist and CRM action plan. Use `--create-records` with provider credentials if you want the script to upsert CRM objects.

## Follow-Up Engine
Build a prioritised follow-up queue from CRM export data:

```bash
python3 skills/crm-sync/scripts/follow_ups.py \
  --config skills/crm-sync/config/crm-config.json \
  --rules skills/crm-sync/config/health-rules.json \
  --input /tmp/followups.json
```

## Operational Notes
- Factual notes can be logged immediately; deal changes require explicit approval.
- Rate-limited API responses are retried with bounded backoff and surfaced as degraded state if retries exhaust.
- Keep provider credentials in environment variables, not committed into JSON config.
- The onboarding script can emit CRM actions without executing them, which is useful for dry runs and task-system integration.

## Verification Checklist
- Search for a known client and confirm contact/company/deal data matches the CRM.
- Add a note and confirm it appears on the correct contact timeline.
- Score five test clients and confirm the status buckets are sensible.
- Feed overdue follow-up data into `follow_ups.py` and confirm overdue items rank first.
- Run onboarding with each template and confirm checklist output is complete.
