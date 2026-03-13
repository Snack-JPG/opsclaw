# Ops Reporting Skill

This skill adds cross-system reporting and operational intelligence to OpsClaw. It combines normalized data from email, calendar, tasks, and CRM into one daily briefing, generates weekly business reviews, tracks KPI trends, detects anomalies, and formats reports for different delivery channels.

## Files
- `SKILL.md`: agent operating instructions
- `scripts/daily_brief.py`: unified daily ops briefing generator
- `scripts/weekly_review.py`: weekly business review builder
- `scripts/anomaly_detector.py`: deterministic anomaly detection engine
- `scripts/kpi_tracker.py`: KPI calculation, trend, and threshold tracker
- `scripts/report_formatter.py`: report formatter for Markdown, plain text, Slack, and Telegram
- `config/kpi-config.json`: KPI definitions, thresholds, and rollup settings
- `config/anomaly-rules.json`: anomaly rules and sensitivity controls
- `config/brief-template.md`: Markdown template for the daily ops brief

## Prerequisites
- `python3` installed locally
- Normalized source data from one or more active OpsClaw skills:
  - email metrics or classified inbox snapshots
  - calendar summaries or event aggregates
  - task snapshots or weekly velocity data
  - CRM follow-up, health, and pipeline metrics

The bundled scripts use the Python standard library only.

## Quick Start
1. Review the KPI definitions:

```bash
$EDITOR skills/ops-reporting/config/kpi-config.json
```

2. Review the anomaly rules:

```bash
$EDITOR skills/ops-reporting/config/anomaly-rules.json
```

3. Generate a daily brief from a normalized payload:

```bash
python3 skills/ops-reporting/scripts/daily_brief.py \
  --input /tmp/ops-brief-input.json \
  --template skills/ops-reporting/config/brief-template.md
```

4. Generate a weekly review:

```bash
python3 skills/ops-reporting/scripts/weekly_review.py \
  --input /tmp/ops-weekly-input.json
```

5. Run anomaly detection:

```bash
python3 skills/ops-reporting/scripts/anomaly_detector.py \
  --input /tmp/ops-anomaly-input.json \
  --rules skills/ops-reporting/config/anomaly-rules.json
```

6. Track KPIs:

```bash
python3 skills/ops-reporting/scripts/kpi_tracker.py \
  --input /tmp/ops-kpi-input.json \
  --config skills/ops-reporting/config/kpi-config.json
```

7. Convert a generated report to Slack blocks:

```bash
python3 skills/ops-reporting/scripts/report_formatter.py \
  --input /tmp/daily-brief-output.json \
  --format slack_blocks
```

## Daily Brief Input
`daily_brief.py` expects a normalized document like this:

```json
{
  "generatedAt": "2026-03-13T07:30:00Z",
  "date": "2026-03-13",
  "timezone": "Europe/London",
  "email": {
    "unreadCount": 14,
    "urgentCount": 2,
    "autoHandledCount": 5,
    "needsResponse": [
      {"from": "Acme", "subject": "Renewal question", "urgency": "high", "summary": "Needs pricing clarification."}
    ],
    "urgentItems": [
      {"from": "VIP Client", "subject": "Contract blocker", "summary": "Signature stalled pending legal answer."}
    ]
  },
  "calendar": {
    "eventCount": 5,
    "meetings": [
      {"title": "Acme weekly sync", "start": "09:00", "end": "09:30", "prepStatus": "ready"}
    ],
    "freeBlocks": ["11:30-13:00"],
    "conflicts": []
  },
  "tasks": {
    "dueTodayCount": 3,
    "overdueCount": 1,
    "blockedCount": 1,
    "dueToday": [{"title": "Send Q1 recap", "priority": "high"}],
    "overdue": [{"title": "Finalize proposal", "ageDays": 2}],
    "blocked": [{"title": "Launch page", "blockReason": "Waiting on copy"}],
    "completedLast7Days": 12
  },
  "crm": {
    "followUpsDueCount": 4,
    "atRiskClientCount": 1,
    "followUpsDue": [{"client": "Acme", "daysOverdue": 1, "recommendedAction": "Send proposal follow-up"}],
    "atRiskClients": [{"name": "Northstar", "healthScore": 46, "reason": "No contact in 18 days"}],
    "pipeline": {"openValue": 48000, "weightedValue": 27000, "wonThisWeek": 0}
  }
}
```

