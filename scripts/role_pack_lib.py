#!/usr/bin/env python3
"""Shared helpers for OpsClaw role-pack deployment scripts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_TEMPLATE = ROOT / "workspace"
SKILLS_DIR = ROOT / "skills"
ROLE_PACKS_DIR = ROOT / "role-packs"

VALID_SKILLS = {
    "email-intel",
    "calendar-ops",
    "crm-sync",
    "task-tracker",
    "ops-reporting",
    "drive-docs",
    "onboarding",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def role_pack_path(role: str) -> Path:
    return ROLE_PACKS_DIR / f"{role}.json"


def load_role_pack(role: str | None = None, role_pack_path_value: str | None = None) -> dict[str, Any]:
    if role_pack_path_value:
        path = Path(role_pack_path_value).resolve()
    elif role:
        path = role_pack_path(role)
    else:
        raise ValueError("Either role or role_pack_path_value must be provided.")
    if not path.exists():
        raise FileNotFoundError(f"Role pack not found: {path}")
    data = load_json(path)
    enabled = set(data.get("enabled_skills", []))
    unknown = sorted(enabled - VALID_SKILLS)
    if unknown:
        raise ValueError(f"Role pack {path.name} includes unknown skills: {', '.join(unknown)}")
    return data


def reset_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def copy_workspace_template(output_dir: Path) -> None:
    shutil.copytree(WORKSPACE_TEMPLATE, output_dir, dirs_exist_ok=True)
    (output_dir / "memory").mkdir(exist_ok=True)
    (output_dir / "memory" / "dead-letters").mkdir(parents=True, exist_ok=True)


def copy_enabled_skills(output_dir: Path, enabled_skills: list[str]) -> None:
    target = output_dir / "skills"
    target.mkdir(exist_ok=True)
    for skill_name in enabled_skills:
        source = SKILLS_DIR / skill_name
        if not source.exists():
            raise FileNotFoundError(f"Skill folder not found: {source}")
        shutil.copytree(source, target / skill_name, dirs_exist_ok=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def quote_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def to_json5(value: Any, indent: int = 0) -> str:
    spacer = " " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for key, item in value.items():
            lines.append(f"{spacer}  {quote_json(key)}: {to_json5(item, indent + 2)},")
        lines.append(f"{spacer}}}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for item in value:
            lines.append(f"{spacer}  {to_json5(item, indent + 2)},")
        lines.append(f"{spacer}]")
        return "\n".join(lines)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return quote_json(value)


def write_json5(path: Path, data: dict[str, Any]) -> None:
    path.write_text(to_json5(data) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-")


def build_user_md(
    company: str,
    user: str,
    role_pack: dict[str, Any],
    channel: str,
    crm: str,
    timezone: str,
) -> str:
    approval = role_pack["approval_policy"]
    briefing = role_pack["briefing"]
    commands = "\n".join(f"- `{command}`" for command in role_pack["example_commands"])
    enabled_skills = "\n".join(f"- `{skill}`" for skill in role_pack["enabled_skills"])
    return f"""# USER.md — {role_pack['display_name']} Deployment Profile

## Business Snapshot
- Company: `{company}`
- Role pack: `{role_pack['role']}`
- Agent purpose: `{role_pack['description']}`
- Timezone of truth: `{timezone}`

## Operator
- Name: `{user}`
- Role: `{role_pack['display_name']}`
- Primary contact channel: `{channel}`
- CRM: `{crm}`
- Preferred briefing style: `{briefing['format_preferences']['style']}`

## Enabled Skills
{enabled_skills}

## Briefing Schedule
- Morning: `{briefing['schedule']['morning']}`
- End of day: `{briefing['schedule']['end_of_day']}`
- Weekly: `{briefing['schedule']['weekly']}`

## Approval Policy
### Execute immediately
{chr(10).join(f"- `{item}`" for item in approval['execute_immediately'])}

### Queue for approval
{chr(10).join(f"- `{item}`" for item in approval['queue_for_approval'])}

### Always block
{chr(10).join(f"- `{item}`" for item in approval['always_block'])}

## Example Commands
{commands}
"""


def build_agents_md(role_pack: dict[str, Any], company: str, user: str, channel: str) -> str:
    enabled_skills = ", ".join(f"`{skill}`" for skill in role_pack["enabled_skills"])
    notes = "\n".join(f"- {note}" for note in role_pack["approval_policy"].get("notes", []))
    return f"""# AGENTS.md — {role_pack['display_name']} Operating Instructions

This workspace runs a role-specific OpsClaw agent for `{company}`. The named operator is `{user}` and the default human channel is `{channel}`.

