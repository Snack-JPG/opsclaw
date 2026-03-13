# Task Tracker Skill

This skill adds provider-backed task tracking, deadline monitoring, standups, and weekly reporting to OpsClaw using Linear, Notion, or Asana.

## Files
- `SKILL.md`: agent operating instructions
- `scripts/linear-client.py`: Linear GraphQL API wrapper and CLI
- `scripts/notion-client.py`: Notion API wrapper and CLI
- `scripts/asana-client.py`: Asana REST API wrapper and CLI
- `scripts/nl_parser.py`: natural-language task parser
- `scripts/standup.py`: daily standup generator from normalized task JSON
- `scripts/report-generator.py`: weekly report builder with velocity analysis
- `config/tracker-config.json`: provider selection and connection template
- `config/report-template.md`: Markdown report template

## Prerequisites
- `python3` installed locally
- One configured task provider:
  - Linear workspace with personal API key
  - Notion integration with task database access
  - Asana workspace with personal access token

The bundled scripts use the Python standard library only.

## Quick Start
1. Edit the tracker config template:

```bash
$EDITOR skills/task-tracker/config/tracker-config.json
```

2. Set `"provider"` to `linear`, `notion`, or `asana`.

3. Export credentials for the selected provider:
- Linear: `LINEAR_API_KEY`
- Notion: `NOTION_API_TOKEN`
- Asana: `ASANA_ACCESS_TOKEN`

4. Test connectivity with one of the provider CLIs below.

## Linear Setup
1. In Linear, open `Settings -> API -> Personal API keys`.
2. Create a key and export it:

```bash
export LINEAR_API_KEY="lin_api_..."
```

3. Configure team and project defaults in `tracker-config.json`.

4. Test issue listing:

```bash
python3 skills/task-tracker/scripts/linear-client.py list-issues \
  --config skills/task-tracker/config/tracker-config.json \
  --limit 10
```

### Common Linear Commands
```bash
python3 skills/task-tracker/scripts/linear-client.py create-issue \
  --config skills/task-tracker/config/tracker-config.json \
  --title "Review Q1 budget" \
  --due-date 2026-03-17 \
  --priority high
```

```bash
python3 skills/task-tracker/scripts/linear-client.py search-issues \
  --config skills/task-tracker/config/tracker-config.json \
  --query "budget"
```

## Notion Setup
1. Create or reuse a Notion integration and copy the internal integration token.
2. Share the tasks database with that integration.
3. Export the token:

```bash
export NOTION_API_TOKEN="secret_..."
```

4. Set the database ID and property mapping in `tracker-config.json`.

5. Test database access:

```bash
python3 skills/task-tracker/scripts/notion-client.py query-database \
  --config skills/task-tracker/config/tracker-config.json \
  --limit 10
```

### Common Notion Commands
```bash
python3 skills/task-tracker/scripts/notion-client.py create-task \
  --config skills/task-tracker/config/tracker-config.json \
  --title "Follow up with Sarah" \
  --due-date 2026-03-20 \
  --priority medium
```

```bash
python3 skills/task-tracker/scripts/notion-client.py update-task \
  --config skills/task-tracker/config/tracker-config.json \
  --page-id <page-id> \
  --status Done
```

## Asana Setup
1. In Asana, create a personal access token with task and project access.
2. Export it:

```bash
export ASANA_ACCESS_TOKEN="..."
```

3. Set workspace, project, and section defaults in `tracker-config.json`.

4. Test project access:

```bash
python3 skills/task-tracker/scripts/asana-client.py list-tasks \
  --config skills/task-tracker/config/tracker-config.json \
  --limit 10
```

### Common Asana Commands
```bash
python3 skills/task-tracker/scripts/asana-client.py create-task \
  --config skills/task-tracker/config/tracker-config.json \
  --title "Prepare weekly standup" \
  --due-date 2026-03-13 \
  --priority high
```

```bash
python3 skills/task-tracker/scripts/asana-client.py list-sections \
  --config skills/task-tracker/config/tracker-config.json
```

## Natural Language Parsing
Parse free text into a structured task payload:

```bash
python3 skills/task-tracker/scripts/nl_parser.py \
  --text "Add task: Review Q1 budget, high priority, due next Tuesday, assign to Alex"
```

The parser returns JSON with extracted title, due date, priority, assignee, project, labels, status, and confidence notes.

## Standup Generation
Build a standup from a normalized task snapshot:

```bash
python3 skills/task-tracker/scripts/standup.py \
  --input /tmp/tasks-standup.json
```

Expected input shape:

```json
{
  "date": "2026-03-13",
  "completedYesterday": [
    {"title": "Ship onboarding checklist"}
  ],
  "inProgress": [
    {"title": "Review Q1 budget", "priority": "high"}
  ],
  "blocked": [
    {"title": "Launch landing page", "blockReason": "Waiting on legal approval"}
  ],
  "dueToday": [
    {"title": "Send client recap"}
  ],
  "overdue": []
}
```

## Weekly Reports
Generate a weekly report from normalized input:

```bash
python3 skills/task-tracker/scripts/report-generator.py \
  --input /tmp/tasks-weekly.json \
  --template skills/task-tracker/config/report-template.md
```

Expected input shape:

```json
{
  "periodStart": "2026-03-09",
  "periodEnd": "2026-03-13",
  "completed": [{"title": "Ship onboarding checklist"}],
  "carriedOver": [{"title": "Finalize pricing page", "ageDays": 8}],
  "created": [{"title": "Review Q1 budget"}],
  "dueNextWeek": [{"title": "Client health review", "dueDate": "2026-03-18"}],
  "history": [
    {"weekStart": "2026-02-16", "completedCount": 7},
    {"weekStart": "2026-02-23", "completedCount": 6},
    {"weekStart": "2026-03-02", "completedCount": 9},
    {"weekStart": "2026-03-09", "completedCount": 5}
  ]
}
```

## Operational Notes
- Keep provider credentials in environment variables, not committed into JSON config.
- The provider clients normalize output so standup and reporting can stay provider-agnostic.
- Use `nl_parser.py` before creating tasks from free text so due dates and priorities are deterministic.
- Overdue and blocked work should be surfaced in heartbeat checks even when no report is requested.

## Verification Checklist
- Parse `Add task: X by Friday` and confirm the due date resolves correctly.
- Create a test task in the configured provider and verify it appears in provider UI.
- Update a task to done and confirm completion state matches the provider.
- Run `standup.py` and confirm each section renders correctly, including blocked reasons.
- Run `report-generator.py` and confirm velocity and recommendations match the sample input.
