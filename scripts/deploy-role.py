#!/usr/bin/env python3
"""Deploy a single OpsClaw role-pack workspace."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from role_pack_lib import (
    build_agents_md,
    build_config,
    build_identity_md,
    build_user_md,
    copy_enabled_skills,
    copy_workspace_template,
    load_role_pack,
    reset_output_dir,
    slugify,
    write_json,
    write_json5,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", help="Role pack name, e.g. founder")
    parser.add_argument("--role-pack", dest="role_pack_path", help="Path to a role pack JSON file")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--user", required=True, help="Human owner or operator name")
    parser.add_argument("--channel", required=True, help="Primary agent channel")
    parser.add_argument("--crm", default="none", help="CRM provider")
    parser.add_argument("--timezone", default="Europe/London", help="Deployment timezone")
    parser.add_argument("--deployment-mode", default="docker-compose", help="Deployment mode")
    parser.add_argument("--shared-client-db", help="Optional path to a shared client-db.json")
    parser.add_argument("--output", required=True, help="Output workspace directory")
    return parser.parse_args()


def sync_state_metadata(output_dir: Path, workspace_id: str, role: str) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    ops_state_path = output_dir / "ops-state.json"
    ops_state = json.loads(ops_state_path.read_text(encoding="utf-8"))
    ops_state["workspaceId"] = workspace_id
    ops_state["lastUpdated"] = now
    ops_state["status"] = "deployed"
    ops_state["role"] = role
    ops_state["routing"] = {"role": role}
    write_json(ops_state_path, ops_state)

    heartbeat_state_path = output_dir / "heartbeat-state.json"
    heartbeat_state = json.loads(heartbeat_state_path.read_text(encoding="utf-8"))
    heartbeat_state["lastHeartbeatRun"] = None
    heartbeat_state["runtime"]["status"] = "ready"
    write_json(heartbeat_state_path, heartbeat_state)


def init_memory(output_dir: Path, company: str, role_pack: dict[str, object], user: str) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    memory_path = output_dir / "memory" / f"{today}.md"
    memory_path.write_text(
        "\n".join(
            [
                f"# {today} — {role_pack['display_name']}",
                "",
                f"- Deployment created for `{company}`.",
                f"- Operator: `{user}`.",
                f"- Role pack: `{role_pack['role']}`.",
                "- Status: ready for onboarding.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def configure_client_db(output_dir: Path, shared_client_db: str | None, workspace_id: str) -> str:
    client_db_path = output_dir / "client-db.json"
    if shared_client_db:
        shared_path = Path(shared_client_db).resolve()
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        if not shared_path.exists():
            template = json.loads(client_db_path.read_text(encoding="utf-8"))
            template["workspaceId"] = workspace_id
            write_json(shared_path, template)
        client_db_path.unlink(missing_ok=True)
        client_db_path.symlink_to(shared_path)
        return str(shared_path)

    client_db = json.loads(client_db_path.read_text(encoding="utf-8"))
    client_db["workspaceId"] = workspace_id
    write_json(client_db_path, client_db)
    return str(client_db_path.resolve())


def main() -> int:
    args = parse_args()
    role_pack = load_role_pack(role=args.role, role_pack_path_value=args.role_pack_path)
    output_dir = Path(args.output).resolve()
    deployment_name = output_dir.name or f"{slugify(args.company)}-{role_pack['role']}"
    workspace_id = f"{slugify(args.company)}-{role_pack['role']}"

    reset_output_dir(output_dir)
    copy_workspace_template(output_dir)
    copy_enabled_skills(output_dir, role_pack["enabled_skills"] + ["onboarding"])

    shared_client_db = configure_client_db(output_dir, args.shared_client_db, workspace_id)
    config = build_config(
        company=args.company,
        role_pack=role_pack,
        user=args.user,
        channel=args.channel,
        crm=args.crm,
        timezone=args.timezone,
        deployment_mode=args.deployment_mode,
        shared_client_db=shared_client_db,
        output_dir=output_dir,
    )

    (output_dir / "SOUL.md").write_text(role_pack["persona"]["soul_md"] + "\n", encoding="utf-8")
    (output_dir / "HEARTBEAT.md").write_text(role_pack["heartbeat"]["heartbeat_md"] + "\n", encoding="utf-8")
    (output_dir / "USER.md").write_text(
        build_user_md(args.company, args.user, role_pack, args.channel, args.crm, args.timezone),
        encoding="utf-8",
    )
    (output_dir / "AGENTS.md").write_text(
        build_agents_md(role_pack, args.company, args.user, args.channel),
        encoding="utf-8",
    )
    (output_dir / "IDENTITY.md").write_text(
        build_identity_md(
            role_pack,
            args.company,
            deployment_name,
            shared_client_db,
            list(config["channels"].keys()),
        ),
        encoding="utf-8",
    )
    write_json5(output_dir / "config.json5", config)
    write_json(output_dir / "role-pack.json", role_pack)

    sync_state_metadata(output_dir, workspace_id, role_pack["role"])
    init_memory(output_dir, args.company, role_pack, args.user)

    print(f"Deployed role pack '{role_pack['role']}' to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
