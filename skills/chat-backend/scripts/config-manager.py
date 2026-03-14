#!/usr/bin/env python3
"""CLI for managing company chat backend configs."""

from __future__ import annotations

import argparse
import json
import sys

from chat_backend_core import ConfigManager


def print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage OpsClaw chat backend company configs.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new company config.")
    init_parser.add_argument("company_name")
    init_parser.add_argument("--company-id", help="Optional explicit company ID.")

    branding_parser = subparsers.add_parser("set-branding", help="Update company branding.")
    branding_parser.add_argument("company")
    branding_parser.add_argument("--name", dest="product_name")
    branding_parser.add_argument("--color")
    branding_parser.add_argument("--logo")
    branding_parser.add_argument("--secondary-color")
    branding_parser.add_argument("--font")

    role_parser = subparsers.add_parser("add-role", help="Add or update a company role.")
    role_parser.add_argument("company")
    role_parser.add_argument("role")
    role_parser.add_argument("--name")
    role_parser.add_argument("--greeting")
    role_parser.add_argument("--description")
    role_parser.add_argument("--avatar")

    subparsers.add_parser("list", help="List configured companies.")

    export_parser = subparsers.add_parser("export", help="Export a full company config as JSON.")
    export_parser.add_argument("company")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    manager = ConfigManager()

    if args.command == "init":
        config = manager.init_company(args.company_name, company_id=args.company_id)
        print_json(config)
        return
    if args.command == "set-branding":
        config = manager.set_branding(
            args.company,
            product_name=args.product_name,
            color=args.color,
            logo=args.logo,
            secondary_color=args.secondary_color,
            font=args.font,
        )
        print_json(config)
        return
    if args.command == "add-role":
        config = manager.add_role(
            args.company,
            args.role,
            name=args.name,
            greeting=args.greeting,
            description=args.description,
            avatar=args.avatar,
        )
        print_json(config)
        return
    if args.command == "list":
        configs = manager.list_configs()
        print_json(
            [
                {
                    "company_id": item.get("company_id"),
                    "company_name": item.get("company_name"),
                    "product_name": item.get("branding", {}).get("product_name"),
                    "roles": sorted(item.get("roles", {}).keys()),
                }
                for item in configs
            ]
        )
        return
    if args.command == "export":
        print_json(manager.load(args.company))
        return


if __name__ == "__main__":
    main()
