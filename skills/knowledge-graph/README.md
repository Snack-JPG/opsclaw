# Knowledge Graph Skill

This skill adds an Obsidian-compatible markdown knowledge base to OpsClaw. Notes live on disk, use YAML frontmatter plus wikilinks, and are indexed into `_graph.json` for fast traversal by agents.

## Files
- `SKILL.md`: agent operating instructions
- `scripts/kb.py`: stdlib-only CLI for vault setup, note creation, search, indexing, graph traversal, related-note discovery, listing, and stats
- `_templates/*.md`: canonical note templates copied into each vault by `kb init`

## Default Vault

The CLI defaults to:

```bash
workspace/knowledge-graph
```

Use `--vault /custom/path` to target another location.

## Quick Start

Initialize the vault:

```bash
python3 skills/knowledge-graph/scripts/kb.py init
```

Create notes:

```bash
python3 skills/knowledge-graph/scripts/kb.py add person "Jane Smith"
python3 skills/knowledge-graph/scripts/kb.py add client "Acme Corp"
python3 skills/knowledge-graph/scripts/kb.py add project "Q2 Launch"
```

Rebuild the graph index:

```bash
python3 skills/knowledge-graph/scripts/kb.py index
```

Traverse and search:

```bash
python3 skills/knowledge-graph/scripts/kb.py graph "Jane Smith"
python3 skills/knowledge-graph/scripts/kb.py related "Q2 Launch"
python3 skills/knowledge-graph/scripts/kb.py search "timeline"
```

Filter and inspect the vault:

```bash
python3 skills/knowledge-graph/scripts/kb.py list --type project --status draft
python3 skills/knowledge-graph/scripts/kb.py stats
```

## Note Format

All notes use this frontmatter schema:

```yaml
---
title: Note Title
type: person|process|client|project|decision|meeting|policy|tool|note
tags: [tag1, tag2]
status: active|archived|draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
author: agent-name
confidentiality: public|internal|restricted
permalink: note-slug
---
```

Links use Obsidian wikilinks such as `[[Acme Corp]]`. Typed relations belong under `## Relations`, and categorized facts belong under `## Observations`.

## Design Rationale

- Zero dependencies: Python stdlib only.
- Files are the database: markdown is the system of record.
- Obsidian-compatible: the vault opens cleanly in Obsidian.
- Agent-friendly: notes are simple files, and `_graph.json` avoids rescanning for every traversal.
