#!/usr/bin/env python3
"""Generate a daily schedule briefing from normalized or live gws calendar data."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_local(dt: datetime, timezone_name: str) -> str:
    zone = ZoneInfo(timezone_name)
    return dt.astimezone(zone).strftime("%H:%M")


def load_events(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return payload["events"]
    raise ValueError("Expected a JSON list or an object with an 'events' list.")


def fetch_events(calendars_path: Path, window: str) -> list[dict[str, Any]]:
    script_path = Path(__file__).with_name("gcal-client.py")
    completed = subprocess.run(
        [sys.executable, str(script_path), "list-events", "--calendars-path", str(calendars_path), "--window", window],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "gcal-client failed")
    payload = json.loads(completed.stdout)
    return payload.get("events", [])


def sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        events,
        key=lambda item: (
            parse_iso_datetime(item["start"]),
            parse_iso_datetime(item["end"]),
            item.get("id") or "",
        ),
    )


def event_needs_prep(event: dict[str, Any], prep_rules: dict[str, Any]) -> bool:
    defaults = prep_rules.get("defaults", {})
    if not defaults.get("enabled", True):
        return False

    title = str(event.get("summary") or "").lower()
    attendees = [str(item.get("email") or "").lower() for item in event.get("attendees", [])]
    for rule in prep_rules.get("rules", []):
        if not rule.get("enabled", True):
            continue
        match = rule.get("match", {})
        keyword_match = any(keyword.lower() in title for keyword in match.get("titleKeywords", []))
        attendee_match = any(email in attendees for email in [entry.lower() for entry in match.get("attendeeEmails", [])])
        if keyword_match or attendee_match:
            return bool(rule.get("requirePrep", True))

    if defaults.get("requirePrepForExternalAttendees", True):
        internal_domains = {str(domain).lower() for domain in prep_rules.get("internalDomains", [])}
        for email in attendees:
            if "@" not in email:
                continue
            if email.split("@", 1)[1] not in internal_domains:
                return True
    return False


def detect_conflicts(events: list[dict[str, Any]], minimum_buffer_minutes: int) -> list[str]:
    ordered = sort_events(events)
    warnings: list[str] = []
    minimum_buffer = timedelta(minutes=minimum_buffer_minutes)

    for current, nxt in zip(ordered, ordered[1:]):
        current_end = parse_iso_datetime(current["end"])
        next_start = parse_iso_datetime(nxt["start"])
        if next_start < current_end:
            overlap_minutes = int((current_end - next_start).total_seconds() // 60)
            warnings.append(f"Conflict: '{current.get('summary')}' overlaps '{nxt.get('summary')}' by {overlap_minutes}m.")
            continue

        gap = next_start - current_end
        if gap < minimum_buffer:
            warnings.append(
                f"Tight buffer: only {int(gap.total_seconds() // 60)}m between '{current.get('summary')}' and '{nxt.get('summary')}'."
            )

        if current.get("location") and nxt.get("location") and current["location"] != nxt["location"] and gap < timedelta(minutes=30):
            warnings.append(
                f"Travel risk: '{current.get('summary')}' at {current['location']} is followed by '{nxt.get('summary')}' at {nxt['location']}."
            )
    return warnings


def compute_free_blocks(events: list[dict[str, Any]], timezone_name: str) -> list[str]:
    ordered = sort_events(events)
    if not ordered:
        return ["Free all day."]

    zone = ZoneInfo(timezone_name)
    first_start = parse_iso_datetime(ordered[0]["start"]).astimezone(zone)
    day_start = datetime.combine(first_start.date(), time(hour=8), tzinfo=zone)
    day_end = datetime.combine(first_start.date(), time(hour=18), tzinfo=zone)

    free_blocks: list[str] = []
    cursor = day_start
    for event in ordered:
        start = parse_iso_datetime(event["start"]).astimezone(zone)
        end = parse_iso_datetime(event["end"]).astimezone(zone)
        if start - cursor >= timedelta(minutes=45):
            free_blocks.append(f"{cursor.strftime('%H:%M')} - {start.strftime('%H:%M')}")
        if end > cursor:
            cursor = end
    if day_end - cursor >= timedelta(minutes=45):
        free_blocks.append(f"{cursor.strftime('%H:%M')} - {day_end.strftime('%H:%M')}")
    return free_blocks or ["No substantial free blocks."]


def next_meeting(events: list[dict[str, Any]], reference: datetime | None = None) -> dict[str, Any] | None:
    now = reference or datetime.now(timezone.utc)
    for event in sort_events(events):
        if parse_iso_datetime(event["end"]) > now:
            return event
    return None


def generate_briefing(events: list[dict[str, Any]], ops_state: dict[str, Any], prep_rules: dict[str, Any], timezone_name: str, minimum_buffer_minutes: int) -> str:
    ordered = sort_events(events)
    calendar_state = ops_state.get("calendar", {})
    prep_status = calendar_state.get("prepStatus", {})
    lines = ["Schedule Briefing", ""]

    if not ordered:
        lines.append("No events on the calendar for this window.")
        return "\n".join(lines)

    first = parse_iso_datetime(ordered[0]["start"]).astimezone(ZoneInfo(timezone_name))
    lines.append(f"Date: {first.strftime('%A %d %B %Y')}")
    lines.append(f"Timezone: {timezone_name}")
    lines.append("")

    lines.append("Timeline")
    for event in ordered:
        start = format_local(parse_iso_datetime(event["start"]), timezone_name)
        end = format_local(parse_iso_datetime(event["end"]), timezone_name)
        prep_needed = event_needs_prep(event, prep_rules)
        prep_state = prep_status.get(event.get("id") or "", "pending" if prep_needed else "not_needed")
        attendees = ", ".join(attendee.get("displayName") or attendee.get("email") or "Unknown" for attendee in event.get("attendees", [])[:3])
        attendee_suffix = f" | attendees: {attendees}" if attendees else ""
        location_suffix = f" | location: {event.get('location')}" if event.get("location") else ""
        lines.append(
            f"- {start}-{end} {event.get('summary')} [{event.get('calendarLabel', event.get('calendarId', 'calendar'))}] | prep: {prep_state}{location_suffix}{attendee_suffix}"
        )
    lines.append("")

    lines.append("Free Blocks")
    for block in compute_free_blocks(ordered, timezone_name):
        lines.append(f"- {block}")
    lines.append("")

    lines.append("Warnings")
    warnings = detect_conflicts(ordered, minimum_buffer_minutes)
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("Next Up")
    upcoming = next_meeting(ordered)
    if upcoming:
        starts = format_local(parse_iso_datetime(upcoming["start"]), timezone_name)
        lines.append(f"- {starts} {upcoming.get('summary')} | prep: {prep_status.get(upcoming.get('id') or '', 'unknown')}")
    else:
        lines.append("- No remaining meetings.")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-path", type=Path, help="Path to normalized events JSON.")
    parser.add_argument("--calendars-path", type=Path, help="Path to calendars.json for live mode.")
    parser.add_argument("--window", default="today", choices=["today", "tomorrow", "week"], help="Calendar window in live mode.")
    parser.add_argument("--ops-state", type=Path, required=True, help="Path to workspace/ops-state.json.")
    parser.add_argument("--prep-rules", type=Path, required=True, help="Path to prep-rules.json.")
    parser.add_argument("--timezone", default=None, help="Override timezone from prep or ops state.")
    parser.add_argument("--minimum-buffer-minutes", type=int, default=10, help="Conflict buffer threshold.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.events_path:
            events = load_events(args.events_path)
        else:
            if not args.calendars_path:
                raise ValueError("--calendars-path is required when fetching live calendar data.")
            events = fetch_events(args.calendars_path, args.window)
        ops_state = load_json(args.ops_state)
        prep_rules = load_json(args.prep_rules)
        timezone_name = args.timezone or load_json(args.calendars_path).get("timezone", "UTC") if args.calendars_path else args.timezone or "UTC"
        briefing = generate_briefing(events, ops_state, prep_rules, timezone_name, args.minimum_buffer_minutes)
        sys.stdout.write(briefing + "\n")
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
