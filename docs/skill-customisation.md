# Skill Customisation Guide

OpsClaw skills are structured so you can adapt them for a client without rewriting the whole platform. This guide covers how to customise safely and how to add a new skill that fits the existing operating model.

## Design Rules

- Keep reads and writes separate.
- Prefer deterministic scripts for transformations, scoring, and normalization.
- Queue external writes for approval unless the action is explicitly safe.
- Use config files for client-specific behavior before changing code.
- Keep normalized output shapes stable so `ops-reporting` can reuse them.

## Skill Structure

Each skill follows the same pattern:

```text
skills/<skill-name>/
├── SKILL.md
├── README.md
├── config/
└── scripts/
```

- `SKILL.md` contains the operating instructions the agent follows.
- `README.md` explains setup, commands, and verification.
- `config/` stores provider config, rules, thresholds, and templates.
- `scripts/` stores deterministic helpers or API wrappers.

## Where To Customise First

### 1. Configuration

Change the files under each skill's `config/` directory before editing code. Examples:

- `skills/email-intel/config/rules.json`
- `skills/calendar-ops/config/prep-rules.json`
- `skills/crm-sync/config/health-rules.json`
- `skills/task-tracker/config/tracker-config.json`
- `skills/ops-reporting/config/kpi-config.json`

This is the right place to tune:

- thresholds
- categories
- provider selection
- templates
- escalation rules
- output defaults

### 2. Workspace policy

If the client needs different behavior, update the workspace files:

- [workspace/SOUL.md](/Users/austin/Desktop/opsclaw/workspace/SOUL.md)
- [workspace/AGENTS.md](/Users/austin/Desktop/opsclaw/workspace/AGENTS.md)
- [workspace/HEARTBEAT.md](/Users/austin/Desktop/opsclaw/workspace/HEARTBEAT.md)
- [workspace/TOOLS.md](/Users/austin/Desktop/opsclaw/workspace/TOOLS.md)

Use these for:

- tone and persona
- escalation policy
- approval rules
- quiet hours
- heartbeat expectations

### 3. Scripts

Only update scripts when the required behavior cannot be expressed in config. Keep script interfaces stable and document any new arguments in the skill README.

## Creating A Custom Skill

### Step 1: Create the directory

Use the same layout as the existing skills:

```text
skills/customer-support/
├── SKILL.md
├── README.md
├── config/
└── scripts/
```

### Step 2: Write `SKILL.md`

Define:

- what systems the skill reads from
- what actions it may take automatically
- what actions require approval
- what state files it updates
- what success and failure look like

Keep the instructions concrete. Avoid vague prompts.

### Step 3: Add deterministic helpers

Put parsing, scoring, formatting, or provider wrapper code in `scripts/`. Follow the existing pattern:

- input via flags and JSON files
- output as JSON or Markdown
- no hidden side effects
- clear non-zero exit codes on failure

### Step 4: Add client-tunable config

Put thresholds, provider settings, templates, and mappings in `config/`. This is what makes the skill reusable across deployments.

### Step 5: Document setup and verification

In `README.md`, include:

- prerequisites
- environment variables
- setup steps
- example commands
- verification checklist

### Step 6: Wire it into templates or config

Enable the skill in `workspace/config.json5` or in one of the template files under `templates/`.

Example:

```json5
skills: {
  entries: {
    "customer-support": { enabled: true }
  }
}
```

## Customisation Patterns

### Provider swaps

Several skills already abstract multiple providers. Extend those first instead of forking logic:

- `crm-sync`: HubSpot or Pipedrive
- `task-tracker`: Linear, Notion, or Asana

If you add a new provider, keep the normalized output shape identical so reporting and standups still work.

### Client-specific templates

Start from an existing client template in `templates/` and adjust:

- channels
- timezone
- enabled skills
- approval defaults
- briefing cadence

This is usually faster and safer than building config by hand.

### Reporting extensions

If a custom skill emits business-critical output, define a normalized JSON payload and feed it into `ops-reporting`. Do not hardwire provider-specific report logic into the reporting skill unless the output truly belongs there.

## Testing Checklist

- Validate shell scripts with `bash -n`.
- Validate Python modules with `python3 -m compileall scripts skills`.
- Test the happy path and one degraded path.
- Confirm duplicate events do not create duplicate actions.
- Confirm explicit approval actions never auto-execute.
- Confirm docs and examples match the actual command flags.

## Anti-Patterns

- Hard-coding secrets in config files.
- Mixing provider-specific payloads into cross-skill reports.
- Auto-sending external communications without an explicit policy change.
- Adding business logic only in prompts when it should be deterministic in code or config.
- Editing `workspace/USER.md` to hold secrets or mutable state.

## Recommended Workflow

1. Copy the closest existing skill or config pattern.
2. Add the smallest useful customization.
3. Test with sample JSON before connecting live APIs.
4. Update docs at the same time as the implementation.
5. Run [scripts/health-check.sh](/Users/austin/Desktop/opsclaw/scripts/health-check.sh) before shipping changes to a client deployment.
