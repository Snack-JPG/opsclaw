#!/usr/bin/env python3
"""Generate a unified daily ops briefing from normalized skill outputs."""

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


def load_text(path: Path) -> str:
    """Load UTF-8 text from disk."""
    return path.read_text(encoding="utf-8")


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


def summarize_item(item: dict[str, Any], keys: list[str]) -> str:
    """Build a concise single-line summary from a dictionary."""
    parts: list[str] = []
    for key in keys:
        value = item.get(key)
        if value in (None, "", []):
            continue
        parts.append(str(value))
    return " | ".join(parts) if parts else "No detail available."


def format_bullets(lines: list[str], empty_text: str) -> str:
    """Render a list of strings as bullets."""
    if not lines:
        return f"- {empty_text}"
    return "\n".join(f"- {line}" for line in lines)


def render_email_section(email: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
    """Render email-specific summary text plus derived priorities and recommendations."""
    if not email:
        return "- Source unavailable.", [], ["Confirm email sync health; daily brief is missing inbox context."]

    priorities: list[str] = []
    recommendations: list[str] = []
    urgent_items = list(email.get("urgentItems", []))
    needs_response = list(email.get("needsResponse", []))
    unread_count = safe_int(email.get("unreadCount"))
    urgent_count = safe_int(email.get("urgentCount"), len(urgent_items))
    auto_handled = safe_int(email.get("autoHandledCount"))

    if urgent_count:
        priorities.append(f"{urgent_count} urgent email item(s) need review.")
        recommendations.append("Clear urgent email items before the second meeting block.")
    if unread_count >= 10:
        recommendations.append("Protect a focused inbox triage block; the response queue is elevated.")

    lines = [
        f"Unread: {unread_count}",
        f"Urgent: {urgent_count}",
        f"Auto-handled: {auto_handled}",
        "Urgent items:",
        format_bullets(
            [
                summarize_item(item, ["from", "subject", "summary"])
                for item in urgent_items[:5]
            ],
            "None",
        ),
        "Needs response:",
        format_bullets(
            [
                summarize_item(item, ["from", "subject", "urgency", "summary"])
                for item in needs_response[:5]
            ],
            "None",
        ),
    ]
    return "\n".join(lines), priorities, recommendations


def render_calendar_section(calendar: dict[str, Any] | None) -> tuple[str, list[str], list[str], float]:
    """Render calendar summary and compute meeting load."""
    if not calendar:
        return "- Source unavailable.", [], ["Verify calendar sync; meeting context is missing from the brief."], 0.0

    priorities: list[str] = []
    recommendations: list[str] = []
    meetings = list(calendar.get("meetings", []))
    conflicts = list(calendar.get("conflicts", []))
    free_blocks = list(calendar.get("freeBlocks", []))
    event_count = safe_int(calendar.get("eventCount"), len(meetings))
    meeting_hours = sum(
        safe_float(item.get("durationHours"))
        for item in meetings
        if item.get("durationHours") is not None
    )

    prep_pending = [
        item for item in meetings if str(item.get("prepStatus") or "unknown").lower() not in {"ready", "done", "not_needed"}
    ]
    if conflicts:
        priorities.append(f"{len(conflicts)} calendar conflict(s) or buffer warnings need attention.")
        recommendations.append("Resolve calendar conflicts before the day compounds.")
    if prep_pending:
        priorities.append(f"{len(prep_pending)} meeting(s) still need prep.")
    if event_count >= 6:
        recommendations.append("Protect focus time; the calendar is dense today.")

    lines = [
        f"Events today: {event_count}",
        f"Estimated meeting hours: {meeting_hours:.1f}",
        "Meetings:",
        format_bullets(
            [
                summarize_item(item, ["start", "end", "title", "prepStatus"])
                for item in meetings[:8]
            ],
            "No meetings scheduled.",
        ),
        "Free blocks:",
        format_bullets([str(block) for block in free_blocks[:5]], "No substantial free blocks."),
        "Conflicts:",
        format_bullets([str(item) for item in conflicts[:5]], "None"),
    ]
    return "\n".join(lines), priorities, recommendations, meeting_hours


def render_tasks_section(tasks: dict[str, Any] | None) -> tuple[str, list[str], list[str], int]:
    """Render task summary and compute focus load contribution."""
    if not tasks:
        return "- Source unavailable.", [], ["Verify task provider sync; delivery risk may be underreported."], 0

    priorities: list[str] = []
    recommendations: list[str] = []
    due_today = list(tasks.get("dueToday", []))
    overdue = list(tasks.get("overdue", []))
    blocked = list(tasks.get("blocked", []))
    due_today_count = safe_int(tasks.get("dueTodayCount"), len(due_today))
    overdue_count = safe_int(tasks.get("overdueCount"), len(overdue))
    blocked_count = safe_int(tasks.get("blockedCount"), len(blocked))

    if overdue_count:
        priorities.append(f"{overdue_count} overdue task(s) need a decision.")
        recommendations.append("Clear or re-plan overdue tasks before taking on new work.")
    if blocked_count:
        priorities.append(f"{blocked_count} blocked task(s) are reducing execution velocity.")
        recommendations.append("Remove blockers early to recover task throughput.")
    if due_today_count >= 4:
        recommendations.append("The due-today queue is crowded; cut or delegate lower-priority items.")

    lines = [
        f"Due today: {due_today_count}",
        f"Overdue: {overdue_count}",
        f"Blocked: {blocked_count}",
        f"Completed last 7 days: {safe_int(tasks.get('completedLast7Days'))}",
        "Due today detail:",
        format_bullets(
            [
                summarize_item(item, ["title", "priority", "assignee"])
                for item in due_today[:6]
            ],
            "None",
        ),
        "Overdue detail:",
        format_bullets(
            [
                summarize_item(item, ["title", "ageDays", "priority"])
                for item in overdue[:6]
            ],
            "None",
        ),
        "Blocked detail:",
        format_bullets(
            [
                summarize_item(item, ["title", "blockReason"])
                for item in blocked[:6]
            ],
            "None",
        ),
    ]
    return "\n".join(lines), priorities, recommendations, due_today_count + overdue_count + blocked_count


def render_crm_section(crm: dict[str, Any] | None) -> tuple[str, list[str], list[str]]:
    """Render CRM summary text."""
    if not crm:
        return "- Source unavailable.", [], ["Verify CRM sync; client and pipeline risk is missing from the brief."]

    priorities: list[str] = []
    recommendations: list[str] = []
    follow_ups_due = list(crm.get("followUpsDue", []))
    at_risk_clients = list(crm.get("atRiskClients", []))
    pipeline = dict(crm.get("pipeline", {}))
    follow_up_count = safe_int(crm.get("followUpsDueCount"), len(follow_ups_due))
    at_risk_count = safe_int(crm.get("atRiskClientCount"), len(at_risk_clients))

    if at_risk_count:
        priorities.append(f"{at_risk_count} at-risk client(s) need proactive outreach.")
        recommendations.append("Schedule outreach for at-risk clients before lower-leverage admin.")
    if follow_up_count:
        priorities.append(f"{follow_up_count} CRM follow-up(s) are due.")
    if safe_float(pipeline.get("weightedValue")) <= 0:
        recommendations.append("Pipeline visibility is weak; verify CRM hygiene and deal probabilities.")

    lines = [
        f"Follow-ups due: {follow_up_count}",
        f"At-risk clients: {at_risk_count}",
        f"Open pipeline value: {safe_float(pipeline.get('openValue')):.2f}",
        f"Weighted pipeline value: {safe_float(pipeline.get('weightedValue')):.2f}",
        f"Won this week: {safe_float(pipeline.get('wonThisWeek')):.2f}",
        "Follow-up detail:",
        format_bullets(
            [
                summarize_item(item, ["client", "daysOverdue", "recommendedAction"])
                for item in follow_ups_due[:5]
            ],
            "None",
        ),
        "At-risk clients:",
        format_bullets(
            [
                summarize_item(item, ["name", "healthScore", "reason"])
                for item in at_risk_clients[:5]
            ],
            "None",
        ),
    ]
    return "\n".join(lines), priorities, recommendations


def dedupe_keep_order(items: list[str]) -> list[str]:
    """Deduplicate while preserving order."""
    seen: set[str] = set()
    results: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(normalized)
    return results


def estimate_focus_load(
    *,
    urgent_count: int,
    meeting_hours: float,
    task_pressure: int,
    follow_up_count: int,
) -> str:
    """Estimate the day's focus load from aggregate signals."""
    load_score = urgent_count * 2 + task_pressure + follow_up_count + int(round(meeting_hours))
    if load_score >= 16:
        return f"Heavy ({load_score}/20): protect priorities and defer low-value work."
    if load_score >= 9:
        return f"Moderate ({load_score}/20): manageable if priorities stay tight."
    return f"Light ({load_score}/20): capacity exists for strategic work."


def render_template(template: str, replacements: dict[str, str]) -> str:
    """Fill the Markdown template with computed values."""
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def build_daily_brief(payload: dict[str, Any], template: str) -> dict[str, Any]:
    """Build a structured daily brief result."""
    date = str(payload.get("date") or payload.get("generatedAt") or utc_now())[:10]
    timezone_name = str(payload.get("timezone") or "UTC")

    email_section, email_priorities, email_recommendations = render_email_section(payload.get("email"))
    calendar_section, calendar_priorities, calendar_recommendations, meeting_hours = render_calendar_section(payload.get("calendar"))
    tasks_section, task_priorities, task_recommendations, task_pressure = render_tasks_section(payload.get("tasks"))
    crm_section, crm_priorities, crm_recommendations = render_crm_section(payload.get("crm"))

    priorities = dedupe_keep_order(
        email_priorities + calendar_priorities + task_priorities + crm_priorities
    )[:3]
    recommendations = dedupe_keep_order(
        email_recommendations + calendar_recommendations + task_recommendations + crm_recommendations
    )[:5]

    urgent_count = safe_int(payload.get("email", {}).get("urgentCount"))
    follow_up_count = safe_int(payload.get("crm", {}).get("followUpsDueCount"))
    attention_lines = priorities or ["No critical issues detected from the available sources."]
    focus_load = estimate_focus_load(
        urgent_count=urgent_count,
        meeting_hours=meeting_hours,
        task_pressure=task_pressure,
        follow_up_count=follow_up_count,
    )

    markdown = render_template(
        template,
        {
            "{{date}}": date,
            "{{timezone}}": timezone_name,
            "{{attention_now}}": format_bullets(attention_lines, "None"),
            "{{email_section}}": email_section,
            "{{calendar_section}}": calendar_section,
            "{{tasks_section}}": tasks_section,
            "{{crm_section}}": crm_section,
            "{{priorities_section}}": format_bullets(priorities, "No major priorities identified."),
            "{{recommendations_section}}": format_bullets(recommendations, "No additional recommendations."),
            "{{focus_load}}": focus_load,
        },
    )

    return {
        "reportType": "daily_ops_brief",
        "generatedAt": str(payload.get("generatedAt") or utc_now()),
        "date": date,
        "timezone": timezone_name,
        "topPriorities": priorities,
        "recommendations": recommendations,
        "focusLoad": focus_load,
        "sections": {
            "email": email_section,
            "calendar": calendar_section,
            "tasks": tasks_section,
            "crm": crm_section,
        },
        "markdown": markdown,
    }


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to normalized daily brief input JSON.")
    parser.add_argument("--template", type=Path, required=True, help="Path to the Markdown brief template.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    try:
        payload = load_json(args.input)
        template = load_text(args.template)
        report = build_daily_brief(payload, template)
        json.dump(report, sys.stdout, indent=2 if args.pretty else None)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
