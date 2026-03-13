---
name: onboarding
description: Guided first-week onboarding for newly deployed OpsClaw role agents. Use when the user asks for onboarding flows, first-week guidance, activation messages, or role-specific “how to use this agent” sequences after deployment.
---

# Onboarding

Use this skill during the first week after a role-pack deployment or when the user asks how the new agent should introduce itself.

## Workflow

1. Read `config/onboarding-config.json` for the role-specific onboarding schedule and tip selection.
2. Read `scripts/tips.json` only for the skills that are enabled in the role.
3. Generate or preview the message for the requested day with:

```bash
python3 skills/onboarding/scripts/onboarding_flow.py --role founder --day 0 --company "Acme Corp" --user "Jane Smith"
```

## Rules

- Keep onboarding messages short and concrete.
- Teach one behaviour per day.
- Reuse the role pack's enabled skills and example commands where possible.
- Do not promise autonomous actions that the approval policy blocks.
- Day 7 should collect feedback and confirm the weekly review rhythm.
