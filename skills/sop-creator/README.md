# SOP Creator Skill

The SOP Creator skill turns conversational process capture into structured, Obsidian-compatible SOP markdown files. It is designed for OpsClaw agents that need to interview employees, convert answers into a repeatable operating procedure, and store the result inside a knowledge graph vault.

## Files

- `SKILL.md`: agent instructions for the conversational workflow
- `scripts/sop.py`: stdlib-only CLI for SOP creation, listing, search, validation, status updates, and export
- `scripts/interview-questions.json`: configurable default interview prompts
- `templates/sop-template.md`: source template used for generated SOP markdown

## Vault Path

The CLI resolves the target vault in this order:

1. `--vault /path/to/processes`
2. `SOP_VAULT_PATH`
3. `./vault/processes/`

For knowledge graph integration, point the CLI at `workspace/knowledge-graph/processes`.

## Usage

Create a blank draft:

```bash
python3 skills/sop-creator/scripts/sop.py create "Matter Opening"
```

Create a full SOP from an interview payload:

```bash
python3 skills/sop-creator/scripts/sop.py create-from-interview "Onboarding New Client" \
  --answers /tmp/onboarding-new-client.json \
  --vault workspace/knowledge-graph/processes
```

List and filter SOPs:

```bash
python3 skills/sop-creator/scripts/sop.py list
python3 skills/sop-creator/scripts/sop.py list --status active
python3 skills/sop-creator/scripts/sop.py list --owner "Operations Team"
```

Search, validate, update, and export:

```bash
python3 skills/sop-creator/scripts/sop.py search "compliance portal"
python3 skills/sop-creator/scripts/sop.py validate onboarding-new-client.md
python3 skills/sop-creator/scripts/sop.py update onboarding-new-client.md --status active
python3 skills/sop-creator/scripts/sop.py export onboarding-new-client.md --format html
python3 skills/sop-creator/scripts/sop.py export onboarding-new-client.md --format text
```

## Interview Payload

Expected JSON shape:

```json
{
  "title": "Onboarding New Client",
  "purpose": "Ensure consistent client onboarding across all regions",
  "scope": "All LPEs and support staff handling new client instructions",
  "owner": "Operations Team",
  "steps": [
    {
      "step": 1,
      "action": "Verify client identity",
      "details": "Check passport or driving licence. Log in CRM.",
      "responsible": "LPE",
      "tools": "Creatio CRM",
      "time": "5 mins"
    }
  ],
  "exceptions": [
    "If client is a PEP, escalate to compliance team before proceeding"
  ],
  "escalation": "Escalate exceptions to the compliance manager and log the incident.",
  "related_docs": [
    "AML Policy",
    "Client Onboarding Checklist"
  ],
  "review_frequency": "Quarterly",
  "additional_notes": "New starters should shadow the process once before running it solo."
}
```

## Template Format

Generated SOPs use:

- YAML frontmatter with `type: process`
- A markdown steps table for quick scanning
- `[[wikilinks]]` for related documents
- Version history and review schedule sections

The template lives in `templates/sop-template.md` and can be adjusted without changing the CLI.

## Export Options

- `--format html`: standalone HTML with inline CSS, printer-friendly layout, and no external assets
- `--format text`: plain text export for copy/paste, email, or terminal workflows
