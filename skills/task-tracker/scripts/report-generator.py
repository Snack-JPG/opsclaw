#!/usr/bin/env python3
"""Weekly report generator for OpsClaw task tracking."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate a weekly task report from normalized JSON.")
    parser.add_argument("--input", required=True, help="Path to normalized weekly task JSON.")
    parser.add_argument("--template", required=True, help="Path to the Markdown template file.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_text(path: Path) -> str:
    """Load UTF-8 text from disk."""
    return path.read_text(encoding="utf-8")


def bullet_list(items: list[dict[str, Any]], *, empty_text: str) -> str:
    """Render a list of task dictionaries as bullets."""
    if not items:
        return f"- {empty_text}"
    lines: list[str] = []
    for item in items:
        title = str(item.get("title") or item.get("name") or "(untitled task)")
        details: list[str] = []
        if item.get("dueDate"):
            details.append(f"due {item['dueDate']}")
        if item.get("ageDays") is not None:
            details.append(f"age {item['ageDays']}d")
        if item.get("priority"):
            details.append(f"priority {item['priority']}")
        if item.get("blockReason"):
            details.append(f"blocked: {item['blockReason']}")
        if details:
            lines.append(f"- {title} ({'; '.join(details)})")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


def compute_velocity(history: list[dict[str, Any]], current_completed: int) -> tuple[float, str]:
    """Compute trailing velocity average and trend string."""
    counts = [int(item.get("completedCount", 0)) for item in history[-4:]]
    if not counts:
        average = float(current_completed)
    else:
        average = mean(counts)
    if current_completed > average + 0.5:
        trend = "above average"
    elif current_completed < average - 0.5:
        trend = "below average"
    else:
        trend = "in line with average"
    return round(average, 2), trend


def build_recommendations(doc: dict[str, Any], completed_count: int, velocity_average: float) -> list[str]:
    """Create simple deterministic weekly recommendations."""
    recommendations: list[str] = []
    carried_over = list(doc.get("carriedOver", []))
    blocked = [item for item in carried_over if item.get("blockReason")] + list(doc.get("blocked", []))
    due_next_week = list(doc.get("dueNextWeek", []))

    if carried_over and len(carried_over) >= max(3, completed_count):
        recommendations.append("Reduce carry-over by narrowing next week's active work in progress.")
    if blocked:
        recommendations.append("Clear blocked items early next week before adding new work.")
    if due_next_week and len(due_next_week) > max(5, completed_count):
        recommendations.append("Rebalance next week's commitments; the due-soon queue is crowded.")
    if completed_count < velocity_average and completed_count > 0:
        recommendations.append("Completion volume dropped below the recent average; inspect blockers and context switching.")
    if completed_count == 0:
        recommendations.append("No work closed this week; verify task states and escalate blocked priorities immediately.")
    if not recommendations:
        recommendations.append("Workload looks balanced; keep the current delivery cadence and protect focus time.")
    return recommendations


def render_markdown(template: str, *, doc: dict[str, Any], velocity_average: float, velocity_trend: str) -> str:
    """Fill the Markdown template with computed sections."""
    completed = list(doc.get("completed", []))
    carried_over = list(doc.get("carriedOver", []))
    created = list(doc.get("created", []))
    due_next_week = list(doc.get("dueNextWeek", []))
    completed_count = len(completed)
    recommendations = build_recommendations(doc, completed_count, velocity_average)

    replacements = {
        "{{period_start}}": str(doc.get("periodStart") or ""),
        "{{period_end}}": str(doc.get("periodEnd") or ""),
        "{{completed_section}}": bullet_list(completed, empty_text="No completed tasks recorded."),
        "{{carried_over_section}}": bullet_list(carried_over, empty_text="No carry-over tasks."),
        "{{created_section}}": bullet_list(created, empty_text="No new tasks created."),
        "{{due_next_week_section}}": bullet_list(due_next_week, empty_text="No tasks due next week."),
        "{{completed_count}}": str(completed_count),
        "{{velocity_average}}": f"{velocity_average:.2f}",
        "{{velocity_trend}}": velocity_trend,
        "{{recommendations_section}}": "\n".join(f"- {item}" for item in recommendations),
    }

    markdown = template
    for needle, replacement in replacements.items():
        markdown = markdown.replace(needle, replacement)
    return markdown


def build_report(doc: dict[str, Any], template: str) -> dict[str, Any]:
    """Build report metadata and rendered Markdown."""
    completed_count = len(doc.get("completed", []))
    velocity_average, velocity_trend = compute_velocity(list(doc.get("history", [])), completed_count)
    recommendations = build_recommendations(doc, completed_count, velocity_average)
    markdown = render_markdown(template, doc=doc, velocity_average=velocity_average, velocity_trend=velocity_trend)
    return {
        "periodStart": doc.get("periodStart"),
        "periodEnd": doc.get("periodEnd"),
        "metrics": {
            "completedCount": completed_count,
            "carriedOverCount": len(doc.get("carriedOver", [])),
            "createdCount": len(doc.get("created", [])),
            "dueNextWeekCount": len(doc.get("dueNextWeek", [])),
            "velocityAverage": velocity_average,
            "velocityTrend": velocity_trend,
        },
        "recommendations": recommendations,
        "markdown": markdown,
    }


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    payload = load_json(Path(args.input))
    template = load_text(Path(args.template))
    print(json.dumps(build_report(payload, template), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
