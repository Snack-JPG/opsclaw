#!/usr/bin/env python3
"""CLI for creating and managing SOP markdown files."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = Path("./vault/processes")
DEFAULT_TEMPLATE = SKILL_DIR / "templates" / "sop-template.md"
FRONTMATTER_DELIMITER = "---"
VALID_STATUSES = {"draft", "active", "archived"}
REQUIRED_HEADINGS = [
    "Purpose",
    "Scope",
    "Process Owner",
    "Steps",
    "Review Schedule",
]
STEP_REQUIRED_FIELDS = ["action", "responsible", "tools"]


@dataclass
class SopRecord:
    path: Path
    frontmatter: Dict[str, object]
    body: str

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title") or self.path.stem.replace("-", " ").title())

    @property
    def status(self) -> str:
        return str(self.frontmatter.get("status") or "draft")

    @property
    def owner(self) -> str:
        return str(self.frontmatter.get("owner") or "")

    @property
    def updated(self) -> str:
        return str(self.frontmatter.get("updated") or self.frontmatter.get("created") or "")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "untitled-sop"


def today_iso() -> str:
    return date.today().isoformat()


def default_author() -> str:
    return (
        os.environ.get("CODEX_AGENT_NAME")
        or os.environ.get("OPENCLAW_AGENT_NAME")
        or os.environ.get("USER")
        or "agent"
    )


def resolve_vault(vault_arg: str | None) -> Path:
    raw = vault_arg or os.environ.get("SOP_VAULT_PATH")
    path = Path(raw).expanduser() if raw else DEFAULT_VAULT
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def parse_simple_yaml(lines: Iterable[str]) -> Dict[str, object]:
    data: Dict[str, object] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = parse_yaml_value(value.strip())
    return data


def parse_yaml_value(value: str) -> object:
    if value == "":
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [part.strip().strip("\"'") for part in inner.split(",") if part.strip()]
    return value.strip().strip("\"'")


def split_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    if not text.startswith(FRONTMATTER_DELIMITER):
        return {}, text

    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, text

    frontmatter_lines: List[str] = []
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            end_index = index
            break
        frontmatter_lines.append(lines[index])

    if end_index is None:
        return {}, text

    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    return parse_simple_yaml(frontmatter_lines), body


def dump_frontmatter(data: Dict[str, object]) -> str:
    ordered_keys = [
        "title",
        "type",
        "status",
        "created",
        "updated",
        "author",
        "owner",
        "review_frequency",
        "permalink",
    ]
    lines = [FRONTMATTER_DELIMITER]
    for key in ordered_keys:
        value = data.get(key, "")
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append(FRONTMATTER_DELIMITER)
    return "\n".join(lines)


def read_sop(path: Path) -> SopRecord:
    text = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    return SopRecord(path=path, frontmatter=frontmatter, body=body)


def write_sop(path: Path, frontmatter: Dict[str, object], body: str) -> None:
    content = f"{dump_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_template() -> str:
    return DEFAULT_TEMPLATE.read_text(encoding="utf-8")


def escape_table_value(value: str) -> str:
    text = " ".join(value.splitlines()).strip()
    text = text.replace("|", "\\|")
    return text or "-"


def normalize_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def compute_next_review_date(review_frequency: str, created_on: str) -> str:
    base = date.fromisoformat(created_on)
    freq = review_frequency.strip().lower()
    delta_days = {
        "weekly": 7,
        "monthly": 30,
        "quarterly": 90,
        "biannual": 182,
        "semiannual": 182,
        "annual": 365,
        "annually": 365,
        "yearly": 365,
    }.get(freq)
    if delta_days is None:
        return "TBD"
    return (base + timedelta(days=delta_days)).isoformat()


def render_steps_table(steps: Sequence[Dict[str, object]]) -> str:
    lines = [
        "| Step | Action | Responsible | Tools | Est. Time |",
        "|------|--------|-------------|-------|-----------|",
    ]
    if not steps:
        lines.append("| 1 | Describe the first action | Process owner | Required systems | TBD |")
        return "\n".join(lines)

    for index, step in enumerate(steps, start=1):
        step_no = step.get("step", index)
        action = escape_table_value(str(step.get("action", "")))
        details = " ".join(str(step.get("details", "")).split())
        if details:
            action = escape_table_value(f"{action} - {details}")
        responsible = escape_table_value(str(step.get("responsible", "")))
        tools = escape_table_value(str(step.get("tools", "")))
        time = escape_table_value(str(step.get("time", "TBD")))
        lines.append(f"| {step_no} | {action or '-'} | {responsible or '-'} | {tools or '-'} | {time or '-'} |")
    return "\n".join(lines)


def render_step_details(steps: Sequence[Dict[str, object]]) -> str:
    if not steps:
        return "### Detailed Instructions\nAdd implementation notes for each step here."

    lines = ["### Detailed Instructions"]
    for index, step in enumerate(steps, start=1):
        step_no = step.get("step", index)
        action = str(step.get("action", f"Step {step_no}")).strip()
        details = str(step.get("details", "")).strip() or "No additional detail provided."
        lines.append(f"#### Step {step_no}: {action}")
        lines.append(details)
        lines.append("")
    return "\n".join(lines).rstrip()


def render_bullets(items: Sequence[str], default_item: str) -> str:
    values = [item for item in items if item]
    if not values:
        values = [default_item]
    return "\n".join(f"- {item}" for item in values)


def render_related_docs(items: Sequence[str]) -> str:
    values = [item for item in items if item]
    if not values:
        values = ["Related Document"]
    return "\n".join(f"- [[{item}]]" for item in values)


def build_sop_markdown(data: Dict[str, object]) -> str:
    template = load_template()
    created_on = str(data["date"])
    review_frequency = str(data.get("review_frequency") or "TBD")
    values = {
        "title": str(data["title"]),
        "date": created_on,
        "author": str(data["author"]),
        "owner": str(data.get("owner") or data["author"]),
        "review_frequency": review_frequency,
        "slug": str(data["slug"]),
        "purpose": str(data.get("purpose") or "Document the reason this process exists."),
        "scope": str(data.get("scope") or "Define which teams, roles, or situations this SOP applies to."),
        "steps_table": render_steps_table(data.get("steps", [])),
        "step_details": render_step_details(data.get("steps", [])),
        "exceptions": render_bullets(
            normalize_list(data.get("exceptions")),
            "No exceptions or edge cases are documented yet.",
        ),
        "escalation": str(data.get("escalation") or "Describe the escalation path when the process cannot be completed as written."),
        "related_docs": render_related_docs(normalize_list(data.get("related_docs"))),
        "next_review_date": compute_next_review_date(review_frequency, created_on),
        "version_history": f"| {created_on} | {data['author']} | Initial creation |",
        "additional_notes": str(data.get("additional_notes") or "Add onboarding tips, prerequisites, or context here."),
    }
    return template.format(**values).rstrip() + "\n"


def parse_interview_answers(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise SystemExit("--answers JSON must contain an object")
    return payload


def create_sop_file(vault: Path, title: str, markdown: str) -> Path:
    slug = slugify(title)
    target = vault / f"{slug}.md"
    suffix = 2
    while target.exists():
        target = vault / f"{slug}-{suffix}.md"
        suffix += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    return target


def list_sop_files(vault: Path) -> List[Path]:
    if not vault.exists():
        return []
    return sorted(path for path in vault.rglob("*.md") if path.is_file())


def extract_heading_map(body: str) -> Dict[str, str]:
    headings = list(re.finditer(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE))
    sections: Dict[str, str] = {}
    for index, match in enumerate(headings):
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        sections[match.group(1).strip()] = body[start:end].strip()
    return sections


def update_version_history(body: str, author: str, change: str, change_date: str) -> str:
    marker = "## Version History"
    if marker not in body:
        suffix = (
            f"\n\n## Version History\n"
            f"| Date | Author | Change |\n"
            f"|------|--------|--------|\n"
            f"| {change_date} | {author} | {change} |\n"
        )
        return body.rstrip() + suffix

    table_row = f"| {change_date} | {author} | {change} |"
    if table_row in body:
        return body

    pattern = re.compile(r"(## Version History\s*\n\| Date \| Author \| Change \|\n\|[-| ]+\|\n)", re.MULTILINE)
    match = pattern.search(body)
    if match:
        insert_at = match.end()
        return body[:insert_at] + table_row + "\n" + body[insert_at:]
    return body.rstrip() + "\n" + table_row + "\n"


def parse_table_rows(lines: Sequence[str]) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows


def markdown_to_html(markdown: str, title: str) -> str:
    body = split_frontmatter(markdown)[1]
    blocks = body.splitlines()
    fragments: List[str] = []
    index = 0

    while index < len(blocks):
        line = blocks[index].rstrip()
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith("# "):
            fragments.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
            index += 1
            continue

        if stripped.startswith("## "):
            fragments.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
            index += 1
            continue

        if stripped.startswith("### "):
            fragments.append(f"<h3>{html.escape(stripped[4:].strip())}</h3>")
            index += 1
            continue

        if stripped.startswith("#### "):
            fragments.append(f"<h4>{html.escape(stripped[5:].strip())}</h4>")
            index += 1
            continue

        if stripped.startswith("|"):
            table_lines: List[str] = []
            while index < len(blocks) and blocks[index].strip().startswith("|"):
                table_lines.append(blocks[index])
                index += 1
            rows = parse_table_rows(table_lines)
            if rows:
                header = rows[0]
                body_rows = rows[1:]
                fragments.append("<table>")
                fragments.append("<thead><tr>" + "".join(f"<th>{html.escape(cell)}</th>" for cell in header) + "</tr></thead>")
                fragments.append("<tbody>")
                for row in body_rows:
                    fragments.append("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>")
                fragments.append("</tbody></table>")
            continue

        if stripped.startswith("- "):
            items: List[str] = []
            while index < len(blocks) and blocks[index].strip().startswith("- "):
                items.append(blocks[index].strip()[2:].strip())
                index += 1
            fragments.append("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>")
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(blocks):
            candidate = blocks[index].strip()
            if not candidate or candidate.startswith(("#", "|", "- ")):
                break
            paragraph_lines.append(candidate)
            index += 1
        paragraph = " ".join(paragraph_lines)
        paragraph = re.sub(r"\[\[([^\]]+)\]\]", r"<span class=\"wikilink\">\1</span>", html.escape(paragraph))
        fragments.append(f"<p>{paragraph}</p>")

    css = """
