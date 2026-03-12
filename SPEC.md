# OpsClaw — Business Operations Agent Platform

## Spec v1.0 | March 2026

---

## Executive Summary

OpsClaw is a production-ready, reusable OpenClaw deployment package that transforms a fresh OpenClaw instance into a fully autonomous business operations assistant. It connects email, calendar, CRM, task management, and reporting into a single AI agent that runs 24/7, triages inputs, takes action, and briefs the business owner via their preferred channel.

**Target buyer:** Non-technical founders and small business operators (1-50 people) who want an AI chief-of-staff but don't know how to build one.

**Delivery model:** Clone the base → customise for client's stack → deploy → ongoing support.

**Revenue:** $1,000-3,000 setup + $500-1,000/month support. Each deployment takes 2-3 days.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway                       │
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ Telegram  │  │  Slack   │  │  Email   │  │ WhatsApp │ │
│  │ Channel   │  │ Channel  │  │ Channel  │  │ Channel  │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │              │              │              │       │
│       └──────────────┴──────┬───────┴──────────────┘       │
│                             │                              │
│                    ┌────────▼────────┐                     │
│                    │   Agent Router   │                     │
│                    └────────┬────────┘                     │
│                             │                              │
│          ┌──────────────────┼──────────────────┐          │
│          │                  │                  │          │
│  ┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐  │
│  │  Ops Agent   │  │ Support Agent│  │ Sales Agent  │  │
│  │  (default)   │  │ (optional)   │  │ (optional)   │  │
│  └───────┬──────┘  └──────────────┘  └──────────────┘  │
│          │                                               │
│  ┌───────▼──────────────────────────────────────────┐   │
│  │                   Skills Layer                     │   │
│  │                                                    │   │
│  │  📧 Email Intel  📅 Calendar  👥 CRM  ✅ Tasks   │   │
│  │  📊 Reporting   🔍 Research  🌐 Browser          │   │
│  └────────────────────────────────────────────────────┘   │
│                                                           │
│  ┌────────────────────────────────────────────────────┐   │
│  │                  Memory Layer                       │   │
│  │                                                     │   │
│  │  SOUL.md    MEMORY.md    memory/YYYY-MM-DD.md      │   │
│  │  ops-state.json    client-db.json    config.json   │   │
│  └────────────────────────────────────────────────────┘   │
│                                                           │
│  ┌────────────────────────────────────────────────────┐   │
│  │              Automation Layer                       │   │
│  │                                                     │   │
│  │  Heartbeat (30m)    Cron Jobs    Webhooks          │   │
│  │  Gmail PubSub       Stripe Hooks  CRM Webhooks    │   │
│  └────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Deployment Options

### Option A: Client's Machine (Mac/Linux)
- Direct install via `npm i -g openclaw`
- Best for: solo founders who want it on their laptop
- Pros: simplest, cheapest, fastest
- Cons: offline when laptop sleeps

### Option B: VPS (Recommended)
- Ubuntu/Debian VPS ($5-20/mo on Hetzner/Contabo/DigitalOcean)
- Always-on, headless operation
- Docker Compose for isolation
- Tailscale for secure remote access
- Best for: businesses that want 24/7 operation

### Option C: Docker Compose (Production)
- Full containerised deployment
- Sandboxed tool execution
- Automated backups
- Best for: security-conscious clients, multi-agent setups

---

## Phase 1: Core Infrastructure

### 1.1 One-Command Setup Script

```bash
#!/bin/bash
# opsclaw-setup.sh — One-command OpsClaw deployment

set -euo pipefail

echo "🦞 OpsClaw Setup v1.0"
echo "====================="

# Check prerequisites
command -v node >/dev/null 2>&1 || { echo "❌ Node.js required"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "❌ npm required"; exit 1; }

# Install OpenClaw
npm i -g openclaw

# Create workspace
mkdir -p ~/.openclaw/workspace/{skills,memory,templates}

# Copy OpsClaw workspace files
cp -r ./workspace/* ~/.openclaw/workspace/

# Run guided setup
openclaw onboard

echo "✅ OpsClaw deployed. Run 'openclaw gateway start' to begin."
```

