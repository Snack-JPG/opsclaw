#!/usr/bin/env python3
"""Prioritised CRM follow-up engine for OpsClaw CRM Sync."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def utc_now() -> datetime:
    """Return current UTC time without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_date(value: str | None) -> date | None:
    """Parse a YYYY-MM-DD date string."""
    if not value:
        return None
    return date.fromisoformat(value)


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def days_since_contact(last_contact: str | None) -> int | None:
    """Return integer days since last contact."""
    parsed = parse_datetime(last_contact)
    if parsed is None:
        return None
    return int((utc_now() - parsed).total_seconds() // 86400)


def load_items(input_path: Path | None) -> list[dict[str, Any]]:
    """Load follow-up input records."""
    if input_path is None:
        payload = json.load(sys.stdin)
    else:
        payload = load_json(input_path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    if isinstance(payload, dict) and isinstance(payload.get("deals"), list):
        return payload["deals"]
    raise ValueError("Expected a JSON list or an object with 'items' or 'deals'.")


def classify_due_date(next_follow_up: date | None, today: date) -> tuple[str, int]:
    """Classify follow-up timing relative to today."""
    if next_follow_up is None:
        return "unscheduled", 999
    delta = (next_follow_up - today).days
    if delta < 0:
        return "overdue", delta
    if delta == 0:
        return "due_today", delta
    return "upcoming", delta


def build_recommendation(item: dict[str, Any], timing: str, stale_days: int | None) -> str:
    """Generate a concise next-step recommendation."""
    client_name = item.get("name") or item.get("company") or "client"
    if timing == "overdue":
        return f"Follow up with {client_name} immediately and reference the outstanding next step."
    if timing == "due_today":
        return f"Reach out to {client_name} today and confirm the current status."
    if stale_days is not None and stale_days >= 21:
        return f"Re-engage {client_name}; contact has been quiet for {stale_days} days."
    return f"Prepare context for {client_name} and queue the follow-up in the next working block."


def score_item(item: dict[str, Any], rules: dict[str, Any], lookahead_days: int, high_value_threshold: float) -> dict[str, Any]:
    """Score a single follow-up item."""
    priority_rules = rules["followUpPriority"]
    today = utc_now().date()
    next_follow_up = parse_date(item.get("nextFollowUpDate") or item.get("nextActivityDate") or item.get("closeDate"))
    timing, day_delta = classify_due_date(next_follow_up, today)
    score = 0
    if timing == "overdue":
        score += priority_rules["overdueBase"] + min(abs(day_delta) * 3, 18)
    elif timing == "due_today":
        score += priority_rules["dueTodayBase"]
    elif timing == "upcoming" and day_delta <= lookahead_days:
        score += priority_rules["upcomingBase"] + max(0, lookahead_days - day_delta)

    health_status = item.get("healthStatus")
    if health_status == "at_risk" or health_status == "critical":
        score += priority_rules["atRiskBonus"]

    value = float(item.get("amount") or item.get("value") or 0)
    if value >= high_value_threshold:
        score += priority_rules["highValueBonus"]

    stale_days = days_since_contact(item.get("lastContactAt"))
    if stale_days is not None and stale_days >= 14:
        score += priority_rules["staleContactBonus"]

    if timing == "unscheduled":
        score = max(score, 30)

    return {
        "clientId": item.get("clientId") or item.get("id"),
        "name": item.get("name") or item.get("title") or item.get("company") or "Unknown client",
        "timing": timing,
        "daysUntilFollowUp": day_delta,
        "priorityScore": int(score),
        "dealStage": item.get("stage") or item.get("dealStage"),
        "amount": value if value else None,
        "healthStatus": health_status,
        "lastContactDaysAgo": stale_days,
        "recommendation": build_recommendation(item, timing, stale_days),
        "nextFollowUpDate": next_follow_up.isoformat() if next_follow_up else None,
    }


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Path to crm-config.json.")
    parser.add_argument("--rules", type=Path, required=True, help="Path to health-rules.json.")
    parser.add_argument("--input", type=Path, help="Path to follow-up JSON. Reads stdin if omitted.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    config = load_json(args.config)
    rules = load_json(args.rules)
    follow_up_config = config.get("followUps", {})
    lookahead_days = int(follow_up_config.get("lookaheadDays", 7))
    high_value_threshold = float(follow_up_config.get("highValueThreshold", 10000))
    items = load_items(args.input)

    scored = [score_item(item, rules, lookahead_days, high_value_threshold) for item in items]
    overdue = [item for item in scored if item["timing"] == "overdue"]
    due_today = [item for item in scored if item["timing"] == "due_today"]
    at_risk = [item for item in scored if item.get("healthStatus") in {"at_risk", "critical"}]

    output = {
        "generatedAt": utc_now().isoformat().replace("+00:00", "Z"),
        "summary": {
            "total": len(scored),
            "overdue": len(overdue),
            "dueToday": len(due_today),
            "atRisk": len(at_risk),
        },
        "items": sorted(scored, key=lambda item: (-item["priorityScore"], item["name"])),
    }
    json.dump(output, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
