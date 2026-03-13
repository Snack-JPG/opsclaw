#!/usr/bin/env python3
"""Generate a weekly business review from normalized operational metrics."""

from __future__ import annotations

import argparse
import json
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


def safe_int(value: Any, default: int = 0) -> int:
    """Convert numeric-like values to integers."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert numeric-like values to floats."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def delta(current: Any, previous: Any) -> dict[str, Any]:
    """Compute an absolute and percentage delta."""
    current_value = safe_float(current)
    previous_value = safe_float(previous)
    absolute = round(current_value - previous_value, 2)
    percent = None if previous_value == 0 else round((absolute / previous_value) * 100.0, 2)
    direction = "flat"
    if absolute > 0:
        direction = "up"
    elif absolute < 0:
        direction = "down"
    return {
        "current": current_value,
        "previous": previous_value,
        "absolute": absolute,
        "percent": percent,
        "direction": direction,
    }


def render_metric_line(label: str, current: Any, previous: Any, *, invert_good: bool = False) -> tuple[str, str]:
    """Format a metric line and classify direction quality."""
    comparison = delta(current, previous)
    absolute = comparison["absolute"]
    percent = comparison["percent"]
    trend = comparison["direction"]
    if percent is None:
        suffix = f"{absolute:+.2f} vs last week"
    else:
        suffix = f"{absolute:+.2f} ({percent:+.1f}%) vs last week"

    quality = "neutral"
    if absolute != 0:
        improved = absolute < 0 if invert_good else absolute > 0
        quality = "better" if improved else "worse"
    return f"- {label}: {comparison['current']:.2f} | {suffix}", quality


def build_overview(current_week: dict[str, Any], previous_week: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    """Build high-level review lines and counts of better or worse movement."""
    lines: list[str] = []
    score = {"better": 0, "worse": 0}

    comparisons = [
        ("Email received", current_week.get("email", {}).get("received"), previous_week.get("email", {}).get("received"), False),
        ("Urgent email", current_week.get("email", {}).get("urgent"), previous_week.get("email", {}).get("urgent"), True),
        ("Meetings", current_week.get("calendar", {}).get("meetings"), previous_week.get("calendar", {}).get("meetings"), True),
        ("Meeting hours", current_week.get("calendar", {}).get("meetingHours"), previous_week.get("calendar", {}).get("meetingHours"), True),
        ("Tasks completed", current_week.get("tasks", {}).get("completed"), previous_week.get("tasks", {}).get("completed"), False),
        ("Overdue tasks", current_week.get("tasks", {}).get("overdue"), previous_week.get("tasks", {}).get("overdue"), True),
        ("Weighted pipeline", current_week.get("crm", {}).get("weightedPipelineValue"), previous_week.get("crm", {}).get("weightedPipelineValue"), False),
        ("Won revenue", current_week.get("crm", {}).get("wonValue"), previous_week.get("crm", {}).get("wonValue"), False),
    ]

    for label, current, previous, invert_good in comparisons:
        line, quality = render_metric_line(label, current, previous, invert_good=invert_good)
        lines.append(line)
        if quality in score:
            score[quality] += 1
    return lines, score


def client_health_dashboard(current_week: dict[str, Any], previous_week: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Generate client health lines and risks."""
    current_crm = current_week.get("crm", {})
    previous_crm = previous_week.get("crm", {})
    lines = [
        render_metric_line("Healthy clients", current_crm.get("healthyClients"), previous_crm.get("healthyClients"))[0],
        render_metric_line("At-risk clients", current_crm.get("atRiskClients"), previous_crm.get("atRiskClients"), invert_good=True)[0],
        render_metric_line("Critical clients", current_crm.get("criticalClients"), previous_crm.get("criticalClients"), invert_good=True)[0],
        render_metric_line("Follow-ups due", current_crm.get("followUpsDue"), previous_crm.get("followUpsDue"), invert_good=True)[0],
    ]
    risks: list[str] = []
    if safe_int(current_crm.get("atRiskClients")) > safe_int(previous_crm.get("atRiskClients")):
        risks.append("At-risk client count increased week over week.")
    if safe_int(current_crm.get("criticalClients")) > 0:
        risks.append("At least one client is in a critical health state.")
    if safe_int(current_crm.get("followUpsDue")) >= 5:
        risks.append("Follow-up hygiene is slipping; the due queue is elevated.")
    return lines, risks


