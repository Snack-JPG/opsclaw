#!/usr/bin/env python3
"""CLI for reading and appending chat message history."""

from __future__ import annotations

import argparse
import json
import sys

from chat_backend_core import MessageStore


def print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or append OpsClaw chat message history.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    history_parser = subparsers.add_parser("history", help="Read stored message history.")
    history_parser.add_argument("company_id")
    history_parser.add_argument("role")
    history_parser.add_argument("user_id")
    history_parser.add_argument("--limit", type=int, default=20)

    append_parser = subparsers.add_parser("append", help="Append a message to history.")
    append_parser.add_argument("company_id")
    append_parser.add_argument("role")
    append_parser.add_argument("user_id")
    append_parser.add_argument("sender", choices=["user", "agent"])
    append_parser.add_argument("text")
    append_parser.add_argument("--agent-name")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    store = MessageStore()

    if args.command == "history":
        print_json(store.load_messages(args.company_id, args.role, args.user_id, limit=args.limit))
        return
    if args.command == "append":
        message = store.append_message(
            args.company_id,
            args.role,
            args.user_id,
            sender=args.sender,
            text=args.text,
            agent_name=args.agent_name,
        )
        print_json(message)
        return


if __name__ == "__main__":
    main()
