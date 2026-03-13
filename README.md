# OpsClaw

OpsClaw is a production-ready OpenClaw deployment package for founders and small teams who want an AI business operations assistant without building the stack from scratch. It packages workspace policy, multi-skill automation, client templates, setup tooling, and deployment guidance into a reusable system you can install, customise, and run in a few hours.

It is designed for operators who need one agent to stay on top of inboxes, calendars, Drive docs, CRMs, task systems, and daily reporting while keeping risky actions approval-gated.

## Why OpsClaw

- Turns a fresh OpenClaw runtime into a business operations assistant.
- Unifies email triage, calendar prep, CRM follow-ups, task tracking, and reporting.
- Ships with reusable templates for common client types.
- Keeps external writes approval-gated and financial actions blocked.
- Supports laptop, VPS, and Docker Compose deployments.
- Includes operational docs, migration tooling, health checks, and backups.

## Architecture

```text
                                           +----------------------+
                                           | Owner Channel        |
                                           | Telegram / Slack     |
                                           | Email / WhatsApp     |
                                           +----------+-----------+
                                                      |
                                                      v
+--------------------+     +--------------------+   +-----------------------+
| Gmail Pub/Sub      | --> | OpenClaw Gateway   |-->| Agent Router          |
| Webhooks / Sched   |     | Hooks + Sessions   |   | Default + Optional    |
+--------------------+     +--------------------+   | Department Agents     |
                                                     +-----------+-----------+
                                                                 |
                       +--------------------+---------------------+--------------------+
                       |                    |                     |                    |
                       v                    v                     v                    v
               +---------------+    +---------------+     +---------------+    +---------------+
               | Email Intel   |    | Calendar Ops  |     | CRM Sync      |    | Task Tracker  |
               | Gmail triage  |    | GCal briefs   |     | HubSpot /     |    | Linear /      |
               | Draft queues  |    | Meeting prep  |     | Pipedrive     |    | Notion /      |
               +-------+-------+    +-------+-------+     +-------+-------+    | Asana         |
                       |                    |                     |            +-------+-------+
                       +--------------------+---------------------+--------------------+
                                                      |
                                                      v
                                            +----------------------+
                                            | Ops Reporting        |
                                            | Daily brief          |
                                            | KPI + anomalies      |
                                            +----------+-----------+
                                                       |
                                                       v
                                            +----------------------+
                                            | Workspace + Memory   |
                                            | SOUL / AGENTS /      |
                                            | HEARTBEAT / state    |
                                            +----------------------+
```

## Feature List

### Core platform

- Opinionated workspace with `SOUL.md`, `AGENTS.md`, `HEARTBEAT.md`, `USER.md`, `IDENTITY.md`, and tool boundaries.
- Heartbeat-driven operating model for scheduled checks, escalations, and briefings.
- Approval policy with clear separation between safe reads, draft generation, explicit approval actions, and blocked financial operations.
- Client templates for solo consultants, agencies, e-commerce operators, SaaS founders, and professional services teams.

### Skills

- `email-intel`: Gmail inbox fetch via `gws`, inbox classification, VIP escalation, brief generation, draft reply suggestions.
- `calendar-ops`: Google Calendar reads and writes via `gws`, daily schedule briefings, conflict checks, availability checks, meeting prep generation.
- `drive-docs`: Google Drive and Google Docs search, upload/download, creation, and update workflows via `gws`.
- `crm-sync`: HubSpot or Pipedrive contact/deal lookup, notes, follow-up prioritisation, onboarding flows, health scoring.
- `task-tracker`: Linear, Notion, or Asana task sync, natural-language task parsing, standups, weekly reports.
- `ops-reporting`: unified daily brief, weekly review, KPI tracking, anomaly detection, channel-specific formatting.

### Operations

- One-command install with `setup.sh`.
- Guided workspace configuration with `config-wizard.sh`.
- Backup, health check, and migration helpers under `scripts/`.
- Docker Compose deployment for always-on operation.
- Security and setup guides for real deployments.

## Quick Start

### 1. Clone and install

```bash
git clone <your-fork-or-repo-url> opsclaw
cd opsclaw
./setup.sh
```

### 2. Configure the workspace

```bash
./config-wizard.sh
```

This writes `workspace/config.json5`, updates `workspace/USER.md`, and sets your starter deployment profile.

### 3. Add secrets

Use `~/.openclaw/opsclaw/.env` or your secret manager for credentials such as:

```bash
OPSCLAW_GATEWAY_TOKEN=replace-me
OPSCLAW_HOOKS_TOKEN=replace-me
HUBSPOT_ACCESS_TOKEN=replace-me
PIPEDRIVE_API_TOKEN=replace-me
LINEAR_API_KEY=replace-me
NOTION_API_TOKEN=replace-me
ASANA_ACCESS_TOKEN=replace-me
```

### 4. Verify the install

```bash
./scripts/health-check.sh
openclaw security audit --deep
```

### 5. Start OpsClaw

```bash
openclaw gateway start
```

For container deployments:

```bash
docker compose up -d
```

## How It Runs

