#!/usr/bin/env python3
"""Format OpsClaw reporting output for multiple delivery channels."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def to_markdown(payload: dict[str, Any]) -> str:
    """Return canonical Markdown output."""
    markdown = payload.get("markdown")
    if markdown:
        return str(markdown)
    return to_plain_text(payload)


def pretty_name(value: str) -> str:
    """Format section names while preserving common acronyms."""
    mapping = {
        "crm": "CRM",
        "kpi": "KPI",
    }
    lowered = value.lower()
    if lowered in mapping:
        return mapping[lowered]
    return value.replace("_", " ").title()


def to_plain_text(payload: dict[str, Any]) -> str:
    """Render a plain-text fallback from common report fields."""
    lines: list[str] = []
    report_type = str(payload.get("reportType") or "report").replace("_", " ").title()
    lines.append(report_type)

    if payload.get("date"):
        lines.append(f"Date: {payload['date']}")
    if payload.get("periodStart") or payload.get("periodEnd"):
        lines.append(f"Period: {payload.get('periodStart', '')} -> {payload.get('periodEnd', '')}")
    lines.append("")

    for key, value in payload.get("sections", {}).items():
        lines.append(pretty_name(str(key)))
        if isinstance(value, str):
            lines.append(value)
        elif isinstance(value, list):
            lines.extend(f"- {item}" for item in value)
        elif isinstance(value, dict):
            lines.extend(f"- {sub_key}: {sub_value}" for sub_key, sub_value in value.items())
        else:
            lines.append(str(value))
        lines.append("")

    recommendations = payload.get("recommendations")
    if isinstance(recommendations, list):
        lines.append("Recommendations")
        lines.extend(f"- {item}" for item in recommendations)
    return "\n".join(lines).strip()


def to_slack_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Render report content as Slack block kit payload."""
    blocks: list[dict[str, Any]] = []
    title = str(payload.get("reportType") or "report").replace("_", " ").title()
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{title}*"}})

    context_bits: list[str] = []
    if payload.get("date"):
        context_bits.append(f"Date: {payload['date']}")
    if payload.get("periodStart") or payload.get("periodEnd"):
        context_bits.append(f"Period: {payload.get('periodStart', '')} -> {payload.get('periodEnd', '')}")
    if context_bits:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " | ".join(context_bits)}]})

    for key, value in payload.get("sections", {}).items():
        if isinstance(value, str):
            text = value
        elif isinstance(value, list):
            text = "\n".join(f"- {item}" for item in value)
        elif isinstance(value, dict):
            text = "\n".join(f"- {sub_key}: {sub_value}" for sub_key, sub_value in value.items())
        else:
            text = str(value)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{pretty_name(str(key))}*\n{text[:2900]}"},
            }
        )
    if isinstance(payload.get("recommendations"), list):
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Recommendations*\n" + "\n".join(f"- {item}" for item in payload["recommendations"]),
                },
            }
        )
    return blocks


def markdown_to_telegram_html(markdown: str) -> str:
    """Convert the limited Markdown used by this repo into Telegram-safe HTML."""
    lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        escaped = html.escape(line)
        if line.startswith("# "):
            lines.append(f"<b>{html.escape(line[2:])}</b>")
        elif line.startswith("## "):
            lines.append(f"<b>{html.escape(line[3:])}</b>")
        elif line.startswith("- "):
            lines.append(f"• {html.escape(line[2:])}")
        else:
            lines.append(escaped)
    return "\n".join(lines)


def format_report(payload: dict[str, Any], output_format: str) -> Any:
    """Format the payload for the requested transport."""
    if output_format == "markdown":
        return to_markdown(payload)
    if output_format == "plain_text":
        return to_plain_text(payload)
    if output_format == "slack_blocks":
        return to_slack_blocks(payload)
    if output_format == "telegram_html":
        return markdown_to_telegram_html(to_markdown(payload))
    raise ValueError(f"Unsupported format: {output_format}")


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Path to a report JSON payload.")
    parser.add_argument(
        "--format",
        required=True,
        choices=["markdown", "plain_text", "slack_blocks", "telegram_html"],
        help="Requested output format.",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    try:
        payload = load_json(args.input)
        formatted = format_report(payload, args.format)
        if isinstance(formatted, str):
            sys.stdout.write(formatted + ("\n" if not formatted.endswith("\n") else ""))
        else:
            json.dump(formatted, sys.stdout, indent=2)
            sys.stdout.write("\n")
        return 0
    except Exception as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
