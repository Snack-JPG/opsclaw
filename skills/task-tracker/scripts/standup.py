#!/usr/bin/env python3
"""Daily standup generator for normalized task snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Generate a daily standup from normalized task JSON.")
    parser.add_argument("--input", required=True, help="Path to a JSON file containing standup task buckets.")
    parser.add_argument("--date", help="Override report date in YYYY-MM-DD.")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def format_task(task: dict[str, Any]) -> str:
    """Render one task line for the standup text block."""
    title = str(task.get("title") or task.get("name") or "(untitled task)")
    details: list[str] = []
    if task.get("priority"):
        details.append(f"priority: {task['priority']}")
    if task.get("dueDate"):
        details.append(f"due: {task['dueDate']}")
    if task.get("assignee"):
        details.append(f"owner: {task['assignee']}")
    if details:
        return f"- {title} ({'; '.join(details)})"
    return f"- {title}"


def format_blocked_task(task: dict[str, Any]) -> str:
    """Render one blocked task line."""
    title = str(task.get("title") or task.get("name") or "(untitled task)")
    reason = str(task.get("blockReason") or task.get("reason") or "No reason recorded")
    return f"- {title} - {reason}"


def render_section(title: str, items: list[dict[str, Any]], *, formatter: Any = format_task) -> str:
    """Render a standup section."""
    lines = [title]
    if not items:
        lines.append("- None")
        return "\n".join(lines)
    lines.extend(formatter(item) for item in items)
    return "\n".join(lines)


def build_standup(doc: dict[str, Any], report_date: str) -> dict[str, Any]:
    """Build standup text and summary counts."""
    completed = list(doc.get("completedYesterday", []))
    in_progress = list(doc.get("inProgress", []))
    blocked = list(doc.get("blocked", []))
    due_today = list(doc.get("dueToday", []))
    overdue = list(doc.get("overdue", []))

    sections = [
        render_section("Done Yesterday", completed),
        render_section("In Progress", in_progress),
        render_section("Blocked", blocked, formatter=format_blocked_task),
        render_section("Due Today", due_today),
    ]
    if overdue:
        sections.append(render_section("Overdue", overdue))

    text = "\n\n".join([f"Standup\nDate: {report_date}", *sections])
    return {
        "date": report_date,
        "counts": {
            "completedYesterday": len(completed),
            "inProgress": len(in_progress),
            "blocked": len(blocked),
            "dueToday": len(due_today),
            "overdue": len(overdue),
        },
        "sections": {
            "completedYesterday": completed,
            "inProgress": in_progress,
            "blocked": blocked,
            "dueToday": due_today,
            "overdue": overdue,
        },
        "text": text,
    }


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    payload = load_json(Path(args.input))
    report_date = args.date or payload.get("date") or date.today().isoformat()
    print(json.dumps(build_standup(payload, report_date), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