### 1.2 Workspace Files

**SOUL.md** — Business ops persona template:
```markdown
# SOUL.md — OpsClaw Business Agent

You are a business operations assistant. You are professional, concise, and action-oriented.

## Core Behaviours
- Prioritise by urgency and business impact
- Always provide context with recommendations
- Never send external communications without approval
- Log all actions to daily memory
- Brief the owner at configured intervals

## Tone
- Professional but not stiff
- Direct — lead with the answer, then context
- Flag risks early, don't bury them

## Boundaries
- No financial transactions without explicit approval
- No external emails/messages without review
- No data deletion
- Escalate anything you're unsure about
```

**AGENTS.md** — Operating instructions template:
```markdown
# AGENTS.md — OpsClaw Operating Instructions

## Every Session
1. Read SOUL.md — your persona
2. Read USER.md — your client's details
3. Read memory/YYYY-MM-DD.md (today + yesterday)
4. Check ops-state.json for pending tasks

## Memory
- Daily notes: memory/YYYY-MM-DD.md
- Long-term: MEMORY.md
- Operational state: ops-state.json
- Client data: client-db.json (if CRM skill active)

## Safety
- Never send external messages without approval
- No financial transactions
- trash > rm
- When in doubt, ask
```

**HEARTBEAT.md** — Autonomous operation template:
```markdown
# HEARTBEAT.md — OpsClaw Autonomous Checks

## Every Heartbeat (30m)
1. Check ops-state.json for pending actions
2. Check email for urgent messages (if email skill active)
3. Check calendar for upcoming events (<2h)
4. Check task deadlines approaching today
5. Update heartbeat-state.json

## Escalation Rules
- URGENT email from VIP contact → message owner immediately
- Meeting in <30min with no prep doc → generate prep doc
- Task overdue by >24h → remind owner
- Anomaly in KPIs → alert with context

## Quiet Hours
- 22:00-07:00 — work silently, don't message unless critical
- Queue non-urgent updates for morning briefing
```

### 1.3 Configuration Template

```json5
{
  // Channel config — uncomment what the client uses
  channels: {
    telegram: {
      enabled: true,
      // token: "BOT_TOKEN_HERE"
    },
    // slack: { enabled: true },
    // whatsapp: { enabled: true },
    // discord: { enabled: true },
  },

  agents: {
    defaults: {
      heartbeat: {
        every: "30m",
        target: "last",
        activeHours: { start: "07:00", end: "22:00" },
      },
      // Sandbox for production deployments
      // sandbox: { mode: "all", scope: "agent" },
    },
  },

  // Webhook ingress for external triggers
  hooks: {
    enabled: true,
    token: "${OPSCLAW_HOOKS_TOKEN}",
    path: "/hooks",
    presets: ["gmail"],
    mappings: [],
  },

  // Skills config
  skills: {
    entries: {
      "email-intel": { enabled: true },
      "calendar-ops": { enabled: true },
      "crm-sync": { enabled: true },
      "task-tracker": { enabled: true },
      "ops-reporting": { enabled: true },
    },
  },
}
```

### 1.4 Security Hardening Checklist

- [ ] Gateway token set (prevents unauthorised WS connections)
- [ ] Webhook hook token set (prevents unauthorised triggers)
- [ ] DM policy set to allowlist (only owner can message)
- [ ] Sandbox enabled for production (Docker isolation)
- [ ] No plaintext API keys in config (use env vars or secrets)
- [ ] Tailscale for remote access (no public ports)
- [ ] Auto-backup workspace + memory daily
- [ ] `openclaw security audit --deep` passes clean

---

## Phase 2: Email Intelligence Skill

### 2.1 Skill Overview

| Feature | Implementation |
|---------|---------------|
| Email ingestion | Gmail Pub/Sub → OpenClaw webhook (built-in) |
| Triage | LLM classifies urgency: critical/high/medium/low |
| Auto-drafts | Template-based responses for routine queries |
| Daily briefing | Cron job at configured time |
| VIP alerts | Instant notification for priority senders |
| Thread tracking | Memory-based conversation continuity |