## Session Bootstrap
1. Read `SOUL.md` for role tone and decision style.
2. Read `USER.md` for deployment details, approvals, and command patterns.
3. Read `IDENTITY.md` for shared-state and routing constraints.
4. Read today's `memory/YYYY-MM-DD.md` and current `ops-state.json`.
5. Read `HEARTBEAT.md` when this run is scheduled or recovering from drift.

## Active Skill Surface
Use only the enabled skills for this role: {enabled_skills}.

## Role Operating Rules
- Prioritise work according to the role-pack objective: {role_pack['description']}
- Keep shared client context in `client-db.json` accurate and readable for the other role agents.
- Escalate any request that exceeds the approval policy or creates external risk.
- Package owner decisions so they can be approved quickly in one message.

## Approval Notes
{notes if notes else "- Use the default explicit-approval model for all consequential external actions."}
"""


def build_identity_md(
    role_pack: dict[str, Any],
    company: str,
    deployment_name: str,
    shared_client_db: str,
    channels: list[str],
) -> str:
    enabled_skills = "\n".join(f"- `{skill}`" for skill in role_pack["enabled_skills"])
    channel_lines = "\n".join(f"- `{channel}`" for channel in channels)
    return f"""# IDENTITY.md — Role Deployment Identity

## Deployment
- Company: `{company}`
- Deployment name: `{deployment_name}`
- Role pack: `{role_pack['role']}`
- Display name: `{role_pack['display_name']}`

## Channels
{channel_lines}

## Shared State
- Shared client database: `{shared_client_db}`
- Separate per-role workspace: `true`
- Shared-state discipline: write role-specific state locally, write shared account facts to `client-db.json`

## Enabled Skills
{enabled_skills}

## Non-Negotiables
- No plaintext secrets in the workspace.
- No approval bypass for external writes.
- No financial actions under any role pack.
- Shared client records must remain safe for cross-role reuse.
"""


def build_config(
    *,
    company: str,
    role_pack: dict[str, Any],
    user: str,
    channel: str,
    crm: str,
    timezone: str,
    deployment_mode: str,
    shared_client_db: str,
    output_dir: Path,
) -> dict[str, Any]:
    channels = {
        channel: {
            "enabled": True,
            "bindings": {
                "role": role_pack["role"],
                "briefing": role_pack["channel_preferences"]["briefing_channel"],
                "alerts": role_pack["channel_preferences"]["alerts_channel"],
            },
        }
    }
    for secondary in role_pack["channel_preferences"].get("secondary", []):
        channels.setdefault(secondary, {"enabled": True})

    skills_entries = {}
    enabled_set = set(role_pack["enabled_skills"])
    for skill in sorted(VALID_SKILLS - {"onboarding"}):
        skills_entries[skill] = {
            "enabled": skill in enabled_set,
            "configOverrides": role_pack["skill_overrides"].get(skill, {}),
        }
    skills_entries["onboarding"] = {
        "enabled": True,
        "configOverrides": {"role": role_pack["role"], "firstWeek": True},
    }

    return {
        "profile": f"role-pack-{role_pack['role']}",
        "company": company,
        "role": role_pack["role"],
        "user": user,
        "description": role_pack["description"],
        "timezone": timezone,
        "deployment": {
            "mode": deployment_mode,
            "workspaceName": output_dir.name,
            "sharedClientDb": shared_client_db,
        },
        "channels": channels,
        "crm": {"provider": crm},
        "agents": {
            "defaults": {
                "heartbeat": {
                    "every": "30m",
                    "target": "last",
                    "activeHours": {"start": "07:00", "end": "22:00"},
                },
                "sandbox": {"mode": "all", "scope": "agent"},
            }
        },
        "skills": {"entries": skills_entries},
        "briefing": {
            "morning": role_pack["briefing"]["schedule"]["morning"],
            "endOfDay": role_pack["briefing"]["schedule"]["end_of_day"],
            "weekly": role_pack["briefing"]["schedule"]["weekly"],
            "style": role_pack["briefing"]["format_preferences"]["style"],
            "includeSections": role_pack["briefing"]["format_preferences"]["include_sections"],
        },
        "approvals": {
            "executeImmediately": role_pack["approval_policy"]["execute_immediately"],
            "queueForApproval": role_pack["approval_policy"]["queue_for_approval"],
            "alwaysBlock": role_pack["approval_policy"]["always_block"],
        },
        "rolePack": {
            "name": role_pack["display_name"],
            "exampleCommands": role_pack["example_commands"],
        },
    }
