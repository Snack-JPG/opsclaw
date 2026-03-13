---
name: ops_reporting
description: Reporting and intelligence for OpsClaw: generate unified daily ops briefs, weekly business reviews, KPI trend reports, and anomaly alerts by combining email, calendar, CRM, and task data.
---

# Ops Reporting Skill

Use this skill whenever the user asks for a combined operational summary, weekly business review, KPI status, anomaly scan, client dashboard, or an on-demand briefing such as `Brief me`, `What needs my attention?`, or `How was last week?`. It also applies to scheduled morning briefs, weekly reviews, and heartbeat-level anomaly monitoring when multiple OpsClaw skills are enabled.

## Load Order
1. Read `workspace/SOUL.md`, `workspace/USER.md`, `workspace/AGENTS.md`, `workspace/ops-state.json`, and `workspace/heartbeat-state.json`.
2. Read today's memory note in `workspace/memory/YYYY-MM-DD.md` and yesterday's note when the current summary depends on unresolved context.
3. Read this skill's config before generating reports or alerts:
   - `config/kpi-config.json`
   - `config/anomaly-rules.json`
   - `config/brief-template.md`
4. Use the bundled scripts for deterministic work:
   - `scripts/daily_brief.py`
   - `scripts/weekly_review.py`
   - `scripts/anomaly_detector.py`
   - `scripts/kpi_tracker.py`
   - `scripts/report_formatter.py`

## Triggers
- `Cron`: daily ops brief at the configured morning briefing time, default `7:30 AM` local timezone.
- `Cron`: weekly business review every Sunday evening or Monday morning per configuration.
- `Heartbeat`: anomaly detection sweep, stale-metric scan, and reporting subsystem health check.
- `Manual`: commands such as `Brief me`, `What's happening?`, `How was last week?`, `Client dashboard`, `KPI status`, or `What needs my attention?`.

## Core Responsibilities
- Combine normalized outputs from `email-intel`, `calendar-ops`, `task-tracker`, and `crm-sync` into one owner-facing briefing.
- Generate weekly business reviews with week-over-week comparisons for activity, client health, task throughput, pipeline, and time allocation.
- Track KPI values against thresholds and historical baselines with explicit status, trend, and alerting output.
- Detect operational anomalies such as volume spikes, client silence, completion drops, calendar overload, and missed follow-ups.
- Return concise recommendations that make the next action obvious rather than just listing data.
- Update reporting timestamps in workspace state when reports complete successfully.

## Daily Ops Brief
Run `scripts/daily_brief.py` with normalized payloads from the active skills.

Required sections when data exists:
- email: unread count, urgent items, response queue, and auto-handled volume
- calendar: today's meetings, prep status, conflicts, and material free blocks
- tasks: due today, overdue, blocked, and velocity signals
- crm: follow-ups due, at-risk clients, and notable pipeline movement
- summary: top priorities, recommendations, and estimated focus load

Rules:
- Degrade gracefully when one or more skills are unavailable; say which source is missing.
- Lead with attention items, not raw counts.
- Keep the brief skimmable enough for a morning readout or chat delivery.
- Support on-demand `Brief me` generation from current state without needing the scheduled run context.

## Weekly Business Review
Run `scripts/weekly_review.py` once per review window or on demand.

The review must include:
1. week-over-week metric comparison
2. client health dashboard summary
3. task velocity and carry-over trend
4. revenue or pipeline movement when CRM revenue data exists
5. time allocation and meeting-load analysis when calendar data exists
6. recommendations for the next week

Rules:
- Compare against at least the previous week when available.
- If historical baselines are missing, mark the insight as lower confidence instead of inventing a trend.
- Surface adverse movement first: declining task throughput, rising overdue work, deteriorating client health, shrinking pipeline, or meeting overload.

## KPI Tracking
Run `scripts/kpi_tracker.py` using `config/kpi-config.json`.

Expected KPI families:
- inbox responsiveness
- task execution
- client health and follow-up hygiene
- meeting load
- pipeline or revenue metrics

Output for each KPI:
- current value
- target or threshold
- status: `healthy`, `warning`, or `critical`
- trend versus baseline
- alert text when the configured threshold is breached

## Anomaly Detection
Run `scripts/anomaly_detector.py` using `config/anomaly-rules.json`.

Default anomaly classes:
- email volume spikes above baseline
- client silence beyond expected cadence
- task completion rate drops
- calendar overload or excessive meeting density
- missed follow-ups for high-value clients or deals

Rules:
- Prefer deterministic thresholds over vague language.
- Include why the anomaly fired and the source metric used.
- Avoid duplicate alerts when the same anomaly remains active; summarize persistence when needed.

## Output Formatting
Use `scripts/report_formatter.py` when the result needs channel-specific output.

Supported formats:
- `markdown`
- `plain_text`
- `slack_blocks`
- `telegram_html`

Formatting rules:
- Markdown is the canonical human-readable output.
- Slack output should use section and context blocks only; keep it compact.
- Telegram HTML should use safe tags only: `b`, `i`, `code`, `a`.
- If a formatter cannot represent a section cleanly, fall back to plain text rather than dropping content.

## Manual Commands
- `Brief me`
  - Generate the current daily ops brief from active skill state.
- `What's happening?`
  - Return an attention-first variant of the current brief.
- `How was last week?`
  - Generate the weekly business review for the most recent full week.
- `Client dashboard`
  - Summarize client health, follow-up risk, and pipeline signals from the weekly review inputs.
- `What needs my attention?`
  - Return active anomalies, critical KPIs, and same-day action items.
- `KPI status`
  - Run the KPI tracker and surface threshold breaches and notable changes.

## Approval Policy
- Briefings, weekly reviews, KPI reports, and anomaly scans are `internal_brief` and execute immediately.
- Formatting reports for Slack, Telegram, or Markdown is `internal_format` and executes immediately.
- This skill never sends external communications on its own.
- If a recommendation implies a write action in another system, the downstream skill's approval policy still applies.

## Reliability and Observability
- Use normalized JSON in and JSON out between scripts.
- Prefer deterministic calculations over narrative-only summarization.
- Apply bounded retry-with-backoff to upstream fetches when this skill owns them.
- Return degraded status explicitly when an input source is missing or stale.
- Capture exhausted failures in `workspace/memory/dead-letters/YYYY-MM-DD.json`.
- Log report type, source availability, anomalies detected, and threshold breaches with sanitized context.

## Setup and References
- Human setup instructions live in `README.md`.
- KPI definitions and thresholds live in `config/kpi-config.json`.
- Anomaly rules and sensitivity settings live in `config/anomaly-rules.json`.
- Daily brief rendering defaults live in `config/brief-template.md`.

## Acceptance Standard
This skill is considered healthy when:
- the daily ops brief combines all active sources into one coherent summary
- the weekly review includes week-over-week comparisons and recommendations
- KPI tracking reports threshold breaches with explicit status and trend
- anomaly detection catches a test `2x` email-volume spike
- `Brief me` produces a current state summary without manual cleanup
