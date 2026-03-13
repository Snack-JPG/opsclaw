#!/usr/bin/env python3
"""Detect operational anomalies from normalized metrics and baselines."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def utc_now() -> str:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric-like values to floats."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def baseline_average(values: list[Any], minimum_points: int) -> float | None:
    """Compute a baseline mean only when enough history exists."""
    cleaned = [safe_float(item) for item in values if item is not None]
    if len(cleaned) < minimum_points:
        return None
    return statistics.mean(cleaned)


def detect_email_spike(current: dict[str, Any], history: dict[str, Any], rule: dict[str, Any], minimum_points: int) -> list[dict[str, Any]]:
    """Detect sudden email volume spikes."""
    if not rule.get("enabled", True):
        return []
    metric = str(rule.get("metric") or "emailVolume")
    current_value = safe_float(current.get(metric))
    baseline = baseline_average(list(history.get(metric, [])), minimum_points)
    if baseline is None or current_value < safe_float(rule.get("minimumCurrent")):
        return []
    multiplier = current_value / baseline if baseline > 0 else 0.0
    if multiplier < safe_float(rule.get("spikeMultiplier"), 2.0):
        return []
    severity = "critical" if multiplier >= safe_float(rule.get("criticalMultiplier"), 2.5) else "warning"
    return [
        {
            "type": "email_volume_spike",
            "severity": severity,
            "metric": metric,
            "current": round(current_value, 2),
            "baseline": round(baseline, 2),
            "ratio": round(multiplier, 2),
            "message": f"Email volume is {multiplier:.2f}x the recent baseline.",
        }
    ]


def detect_task_drop(current: dict[str, Any], history: dict[str, Any], rule: dict[str, Any], minimum_points: int) -> list[dict[str, Any]]:
    """Detect a drop in task completion."""
    if not rule.get("enabled", True):
        return []
    metric = str(rule.get("metric") or "taskCompletionCount")
    current_value = safe_float(current.get(metric))
    baseline = baseline_average(list(history.get(metric, [])), minimum_points)
    if baseline is None or baseline < safe_float(rule.get("minimumBaseline"), 0):
        return []
    ratio = current_value / baseline if baseline > 0 else 0.0
    if ratio > safe_float(rule.get("dropRatio"), 0.6):
        return []
    severity = "critical" if ratio <= safe_float(rule.get("criticalDropRatio"), 0.4) else "warning"
    return [
        {
            "type": "task_completion_drop",
            "severity": severity,
            "metric": metric,
            "current": round(current_value, 2),
            "baseline": round(baseline, 2),
            "ratio": round(ratio, 2),
            "message": f"Task completion volume fell to {ratio:.2f}x of baseline.",
        }
    ]


def detect_calendar_overload(current: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect overloaded meeting schedules."""
    if not rule.get("enabled", True):
        return []
    metric = str(rule.get("metric") or "meetingCount")
    current_value = safe_float(current.get(metric))
    critical_above = safe_float(rule.get("criticalAbove"), 8)
    warning_above = safe_float(rule.get("warningAbove"), 6)
    if current_value < warning_above:
        return []
    severity = "critical" if current_value >= critical_above else "warning"
    return [
        {
            "type": "calendar_overload",
            "severity": severity,
            "metric": metric,
            "current": round(current_value, 2),
            "message": f"Meeting count is at {current_value:.0f}, above the configured load threshold.",
        }
    ]