### 2.2 Skill Structure

```
skills/email-intel/
├── SKILL.md              # Agent instructions
├── scripts/
│   ├── gmail-setup.sh    # One-command Gmail API setup
│   ├── classify.py       # Email classification logic
│   └── templates/        # Response templates by category
├── config/
│   ├── vip-senders.json  # Priority sender list
│   ├── categories.json   # Email category definitions
│   └── rules.json        # Auto-response rules
└── README.md
```

### 2.3 SKILL.md

```markdown
---
name: email_intel
description: Email intelligence — triage, classify, draft responses, and generate briefings from Gmail/Outlook inbox.
---

# Email Intelligence Skill

## Triggers
- **Webhook**: Gmail Pub/Sub push (new email arrives)
- **Cron**: Daily briefing at configured time
- **Heartbeat**: Check for urgent unread emails
- **Manual**: "Check my email" / "Draft a reply to X"

## On New Email (webhook trigger)
1. Read the email content from the webhook payload
2. Classify urgency: critical / high / medium / low
3. Categorise: client / internal / billing / marketing / spam
4. If sender is in vip-senders.json → alert owner immediately
5. If matches auto-response rule → draft response, queue for approval
6. Log to memory/YYYY-MM-DD.md
7. Update ops-state.json email queue

## Daily Briefing (cron trigger)
1. Fetch all unread emails from last 24h
2. Group by category and urgency
3. Generate briefing summary:
   - Critical items (with recommended actions)
   - Requires response (with draft suggestions)
   - FYI only (one-line summaries)
   - Filtered out (spam/marketing count)
4. Send via configured channel

## Commands
- "Check email" → scan inbox, report new items
- "Draft reply to [sender/subject]" → generate response draft
- "Mark [email] as handled" → update ops-state.json
- "Add [email] to VIP list" → update vip-senders.json
- "Email summary" → generate on-demand briefing
```

### 2.4 Gmail Pub/Sub Integration

OpenClaw has **native Gmail webhook support**. The flow:

1. Client sets up Google Cloud project + Pub/Sub topic
2. Gmail watch API pushes notifications to Pub/Sub
3. `gog gmail watch serve` forwards to OpenClaw webhook
4. OpenClaw's `gmail` preset mapping processes the payload
5. Agent runs email triage in isolated session

Config:
```json5
{
  hooks: {
    presets: ["gmail"],
    gmail: {
      model: "anthropic/claude-sonnet-4-20250514",  // cheaper model for email triage
      thinking: "off",
    },
    mappings: [{
      match: { path: "gmail" },
      action: "agent",
      wakeMode: "now",
      name: "Gmail",
      sessionKey: "hook:gmail:{{messages[0].id}}",
      messageTemplate: "New email from {{messages[0].from}}\nSubject: {{messages[0].subject}}\n\n{{messages[0].body}}",
      deliver: true,
      channel: "last",
    }],
  },
}
```

---

## Phase 3: Calendar & Scheduling Skill

### 3.1 Skill Overview

| Feature | Implementation |
|---------|---------------|
| Calendar read | Google Calendar API (OAuth2) |
| Daily briefing | Cron job — "Here's your day" |
| Meeting prep | Auto-generate context docs before meetings |
| Conflict detection | Flag double-bookings |
| Quick queries | "What's next?" / "Am I free Friday 3pm?" |

### 3.2 Skill Structure

```
skills/calendar-ops/
├── SKILL.md
├── scripts/
│   ├── gcal-auth.py      # Google Calendar OAuth setup
│   ├── gcal-client.py    # Calendar API wrapper
│   └── prep-generator.py # Meeting prep doc generator
├── config/
│   ├── calendars.json    # Which calendars to monitor
│   └── prep-rules.json   # When to auto-generate prep docs
└── README.md
```

### 3.3 SKILL.md

