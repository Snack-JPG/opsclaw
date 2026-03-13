# OpsClaw Demo Script

This is a scripted five-minute Loom walkthrough for showing OpsClaw as a complete business operations agent package. Keep the pace tight. Show the product working, not just files.

## Demo Goal

Prove that OpsClaw can be installed quickly, configured for a real operator, and used to automate inbox, calendar, CRM, task, and reporting workflows with approval-safe controls.

## Recording Setup

- Use a clean terminal and editor theme with high contrast.
- Have the repo open in a browser tab and local editor.
- Prepare sample outputs for email triage, meeting prep, CRM follow-up, and daily brief.
- Keep one terminal ready with commands already tested.

## Scene 1: Hook and positioning

### Duration

30 seconds

### Show

- GitHub repo landing on `README.md`
- Architecture diagram
- Feature sections and pricing tiers

### Say

"This is OpsClaw, a deployment package for turning OpenClaw into a business operations assistant. It gives a founder or small team one agent that can watch inboxes, calendars, CRM, tasks, and produce daily operating briefs without building the whole stack from scratch."

## Scene 2: Repository tour

### Duration

35 seconds

### Show

- Repo tree in editor
- `workspace/`
- `skills/`
- `templates/`
- `docs/`
- `scripts/`

### Say

"The repo is split into reusable pieces: workspace policy and memory, skill modules for each business system, client templates for common business types, operator docs, and utility scripts for backup, health checks, and migrations."

## Scene 3: One-command setup

### Duration

45 seconds

### Show

- `setup.sh`
- `config-wizard.sh`
- A terminal running `./setup.sh`
- A terminal running `./config-wizard.sh`

### Say

"Setup is designed to be fast. `setup.sh` installs or verifies OpenClaw, copies the workspace into `~/.openclaw`, and installs the support assets. `config-wizard.sh` then asks a few deployment questions and writes a starter config and user profile."

## Scene 4: Skill stack

### Duration

60 seconds

### Show

- `skills/email-intel/README.md`
- `skills/calendar-ops/README.md`
- `skills/crm-sync/README.md`
- `skills/task-tracker/README.md`
- `skills/ops-reporting/README.md`

### Say

"The package comes with five production-oriented skills. Email Intelligence classifies inbox activity and drafts replies for approval. Calendar Ops handles schedule briefings and meeting prep. CRM Sync works with HubSpot or Pipedrive. Task Tracker supports Linear, Notion, and Asana. Ops Reporting combines all of that into daily and weekly operating views."

## Scene 5: Email and meeting workflow

### Duration

55 seconds

### Show

- Sample email classification output
- Draft queue example
- Meeting prep output
- `workspace/ops-state.json` showing pending approvals or urgent items

### Say

"Here’s the operating loop. A new email lands, gets classified, and if it’s routine the system can draft a response without sending it. VIP or urgent messages get escalated. The same agent checks the calendar, detects upcoming meetings, and generates prep with context so the owner sees what matters before the meeting starts."

## Scene 6: CRM and task visibility

### Duration

45 seconds

### Show

- CRM lookup or follow-up queue output
- Task standup or weekly report output

### Say

"On the CRM side, OpsClaw can look up contact and deal context, score client health, and prioritise overdue follow-ups. On the task side it can normalize work from Linear, Notion, or Asana, then produce standups and weekly summaries without locking the operator into one provider."

## Scene 7: Unified reporting and safeguards

### Duration

45 seconds

### Show

- Daily brief output
- KPI or anomaly output
- Approval rules in docs or workspace files

### Say

"The reporting layer turns all of that raw activity into one daily brief. It highlights urgent inbox items, meetings that need prep, overdue tasks, at-risk clients, and KPI anomalies. Critically, OpsClaw does not auto-send risky external actions. Those stay approval-gated, and financial actions are blocked."

## Scene 8: Close with deployment value

### Duration

25 seconds

### Show

- Pricing table in `README.md`
- Template library table
- Health and backup scripts

### Say

"This is built to be sold and deployed. There are client templates, clear tiers, health checks, migration tooling, and backup scripts. So this is not just a prompt pack, it’s an operational system you can install for a founder, customise in a day or two, and support as an ongoing service."

## Demo Checklist

- Keep total runtime under 5 minutes.
- Avoid showing any fake credentials.
- Use realistic but non-sensitive sample data.
- If live APIs are unavailable, use pre-generated script output and say it is recorded sample output.
- End on the README, not on a terminal error or a config file.
