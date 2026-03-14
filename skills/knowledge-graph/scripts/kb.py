#!/usr/bin/env python3
"""OpsClaw knowledge graph CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VAULT = ROOT / "workspace" / "knowledge-graph"
GRAPH_FILE = "_graph.json"
FRONTMATTER_DELIMITER = "---"
WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")

TYPE_TO_FOLDER = {
    "person": "people",
    "process": "processes",
    "client": "clients",
    "project": "projects",
    "decision": "decisions",
    "meeting": "meetings",
    "policy": "policies",
    "tool": "tools",
    "note": "general",
    "general": "general",
}

FOLDER_TO_TYPE = {
    "people": "person",
    "processes": "process",
    "clients": "client",
    "projects": "project",
    "decisions": "decision",
    "meetings": "meeting",
    "policies": "policy",
    "tools": "tool",
    "general": "note",
}

TEMPLATE_TYPES = [
    "person",
    "process",
    "client",
    "project",
    "decision",
    "meeting",
    "policy",
    "tool",
    "note",
]


@dataclass
class NoteRecord:
    slug: str
    title: str
    note_type: str
    tags: List[str]
    status: str
    author: str
    confidentiality: str
    created: str
    updated: str
    permalink: str
    path: Path
    links_to: List[str]
    linked_from: List[str]


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "note"


def today_iso() -> str:
    return date.today().isoformat()


def default_author() -> str:
    return (
        os.environ.get("CODEX_AGENT_NAME")
        or os.environ.get("OPENCLAW_AGENT_NAME")
        or os.environ.get("USER")
        or "agent"
    )


def ensure_vault(vault: Path) -> None:
    if not vault.exists():
        raise SystemExit(f"Vault does not exist: {vault}")


def note_files(vault: Path) -> List[Path]:
    files = []
    for path in vault.rglob("*.md"):
        if "_templates" in path.parts:
            continue
        files.append(path)
    return sorted(files)


def split_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    if not text.startswith(FRONTMATTER_DELIMITER):
        return {}, text

    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}, text

    fm_lines: List[str] = []
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            end_index = index
            break
        fm_lines.append(lines[index])

    if end_index is None:
        return {}, text

    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    return parse_simple_yaml(fm_lines), body


def parse_simple_yaml(lines: Iterable[str]) -> Dict[str, object]:
    data: Dict[str, object] = {}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        data[key] = parse_yaml_value(value)
    return data


def parse_yaml_value(value: str):
    if value == "":
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
    return value.strip("\"'")


def dump_frontmatter(data: Dict[str, object]) -> str:
    ordered_keys = [
        "title",
        "type",
        "tags",
        "status",
        "created",
        "updated",
        "author",
        "confidentiality",
        "permalink",
    ]
    lines = [FRONTMATTER_DELIMITER]
    for key in ordered_keys:
        value = data.get(key, "")
        if isinstance(value, list):
            rendered = "[" + ", ".join(value) + "]"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append(FRONTMATTER_DELIMITER)
    return "\n".join(lines)


def read_note(path: Path) -> Tuple[Dict[str, object], str]:
    text = path.read_text(encoding="utf-8")
    return split_frontmatter(text)


def write_note(path: Path, frontmatter: Dict[str, object], body: str) -> None:
    content = f"{dump_frontmatter(frontmatter)}\n\n{body.rstrip()}\n"
    path.write_text(content, encoding="utf-8")


def infer_type_from_path(path: Path, vault: Path) -> str:
    try:
        folder = path.relative_to(vault).parts[0]
    except IndexError:
        return "note"
    return FOLDER_TO_TYPE.get(folder, "note")


def normalize_tags(value) -> List[str]:
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def extract_wikilinks(body: str) -> List[str]:
    results = []
    for match in WIKILINK_RE.findall(body):
        target = match.split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            results.append(target)
    return results


def load_graph(vault: Path) -> Dict[str, dict]:
    graph_path = vault / GRAPH_FILE
    if graph_path.exists():
        return json.loads(graph_path.read_text(encoding="utf-8") or "{}")
    return build_index(vault, write_graph=False)


def build_index(vault: Path, write_graph: bool = True) -> Dict[str, dict]:
    ensure_vault(vault)
    notes: Dict[str, dict] = {}
    title_map: Dict[str, str] = {}
    permalink_map: Dict[str, str] = {}

    for path in note_files(vault):
        frontmatter, body = read_note(path)
        title = str(frontmatter.get("title") or path.stem.replace("-", " ").title()).strip()
        slug = str(frontmatter.get("permalink") or path.stem).strip() or path.stem
        note_type = str(frontmatter.get("type") or infer_type_from_path(path, vault)).strip() or "note"
        tags = normalize_tags(frontmatter.get("tags"))
        status = str(frontmatter.get("status") or "draft").strip()
        author = str(frontmatter.get("author") or default_author()).strip()
        confidentiality = str(frontmatter.get("confidentiality") or "internal").strip()
        created = str(frontmatter.get("created") or "").strip()
        updated = str(frontmatter.get("updated") or "").strip()
        outgoing_titles = extract_wikilinks(body)

        notes[slug] = {
            "title": title,
            "type": note_type,
            "tags": tags,
            "status": status,
            "author": author,
            "confidentiality": confidentiality,
            "created": created,
            "updated": updated,
            "permalink": slug,
            "path": str(path.relative_to(vault)),
            "raw_links": outgoing_titles,
            "links_to": [],
            "linked_from": [],
        }
        title_map[slugify(title)] = slug
        permalink_map[slug] = slug
        permalink_map[path.stem] = slug

    for slug, note in notes.items():
        resolved_links: List[str] = []
        seen = set()
        for target in note.pop("raw_links", []):
            target_slug = (
                permalink_map.get(target)
                or permalink_map.get(slugify(target))
                or title_map.get(slugify(target))
                or slugify(target)
            )
            if target_slug not in seen:
                seen.add(target_slug)
                resolved_links.append(target_slug)
        note["links_to"] = resolved_links

    for source_slug, note in notes.items():
        for target_slug in note["links_to"]:
            if target_slug in notes and source_slug not in notes[target_slug]["linked_from"]:
                notes[target_slug]["linked_from"].append(source_slug)

    for note in notes.values():
        note["linked_from"].sort()

    if write_graph:
        graph_path = vault / GRAPH_FILE
        graph_path.write_text(json.dumps(notes, indent=2, sort_keys=True), encoding="utf-8")
    return notes


def resolve_note(identifier: str, graph: Dict[str, dict]) -> Tuple[str, dict]:
    needle = identifier.strip()
    slug = slugify(needle)

    if needle in graph:
        return needle, graph[needle]
    if slug in graph:
        return slug, graph[slug]

    lowered = needle.lower()
    for candidate_slug, note in graph.items():
        if note["title"].lower() == lowered:
            return candidate_slug, note
        if Path(note["path"]).stem.lower() == lowered:
            return candidate_slug, note

    raise SystemExit(f"Note not found: {identifier}")


def render_note_summary(slug: str, note: dict) -> str:
    tags = ", ".join(note.get("tags", [])) or "-"
    return (
        f"{note['title']} [{slug}]\n"
        f"  type={note.get('type', 'note')} status={note.get('status', 'draft')} "
        f"tags={tags} path={note.get('path', '')}"
    )


def cmd_init(args: argparse.Namespace) -> int:
    vault = args.vault
    for folder in set(TYPE_TO_FOLDER.values()):
        (vault / folder).mkdir(parents=True, exist_ok=True)

    template_src = ROOT / "skills" / "knowledge-graph" / "_templates"
    template_dst = vault / "_templates"
    template_dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(template_src.glob("*.md")):
        shutil.copyfile(path, template_dst / path.name)

    graph_path = vault / GRAPH_FILE
    if not graph_path.exists():
        graph_path.write_text("{}", encoding="utf-8")

    print(f"Initialized vault at {vault}")
    return 0


def load_template(template_type: str) -> str:
    path = ROOT / "skills" / "knowledge-graph" / "_templates" / f"{template_type}.md"
    if not path.exists():
        raise SystemExit(f"Template not found: {path}")
    return path.read_text(encoding="utf-8")


def unique_note_path(directory: Path, slug: str) -> Path:
    path = directory / f"{slug}.md"
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = directory / f"{slug}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


def cmd_add(args: argparse.Namespace) -> int:
    vault = args.vault
    ensure_vault(vault)
    note_type = args.note_type.strip().lower()
    folder = TYPE_TO_FOLDER.get(note_type)
    if folder is None:
        raise SystemExit(f"Unsupported note type: {args.note_type}")

    canonical_type = "note" if note_type == "general" else note_type
    template_type = "note" if canonical_type == "note" else canonical_type
    slug = slugify(args.title)
    destination = unique_note_path(vault / folder, slug)
    note_date = today_iso()
    template = load_template(template_type)
    content = (
        template.replace("{{title}}", args.title)
        .replace("{{type}}", canonical_type)
        .replace("{{created}}", note_date)
        .replace("{{updated}}", note_date)
        .replace("{{author}}", default_author())
        .replace("{{permalink}}", destination.stem)
    )
    destination.write_text(content.rstrip() + "\n", encoding="utf-8")
    print(destination)
    return 0


def format_search_hit(path: Path, line_number: int, lines: List[str]) -> str:
    output = [f"{path}:{line_number}"]
    start = max(0, line_number - 2)
    end = min(len(lines), line_number + 1)
    for index in range(start, end):
        marker = ">" if index + 1 == line_number else " "
        output.append(f"  {marker} {index + 1}: {lines[index]}")
    return "\n".join(output)


def cmd_search(args: argparse.Namespace) -> int:
    vault = args.vault
    ensure_vault(vault)
    query = args.query.lower()
    matches: List[str] = []
    for path in note_files(vault):
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines, start=1):
            if query in line.lower():
                matches.append(format_search_hit(path.relative_to(vault), index, lines))
    if not matches:
        print(f"No matches for: {args.query}")
        return 1
    print("\n\n".join(matches))
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    graph = load_graph(args.vault)
    slug, note = resolve_note(args.note, graph)
    print(f"{note['title']} [{slug}]")
    print("Outgoing:")
    if note["links_to"]:
        for target_slug in note["links_to"]:
            target = graph.get(target_slug)
            label = target["title"] if target else target_slug
            print(f"- {label} [{target_slug}]")
    else:
        print("- None")

    print("Incoming:")
    if note["linked_from"]:
        for source_slug in note["linked_from"]:
            source = graph.get(source_slug)
            label = source["title"] if source else source_slug
            print(f"- {label} [{source_slug}]")
    else:
        print("- None")
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    graph = build_index(args.vault, write_graph=True)
    print(f"Indexed {len(graph)} notes into {args.vault / GRAPH_FILE}")
    return 0


def cmd_related(args: argparse.Namespace) -> int:
    graph = load_graph(args.vault)
    slug, note = resolve_note(args.note, graph)
    note_tags = set(note.get("tags", []))
    direct = set(note.get("links_to", [])) | set(note.get("linked_from", []))
    scored: List[Tuple[int, str, List[str]]] = []

    for candidate_slug, candidate in graph.items():
        if candidate_slug == slug:
            continue
        score = 0
        reasons: List[str] = []
        if candidate_slug in direct:
            score += 10
            reasons.append("direct-link")
        shared_tags = sorted(note_tags & set(candidate.get("tags", [])))
        if shared_tags:
            score += len(shared_tags) * 3
            reasons.append("shared-tags=" + ",".join(shared_tags))
        if candidate.get("type") == note.get("type"):
            score += 1
            reasons.append(f"type={candidate.get('type')}")
        if score:
            scored.append((score, candidate_slug, reasons))

    scored.sort(key=lambda item: (-item[0], graph[item[1]]["title"].lower()))
    if not scored:
        print(f"No related notes found for {note['title']}")
        return 0

    print(f"Related to {note['title']} [{slug}]")
    for score, candidate_slug, reasons in scored[:10]:
        candidate = graph[candidate_slug]
        print(f"- {candidate['title']} [{candidate_slug}] score={score} ({'; '.join(reasons)})")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    graph = load_graph(args.vault)
    results = []
    for slug, note in sorted(graph.items(), key=lambda item: item[1]["title"].lower()):
        if args.note_type and note.get("type") != args.note_type:
            continue
        if args.status and note.get("status") != args.status:
            continue
        if args.tag and args.tag not in note.get("tags", []):
            continue
        results.append(render_note_summary(slug, note))
    if not results:
        print("No notes found.")
        return 0
    print("\n".join(results))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    graph = load_graph(args.vault)
    counts = Counter(note.get("type", "note") for note in graph.values())
    connected = sorted(
        graph.items(),
        key=lambda item: (-(len(item[1]["links_to"]) + len(item[1]["linked_from"])), item[1]["title"].lower()),
    )
    orphans = [
        (slug, note)
        for slug, note in graph.items()
        if not note["links_to"] and not note["linked_from"]
    ]

    print(f"Vault: {args.vault}")
    print(f"Total notes: {len(graph)}")
    print("Notes per type:")
    for note_type, count in sorted(counts.items()):
        print(f"- {note_type}: {count}")

    print("Most connected:")
    if connected:
        for slug, note in connected[:10]:
            degree = len(note["links_to"]) + len(note["linked_from"])
            print(f"- {note['title']} [{slug}] degree={degree}")
    else:
        print("- None")

    print("Orphan notes:")
    if orphans:
        for slug, note in sorted(orphans, key=lambda item: item[1]["title"].lower()):
            print(f"- {note['title']} [{slug}]")
    else:
        print("- None")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpsClaw knowledge graph CLI")
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help=f"Vault path (default: {DEFAULT_VAULT})",
    )
    parser._positionals.title = "positional arguments"
    parser._optionals.title = "optional arguments"
    parser.add_argument(
        "--vault",
        type=Path,
        default=DEFAULT_VAULT,
        help=f"Vault path (default: {DEFAULT_VAULT})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", parents=[shared], help="Initialize a knowledge graph vault")
    init_parser.set_defaults(func=cmd_init)

    add_parser = subparsers.add_parser("add", parents=[shared], help="Add a note from a template")
    add_parser.add_argument("note_type", help="person|process|client|project|decision|meeting|policy|tool|note|general")
    add_parser.add_argument("title", help="Note title")
    add_parser.set_defaults(func=cmd_add)

    search_parser = subparsers.add_parser("search", parents=[shared], help="Search markdown notes")
    search_parser.add_argument("query", help="Search text")
    search_parser.set_defaults(func=cmd_search)

    graph_parser = subparsers.add_parser("graph", parents=[shared], help="Show incoming and outgoing links")
    graph_parser.add_argument("note", help="Note slug or title")
    graph_parser.set_defaults(func=cmd_graph)

    index_parser = subparsers.add_parser("index", parents=[shared], help="Rebuild _graph.json")
    index_parser.set_defaults(func=cmd_index)

    related_parser = subparsers.add_parser("related", parents=[shared], help="Find related notes")
    related_parser.add_argument("note", help="Note slug or title")
    related_parser.set_defaults(func=cmd_related)

    list_parser = subparsers.add_parser("list", parents=[shared], help="List notes with optional filters")
    list_parser.add_argument("--type", dest="note_type", choices=sorted(set(FOLDER_TO_TYPE.values())), help="Filter by type")
    list_parser.add_argument("--tag", help="Filter by tag")
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.set_defaults(func=cmd_list)

    stats_parser = subparsers.add_parser("stats", parents=[shared], help="Show vault statistics")
    stats_parser.set_defaults(func=cmd_stats)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.vault = args.vault.resolve()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
