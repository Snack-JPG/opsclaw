#!/usr/bin/env python3
"""Generate a concise email briefing from classified Gmail data."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from classify import classify
from gws_gmail import iso_now, list_messages, parse_iso_datetime


URGENCY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def summarize_email(item: dict[str, Any]) -> str:
    snippet = (item.get("snippet") or item.get("body") or "").strip().replace("\n", " ")
    return snippet[:140] + ("..." if len(snippet) > 140 else "")


def load_items(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "emails" in data and isinstance(data["emails"], list):
        return data["emails"]
    raise ValueError("Expected a JSON list or an object with an 'emails' list.")


def filter_window(items: list[dict[str, Any]], since: datetime) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in items:
        received = parse_iso_datetime(item.get("receivedAt"))
        if received is None or received >= since:
            filtered.append(item)
    return filtered


def format_sender(item: dict[str, Any]) -> str:
    sender = item.get("from", {})
    return sender.get("name") or sender.get("email") or "Unknown sender"


def oldest_action_item(items: list[dict[str, Any]]) -> str:
    action_items = [
        parse_iso_datetime(item.get("receivedAt"))
        for item in items
        if item.get("classification", {}).get("urgency") in {"critical", "high"}
    ]
    action_items = [timestamp for timestamp in action_items if timestamp is not None]
    if not action_items:
        return "none"
    oldest = min(action_items)
    age = datetime.now(timezone.utc).replace(microsecond=0) - oldest
    hours = int(age.total_seconds() // 3600)
    minutes = int((age.total_seconds() % 3600) // 60)
    return f"{hours}h {minutes}m"


def generate_briefing(items: list[dict[str, Any]], ops_state: dict[str, Any], period_hours: int) -> str:
    sorted_items = sorted(
        items,
        key=lambda item: (
            URGENCY_ORDER.get(item.get("classification", {}).get("urgency", "low"), 9),
            item.get("receivedAt") or "",
        ),
    )

    critical = [
        item for item in sorted_items if item.get("classification", {}).get("urgency") == "critical"
    ]
    requires_response = [
        item
        for item in sorted_items
        if item.get("classification", {}).get("urgency") in {"high", "medium"}
        and item.get("classification", {}).get("category") not in {"marketing", "spam"}
    ]
    fyi = [
        item
        for item in sorted_items
        if item.get("classification", {}).get("urgency") == "low"
        and item.get("classification", {}).get("category") not in {"marketing", "spam"}
    ]
    filtered_counts = Counter(
        item.get("classification", {}).get("category", "unknown")
        for item in sorted_items
        if item.get("classification", {}).get("category") in {"marketing", "spam"}
    )

    lines = ["Email Briefing"]
    period_end = datetime.now(timezone.utc).replace(microsecond=0)
    period_start = period_end - timedelta(hours=period_hours)
    lines.append(
        f"Period: {period_start.isoformat().replace('+00:00', 'Z')} -> {period_end.isoformat().replace('+00:00', 'Z')}"
    )
    lines.append("")

    lines.append("Critical")
    if critical:
        for item in critical:
            lines.append(
                f"- {format_sender(item)} - {item.get('subject', '(no subject)')}: {summarize_email(item)} | Recommended: {item.get('recommendedAction')}"
            )
    else:
        lines.append("- None")
    lines.append("")

    lines.append("Requires Response")
    if requires_response:
        for item in requires_response[:12]:
            classification = item.get("classification", {})
            lines.append(
                f"- {format_sender(item)} - {item.get('subject', '(no subject)')} [{classification.get('urgency')}/{classification.get('category')}]: {summarize_email(item)}"
            )
            draft_hint = "draft queued" if item.get("draft") else "draft recommended"
            lines.append(f"  Draft: {draft_hint}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("FYI")
    if fyi:
        for item in fyi[:12]:
            lines.append(f"- {format_sender(item)} - {item.get('subject', '(no subject)')}: {summarize_email(item)}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("Filtered Out")
    lines.append(f"- Marketing: {filtered_counts.get('marketing', 0)}")
    lines.append(f"- Spam: {filtered_counts.get('spam', 0)}")
    lines.append("")

    email_state = ops_state.get("email", {})
    lines.append("Queue Health")
    lines.append(f"- Unread: {email_state.get('unreadCount', 0)}")
    lines.append(f"- Urgent queue: {len(email_state.get('urgentQueue', []))}")
    lines.append(f"- Pending drafts: {len(email_state.get('pendingDrafts', []))}")
    lines.append(f"- Oldest high-priority item: {oldest_action_item(sorted_items)}")
    return "\n".join(lines)


def fetch_and_classify(args: argparse.Namespace) -> list[dict[str, Any]]:
    categories = load_json(args.categories)
    vip = load_json(args.vip)
    messages = list_messages(
        query=args.query or f"in:inbox newer_than:{max(1, args.hours // 24 or 1)}d",
        max_results=args.max_results,
        label_ids=["INBOX"],
        unread_only=not args.include_read,
    )
    return [classify(item, categories, vip) for item in messages]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emails-path", type=Path, help="Path to classified emails JSON.")
    parser.add_argument("--ops-state", type=Path, required=True, help="Path to workspace/ops-state.json.")
    parser.add_argument("--hours", type=int, default=24, help="Briefing lookback window.")
    parser.add_argument("--categories", type=Path, help="Path to categories.json for live Gmail fetch mode.")
    parser.add_argument("--vip", type=Path, help="Path to vip-senders.json for live Gmail fetch mode.")
    parser.add_argument("--query", help="Optional Gmail search query override.")
    parser.add_argument("--max-results", type=int, default=25, help="Max inbox messages to fetch in live mode.")
    parser.add_argument("--include-read", action="store_true", help="Include read mail in live mode.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.emails_path:
        items = load_items(args.emails_path)
    else:
        if not args.categories or not args.vip:
            raise SystemExit("--categories and --vip are required when fetching inbox data via gws.")
        items = fetch_and_classify(args)

    since = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=args.hours)
    filtered_items = filter_window(items, since)
    ops_state = load_json(args.ops_state)
    briefing = generate_briefing(filtered_items, ops_state, args.hours)
    sys.stdout.write(briefing + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