def detect_missed_followups(current: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect elevated missed follow-up counts and VIP misses."""
    if not rule.get("enabled", True):
        return []
    metric = str(rule.get("metric") or "missedFollowUps")
    current_value = safe_float(current.get(metric))
    warning_above = safe_float(rule.get("warningAbove"), 1)
    critical_above = safe_float(rule.get("criticalAbove"), 3)
    anomalies: list[dict[str, Any]] = []
    if current_value >= warning_above:
        severity = "critical" if current_value >= critical_above else "warning"
        anomalies.append(
            {
                "type": "missed_followups",
                "severity": severity,
                "metric": metric,
                "current": round(current_value, 2),
                "message": f"{current_value:.0f} follow-up(s) are missed or overdue.",
            }
        )

    critical_tier = str(rule.get("criticalTier") or "vip").lower()
    for client in list(current.get("clients", [])):
        if str(client.get("tier") or "").lower() != critical_tier:
            continue
        if safe_float(client.get("missedFollowUps")) >= 1:
            anomalies.append(
                {
                    "type": "vip_missed_followup",
                    "severity": "critical",
                    "client": client.get("name"),
                    "message": f"VIP client '{client.get('name')}' has a missed follow-up.",
                }
            )
    return anomalies


def detect_client_silence(current: dict[str, Any], rule: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect stale client communication relative to cadence."""
    if not rule.get("enabled", True):
        return []
    anomalies: list[dict[str, Any]] = []
    for client in list(current.get("clients", [])):
        cadence = safe_float(client.get("expectedCadenceDays"))
        days_since_contact = safe_float(client.get("daysSinceContact"))
        if cadence <= 0 or days_since_contact <= 0:
            continue

        tier = str(client.get("tier") or "standard").lower()
        multiplier = safe_float(
            rule.get("vipMultiplier") if tier == "vip" else rule.get("standardMultiplier"),
            1.5 if tier == "vip" else 2.0,
        )
        threshold = cadence * multiplier
        if days_since_contact <= threshold:
            continue

        severity = "critical" if days_since_contact >= safe_float(rule.get("criticalAfterDays"), 21) else "warning"
        anomalies.append(
            {
                "type": "client_silence",
                "severity": severity,
                "client": client.get("name"),
                "current": days_since_contact,
                "threshold": round(threshold, 2),
                "message": f"Client '{client.get('name')}' has been silent for {days_since_contact:.0f} days.",
            }
        )
    return anomalies


def build_summary(anomalies: list[dict[str, Any]]) -> list[str]:
    """Create concise summary lines from anomalies."""
    if not anomalies:
        return ["No anomalies detected from the provided metrics."]
    ordered = sorted(anomalies, key=lambda item: (0 if item.get("severity") == "critical" else 1, item.get("type", "")))
    return [str(item.get("message") or item.get("type")) for item in ordered]


def detect_anomalies(payload: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """Run all anomaly checks."""
    defaults = dict(rules.get("defaults", {}))
    minimum_points = int(defaults.get("minimumBaselinePoints", 3))
    current = dict(payload.get("current", {}))
    history = dict(payload.get("history", {}))
    rule_set = dict(rules.get("rules", {}))

    anomalies = []
    anomalies.extend(detect_email_spike(current, history, dict(rule_set.get("emailVolumeSpike", {})), minimum_points))
    anomalies.extend(detect_task_drop(current, history, dict(rule_set.get("taskCompletionDrop", {})), minimum_points))
    anomalies.extend(detect_calendar_overload(current, dict(rule_set.get("calendarOverload", {}))))
    anomalies.extend(detect_missed_followups(current, dict(rule_set.get("missedFollowUps", {}))))
    anomalies.extend(detect_client_silence(current, dict(rule_set.get("clientSilence", {}))))

    critical_count = sum(1 for item in anomalies if item.get("severity") == "critical")
    return {
        "reportType": "anomaly_detection",
        "generatedAt": str(payload.get("generatedAt") or utc_now()),
        "anomalyCount": len(anomalies),
        "criticalCount": critical_count,
        "anomalies": sorted(anomalies, key=lambda item: (0 if item.get("severity") == "critical" else 1, item.get("type", ""))),
        "summary": build_summary(anomalies),
    }


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to anomaly detection input JSON.")
    parser.add_argument("--rules", type=Path, required=True, help="Path to anomaly rules JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    try:
        payload = load_json(args.input)
        rules = load_json(args.rules)
        result = detect_anomalies(payload, rules)
        json.dump(result, sys.stdout, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