```markdown
---
name: calendar_ops
description: Calendar management — daily schedule briefing, meeting prep, conflict detection, and availability queries via Google Calendar.
---

# Calendar Operations Skill

## Triggers
- **Cron**: Morning briefing (configurable, default 7:00 AM)
- **Cron**: Pre-meeting prep (30 min before meetings with prep rules)
- **Heartbeat**: Check for meetings in next 2 hours
- **Manual**: "What's my schedule?" / "Am I free at X?"

## Morning Briefing
1. Fetch today's events from all configured calendars
2. Generate schedule overview:
   - Timeline view with gaps highlighted
   - Meeting prep status (done/pending)
   - Travel time warnings (if location-based)
   - Conflicts flagged
3. Send via configured channel at briefing time

## Meeting Prep (auto-generated)
When a meeting is approaching (30 min before):
1. Check prep-rules.json — does this meeting type need prep?
2. Search memory for recent interactions with attendees
3. Check email for recent threads with attendees
4. Check CRM for client details (if CRM skill active)
5. Generate prep doc:
   - Attendee context
   - Last interaction summary
   - Open items / action items
   - Suggested talking points
6. Send prep doc via configured channel

## Commands
- "What's my schedule today/tomorrow/this week?"
- "Am I free [day] at [time]?"
- "Prep for my [meeting name] meeting"
- "Move my [meeting] to [time]" (with confirmation)
- "Cancel [meeting]" (with confirmation)
```

### 3.4 Cron Jobs

```json5
// Morning briefing
{
  name: "Morning Schedule",
  schedule: { kind: "cron", expr: "0 7 * * 1-5", tz: "Europe/London" },
  payload: { kind: "agentTurn", message: "Generate today's schedule briefing. Include all calendar events, flag any conflicts, and note which meetings need prep docs." },
  sessionTarget: "isolated",
  delivery: { mode: "announce" },
}

// Pre-meeting prep (check every 15 min)
{
  name: "Meeting Prep Check",
  schedule: { kind: "cron", expr: "*/15 8-18 * * 1-5", tz: "Europe/London" },
  payload: { kind: "agentTurn", message: "Check calendar for meetings starting in the next 30 minutes that need prep docs. Generate prep for any that don't have one yet." },
  sessionTarget: "isolated",
  delivery: { mode: "announce" },
}
```

---

## Phase 4: CRM & Client Management Skill

### 4.1 Skill Overview

| Feature | Implementation |
|---------|---------------|
| CRM sync | HubSpot or Pipedrive API |
| Auto-logging | Log email/call interactions to CRM |
| Client health | Score based on recent activity |
| Follow-ups | Cron-based reminder system |
| Onboarding | Checklist automation for new clients |

### 4.2 Skill Structure

```
skills/crm-sync/
├── SKILL.md
├── scripts/
│   ├── hubspot-client.py    # HubSpot API wrapper
│   ├── pipedrive-client.py  # Pipedrive API wrapper
│   ├── health-scorer.py     # Client health algorithm
│   └── onboarding.py        # Onboarding checklist runner
├── config/
│   ├── crm-config.json      # CRM connection details
│   ├── health-rules.json    # Scoring criteria
│   └── onboarding-templates/ # Per-service-type checklists
└── README.md
```

### 4.3 SKILL.md