## Weekly Review Input
`weekly_review.py` expects current and previous-week rollups. A minimal example:

```json
{
  "periodStart": "2026-03-09",
  "periodEnd": "2026-03-15",
  "currentWeek": {
    "email": {"received": 82, "urgent": 7, "responseDue": 14},
    "calendar": {"meetings": 19, "meetingHours": 14.5, "prepReadyRate": 0.84},
    "tasks": {"completed": 18, "created": 21, "overdue": 3, "blocked": 2},
    "crm": {
      "healthyClients": 9,
      "atRiskClients": 2,
      "criticalClients": 1,
      "followUpsDue": 5,
      "pipelineValue": 62000,
      "weightedPipelineValue": 41000,
      "wonValue": 8000
    }
  },
  "previousWeek": {
    "email": {"received": 64, "urgent": 5, "responseDue": 11},
    "calendar": {"meetings": 15, "meetingHours": 11.0, "prepReadyRate": 0.9},
    "tasks": {"completed": 22, "created": 18, "overdue": 1, "blocked": 1},
    "crm": {
      "healthyClients": 10,
      "atRiskClients": 1,
      "criticalClients": 0,
      "followUpsDue": 2,
      "pipelineValue": 70000,
      "weightedPipelineValue": 45000,
      "wonValue": 12000
    }
  }
}
```

## Anomaly Detection Input
`anomaly_detector.py` reads current metrics and a short baseline history:

```json
{
  "current": {
    "emailVolume": 48,
    "taskCompletionCount": 2,
    "meetingCount": 8,
    "missedFollowUps": 2,
    "clients": [
      {"name": "Acme", "daysSinceContact": 17, "expectedCadenceDays": 7, "tier": "vip"}
    ]
  },
  "history": {
    "emailVolume": [18, 20, 22, 21, 19],
    "taskCompletionCount": [7, 6, 8, 7, 6],
    "meetingCount": [3, 4, 5, 4, 3]
  }
}
```

## KPI Tracking Input
`kpi_tracker.py` expects current metrics plus optional history:

```json
{
  "generatedAt": "2026-03-13T07:30:00Z",
  "metrics": {
    "inbox_response_due": 14,
    "urgent_email_backlog": 2,
    "tasks_completed_week": 18,
    "tasks_overdue": 3,
    "crm_followups_due": 5,
    "at_risk_clients": 2,
    "calendar_meeting_hours_week": 14.5,
    "weighted_pipeline_value": 41000
  },
  "history": {
    "inbox_response_due": [11, 12, 13, 14],
    "tasks_completed_week": [22, 19, 20, 18]
  }
}
```

## Operational Notes
- Keep source data normalized and provider-agnostic before it reaches this skill.
- Use KPI tracking and anomaly detection together: KPIs show persistent health, anomalies catch abrupt change.
- Markdown is the canonical output; use `report_formatter.py` for channel-specific transport layers.
- If one source system is stale or missing, keep generating the report and state the gap explicitly.

## Verification Checklist
- Run `daily_brief.py` with mixed email, calendar, task, and CRM data and confirm the top priorities are sensible.
- Run `weekly_review.py` with current and previous-week inputs and confirm week-over-week deltas match expectations.
- Feed `anomaly_detector.py` a `2x` email spike and confirm it fires.
- Feed `kpi_tracker.py` values across healthy, warning, and critical thresholds and confirm statuses are correct.
- Convert the same report through all formatter modes and confirm the content remains intact.
