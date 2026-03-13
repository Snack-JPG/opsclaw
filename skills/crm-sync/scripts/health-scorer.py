#!/usr/bin/env python3
"""Client health scoring engine for OpsClaw CRM Sync."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScoreBreakdown:
    """Single factor health score breakdown."""

    score: float
    max_score: float
    status: str
    reason: str
    inferred: bool


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def utc_now() -> datetime:
    """Return current UTC time without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a numeric value into a range."""
    return max(lower, min(value, upper))


def score_bucket(ratio: float) -> str:
    """Map a factor ratio to a human-readable bucket."""
    if ratio >= 0.8:
        return "strong"
    if ratio >= 0.55:
        return "stable"
    if ratio >= 0.3:
        return "warning"
    return "critical"


def score_recency(client: dict[str, Any], rules: dict[str, Any]) -> ScoreBreakdown:
    """Score recent contact recency."""
    max_score = float(rules["weights"]["recency"])
    recency_rules = rules["recencyDays"]
    last_contact = parse_datetime(client.get("lastContactAt"))
    if last_contact is None:
        return ScoreBreakdown(max_score * 0.35, max_score, "warning", "Last contact missing; partial score inferred.", True)
    age_days = max(0.0, (utc_now() - last_contact).total_seconds() / 86400)
    if age_days <= recency_rules["excellent"]:
        ratio = 1.0
        reason = f"Contacted {age_days:.1f} days ago."
    elif age_days <= recency_rules["good"]:
        ratio = 0.8
        reason = f"Contacted {age_days:.1f} days ago."
    elif age_days <= recency_rules["warning"]:
        ratio = 0.55
        reason = f"Contact stale at {age_days:.1f} days."
    elif age_days <= recency_rules["critical"]:
        ratio = 0.25
        reason = f"Contact is overdue at {age_days:.1f} days."
    else:
        ratio = 0.05
        reason = f"No contact for {age_days:.1f} days."
    return ScoreBreakdown(max_score * ratio, max_score, score_bucket(ratio), reason, False)


def score_momentum(client: dict[str, Any], rules: dict[str, Any]) -> ScoreBreakdown:
    """Score deal momentum based on days stuck in stage."""
    max_score = float(rules["weights"]["momentum"])
    stage = str(client.get("dealStage") or "default").lower()
    days_in_stage = client.get("daysInStage")
    if days_in_stage is None:
        return ScoreBreakdown(max_score * 0.5, max_score, "warning", "Days in stage missing; neutral score inferred.", True)
    stage_limits = rules["momentumDaysInStage"]
    limit = float(stage_limits.get(stage, stage_limits.get("default", 30)))
    ratio = clamp(1.0 - (float(days_in_stage) / max(limit * 1.5, 1.0)) + 0.33, 0.05, 1.0)
    reason = f"Stage '{stage}' for {days_in_stage} days vs threshold {limit}."
    return ScoreBreakdown(max_score * ratio, max_score, score_bucket(ratio), reason, False)


def score_rate(value: Any, max_score: float, thresholds: dict[str, float], label: str) -> ScoreBreakdown:
    """Score a rate-based metric."""
    if value is None:
        return ScoreBreakdown(max_score * 0.45, max_score, "warning", f"{label} missing; partial score inferred.", True)
    ratio_value = clamp(float(value), 0.0, 1.0)
    if ratio_value >= thresholds["excellent"]:
        ratio = 1.0
    elif ratio_value >= thresholds["good"]:
        ratio = 0.78
    elif ratio_value >= thresholds["warning"]:
        ratio = 0.45
    else:
        ratio = 0.12
    reason = f"{label} at {ratio_value:.0%}."
    return ScoreBreakdown(max_score * ratio, max_score, score_bucket(ratio), reason, False)


def score_tasks(client: dict[str, Any], rules: dict[str, Any]) -> ScoreBreakdown:
    """Score task completion."""
    max_score = float(rules["weights"]["tasks"])
    completion_rate = client.get("taskCompletionRate")
    if completion_rate is None:
        open_tasks = int(client.get("openTasks", 0) or 0)
        completed_tasks = int(client.get("completedTasks", 0) or 0)
        total = open_tasks + completed_tasks
        completion_rate = (completed_tasks / total) if total else None
    return score_rate(completion_rate, max_score, rules["taskCompletionRate"], "Task completion rate")


def score_client(client: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """Score a single client."""
    recency = score_recency(client, rules)
    momentum = score_momentum(client, rules)
    response = score_rate(client.get("responseRate"), float(rules["weights"]["responseRate"]), rules["responseRate"], "Response rate")
    meetings = score_rate(
        client.get("meetingAttendanceRate"),
        float(rules["weights"]["meetings"]),
        rules["meetingAttendanceRate"],
        "Meeting attendance rate",
    )
    tasks = score_tasks(client, rules)

    breakdown = {
        "recency": recency,
        "momentum": momentum,
        "responseRate": response,
        "meetings": meetings,
        "tasks": tasks,
    }
    total_score = round(sum(item.score for item in breakdown.values()), 2)
    thresholds = rules["thresholds"]
    if total_score > thresholds["healthy"]:
        status = "healthy"
    elif total_score >= thresholds["atRisk"]:
        status = "at_risk"
    else:
        status = "critical"

    confidence = 1.0 - (0.12 * sum(1 for item in breakdown.values() if item.inferred))
    factors = {
        name: {
            "score": round(item.score, 2),
            "maxScore": item.max_score,
            "status": item.status,
            "reason": item.reason,
            "inferred": item.inferred,
        }
        for name, item in breakdown.items()
    }

    risk_drivers = sorted(
        [{"factor": name, "score": item.score, "reason": item.reason} for name, item in breakdown.items()],
        key=lambda item: item["score"],
    )[:2]
    return {
        "clientId": client.get("clientId") or client.get("id") or client.get("name"),
        "name": client.get("name") or client.get("companyName") or "Unknown client",
        "score": total_score,
        "status": status,
        "confidence": round(clamp(confidence, 0.4, 1.0), 2),
        "factors": factors,
        "riskDrivers": risk_drivers,
    }


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, required=True, help="Path to health-rules.json.")
    parser.add_argument("--input", type=Path, help="Path to client metrics JSON. Reads stdin if omitted.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def load_clients(input_path: Path | None) -> list[dict[str, Any]]:
    """Load client metrics from JSON."""
    if input_path is None:
        payload = json.load(sys.stdin)
    else:
        payload = load_json(input_path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("clients"), list):
        return payload["clients"]
    raise ValueError("Expected a JSON list or an object with a 'clients' list.")


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    rules = load_json(args.rules)
    clients = load_clients(args.input)
    results = [score_client(client, rules) for client in clients]
    output = {
        "generatedAt": utc_now().isoformat().replace("+00:00", "Z"),
        "clientCount": len(results),
        "clients": sorted(results, key=lambda item: item["score"]),
    }
    json.dump(output, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
