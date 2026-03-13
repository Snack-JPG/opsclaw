#!/usr/bin/env python3
"""Generate meeting prep documents using gws calendar and gmail context."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_module(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GMAIL_HELPERS = load_module("opsclaw_email_gws_gmail", REPO_ROOT / "skills" / "email-intel" / "scripts" / "gws_gmail.py")


def load_json(path: Path | None) -> Any:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_event(calendars_path: Path, calendar_id: str, event_id: str) -> dict[str, Any]:
    script_path = Path(__file__).with_name("gcal-client.py")
    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "get-event",
            "--calendars-path",
            str(calendars_path),
            "--calendar-id",
            calendar_id,
            "--event-id",
            event_id,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "gcal-client get-event failed")
    payload = json.loads(completed.stdout)
    return payload["event"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "meeting"


@dataclass(frozen=True)
class PrepDecision:
    required: bool
    priority: str
    reasons: list[str]


def event_duration_minutes(event_doc: dict[str, Any]) -> int:
    start = parse_iso_datetime(event_doc.get("start"))
    end = parse_iso_datetime(event_doc.get("end"))
    if not start or not end:
        return 0
    return max(0, int((end - start).total_seconds() // 60))


def attendee_emails(event_doc: dict[str, Any]) -> list[str]:
    attendees = event_doc.get("attendees", [])
    return [str(item.get("email")).lower() for item in attendees if item.get("email")]


def is_external_attendee(email: str, internal_domains: set[str]) -> bool:
    if "@" not in email:
        return False
    return email.split("@", 1)[1].lower() not in internal_domains


def should_generate_prep(event_doc: dict[str, Any], prep_rules: dict[str, Any], internal_domains: set[str]) -> PrepDecision:
    defaults = prep_rules.get("defaults", {})
    if not defaults.get("enabled", True):
        return PrepDecision(False, "low", ["prep disabled in defaults"])

    reasons: list[str] = []
    title = normalize_text(event_doc.get("summary")).lower()
    duration = event_duration_minutes(event_doc)
    if duration < int(defaults.get("minDurationMinutes", 20)):
        return PrepDecision(False, "low", [f"duration below minimum: {duration}m"])

    emails = attendee_emails(event_doc)
    external_present = any(is_external_attendee(email, internal_domains) for email in emails)
    if defaults.get("requirePrepForExternalAttendees", True) and external_present:
        reasons.append("external attendee present")

    if defaults.get("requirePrepForUnknownAttendees", False) and not emails:
        reasons.append("attendee list unavailable")

    priority = "medium"
    matched_explicit_rule = False
    for rule in prep_rules.get("rules", []):
        if not rule.get("enabled", True):
            continue
        match = rule.get("match", {})
        matched = False

        for keyword in match.get("titleKeywords", []):
            if keyword.lower() in title:
                matched = True
                reasons.append(f"rule '{rule.get('name', 'unnamed')}' matched title keyword '{keyword}'")
                break

        if not matched and match.get("attendeeEmails"):
            matched_emails = {email.lower() for email in match["attendeeEmails"]}
            if any(email in matched_emails for email in emails):
                matched = True
                reasons.append(f"rule '{rule.get('name', 'unnamed')}' matched attendee email")

        if matched:
            matched_explicit_rule = True
            priority = str(rule.get("priority") or priority)
            if not rule.get("requirePrep", True):
                return PrepDecision(False, priority, reasons)

    if matched_explicit_rule or reasons:
        return PrepDecision(True, priority, reasons)
    return PrepDecision(False, priority, ["no prep rule matched"])


def fetch_recent_interactions(event_doc: dict[str, Any], max_results: int) -> list[dict[str, Any]]:
    participants = attendee_emails(event_doc)[:4]
    subject = normalize_text(event_doc.get("summary"))
    query_terms = [f'from:{email}' for email in participants]
    if subject:
        query_terms.append(f'subject:"{subject[:40]}"')
    if not query_terms:
        return []
    query = " newer_than:30d ".join(query_terms) if len(query_terms) == 1 else "(" + " OR ".join(query_terms) + ") newer_than:30d"
    try:
        messages = GMAIL_HELPERS.list_messages(query=query, max_results=max_results, label_ids=["INBOX"], unread_only=False)
    except Exception:
        return []
    interactions: list[dict[str, Any]] = []
    for item in messages:
        interactions.append(
            {
                "timestamp": item.get("receivedAt"),
                "source": "gmail",
                "summary": normalize_text(item.get("subject")) + ": " + normalize_text(item.get("snippet") or item.get("body"))[:200],
            }
        )
    return interactions


def summarize_interactions(interactions_doc: Any, limit: int) -> list[str]:
    items = interactions_doc if isinstance(interactions_doc, list) else interactions_doc.get("interactions", [])
    summarized: list[str] = []
    for item in items[:limit]:
        when = normalize_text(item.get("timestamp") or item.get("date") or item.get("occurredAt"))
        source = normalize_text(item.get("source") or item.get("type") or "note")
        summary = normalize_text(item.get("summary") or item.get("snippet") or item.get("text"))
        if not summary:
            continue
        prefix = f"{when} [{source}] " if when else f"[{source}] "
        summarized.append(prefix + summary)
    return summarized


def build_attendee_notes(event_doc: dict[str, Any], attendee_context_doc: Any, crm_context_doc: Any) -> list[str]:
    notes: list[str] = []
    attendees = event_doc.get("attendees", [])
    attendee_context_map = attendee_context_doc if isinstance(attendee_context_doc, dict) else {}
    crm_entries = crm_context_doc.get("contacts", crm_context_doc) if isinstance(crm_context_doc, dict) else {}

    for attendee in attendees:
        email = str(attendee.get("email") or "").lower()
        display_name = attendee.get("displayName") or email or "Unknown attendee"
        context = attendee_context_map.get(email, {}) if isinstance(attendee_context_map, dict) else {}
        crm = crm_entries.get(email, {}) if isinstance(crm_entries, dict) else {}
        line_parts = [display_name]
        if crm.get("company"):
            line_parts.append(f"company={crm['company']}")
        if crm.get("tier"):
            line_parts.append(f"tier={crm['tier']}")
        if context.get("summary"):
            line_parts.append(f"context={normalize_text(context['summary'])}")
        if crm.get("notes"):
            line_parts.append(f"crm={normalize_text(crm['notes'])}")
        notes.append(" | ".join(line_parts))

    return notes


def infer_talking_points(event_doc: dict[str, Any], decision: PrepDecision, interactions: list[str]) -> list[str]:
    talking_points: list[str] = []
    title = normalize_text(event_doc.get("summary"))
    description = normalize_text(event_doc.get("description"))

    if title:
        talking_points.append(f"Open by confirming the objective of '{title}'.")
    if description:
        talking_points.append(f"Use the invite description as the baseline agenda: {description[:160]}")
    if interactions:
        talking_points.append("Review the most recent follow-up or unanswered question before the meeting starts.")
    if "high" in decision.priority:
        talking_points.append("End with explicit ownership, next steps, and a dated follow-up commitment.")
    else:
        talking_points.append("Capture concrete actions and confirm whether another meeting is needed.")
    return talking_points


def infer_open_items(interactions: list[str]) -> list[str]:
    verbs = ("follow up", "send", "review", "approve", "decide", "confirm", "share", "deliver")
    items = [entry for entry in interactions if any(verb in entry.lower() for verb in verbs)]
    return items[:5] or ["No explicit open items found in the supplied context."]


def generate_prep(event_doc: dict[str, Any], prep_rules: dict[str, Any], attendee_context_doc: Any, interactions_doc: Any, crm_context_doc: Any) -> dict[str, Any]:
    internal_domains = {str(domain).lower() for domain in prep_rules.get("internalDomains", [])}
    decision = should_generate_prep(event_doc, prep_rules, internal_domains)
    interaction_limit = int(prep_rules.get("defaults", {}).get("includeRecentInteractionLimit", 5))
    interactions = summarize_interactions(interactions_doc, interaction_limit)
    attendees = build_attendee_notes(event_doc, attendee_context_doc, crm_context_doc)
    talking_points = infer_talking_points(event_doc, decision, interactions)
    open_items = infer_open_items(interactions)

    objective = normalize_text(event_doc.get("summary")) or "Clarify the meeting objective."
    start = parse_iso_datetime(event_doc.get("start"))
    end = parse_iso_datetime(event_doc.get("end"))

    return {
        "generatedAt": utc_now().isoformat().replace("+00:00", "Z"),
        "event": {
            "id": event_doc.get("id"),
            "summary": event_doc.get("summary"),
            "start": start.isoformat().replace("+00:00", "Z") if start else None,
            "end": end.isoformat().replace("+00:00", "Z") if end else None,
            "location": event_doc.get("location"),
            "calendarId": event_doc.get("calendarId"),
        },
        "prepRequired": decision.required,
        "priority": decision.priority,
        "reasons": decision.reasons,
        "objective": objective,
        "attendeeContext": attendees or ["No attendee context supplied."],
        "recentInteractions": interactions or ["No recent interactions supplied."],
        "openItems": open_items,
        "talkingPoints": talking_points,
        "recommendedOutcome": "Leave the meeting with clear owners, dates, and the next decision point.",
    }


def render_markdown(prep_doc: dict[str, Any]) -> str:
    event = prep_doc["event"]
    lines = [
        f"# Meeting Prep: {event.get('summary') or 'Untitled Meeting'}",
        "",
        f"- Generated: {prep_doc.get('generatedAt')}",
        f"- Starts: {event.get('start') or 'Unknown'}",
        f"- Ends: {event.get('end') or 'Unknown'}",
        f"- Location: {event.get('location') or 'Not specified'}",
        f"- Calendar: {event.get('calendarId') or 'Unknown'}",
        f"- Prep required: {'yes' if prep_doc.get('prepRequired') else 'no'}",
        f"- Priority: {prep_doc.get('priority')}",
        "",
        "## Why This Needs Prep",
    ]

    for reason in prep_doc.get("reasons", []):
        lines.append(f"- {reason}")

    lines.extend(["", "## Objective", prep_doc.get("objective") or "No objective supplied.", "", "## Attendee Context"])
    for item in prep_doc.get("attendeeContext", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Recent Interactions"])
    for item in prep_doc.get("recentInteractions", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Open Items"])
    for item in prep_doc.get("openItems", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Suggested Talking Points"])
    for item in prep_doc.get("talkingPoints", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Recommended Outcome", prep_doc.get("recommendedOutcome") or "No recommendation generated."])
    return "\n".join(lines) + "\n"


def default_output_path(event_doc: dict[str, Any], prep_rules: dict[str, Any]) -> Path:
    directory = Path(prep_rules.get("defaults", {}).get("writeToDirectory", "workspace/prep"))
    start = parse_iso_datetime(event_doc.get("start"))
    prefix = start.strftime("%Y-%m-%d-%H%M") if start else utc_now().strftime("%Y-%m-%d-%H%M")
    filename = f"{prefix}-{slugify(normalize_text(event_doc.get('summary')))}.md"
    return directory / filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-path", type=Path, help="Path to a normalized event JSON document.")
    parser.add_argument("--calendars-path", type=Path, help="Path to calendars.json for live fetch mode.")
    parser.add_argument("--calendar-id", help="Calendar ID for live fetch mode.")
    parser.add_argument("--event-id", help="Event ID for live fetch mode.")
    parser.add_argument("--prep-rules", type=Path, required=True, help="Path to prep-rules.json.")
    parser.add_argument("--attendee-context", type=Path, help="Optional attendee context JSON.")
    parser.add_argument("--recent-interactions", type=Path, help="Optional recent interaction JSON.")
    parser.add_argument("--crm-context", type=Path, help="Optional CRM context JSON.")
    parser.add_argument("--output", type=Path, help="Optional file path for the markdown prep doc.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Primary stdout output format.")
    parser.add_argument("--write-default-output", action="store_true", help="Write markdown to the default output directory from prep-rules.json.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.event_path:
            event_doc = load_json(args.event_path)
        else:
            if not args.calendars_path or not args.calendar_id or not args.event_id:
                raise ValueError("--calendars-path, --calendar-id, and --event-id are required in live fetch mode.")
            event_doc = fetch_event(args.calendars_path, args.calendar_id, args.event_id)

        prep_rules = load_json(args.prep_rules)
        attendee_context_doc = load_json(args.attendee_context)
        if args.recent_interactions:
            interactions_doc = load_json(args.recent_interactions)
        else:
            fetched = fetch_recent_interactions(event_doc, int(prep_rules.get("defaults", {}).get("includeRecentInteractionLimit", 5)))
            interactions_doc = {"interactions": fetched}
        crm_context_doc = load_json(args.crm_context)
        prep_doc = generate_prep(event_doc, prep_rules, attendee_context_doc, interactions_doc, crm_context_doc)
        markdown = render_markdown(prep_doc)

        output_path = args.output
        if output_path is None and args.write_default_output:
            output_path = default_output_path(event_doc, prep_rules)

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
            prep_doc["outputPath"] = str(output_path)

        if args.format == "json":
            json.dump(prep_doc, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(markdown)
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