```markdown
---
name: crm_sync
description: CRM integration — sync contacts, log interactions, track client health, automate follow-ups and onboarding via HubSpot or Pipedrive.
---

# CRM Sync Skill

## Triggers
- **Webhook**: New deal created / deal stage changed
- **Cron**: Daily follow-up check (9:00 AM)
- **Cron**: Weekly client health review (Monday 8:00 AM)
- **Heartbeat**: Check for overdue follow-ups
- **Manual**: "Look up [client]" / "Log a call with [client]"

## Auto-Logging
When email skill detects client communication:
1. Match sender to CRM contact
2. Log interaction with summary
3. Update "last contact" timestamp
4. If deal is active, add note to deal timeline

## Client Health Scoring
Weekly cron generates health scores:
- Last contact recency (weight: 30%)
- Deal stage momentum (weight: 25%)
- Email response rate (weight: 20%)
- Meeting attendance (weight: 15%)
- Open task completion (weight: 10%)

Scores: 🟢 Healthy (>70) | 🟡 At Risk (40-70) | 🔴 Critical (<40)

## Follow-Up Engine
Daily at 9:00 AM:
1. Query CRM for deals with upcoming follow-up dates
2. Query overdue follow-ups
3. Generate follow-up suggestions with context
4. Send prioritised list to owner

## New Client Onboarding
When triggered (manual or webhook):
1. Load onboarding template for service type
2. Create CRM deal + contact (if not exists)
3. Send welcome email (draft, await approval)
4. Create task checklist in task tracker
5. Schedule kickoff call
6. Set follow-up reminders
7. Log all actions to memory

## Commands
- "Look up [client name/company]"
- "Log call with [client] about [topic]"
- "Client health report"
- "Start onboarding for [client] — [service type]"
- "Follow-up list"
- "Update [client] deal to [stage]"
```

---

## Phase 5: Task & Project Tracking Skill

### 5.1 Skill Overview

| Feature | Implementation |
|---------|---------------|
| Task creation | Natural language → Linear/Notion/Asana API |
| Deadline tracking | Cron-based reminders |
| Weekly reports | Auto-generated progress summaries |
| Standup generation | Daily standup from completed/in-progress tasks |
| Escalation | Alert on overdue/blocked items |

### 5.2 Skill Structure

```
skills/task-tracker/
├── SKILL.md
├── scripts/
│   ├── linear-client.py     # Linear API wrapper
│   ├── notion-client.py     # Notion API wrapper
│   ├── asana-client.py      # Asana API wrapper
│   └── report-generator.py  # Weekly report builder
├── config/
│   ├── tracker-config.json  # Which tool + project setup
│   └── report-template.md   # Report format
└── README.md
```

### 5.3 SKILL.md

```markdown
---
name: task_tracker
description: Task and project tracking — create tasks from natural language, track deadlines, generate standups and weekly reports via Linear, Notion, or Asana.
---

# Task Tracker Skill

## Triggers
- **Cron**: Daily standup summary (8:30 AM)
- **Cron**: Weekly progress report (Friday 4:00 PM)
- **Heartbeat**: Check for tasks due today / overdue
- **Manual**: "Add task: [description]" / "What's overdue?"

## Natural Language Task Creation
Parse commands like:
- "Remind me to follow up with Sarah on Friday" → Task: "Follow up with Sarah", Due: Friday
- "Add task: Review Q1 budget, high priority, due next Tuesday" → Task with priority + date
- "Block: waiting on client approval for the design" → Blocked task with reason

## Daily Standup (8:30 AM)
1. Fetch tasks completed yesterday
2. Fetch tasks in progress
3. Fetch blocked tasks
4. Generate standup format:
   - ✅ Done yesterday: [list]
   - 🔄 In progress: [list]
   - 🚫 Blocked: [list with reasons]
   - 📅 Due today: [list]

## Weekly Report (Friday 4:00 PM)
1. Tasks completed this week (with effort/time if tracked)
2. Tasks carried over
3. New tasks created
4. Velocity trend (tasks completed per week, 4-week average)
5. Recommendations (overloaded? under-committed?)

## Commands
- "Add task: [description]" (with optional priority, due date, project)
- "What's due today/this week?"
- "What's overdue?"
- "Mark [task] as done"
- "Block [task] — [reason]"
- "Weekly report"
- "Standup"
```

---

## Phase 6: Reporting & Intelligence Skill

### 6.1 Skill Overview

| Feature | Implementation |
|---------|---------------|
| Daily ops brief | Combines all skill data into one briefing |
| Weekly review | Business health summary |
| KPI tracking | Pull from connected tools |
| Anomaly detection | Flag unusual patterns |
| On-demand reports | "How was last week?" |

### 6.2 SKILL.md