def task_velocity_summary(current_week: dict[str, Any], previous_week: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Summarize task execution performance."""
    current_tasks = current_week.get("tasks", {})
    previous_tasks = previous_week.get("tasks", {})
    completed = safe_int(current_tasks.get("completed"))
    created = safe_int(current_tasks.get("created"))
    overdue = safe_int(current_tasks.get("overdue"))
    blocked = safe_int(current_tasks.get("blocked"))
    completion_ratio = 0.0 if created <= 0 else round(completed / created, 2)

    lines = [
        render_metric_line("Tasks completed", completed, previous_tasks.get("completed"))[0],
        render_metric_line("Tasks created", created, previous_tasks.get("created"), invert_good=True)[0],
        render_metric_line("Overdue tasks", overdue, previous_tasks.get("overdue"), invert_good=True)[0],
        render_metric_line("Blocked tasks", blocked, previous_tasks.get("blocked"), invert_good=True)[0],
        f"- Completion ratio: {completion_ratio:.2f}",
    ]
    risks: list[str] = []
    if completed < safe_int(previous_tasks.get("completed")):
        risks.append("Task completion volume dropped from last week.")
    if overdue > safe_int(previous_tasks.get("overdue")):
        risks.append("Overdue work increased week over week.")
    if blocked > 0:
        risks.append("Blocked work is still present and slowing delivery.")
    return lines, risks


def revenue_pipeline_summary(current_week: dict[str, Any], previous_week: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Summarize revenue and pipeline movement."""
    current_crm = current_week.get("crm", {})
    previous_crm = previous_week.get("crm", {})
    lines = [
        render_metric_line("Pipeline value", current_crm.get("pipelineValue"), previous_crm.get("pipelineValue"))[0],
        render_metric_line("Weighted pipeline value", current_crm.get("weightedPipelineValue"), previous_crm.get("weightedPipelineValue"))[0],
        render_metric_line("Won revenue", current_crm.get("wonValue"), previous_crm.get("wonValue"))[0],
    ]
    risks: list[str] = []
    if safe_float(current_crm.get("weightedPipelineValue")) < safe_float(previous_crm.get("weightedPipelineValue")):
        risks.append("Weighted pipeline contracted week over week.")
    if safe_float(current_crm.get("wonValue")) <= 0:
        risks.append("No revenue closed this week from the provided CRM data.")
    return lines, risks


def time_allocation_summary(current_week: dict[str, Any], previous_week: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Summarize meeting load and prep quality."""
    current_calendar = current_week.get("calendar", {})
    previous_calendar = previous_week.get("calendar", {})
    prep_rate = safe_float(current_calendar.get("prepReadyRate"))
    lines = [
        render_metric_line("Meetings", current_calendar.get("meetings"), previous_calendar.get("meetings"), invert_good=True)[0],
        render_metric_line("Meeting hours", current_calendar.get("meetingHours"), previous_calendar.get("meetingHours"), invert_good=True)[0],
        f"- Prep ready rate: {prep_rate:.0%}",
    ]
    risks: list[str] = []
    if safe_float(current_calendar.get("meetingHours")) >= 15:
        risks.append("Meeting load consumed a large share of the week.")
    if prep_rate < 0.8 and prep_rate > 0:
        risks.append("Prep coverage is slipping below the desired level.")
    return lines, risks


def build_recommendations(
    *,
    overview_score: dict[str, int],
    client_risks: list[str],
    task_risks: list[str],
    revenue_risks: list[str],
    time_risks: list[str],
) -> list[str]:
    """Create deterministic weekly recommendations."""
    recommendations: list[str] = []
    if task_risks:
        recommendations.append("Reduce work in progress early next week and clear blocked or overdue tasks first.")
    if client_risks:
        recommendations.append("Schedule outreach for at-risk clients and clear follow-up debt before new prospecting.")
    if revenue_risks:
        recommendations.append("Review pipeline quality and advance the highest-probability deals with a concrete next step.")
    if time_risks:
        recommendations.append("Trim meeting load or consolidate status meetings to recover maker time.")
    if overview_score["worse"] > overview_score["better"]:
        recommendations.append("Overall momentum softened; narrow priorities and protect execution time.")
    if not recommendations:
        recommendations.append("Business health looks stable; keep the current operating cadence and guard focus time.")
    return recommendations


def to_markdown_sections(title: str, lines: list[str]) -> str:
    """Render a Markdown section."""
    return "\n".join([f"## {title}"] + (lines if lines else ["- No data available."]))


def build_weekly_review(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the weekly review document."""
    current_week = dict(payload.get("currentWeek", {}))
    previous_week = dict(payload.get("previousWeek", {}))

    overview_lines, overview_score = build_overview(current_week, previous_week)
    client_lines, client_risks = client_health_dashboard(current_week, previous_week)
    task_lines, task_risks = task_velocity_summary(current_week, previous_week)
    revenue_lines, revenue_risks = revenue_pipeline_summary(current_week, previous_week)
    time_lines, time_risks = time_allocation_summary(current_week, previous_week)
    recommendations = build_recommendations(
        overview_score=overview_score,
        client_risks=client_risks,
        task_risks=task_risks,
        revenue_risks=revenue_risks,
        time_risks=time_risks,
    )

    markdown_sections = [
        "# Weekly Business Review",
        f"Period: {payload.get('periodStart', '')} -> {payload.get('periodEnd', '')}",
        "",
        to_markdown_sections("Week-over-Week Overview", overview_lines),
        "",
        to_markdown_sections("Client Health Dashboard", client_lines + [f"- Risk: {item}" for item in client_risks]),
        "",
        to_markdown_sections("Task Velocity", task_lines + [f"- Risk: {item}" for item in task_risks]),
        "",
        to_markdown_sections("Revenue and Pipeline", revenue_lines + [f"- Risk: {item}" for item in revenue_risks]),
        "",
        to_markdown_sections("Time Allocation", time_lines + [f"- Risk: {item}" for item in time_risks]),
        "",
        "## Recommendations",
        "\n".join(f"- {item}" for item in recommendations),
    ]

    return {
        "reportType": "weekly_business_review",
        "generatedAt": str(payload.get("generatedAt") or utc_now()),
        "periodStart": payload.get("periodStart"),
        "periodEnd": payload.get("periodEnd"),
        "overviewScore": overview_score,
        "recommendations": recommendations,
        "sections": {
            "overview": overview_lines,
            "clientHealth": client_lines,
            "taskVelocity": task_lines,
            "revenuePipeline": revenue_lines,
            "timeAllocation": time_lines,
        },
        "risks": {
            "clientHealth": client_risks,
            "taskVelocity": task_risks,
            "revenuePipeline": revenue_risks,
            "timeAllocation": time_risks,
        },
        "markdown": "\n".join(markdown_sections),
    }


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to normalized weekly review JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    try:
        payload = load_json(args.input)
        report = build_weekly_review(payload)
        json.dump(report, sys.stdout, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
