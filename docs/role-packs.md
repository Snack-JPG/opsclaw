# Role Packs

Role packs are reusable deployment profiles for multi-agent OpsClaw setups. Each role pack defines one agent's skill surface, operating persona, briefing cadence, approval posture, and example commands.

## Built-in role packs

- `founder`: full-stack operating partner with daily brief, weekly review, and anomaly detection
- `sales`: pipeline, CRM, follow-ups, and meeting prep
- `support`: ticket triage, client history, SLA tracking, and response drafts
- `admin`: scheduling, onboarding checklists, and document chasing
- `finance`: invoice follow-up, expense alerts, reporting, and finance document collection
- `marketing`: campaigns, social monitoring, KPI reporting, and lead scoring

## Role pack file shape

Each JSON file under `role-packs/` includes:

- `role`, `display_name`, `description`
- `enabled_skills`
- `skill_overrides`
- `persona.soul_md`
- `heartbeat.heartbeat_md`
- `briefing`
- `approval_policy`
- `channel_preferences`
- `example_commands`

## Creating a custom role pack

1. Copy one of the JSON files in `role-packs/`.
2. Change the role metadata and description so the deployment purpose is explicit.
3. Keep `enabled_skills` limited to the skills that role should actually use.
4. Add `skill_overrides` for role-specific categories, KPI focus, thresholds, or workflow preferences.
5. Write role-specific `SOUL.md` and `HEARTBEAT.md` text inside the JSON so the deployed workspace has the correct behaviour from day one.
6. Set briefing schedule, approval policy, channel preferences, and example commands.
7. Deploy it with `scripts/deploy-role.py --role-pack /path/to/custom-role.json ...`.

## Single-role deployment

```bash
python3 scripts/deploy-role.py \
  --role founder \
  --company "Acme Corp" \
  --user "Jane Smith" \
  --channel telegram \
  --crm hubspot \
  --output ./deployments/acme-founder
```

The generated workspace includes:

- customised `SOUL.md`, `AGENTS.md`, `HEARTBEAT.md`, `USER.md`, and `IDENTITY.md`
- `config.json5` with role bindings and enabled skills
- only the relevant skill folders plus the onboarding skill
- role metadata in `role-pack.json`
- fresh `memory/`, `ops-state.json`, and `heartbeat-state.json`

## Multi-role company deployment

```bash
python3 scripts/deploy-company.py \
  --config templates/company-config.json \
  --output ./deployments/acme
```

This creates:

- `roles/<role>/` workspaces for each configured role
- `shared/client-db.json` for shared account context
- `channel-bindings.json` for message routing
- `deployment-manifest.json` for the full generated topology
- a root `docker-compose.yml` with one service per role agent

## Notes

- The generated workspaces keep external writes approval-gated.
- Financial actions remain blocked across all built-in role packs.
- The onboarding skill is included automatically so first-week adoption can be guided per role.
