#!/usr/bin/env python3
"""Natural-language parser for OpsClaw task tracking commands."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

PRIORITY_ALIASES = {
    "urgent": "urgent",
    "highest": "urgent",
    "p1": "urgent",
    "high": "high",
    "p2": "high",
    "medium": "medium",
    "normal": "medium",
    "p3": "medium",
    "low": "low",
    "lowest": "low",
    "p4": "low",
}

STATUS_ALIASES = {
    "todo": "todo",
    "to do": "todo",
    "in progress": "in_progress",
    "doing": "in_progress",
    "done": "done",
    "complete": "done",
    "completed": "done",
    "blocked": "blocked",
}


@dataclass(frozen=True)
class ParseResult:
    """Structured output from the natural-language parser."""

    title: str | None
    due_date: str | None
    priority: str | None
    assignee: str | None
    project: str | None
    labels: list[str]
    status: str
    block_reason: str | None
    command: str
    confidence: str
    notes: list[str]
    source_text: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable form."""
        return {
            "title": self.title,
            "dueDate": self.due_date,
            "priority": self.priority,
            "assignee": self.assignee,
            "project": self.project,
            "labels": self.labels,
            "status": self.status,
            "blockReason": self.block_reason,
            "command": self.command,
            "confidence": self.confidence,
            "notes": self.notes,
            "sourceText": self.source_text,
        }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Parse a natural-language task command into structured JSON.")
    parser.add_argument("--text", required=True, help="Raw task command or description.")
    parser.add_argument(
        "--today",
        help="Reference date in YYYY-MM-DD. Defaults to the local current date.",
    )
    return parser.parse_args()


def normalize_whitespace(value: str) -> str:
    """Collapse repeated whitespace and trim punctuation."""
    value = re.sub(r"\s+", " ", value.strip())
    return value.strip(" ,")


def parse_reference_date(value: str | None) -> date:
    """Resolve the parser's reference date."""
    if not value:
        return date.today()
    return date.fromisoformat(value)


def find_priority(text: str) -> tuple[str | None, str]:
    """Extract normalized priority from free text."""
    lower_text = text.lower()
    for phrase, normalized in sorted(PRIORITY_ALIASES.items(), key=lambda item: -len(item[0])):
        pattern = re.compile(rf"\b{re.escape(phrase)}(?:\s+priority)?\b", re.IGNORECASE)
        if pattern.search(lower_text):
            return normalized, normalize_whitespace(pattern.sub("", text, count=1))
    return None, text


def find_labels(text: str) -> tuple[list[str], str]:
    """Extract labels from hashtags or explicit label clauses."""
    labels: list[str] = []
    for match in re.finditer(r"#([A-Za-z0-9_-]+)", text):
        labels.append(match.group(1))
    text = re.sub(r"#([A-Za-z0-9_-]+)", "", text)

    label_match = re.search(r"\blabels?\s*:\s*([A-Za-z0-9_, -]+)", text, re.IGNORECASE)
    if label_match:
        raw_labels = label_match.group(1)
        labels.extend(
            item.strip().lower().replace(" ", "-")
            for item in raw_labels.split(",")
            if item.strip()
        )
        text = text[: label_match.start()] + text[label_match.end() :]

    unique_labels: list[str] = []
    seen: set[str] = set()
    for label in labels:
        normalized = label.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_labels.append(normalized)
    return unique_labels, normalize_whitespace(text)


def resolve_weekday(target_weekday: int, reference: date, *, next_only: bool) -> date:
    """Resolve the next occurrence of a weekday."""
    delta = (target_weekday - reference.weekday()) % 7
    if delta == 0 and next_only:
        delta = 7
    return reference + timedelta(days=delta)