```markdown
---
name: ops_reporting
description: Operational reporting — daily briefings, weekly reviews, KPI tracking, and anomaly detection combining data from all connected skills.
---

# Ops Reporting Skill

## Daily Ops Brief (configurable time, default 7:30 AM)
Combines data from all active skills:

### Email Section (if email-intel active)
- Unread count + urgent items
- Emails needing response
- Auto-handled count

### Calendar Section (if calendar-ops active)
- Today's schedule
- Prep status for meetings
- Free time blocks

### Tasks Section (if task-tracker active)
- Due today
- Overdue items
- Blocked items

### CRM Section (if crm-sync active)
- Follow-ups due
- Deals at risk
- New leads

### Summary
- Top 3 priorities for today
- Recommended actions
- Estimated time needed

## Weekly Business Review (Sunday evening or Monday morning)
1. Week-over-week metrics comparison
2. Client health dashboard
3. Task velocity + trends
4. Revenue/pipeline movement (if CRM connected)
5. Time allocation analysis
6. Recommendations for next week

## Anomaly Detection
Flag when:
- Email volume spikes >2x normal
- Client goes silent (no contact >2 weeks when usually weekly)
- Task completion rate drops significantly
- Calendar overbooked (>6 meetings/day)
- Follow-up missed for high-value deal

## Commands
- "Brief me" / "What's happening?"
- "How was last week?"
- "Client dashboard"
- "What needs my attention?"
```

---

## Phase 7: Documentation & Showcase

### 7.1 Deliverables

- [ ] **README.md** — Architecture diagram, feature list, "How to Run"
- [ ] **DEMO.md** — Scripted demo walkthrough for Loom recording
- [ ] **setup.sh** — One-command deployment
- [ ] **config-wizard.sh** — Interactive configuration (which channels, which CRM, etc.)
- [ ] **Loom video** — 5-min walkthrough showing the agent in action
- [ ] **Screenshots** — Daily briefing, email triage, meeting prep, CRM sync
- [ ] **Template library** — Pre-built configs for:
  - Solo consultant
  - Agency (5-15 people)
  - E-commerce operator
  - SaaS founder
  - Professional services (accountancy/legal)

### 7.2 Repository Structure

```
opsclaw/
├── README.md                    # Project overview + screenshots
├── SPEC.md                      # This document
├── DEMO.md                      # Demo script for Loom
├── LICENSE                      # MIT
├── setup.sh                     # One-command setup
├── config-wizard.sh             # Interactive config
├── docker-compose.yml           # Production deployment
├── workspace/                   # Template workspace
│   ├── AGENTS.md
│   ├── SOUL.md
│   ├── USER.md
│   ├── HEARTBEAT.md
│   ├── IDENTITY.md
│   ├── TOOLS.md
│   └── memory/
│       └── .gitkeep
├── skills/                      # Custom skills
│   ├── email-intel/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── config/
│   ├── calendar-ops/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── config/
│   ├── crm-sync/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── config/
│   ├── task-tracker/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── config/
│   └── ops-reporting/
│       ├── SKILL.md
│       ├── scripts/
│       └── config/
├── templates/                   # Client-type configs
│   ├── solo-consultant.json5
│   ├── agency.json5
│   ├── ecommerce.json5
│   ├── saas-founder.json5
│   └── professional-services.json5
├── docs/                        # Extended documentation
│   ├── setup-guide.md
│   ├── skill-customisation.md
│   ├── security-guide.md
│   ├── troubleshooting.md
│   └── api-integrations.md
└── scripts/                     # Utility scripts
    ├── backup.sh
    ├── health-check.sh
    └── migrate.sh
```

---

## Multi-Agent Architecture (Premium Tier)

For larger businesses, OpsClaw supports **department-level agents**:

```json5
{
  agents: {
    list: [
      { id: "ops", workspace: "~/.openclaw/workspace-ops", default: true },
      { id: "support", workspace: "~/.openclaw/workspace-support" },
      { id: "sales", workspace: "~/.openclaw/workspace-sales" },
    ],
  },
  bindings: [
    // Support queries from customers go to support agent
    { agentId: "support", match: { channel: "slack", peer: { id: "C_SUPPORT_CHANNEL" } } },
    // Sales channel goes to sales agent
    { agentId: "sales", match: { channel: "slack", peer: { id: "C_SALES_CHANNEL" } } },
    // Everything else → ops agent
  ],
}
```

Each agent has its own:
- Persona (SOUL.md) tailored to department
- Memory (separate operational context)
- Skills (support agent has ticket tracking; sales agent has pipeline tools)
- Channel bindings (right messages → right agent)

---

## Pricing Strategy

### Tier 1: Starter ($500)
- Single agent
- 1 channel (Telegram or Slack)
- Email intelligence skill
- Daily briefing cron
- Basic memory setup
- 1 hour setup call + deployment

### Tier 2: Professional ($1,500)
- Single agent
- 2-3 channels
- Email + Calendar + Task tracking skills
- CRM integration (HubSpot or Pipedrive)
- Ops reporting + weekly reviews
- Security hardening
- 2 hours setup + 1 month support

### Tier 3: Enterprise ($3,000-5,000)
- Multi-agent (up to 4 department agents)
- All channels
- All skills + custom skill development
- Docker Compose production deployment
- Tailscale networking
- Full security audit
- 4 hours setup + 3 months support

### Ongoing Support
- $300/month — bug fixes, config updates, new skill requests
- $500/month — above + monthly review call + optimisation
- $1,000/month — above + custom skill development + priority support

---

## Build Timeline

| Phase | Days | Deliverable |
|-------|------|-------------|
| 1. Core Infrastructure | 1-2 | Setup script, workspace templates, config, security |
| 2. Email Intelligence | 2-3 | Gmail webhook, triage, auto-drafts, daily briefing |
| 3. Calendar & Scheduling | 3-4 | GCal integration, briefings, meeting prep |
| 4. CRM Integration | 4-5 | HubSpot/Pipedrive sync, health scoring, follow-ups |
| 5. Task Tracking | 5-6 | Linear/Notion/Asana, standups, weekly reports |
| 6. Reporting | 6-7 | Combined briefings, anomaly detection, dashboards |
| 7. Docs & Showcase | 7-8 | README, Loom, templates, config wizard |

**Total: 8 working days to portfolio-ready.**

---

## Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Orchestration | OpenClaw | The whole point |
| AI Model | Claude Sonnet (default), configurable | Best reasoning-to-cost ratio |
| Email | Gmail API + Pub/Sub | Native OpenClaw support |
| Calendar | Google Calendar API | Most common, good API |
| CRM | HubSpot / Pipedrive APIs | Most popular SMB CRMs |
| Tasks | Linear / Notion / Asana APIs | Client's choice |
| Hosting | VPS + Docker Compose | Always-on, isolated |
| Networking | Tailscale | Zero-config VPN, secure |
| Channels | Telegram + Slack (primary) | Most business-friendly |

---

## Success Metrics (Portfolio)

To demonstrate value, each demo should show:
- **Time saved:** "This agent handles 2+ hours of daily ops work"
- **Response time:** "Urgent emails flagged in <5 minutes vs hours"
- **Zero missed follow-ups:** "CRM follow-ups never slip through"
- **Briefing quality:** "One message tells you everything you need to know"
- **Security:** "Sandboxed, encrypted, your data never leaves your server"

---

## Next Steps

1. ✅ Spec written (this document)
2. ⬜ Codex review + adjustments
3. ⬜ Create project structure
4. ⬜ Build Phase 1 (core infrastructure)
5. ⬜ Build Phase 2 (email intelligence)
6. ⬜ Build Phase 3 (calendar)
7. ⬜ Build Phase 4 (CRM)
8. ⬜ Build Phase 5 (tasks)
9. ⬜ Build Phase 6 (reporting)
10. ⬜ Build Phase 7 (docs + showcase)
11. ⬜ Record Loom demo
12. ⬜ Publish to GitHub
13. ⬜ Add to Upwork portfolio