body {
  margin: 0;
  background: #eef3f7;
  color: #163247;
  font-family: Georgia, "Times New Roman", serif;
}
.page {
  max-width: 960px;
  margin: 32px auto;
  background: #ffffff;
  border-top: 10px solid #1f5f8b;
  box-shadow: 0 18px 42px rgba(22, 50, 71, 0.12);
  padding: 48px 56px 56px;
}
h1, h2, h3, h4 {
  color: #12324a;
  font-family: "Avenir Next", "Segoe UI", sans-serif;
}
h1 {
  margin: 0 0 20px;
  font-size: 2.2rem;
  line-height: 1.1;
}
h2 {
  margin-top: 32px;
  padding-bottom: 8px;
  border-bottom: 1px solid #d7e3ec;
}
h3 {
  margin-top: 24px;
}
p, li, td, th {
  font-size: 1rem;
  line-height: 1.6;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 18px 0 24px;
}
th {
  background: #1f5f8b;
  color: #ffffff;
  text-align: left;
}
th, td {
  padding: 12px 14px;
  border: 1px solid #d7e3ec;
  vertical-align: top;
}
tr:nth-child(even) td {
  background: #f7fafc;
}
ul {
  padding-left: 22px;
}
.meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}
.meta-card {
  border: 1px solid #d7e3ec;
  background: #f7fafc;
  padding: 12px 14px;
}
.meta-card strong {
  display: block;
  font-family: "Avenir Next", "Segoe UI", sans-serif;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #567489;
  margin-bottom: 4px;
}
.wikilink {
  color: #1f5f8b;
  font-weight: 600;
}
@media print {
  body {
    background: #ffffff;
  }
  .page {
    box-shadow: none;
    margin: 0;
    max-width: none;
    border-top: 6px solid #1f5f8b;
    padding: 24px 28px;
  }
}
"""

    fm, _ = split_frontmatter(markdown)
    meta_cards = [
        ("Status", str(fm.get("status", ""))),
        ("Owner", str(fm.get("owner", ""))),
        ("Updated", str(fm.get("updated", ""))),
        ("Review", str(fm.get("review_frequency", ""))),
    ]
    meta_html = "".join(
        f"<div class=\"meta-card\"><strong>{html.escape(label)}</strong>{html.escape(value or '-')}</div>"
        for label, value in meta_cards
    )

    return (
        "<!DOCTYPE html>"
        "<html lang=\"en\">"
        "<head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{html.escape(title)}</title>"
        f"<style>{css}</style>"
        "</head>"
        "<body>"
        "<main class=\"page\">"
        f"<div class=\"meta\">{meta_html}</div>"
        + "".join(fragments)
        + "</main></body></html>"
    )


def markdown_to_text(markdown: str) -> str:
    _, body = split_frontmatter(markdown)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)
    text = re.sub(r"^#\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^###\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^####\s+", "", text, flags=re.MULTILINE)
    text = text.replace("|", " | ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def cmd_create(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    author = default_author()
    created_on = today_iso()
    title = args.title.strip()
    markdown = build_sop_markdown(
        {
            "title": title,
            "slug": slugify(title),
            "date": created_on,
            "author": author,
            "owner": author,
            "review_frequency": "TBD",
            "steps": [],
            "exceptions": [],
            "related_docs": [],
            "escalation": "",
            "additional_notes": "",
        }
    )
    path = create_sop_file(vault, title, markdown)
    print(path)
    return 0


def cmd_create_from_interview(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    payload = parse_interview_answers(Path(args.answers))
    title = args.title.strip() or str(payload.get("title") or "").strip()
    if not title:
        raise SystemExit("A title is required")
    author = default_author()
    created_on = today_iso()
    markdown = build_sop_markdown(
        {
            "title": title,
            "slug": slugify(title),
            "date": created_on,
            "author": author,
            "owner": payload.get("owner") or author,
            "review_frequency": payload.get("review_frequency") or "TBD",
            "purpose": payload.get("purpose") or "",
            "scope": payload.get("scope") or "",
            "steps": payload.get("steps") or [],
            "exceptions": payload.get("exceptions") or [],
            "escalation": payload.get("escalation") or payload.get("what_if_wrong") or "",
            "related_docs": payload.get("related_docs") or [],
            "additional_notes": payload.get("additional_notes") or payload.get("anything_else") or "",
        }
    )
    path = create_sop_file(vault, title, markdown)
    print(path)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    records: List[SopRecord] = []
    for path in list_sop_files(vault):
        record = read_sop(path)
        if args.status and record.status.lower() != args.status.lower():
            continue
        if args.owner and record.owner.lower() != args.owner.lower():
            continue
        records.append(record)

    if not records:
        print("No SOPs found.")
        return 0

    title_width = max(len("Title"), *(len(record.title) for record in records))
    status_width = max(len("Status"), *(len(record.status) for record in records))
    owner_width = max(len("Owner"), *(len(record.owner or "-") for record in records))
    header = f"{'Title':<{title_width}}  {'Status':<{status_width}}  {'Owner':<{owner_width}}  Last Updated  File"
    print(header)
    print("-" * len(header))
    for record in records:
        relative = record.path.relative_to(vault)
        print(
            f"{record.title:<{title_width}}  {record.status:<{status_width}}  "
            f"{(record.owner or '-'): <{owner_width}}  {record.updated or '-':<11}  {relative}"
        )
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    if args.status not in VALID_STATUSES:
        raise SystemExit(f"Invalid status: {args.status}")
    path = (vault / args.filename).resolve() if not Path(args.filename).is_absolute() else Path(args.filename)
    if not path.exists():
        raise SystemExit(f"SOP not found: {path}")
    record = read_sop(path)
    now = today_iso()
    record.frontmatter["status"] = args.status
    record.frontmatter["updated"] = now
    record.body = update_version_history(record.body, default_author(), f"Status changed to {args.status}", now)
    write_sop(path, record.frontmatter, record.body)
    print(path)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    query = args.query.lower()
    matches = 0
    for path in list_sop_files(vault):
        lines = path.read_text(encoding="utf-8").splitlines()
        line_hits = [index for index, line in enumerate(lines) if query in line.lower()]
        if not line_hits:
            continue
        matches += 1
        print(f"{path.relative_to(vault)}")
        for line_index in line_hits:
            start = max(0, line_index - 1)
            end = min(len(lines), line_index + 2)
            for context_index in range(start, end):
                prefix = ">" if context_index == line_index else " "
                print(f"  {prefix} {context_index + 1:>4}: {lines[context_index]}")
        print()
    if matches == 0:
        print("No matches found.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    path = (vault / args.filename).resolve() if not Path(args.filename).is_absolute() else Path(args.filename)
    if not path.exists():
        raise SystemExit(f"SOP not found: {path}")
    record = read_sop(path)
    sections = extract_heading_map(record.body)
    missing_sections = [heading for heading in REQUIRED_HEADINGS if heading not in sections]
    issues: List[str] = []

    if missing_sections:
        issues.extend(f"Missing section: {heading}" for heading in missing_sections)

    owner = str(record.frontmatter.get("owner") or "").strip()
    if not owner and not sections.get("Process Owner", "").strip():
        issues.append("Missing owner in frontmatter and Process Owner section")

    review_text = sections.get("Review Schedule", "").strip()
    if not review_text:
        issues.append("Missing review schedule details")
    elif "next review:" not in review_text.lower():
        issues.append("Review Schedule section is missing a next review date")

    steps_section = sections.get("Steps", "")
    table_lines = [line for line in steps_section.splitlines() if line.strip().startswith("|")]
    rows = parse_table_rows(table_lines)
    if len(rows) < 2:
        issues.append("Steps table is missing or has no data rows")
    else:
        headers = [header.strip().lower() for header in rows[0]]
        for field in STEP_REQUIRED_FIELDS:
            if field not in headers:
                issues.append(f"Steps table missing required column: {field}")
        for row_number, row in enumerate(rows[1:], start=1):
            row_map = {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
            for field in STEP_REQUIRED_FIELDS:
                if field in row_map and not row_map[field].strip():
                    issues.append(f"Step row {row_number} missing value for: {field}")

    if issues:
        print("Validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Validation passed.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    vault = resolve_vault(args.vault)
    path = (vault / args.filename).resolve() if not Path(args.filename).is_absolute() else Path(args.filename)
    if not path.exists():
        raise SystemExit(f"SOP not found: {path}")
    markdown = path.read_text(encoding="utf-8")
    record = read_sop(path)

    if args.format == "html":
        output = path.with_suffix(".html")
        output.write_text(markdown_to_html(markdown, record.title), encoding="utf-8")
    elif args.format == "text":
        output = path.with_suffix(".txt")
        output.write_text(markdown_to_text(markdown), encoding="utf-8")
    else:
        raise SystemExit(f"Unsupported format: {args.format}")

    print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sop", description="Create and manage SOP markdown files.")
    vault_parent = argparse.ArgumentParser(add_help=False)
    vault_parent.add_argument("--vault", help="Vault path. Defaults to SOP_VAULT_PATH or ./vault/processes/")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new SOP from the template.", parents=[vault_parent])
    create.add_argument("title")
    create.set_defaults(func=cmd_create)

    create_from_interview = subparsers.add_parser(
        "create-from-interview",
        help="Create an SOP from a JSON interview payload.",
        parents=[vault_parent],
    )
    create_from_interview.add_argument("title")
    create_from_interview.add_argument("--answers", required=True, help="Path to the interview answers JSON file.")
    create_from_interview.set_defaults(func=cmd_create_from_interview)

    list_cmd = subparsers.add_parser("list", help="List SOPs in the vault.", parents=[vault_parent])
    list_cmd.add_argument("--status", choices=sorted(VALID_STATUSES))
    list_cmd.add_argument("--owner")
    list_cmd.set_defaults(func=cmd_list)

    update = subparsers.add_parser("update", help="Update the status of an SOP.", parents=[vault_parent])
    update.add_argument("filename", help="Filename within the vault or an absolute path.")
    update.add_argument("--status", required=True, choices=sorted(VALID_STATUSES))
    update.set_defaults(func=cmd_update)

    search = subparsers.add_parser("search", help="Search across SOP files.", parents=[vault_parent])
    search.add_argument("query")
    search.set_defaults(func=cmd_search)

    validate = subparsers.add_parser("validate", help="Validate an SOP structure.", parents=[vault_parent])
    validate.add_argument("filename", help="Filename within the vault or an absolute path.")
    validate.set_defaults(func=cmd_validate)

    export = subparsers.add_parser("export", help="Export an SOP to another format.", parents=[vault_parent])
    export.add_argument("filename", help="Filename within the vault or an absolute path.")
    export.add_argument("--format", required=True, choices=["html", "text"])
    export.set_defaults(func=cmd_export)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