def parse_due_date(text: str, reference: date) -> tuple[str | None, str, list[str]]:
    """Extract a due date and return remaining text plus parser notes."""
    notes: list[str] = []
    patterns: list[tuple[re.Pattern[str], Any]] = [
        (re.compile(r"\b(?:due|by|on)\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE), "iso"),
        (re.compile(r"\b(?:due|by|on)\s+tomorrow\b", re.IGNORECASE), "tomorrow"),
        (re.compile(r"\b(?:due|by|on)\s+today\b", re.IGNORECASE), "today"),
        (re.compile(r"\b(?:due|by|on)\s+next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE), "next_weekday"),
        (re.compile(r"\b(?:due|by|on)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE), "weekday"),
        (re.compile(r"\b(?:due)\s+next\s+week\b", re.IGNORECASE), "next_week"),
        (re.compile(r"\b(?:due)\s+this\s+week\b", re.IGNORECASE), "this_week"),
    ]
    for pattern, kind in patterns:
        match = pattern.search(text)
        if not match:
            continue
        due: date | None = None
        if kind == "iso":
            due = date.fromisoformat(match.group(1))
        elif kind == "tomorrow":
            due = reference + timedelta(days=1)
        elif kind == "today":
            due = reference
        elif kind == "next_weekday":
            due = resolve_weekday(WEEKDAY_INDEX[match.group(1).lower()], reference, next_only=True)
        elif kind == "weekday":
            due = resolve_weekday(WEEKDAY_INDEX[match.group(1).lower()], reference, next_only=False)
            if due == reference:
                notes.append(f"Resolved '{match.group(1)}' to today ({due.isoformat()}).")
        elif kind == "next_week":
            next_monday = resolve_weekday(0, reference, next_only=True)
            due = next_monday + timedelta(days=4)
            notes.append(f"Interpreted 'next week' as Friday ({due.isoformat()}).")
        elif kind == "this_week":
            this_friday = resolve_weekday(4, reference, next_only=False)
            if this_friday < reference:
                this_friday = reference
            due = this_friday
            notes.append(f"Interpreted 'this week' as {due.isoformat()}.")
        cleaned = normalize_whitespace(text[: match.start()] + " " + text[match.end() :])
        return due.isoformat() if due else None, cleaned, notes
    return None, text, notes


def find_assignee(text: str) -> tuple[str | None, str]:
    """Extract an assignee hint from free text."""
    patterns = [
        re.compile(r"\bassign(?:ed)?\s+to\s+([A-Za-z0-9@._ -]+?)(?=(?:,| due\b| by\b| on\b| in project\b| labels?\b|$))", re.IGNORECASE),
        re.compile(r"\bfor\s+([A-Z][A-Za-z0-9._ -]+?)(?=(?:,| due\b| by\b| on\b| in project\b| labels?\b|$))"),
        re.compile(r"@([A-Za-z0-9._-]+)"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            assignee = normalize_whitespace(match.group(1))
            cleaned = normalize_whitespace(text[: match.start()] + " " + text[match.end() :])
            return assignee, cleaned
    return None, text


def find_project(text: str) -> tuple[str | None, str]:
    """Extract project context."""
    pattern = re.compile(r"\b(?:in|for)\s+project\s+([A-Za-z0-9._ -]+?)(?=(?:,| due\b| by\b| on\b| labels?\b|$))", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None, text
    project = normalize_whitespace(match.group(1))
    cleaned = normalize_whitespace(text[: match.start()] + " " + text[match.end() :])
    return project, cleaned


def detect_command_and_status(text: str) -> tuple[str, str, str | None, str]:
    """Infer the high-level command and initial status."""
    lower = text.lower().strip()
    block_reason: str | None = None
    command = "create"
    status = "todo"
    working = text

    if lower.startswith("mark ") and re.search(r"\b(as )?(done|complete|completed)\b", lower):
        command = "mark_done"
        status = "done"
        working = re.sub(r"\bmark\b", "", working, count=1, flags=re.IGNORECASE)
        working = re.sub(r"\b(as )?(done|complete|completed)\b", "", working, count=1, flags=re.IGNORECASE)
    elif lower.startswith("block"):
        command = "block"
        status = "blocked"
        working = re.sub(r"^\s*block\s*:?\s*", "", working, count=1, flags=re.IGNORECASE)
        split = re.split(r"\s+-\s+|\s+because\s+|\s+waiting\s+on\s+", working, maxsplit=1, flags=re.IGNORECASE)
        if len(split) == 2:
            working = split[0]
            reason_suffix = "waiting on " + split[1] if "waiting on" in lower else split[1]
            block_reason = normalize_whitespace(reason_suffix)
    return command, status, block_reason, normalize_whitespace(working)


def strip_leading_task_phrases(text: str) -> str:
    """Remove generic command prefixes that are not part of the task title."""
    patterns = [
        r"^\s*add\s+task\s*:?\s*",
        r"^\s*task\s*:?\s*",
        r"^\s*remind\s+me\s+to\s+",
        r"^\s*please\s+",
        r"^\s*create\s+(?:a\s+)?task\s*:?\s*",
    ]
    working = text
    for raw_pattern in patterns:
        working = re.sub(raw_pattern, "", working, count=1, flags=re.IGNORECASE)
    return normalize_whitespace(working)


def parse_text(text: str, reference: date) -> ParseResult:
    """Parse natural language into a normalized task payload."""
    notes: list[str] = []
    command, status, block_reason, working = detect_command_and_status(text)
    working = strip_leading_task_phrases(working)

    priority, working = find_priority(working)
    labels, working = find_labels(working)
    assignee, working = find_assignee(working)
    project, working = find_project(working)
    due_date, working, due_notes = parse_due_date(working, reference)
    notes.extend(due_notes)

    status_match = re.search(r"\b(todo|to do|in progress|doing|done|complete|completed|blocked)\b", working, re.IGNORECASE)
    if status_match and status == "todo":
        status = STATUS_ALIASES[status_match.group(1).lower()]
        working = normalize_whitespace(working[: status_match.start()] + " " + working[status_match.end() :])

    title = normalize_whitespace(working)
    if command == "mark_done":
        title = re.sub(r"^\s*the\s+", "", title, count=1, flags=re.IGNORECASE)
        title = normalize_whitespace(title)

    confidence = "high"
    if not title:
        confidence = "low"
        notes.append("Could not confidently determine a task title.")
    elif due_date is None:
        confidence = "medium"
        notes.append("No due date detected.")
    elif due_notes:
        confidence = "medium"

    return ParseResult(
        title=title or None,
        due_date=due_date,
        priority=priority,
        assignee=assignee,
        project=project,
        labels=labels,
        status=status,
        block_reason=block_reason,
        command=command,
        confidence=confidence,
        notes=notes,
        source_text=text,
    )


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    reference = parse_reference_date(args.today)
    result = parse_text(args.text, reference)
    print(json.dumps(result.to_dict(), ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
