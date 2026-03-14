---
name: knowledge_graph
description: Obsidian-style markdown knowledge graph for OpsClaw. Use when the user wants to store, search, index, or traverse company knowledge as linked notes about people, clients, projects, processes, decisions, meetings, policies, tools, or general notes.
---

# Knowledge Graph Skill

Use this skill when the user wants a file-based company knowledge base that AI agents can read and update directly, or when the task involves linked markdown notes, wikilinks, note templates, vault indexing, or note traversal.

## Load Order
1. Confirm the vault path. Default: `workspace/knowledge-graph`.
2. Use the bundled CLI for deterministic operations:
   - `scripts/kb.py`
3. Only read note files that are relevant to the current request. Use `_graph.json` for fast traversal before opening many notes.

## Vault Model
- The vault is plain markdown plus `_graph.json`.
- Folders:
  - `people/`
  - `processes/`
  - `clients/`
  - `projects/`
  - `decisions/`
  - `meetings/`
  - `policies/`
  - `tools/`
  - `general/`
  - `_templates/`
- Links use Obsidian wikilinks: `[[Note Title]]`.
- Notes use YAML frontmatter with these fields:
  - `title`
  - `type`
  - `tags`
  - `status`
  - `created`
  - `updated`
  - `author`
  - `confidentiality`
  - `permalink`

## Commands
- Initialize a vault:

```bash
python3 skills/knowledge-graph/scripts/kb.py init
```

- Add a note from a template:

```bash
python3 skills/knowledge-graph/scripts/kb.py add person "Jane Smith"
python3 skills/knowledge-graph/scripts/kb.py add project "Q2 Launch"
```

- Search note contents:

```bash
python3 skills/knowledge-graph/scripts/kb.py search "pricing review"
```

- Rebuild the graph index:

```bash
python3 skills/knowledge-graph/scripts/kb.py index
```

- Show graph connections for a note:

```bash
python3 skills/knowledge-graph/scripts/kb.py graph "Q2 Launch"
```

- Find related notes:

```bash
python3 skills/knowledge-graph/scripts/kb.py related "Q2 Launch"
```

- List notes with optional filters:

```bash
python3 skills/knowledge-graph/scripts/kb.py list --type project --status active
python3 skills/knowledge-graph/scripts/kb.py list --tag risk
```

- Show vault statistics:

```bash
python3 skills/knowledge-graph/scripts/kb.py stats
```

## Authoring Rules
- Prefer one durable concept per note.
- Keep titles human-readable. The CLI handles slug generation for filenames and permalinks.
- Put link-heavy facts in a `## Relations` section with typed bullets such as:
  - `- works_at [[Acme Corp]]`
  - `- manages [[Q2 Launch]]`
- Put atomic facts in `## Observations` using bracketed categories such as:
  - `- [decision] We chose Python for the backend`
  - `- [risk] Timeline is tight for Q2`
  - `- [action] Schedule review meeting by Friday`
- Update `updated` when editing existing notes.
- Run `kb.py index` after meaningful note edits so `_graph.json` stays current.

## Operational Guidance
- Use `_graph.json` first for traversal, incoming-link lookups, type filters, tag filters, and stats.
- Use `search` when exact note names are unknown or the user asks for raw text matches.
- Use `related` to surface likely neighbors before opening a large set of notes.
- If the user wants a custom vault location, pass `--vault /path/to/vault` to every command.

## Acceptance Standard
- `init` creates the full vault folder set, templates, and an empty `_graph.json`.
- `add` creates correctly templated notes with valid frontmatter and slugs.
- `index` rebuilds `_graph.json` from markdown files only.
- `graph` shows outgoing and incoming note links.
- `related`, `list`, and `stats` work from the indexed graph without external services.
