#!/usr/bin/env python3
"""Track KPI values, trends, and threshold alerts for OpsClaw reporting."""

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


def compare_to_baseline(current: float, history: list[Any], window: int) -> dict[str, Any]:
    """Compute a simple baseline comparison from historical values."""
    cleaned = [safe_float(item) for item in history[-window:] if item is not None]
    if not cleaned:
        return {"baseline": None, "delta": None, "percent": None, "trend": "unknown"}
    baseline = statistics.mean(cleaned)
    delta = round(current - baseline, 2)
    percent = None if baseline == 0 else round((delta / baseline) * 100.0, 2)
    if abs(delta) < 0.01:
        trend = "flat"
    elif delta > 0:
        trend = "up"
    else:
        trend = "down"
    return {"baseline": round(baseline, 2), "delta": delta, "percent": percent, "trend": trend}


def evaluate_status(metric: dict[str, Any], current: float) -> tuple[str, str | None]:
    """Evaluate KPI status against thresholds."""
    direction = str(metric.get("direction") or "lower_is_better")
    label = str(metric.get("label") or metric.get("id") or "metric")

    if direction == "higher_is_better":
        critical_below = metric.get("criticalBelow")
        warning_below = metric.get("warningBelow")
        if critical_below is not None and current <= safe_float(critical_below):
            return "critical", f"{label} is below the critical threshold."
        if warning_below is not None and current <= safe_float(warning_below):
            return "warning", f"{label} is below the warning threshold."
        return "healthy", None

    critical_above = metric.get("criticalAbove")
    warning_above = metric.get("warningAbove")
    if critical_above is not None and current >= safe_float(critical_above):
        return "critical", f"{label} is above the critical threshold."
    if warning_above is not None and current >= safe_float(warning_above):
        return "warning", f"{label} is above the warning threshold."
    return "healthy", None


def evaluate_metric(metric: dict[str, Any], payload: dict[str, Any], history_window: int) -> dict[str, Any]:
    """Evaluate one KPI definition."""
    metric_id = str(metric["id"])
    current = safe_float(payload.get("metrics", {}).get(metric_id))
    history = list(payload.get("history", {}).get(metric_id, []))
    baseline = compare_to_baseline(current, history, history_window)
    status, alert = evaluate_status(metric, current)
    direction = str(metric.get("direction") or "lower_is_better")
    trend = baseline["trend"]
    if trend == "unknown":
        trend_direction = "unknown"
    elif trend == "flat":
        trend_direction = "flat"
    else:
        improving = (
            (trend == "down" and direction == "lower_is_better")
            or (trend == "up" and direction == "higher_is_better")
        )
        trend_direction = "improving" if improving else "worsening"
    return {
        "id": metric_id,
        "label": metric.get("label", metric_id),
        "description": metric.get("description"),
        "unit": metric.get("unit", "count"),
        "current": round(current, 2),
        "status": status,
        "thresholds": {
            key: metric[key]
            for key in ("warningAbove", "criticalAbove", "warningBelow", "criticalBelow")
            if key in metric
        },
        "baseline": baseline["baseline"],
        "delta": baseline["delta"],
        "percentDelta": baseline["percent"],
        "trend": trend,
        "trendDirection": trend_direction,
        "alert": alert if metric.get("alertOnThresholdBreach", False) else None,
    }


def summarize_alerts(results: list[dict[str, Any]]) -> list[str]:
    """Summarize threshold breaches."""
    alerts = [item["alert"] for item in results if item.get("alert")]
    return [str(alert) for alert in alerts]


def track_kpis(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Build the KPI tracking result."""
    history_window = int(config.get("historyWindow", 4))
    definitions = list(config.get("metrics", []))
    results = [evaluate_metric(metric, payload, history_window) for metric in definitions]

    order = {"critical": 0, "warning": 1, "healthy": 2}
    results.sort(key=lambda item: (order.get(item["status"], 9), item["label"]))
    alerts = summarize_alerts(results)
    status_counts = {
        "critical": sum(1 for item in results if item["status"] == "critical"),
        "warning": sum(1 for item in results if item["status"] == "warning"),
        "healthy": sum(1 for item in results if item["status"] == "healthy"),
    }

    return {
        "reportType": "kpi_tracking",
        "generatedAt": str(payload.get("generatedAt") or utc_now()),
        "statusCounts": status_counts,
        "alerts": alerts,
        "metrics": results,
    }


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to KPI input JSON.")
    parser.add_argument("--config", type=Path, required=True, help="Path to KPI configuration JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    try:
        payload = load_json(args.input)
        config = load_json(args.config)
        result = track_kpis(payload, config)
        json.dump(result, sys.stdout, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
