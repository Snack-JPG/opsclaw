#!/usr/bin/env python3
"""Google Calendar wrapper built on top of gws."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def run_gws(command: list[str]) -> Any:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown gws error"
        raise RuntimeError(f"{' '.join(command)} failed: {stderr}")
    stdout = completed.stdout.strip()
    if not stdout:
        return {}
    return json.loads(stdout)


def gws_calendar(resource: str, method: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
    command = ["gws", "calendar", resource, method]
    if params is not None:
        command.extend(["--params", json.dumps(params)])
    if body is not None:
        command.extend(["--json", json.dumps(body)])
    return run_gws(command)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@dataclass(frozen=True)
class CalendarEntry:
    id: str
    label: str
    enabled: bool
    monitor: bool
    include_in_availability: bool
    include_in_conflicts: bool


@dataclass(frozen=True)
class CalendarConfig:
    timezone: str
    minimum_buffer_minutes: int
    availability_granularity_minutes: int
    calendars: list[CalendarEntry]

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "CalendarConfig":
        defaults = doc.get("defaults", {})
        calendars = [
            CalendarEntry(
                id=str(item["id"]),
                label=str(item.get("label") or item["id"]),
                enabled=bool(item.get("enabled", True)),
                monitor=bool(item.get("monitor", True)),
                include_in_availability=bool(item.get("includeInAvailability", True)),
                include_in_conflicts=bool(item.get("includeInConflicts", True)),
            )
            for item in doc.get("calendars", [])
        ]
        if not calendars:
            raise ValueError("calendars.json must define at least one calendar.")
        return cls(
            timezone=str(doc.get("timezone") or "UTC"),
            minimum_buffer_minutes=int(defaults.get("minimumBufferMinutes", 10)),
            availability_granularity_minutes=int(defaults.get("availabilityGranularityMinutes", 15)),
            calendars=calendars,
        )

    def monitored(self) -> list[CalendarEntry]:
        return [entry for entry in self.calendars if entry.enabled and entry.monitor]

    def availability_calendars(self) -> list[CalendarEntry]:
        return [entry for entry in self.calendars if entry.enabled and entry.include_in_availability]

    def conflict_calendars(self) -> set[str]:
        return {entry.id for entry in self.calendars if entry.enabled and entry.include_in_conflicts}


def parse_event_time(event: dict[str, Any], field: str) -> tuple[datetime, bool]:
    payload = event.get(field, {})
    if isinstance(payload, dict):
        if "dateTime" in payload:
            return parse_iso_datetime(payload["dateTime"]), False
        if "date" in payload:
            base = date.fromisoformat(payload["date"])
            return datetime.combine(base, time.min, tzinfo=timezone.utc), True
    if isinstance(payload, str):
        return parse_iso_datetime(payload), False
    raise ValueError(f"Event missing {field} time payload.")


def normalize_google_event(event: dict[str, Any], calendar: CalendarEntry) -> dict[str, Any]:
    start_dt, is_all_day = parse_event_time(event, "start")
    end_dt, _ = parse_event_time(event, "end")
    attendees = [
        {
            "email": attendee.get("email"),
            "displayName": attendee.get("displayName"),
            "responseStatus": attendee.get("responseStatus"),
            "optional": attendee.get("optional", False),
        }
        for attendee in event.get("attendees", []) or []
    ]
    organizer = event.get("organizer") or {}
    creator = event.get("creator") or {}
    return {
        "id": event.get("id"),
        "calendarId": calendar.id,
        "calendarLabel": calendar.label,
        "summary": event.get("summary") or "(untitled event)",
        "description": event.get("description") or "",
        "location": event.get("location") or "",
        "status": event.get("status") or "confirmed",
        "htmlLink": event.get("htmlLink"),
        "start": isoformat_utc(start_dt),
        "end": isoformat_utc(end_dt),
        "isAllDay": is_all_day,
        "attendees": attendees,
        "attendeeCount": len(attendees),
        "organizer": {
            "email": organizer.get("email"),
            "displayName": organizer.get("displayName"),
            "self": organizer.get("self", False),
        },
        "creator": {
            "email": creator.get("email"),
            "displayName": creator.get("displayName"),
            "self": creator.get("self", False),
        },
        "meetingLink": event.get("hangoutLink")
        or (((event.get("conferenceData") or {}).get("entryPoints") or [{}])[0]).get("uri"),
        "updated": event.get("updated"),
    }


def event_sort_key(event: dict[str, Any]) -> tuple[datetime, datetime, str]:
    return (
        parse_iso_datetime(event["start"]),
        parse_iso_datetime(event["end"]),
        event.get("id") or "",
    )


class GoogleCalendarClient:
    def __init__(self, config: CalendarConfig) -> None:
        self._config = config

    def list_events(self, start: datetime, end: datetime, calendars: list[CalendarEntry] | None = None) -> list[dict[str, Any]]:
        active = calendars or self._config.monitored()
        normalized: list[dict[str, Any]] = []
        for calendar in active:
            response = gws_calendar(
                "events",
                "list",
                params={
                    "calendarId": calendar.id,
                    "timeMin": isoformat_utc(start),
                    "timeMax": isoformat_utc(end),
                    "singleEvents": True,
                    "orderBy": "startTime",
                },
            )
            for raw_event in response.get("items", []) or []:
                if raw_event.get("status") == "cancelled":
                    continue
                normalized.append(normalize_google_event(raw_event, calendar))
        return sorted(normalized, key=event_sort_key)

    def get_event(self, calendar_id: str, event_id: str) -> dict[str, Any]:
        calendar = next((item for item in self._config.calendars if item.id == calendar_id), None)
        if calendar is None:
            raise ValueError(f"Calendar not found in config: {calendar_id}")
        response = gws_calendar("events", "get", params={"calendarId": calendar_id, "eventId": event_id})
        return normalize_google_event(response, calendar)

    def create_event(self, calendar_id: str, event_doc: dict[str, Any]) -> dict[str, Any]:
        calendar = next((item for item in self._config.calendars if item.id == calendar_id), None)
        if calendar is None:
            raise ValueError(f"Calendar not found in config: {calendar_id}")
        response = gws_calendar("events", "insert", params={"calendarId": calendar_id}, body=event_doc)
        return normalize_google_event(response, calendar)

    def update_event(self, calendar_id: str, event_id: str, event_doc: dict[str, Any]) -> dict[str, Any]:
        calendar = next((item for item in self._config.calendars if item.id == calendar_id), None)
        if calendar is None:
            raise ValueError(f"Calendar not found in config: {calendar_id}")
        response = gws_calendar(
            "events",
            "patch",
            params={"calendarId": calendar_id, "eventId": event_id, "sendUpdates": "all"},
            body=event_doc,
        )
        return normalize_google_event(response, calendar)

    def delete_event(self, calendar_id: str, event_id: str) -> dict[str, Any]:
        gws_calendar("events", "delete", params={"calendarId": calendar_id, "eventId": event_id, "sendUpdates": "all"})
        return {"status": "deleted", "calendarId": calendar_id, "eventId": event_id}


def compute_window(name: str, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    local_now = utc_now().astimezone(zone)

    if name == "today":
        start_local = datetime.combine(local_now.date(), time.min, tzinfo=zone)
        end_local = start_local + timedelta(days=1)
    elif name == "tomorrow":
        start_local = datetime.combine(local_now.date() + timedelta(days=1), time.min, tzinfo=zone)
        end_local = start_local + timedelta(days=1)
    elif name == "week":
        weekday_offset = local_now.weekday()
        start_local = datetime.combine(local_now.date() - timedelta(days=weekday_offset), time.min, tzinfo=zone)
        end_local = start_local + timedelta(days=7)
    else:
        raise ValueError(f"Unsupported window: {name}")
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def detect_conflicts(events: list[dict[str, Any]], conflict_calendar_ids: set[str], minimum_buffer_minutes: int) -> list[dict[str, Any]]:
    relevant = [event for event in events if event.get("calendarId") in conflict_calendar_ids]
    ordered = sorted(relevant, key=event_sort_key)
    conflicts: list[dict[str, Any]] = []
    minimum_buffer = timedelta(minutes=minimum_buffer_minutes)

    for current, nxt in zip(ordered, ordered[1:]):
        current_end = parse_iso_datetime(current["end"])
        next_start = parse_iso_datetime(nxt["start"])
        next_end = parse_iso_datetime(nxt["end"])

        if next_start < current_end:
            conflicts.append(
                {"type": "overlap", "eventIds": [current.get("id"), nxt.get("id")], "events": [current, nxt], "minutes": int((current_end - next_start).total_seconds() // 60)}
            )
            continue

        gap = next_start - current_end
        if gap < minimum_buffer:
            conflicts.append(
                {"type": "buffer", "eventIds": [current.get("id"), nxt.get("id")], "events": [current, nxt], "minutes": int(gap.total_seconds() // 60)}
            )

        if current.get("location") and nxt.get("location") and current["location"] != nxt["location"] and gap < timedelta(minutes=30):
            conflicts.append(
                {"type": "travel", "eventIds": [current.get("id"), nxt.get("id")], "events": [current, nxt], "minutes": int(gap.total_seconds() // 60)}
            )

        if next_end < current_end:
            conflicts.append(
                {"type": "nested_overlap", "eventIds": [current.get("id"), nxt.get("id")], "events": [current, nxt], "minutes": int((current_end - next_end).total_seconds() // 60)}
            )
    return conflicts


def check_availability(events: list[dict[str, Any]], start: datetime, end: datetime, minimum_buffer_minutes: int) -> dict[str, Any]:
    minimum_buffer = timedelta(minutes=minimum_buffer_minutes)
    blocked_by: list[dict[str, Any]] = []

    for event in events:
        event_start = parse_iso_datetime(event["start"])
        event_end = parse_iso_datetime(event["end"])
        buffered_start = event_start - minimum_buffer
        buffered_end = event_end + minimum_buffer
        overlaps = start < buffered_end and end > buffered_start
        if overlaps:
            blocked_by.append(event)

    return {
        "available": not blocked_by,
        "start": isoformat_utc(start),
        "end": isoformat_utc(end),
        "bufferMinutes": minimum_buffer_minutes,
        "blockingEvents": blocked_by,
    }


def next_event(events: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any] | None:
    reference = now or utc_now()
    for event in sorted(events, key=event_sort_key):
        if parse_iso_datetime(event["end"]) > reference:
            return event
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_shared_window_args(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--start", help="ISO timestamp for the query start.")
        cmd.add_argument("--end", help="ISO timestamp for the query end.")
        cmd.add_argument("--window", choices=["today", "tomorrow", "week"], help="Named time window.")

    list_parser = subparsers.add_parser("list-events", help="List events from monitored calendars.")
    list_parser.add_argument("--token-path", type=Path, help="Ignored: gws handles auth centrally.")
    list_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    add_shared_window_args(list_parser)

    next_parser = subparsers.add_parser("next-event", help="Return the next event.")
    next_parser.add_argument("--token-path", type=Path, help="Ignored: gws handles auth centrally.")
    next_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    next_parser.add_argument("--lookahead-hours", type=int, default=24, help="Hours of future events to fetch.")

    availability_parser = subparsers.add_parser("availability", help="Check whether a slot is free.")
    availability_parser.add_argument("--token-path", type=Path, help="Ignored: gws handles auth centrally.")
    availability_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    availability_parser.add_argument("--start", required=True, help="Requested start timestamp.")
    availability_parser.add_argument("--end", required=True, help="Requested end timestamp.")

    create_parser = subparsers.add_parser("create-event", help="Create an event from a JSON document.")
    create_parser.add_argument("--token-path", type=Path, help="Ignored: gws handles auth centrally.")
    create_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    create_parser.add_argument("--calendar-id", required=True, help="Target Google calendar ID.")
    create_parser.add_argument("--event-path", type=Path, required=True, help="Path to a Google event JSON body.")

    get_parser = subparsers.add_parser("get-event", help="Fetch a single event.")
    get_parser.add_argument("--token-path", type=Path, help="Ignored: gws handles auth centrally.")
    get_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    get_parser.add_argument("--calendar-id", required=True, help="Target Google calendar ID.")
    get_parser.add_argument("--event-id", required=True, help="Google Calendar event ID.")

    update_parser = subparsers.add_parser("update-event", help="Patch an existing event from a JSON document.")
    update_parser.add_argument("--token-path", type=Path, help="Ignored: gws handles auth centrally.")
    update_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    update_parser.add_argument("--calendar-id", required=True, help="Target Google calendar ID.")
    update_parser.add_argument("--event-id", required=True, help="Google Calendar event ID.")
    update_parser.add_argument("--event-path", type=Path, required=True, help="Path to a partial Google event JSON body.")

    delete_parser = subparsers.add_parser("delete-event", help="Delete an event.")
    delete_parser.add_argument("--token-path", type=Path, help="Ignored: gws handles auth centrally.")
    delete_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    delete_parser.add_argument("--calendar-id", required=True, help="Target Google calendar ID.")
    delete_parser.add_argument("--event-id", required=True, help="Google Calendar event ID.")

    conflicts_parser = subparsers.add_parser("conflicts", help="Detect overlaps from events JSON.")
    conflicts_parser.add_argument("--events-path", type=Path, required=True, help="Path to normalized events JSON.")
    conflicts_parser.add_argument("--calendars-path", type=Path, required=True, help="Path to calendars.json.")
    return parser.parse_args()


def resolve_window(args: argparse.Namespace, timezone_name: str) -> tuple[datetime, datetime]:
    if getattr(args, "start", None) and getattr(args, "end", None):
        return parse_iso_datetime(args.start), parse_iso_datetime(args.end)
    if getattr(args, "window", None):
        return compute_window(args.window, timezone_name)
    raise ValueError("Specify either --start and --end, or --window.")


def load_events_payload(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return payload["events"]
    raise ValueError("Expected a JSON list or object with an 'events' list.")


def main() -> int:
    args = parse_args()

    try:
        if args.command == "conflicts":
            config = CalendarConfig.from_doc(load_json(args.calendars_path))
            events = load_events_payload(args.events_path)
            result = {"ok": True, "conflicts": detect_conflicts(events, config.conflict_calendars(), config.minimum_buffer_minutes)}
        else:
            config = CalendarConfig.from_doc(load_json(args.calendars_path))
            client = GoogleCalendarClient(config)

            if args.command == "list-events":
                start, end = resolve_window(args, config.timezone)
                events = client.list_events(start, end)
                result = {"ok": True, "events": events, "count": len(events), "start": isoformat_utc(start), "end": isoformat_utc(end)}
            elif args.command == "next-event":
                start = utc_now()
                end = start + timedelta(hours=args.lookahead_hours)
                events = client.list_events(start, end)
                result = {"ok": True, "nextEvent": next_event(events, start), "count": len(events), "start": isoformat_utc(start), "end": isoformat_utc(end)}
            elif args.command == "availability":
                start = parse_iso_datetime(args.start)
                end = parse_iso_datetime(args.end)
                if end <= start:
                    raise ValueError("Availability check requires end > start.")
                events = client.list_events(start - timedelta(minutes=config.minimum_buffer_minutes), end + timedelta(minutes=config.minimum_buffer_minutes), calendars=config.availability_calendars())
                result = {"ok": True, **check_availability(events, start, end, config.minimum_buffer_minutes)}
            elif args.command == "create-event":
                event_doc = load_json(args.event_path)
                result = {"ok": True, "event": client.create_event(args.calendar_id, event_doc)}
            elif args.command == "get-event":
                result = {"ok": True, "event": client.get_event(args.calendar_id, args.event_id)}
            elif args.command == "update-event":
                event_doc = load_json(args.event_path)
                result = {"ok": True, "event": client.update_event(args.calendar_id, args.event_id, event_doc)}
            elif args.command == "delete-event":
                result = {"ok": True, **client.delete_event(args.calendar_id, args.event_id)}
            else:
                raise ValueError(f"Unsupported command: {args.command}")
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc), "command": args.command}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