1. `setup.sh` installs OpenClaw and the Google Workspace CLI (`gws`) if needed, then copies workspace, docs, scripts, templates, and skills into `~/.openclaw/`.
2. `config-wizard.sh` generates a baseline `workspace/config.json5` and personalises `workspace/USER.md`.
3. `gws auth setup --login` provisions shared Google Workspace auth for Gmail, Calendar, Drive, and Docs skills.
4. Skills are enabled per template or per deployment.
5. Hooks, scheduled jobs, and heartbeat checks drive ongoing monitoring and briefing generation.
6. High-risk actions are queued for approval instead of executed automatically.

## Screenshots

Add polished captures here before publishing a public showcase. Recommended set:

| Screenshot | What to show | Suggested filename |
| --- | --- | --- |
| Daily briefing | Unified morning brief with priorities, schedule, tasks, and client risks | `docs/screenshots/daily-briefing.png` |
| Email triage | VIP escalation plus approval-safe draft queue | `docs/screenshots/email-triage.png` |
| Meeting prep | Auto-generated meeting prep with attendees, context, and goals | `docs/screenshots/meeting-prep.png` |
| CRM sync | Follow-up queue or health scoring output | `docs/screenshots/crm-sync.png` |

## Tech Stack

| Layer | Tools |
| --- | --- |
| Runtime | OpenClaw, Node.js 20+, npm |
| Automation scripts | Bash, Python 3 |
| Messaging and hooks | OpenClaw Gateway, webhooks, Gmail / Calendar / Drive / Docs via `gws` |
| Google Workspace | Google Workspace CLI (`gws`) for Gmail, Calendar, Drive, Docs |
| CRM | HubSpot API, Pipedrive API |
| Task systems | Linear GraphQL API, Notion API, Asana API |
| Reporting | Markdown, plain text, Slack blocks, Telegram-friendly output |
| Deployment | macOS or Ubuntu, Docker Compose, optional Tailscale |

## API Integrations

| Integration | Purpose | Status |
| --- | --- | --- |
| Gmail via `gws` | Inbox fetch, classification, draft workflows | Implemented |
| Google Calendar via `gws` | Scheduling, availability, prep, briefing | Implemented |
| Google Drive / Docs via `gws` | File search, upload/download, doc creation and updates | Implemented |
| HubSpot | Contact and deal lookup, notes, follow-up workflows | Implemented |
| Pipedrive | CRM lookup, notes, onboarding, follow-up workflows | Implemented |
| Linear | Issue and task operations | Implemented |
| Notion | Task database operations | Implemented |
| Asana | Task creation and reporting | Implemented |

See [docs/api-integrations.md](docs/api-integrations.md) for setup expectations, auth model, and operational notes.

## Deployment Modes

| Mode | Best for | Notes |
| --- | --- | --- |
| Client machine | Solo operators, quick pilots | Fastest setup, but sleeps when the machine sleeps |
| VPS | Small teams that need 24/7 coverage | Best default for production |
| Docker Compose | Security-conscious and multi-agent installs | Easiest to standardise and operate |

## Template Library

| Template | Intended user | Defaults |
| --- | --- | --- |
| `solo-consultant.json5` | One-person service business | Telegram, email, concise briefings |
| `agency.json5` | 5-15 person client services team | Slack, full skill set, standard briefings |
| `ecommerce.json5` | Store operator with high inbox volume | Telegram, tighter heartbeat, calendar optional |
| `saas-founder.json5` | Founder-led SaaS team | Slack, full stack, escalation keywords |
| `professional-services.json5` | Legal, accounting, advisory | Approval-heavy, compliance-minded defaults |

## Pricing Tiers

| Tier | Price | Best for | Includes |
| --- | --- | --- | --- |
| Starter | $500 setup | Solo founder pilot | Single agent, one channel, email triage, setup assistance |
| Growth | $1,500 setup + $500/mo | Small team ops function | Full skill stack, CRM and task integrations, weekly reviews, support |
| Premium | $3,000 setup + $1,000/mo | Multi-department operator | Multi-agent routing, advanced reporting, custom workflows, ongoing tuning |

## Repository Layout

```text
opsclaw/
├── README.md
├── DEMO.md
├── SPEC.md
├── setup.sh
├── config-wizard.sh
├── docker-compose.yml
├── docs/
├── scripts/
├── skills/
├── templates/
└── workspace/
```

## Documentation

- [docs/setup-guide.md](docs/setup-guide.md)
- [docs/security-guide.md](docs/security-guide.md)
- [docs/skill-customisation.md](docs/skill-customisation.md)
- [docs/troubleshooting.md](docs/troubleshooting.md)
- [docs/api-integrations.md](docs/api-integrations.md)
- [DEMO.md](DEMO.md)

## Contributing

Contributions should preserve the core operating model: deterministic helpers where possible, explicit approvals for external writes, and documentation that makes deployments reproducible.

1. Fork the repo and create a focused branch.
2. Keep changes scoped to one capability or one documentation area.
3. Update docs when behavior, setup, or operator workflow changes.
4. Validate shell scripts with `bash -n` and Python modules with `python3 -m compileall scripts skills`.
5. Open a pull request with the deployment impact, verification steps, and any migration notes.

Bug reports and requests are supported through the issue templates in `.github/ISSUE_TEMPLATE/`.

## Security

- Never commit live tokens, OAuth credentials, or `.env` files.
- Treat `workspace/`, memory files, CRM exports, and generated reports as confidential.
- Run `openclaw security audit --deep` before production launch.
- Use [docs/security-guide.md](docs/security-guide.md) as the pre-flight checklist.

## License

MIT. See [LICENSE](LICENSE).
