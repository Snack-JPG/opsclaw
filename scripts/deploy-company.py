#!/usr/bin/env python3
"""Deploy a complete multi-role OpsClaw company setup."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from role_pack_lib import load_json, slugify, write_json


ROOT = Path(__file__).resolve().parent.parent
DEPLOY_ROLE_SCRIPT = ROOT / "scripts" / "deploy-role.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Company config JSON")
    parser.add_argument("--output", required=True, help="Output directory")
    return parser.parse_args()


def render_compose(company_slug: str, roles: list[dict[str, str]], output_dir: Path) -> str:
    lines = ['services:']
    for role in roles:
        service_name = f"{company_slug}-{role['role']}"
        workspace_rel = Path("roles") / role["role"]
        lines.extend(
            [
                f"  {service_name}:",
                "    image: node:22-bookworm-slim",
                f"    container_name: {service_name}",
                "    working_dir: /opt/opsclaw",
                "    restart: unless-stopped",
                "    environment:",
                f"      OPSCLAW_WORKSPACE: /data/{workspace_rel.as_posix()}",
                "      PYTHONUNBUFFERED: \"1\"",
                "    command: >",
                "      bash -lc \"",
                "        npm install -g openclaw &&",
                "        openclaw gateway start",
                "      \"",
                "    volumes:",
                f"      - {ROOT.resolve()}:/opt/opsclaw",
                f"      - {output_dir.resolve()}:/data",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    output_dir = Path(args.output).resolve()
    company_config = load_json(config_path)

    company = company_config["company"]
    shared = company_config["shared"]
    roles = company_config["roles"]

    company_slug = slugify(company["name"])
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shared_dir = output_dir / "shared"
    roles_dir = output_dir / "roles"
    shared_dir.mkdir(parents=True, exist_ok=True)
    roles_dir.mkdir(parents=True, exist_ok=True)

    shared_client_db = shared_dir / "client-db.json"
    write_json(
        shared_client_db,
        {
            "$schema": "opsclaw/client-db/v1",
            "version": 1,
            "workspaceId": f"{company_slug}-shared",
            "company": company["name"],
            "clients": {},
        },
    )

    routes: list[dict[str, str]] = []
    for role in roles:
        role_output = roles_dir / role["role"]
        cmd = [
            sys.executable,
            str(DEPLOY_ROLE_SCRIPT),
            "--role",
            role["role"],
            "--company",
            company["name"],
            "--user",
            role.get("user", company["owner"]),
            "--channel",
            role.get("channel", shared["channels"]["primary"]),
            "--crm",
            shared.get("crm", "none"),
            "--timezone",
            company.get("timezone", "Europe/London"),
            "--deployment-mode",
            company.get("deployment_mode", "docker-compose"),
            "--shared-client-db",
            str(shared_client_db),
            "--output",
            str(role_output),
        ]
        subprocess.run(cmd, check=True)
        routes.append(
            {
                "role": role["role"],
                "user": role.get("user", company["owner"]),
                "channel": role.get("channel", shared["channels"]["primary"]),
                "briefing_channel": role.get("briefing_channel", role.get("channel", shared["channels"]["primary"])),
                "workspace": str(role_output),
            }
        )

    write_json(
        output_dir / "channel-bindings.json",
        {
            "company": company["name"],
            "primaryChannel": shared["channels"]["primary"],
            "routes": routes,
        },
    )
    write_json(
        output_dir / "deployment-manifest.json",
        {
            "company": company,
            "shared": {
                "crm": shared.get("crm", "none"),
                "channels": shared["channels"],
                "clientDb": str(shared_client_db),
            },
            "roles": routes,
        },
    )
    (output_dir / "docker-compose.yml").write_text(
        render_compose(company_slug, routes, output_dir),
        encoding="utf-8",
    )

    print(f"Deployed {len(routes)} role workspaces to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
