---
name: sop_creator
description: Conversational SOP builder for OpsClaw. Use when the user wants to interview employees, turn process answers into a structured Standard Operating Procedure, store SOPs as Obsidian-compatible process notes, search them, validate them, or export them to HTML or text.
---

# SOP Creator

Use this skill when the user wants to capture a business process through chat and save it as a structured SOP in the knowledge graph vault.

## Load Order
1. Confirm the SOP vault path. Default: `./vault/processes/`.
2. If the user is using the knowledge graph skill, prefer `workspace/knowledge-graph/processes`.
3. Read `scripts/interview-questions.json` when you need the standard interview flow.
4. Use `scripts/sop.py` for deterministic creation, listing, validation, search, status changes, and export.

## Interview Flow
1. Ask one question at a time from `scripts/interview-questions.json`.
2. Capture the answers into a JSON object with keys that match the CLI payload:
   - `title`
   - `purpose`
   - `scope`
   - `owner`
   - `steps`
   - `exceptions`
   - `escalation`
   - `related_docs`
   - `review_frequency`
   - `additional_notes`
3. Normalize steps into objects with:
   - `step`
   - `action`
   - `details`
   - `responsible`
   - `tools`
   - `time`
4. Create the SOP with `create-from-interview`.
5. Run `validate` before presenting the final file path back to the user.

## Commands

Create a blank SOP draft:

```bash
python3 skills/sop-creator/scripts/sop.py create "Client Onboarding"
```

Create from an interview payload:

```bash
python3 skills/sop-creator/scripts/sop.py create-from-interview "Client Onboarding" \
  --answers /tmp/client-onboarding.json
```

List SOPs:

```bash
python3 skills/sop-creator/scripts/sop.py list
python3 skills/sop-creator/scripts/sop.py list --status draft
python3 skills/sop-creator/scripts/sop.py list --owner "Operations Team"
```

Update status:

```bash
python3 skills/sop-creator/scripts/sop.py update client-onboarding.md --status active
```

Search the vault:

```bash
python3 skills/sop-creator/scripts/sop.py search "AML checks"
```

Validate structure:

```bash
python3 skills/sop-creator/scripts/sop.py validate client-onboarding.md
```

Export:

```bash
python3 skills/sop-creator/scripts/sop.py export client-onboarding.md --format html
python3 skills/sop-creator/scripts/sop.py export client-onboarding.md --format text
```

## Conversational Operating Rules
- Ask focused questions and do not dump the full questionnaire unless the user asks for it.
- Reflect incomplete or ambiguous steps back to the user before generating the final SOP.
- Keep related documents in Obsidian wikilink form such as `[[AML Policy]]`.
- Use `--vault` or `SOP_VAULT_PATH` whenever the user has a non-default vault.
- Treat SOPs as process notes: frontmatter `type` must remain `process`.

## Knowledge Graph Integration
- SOP files are plain markdown notes stored under the process folder in the vault.
- Related documents should stay as wikilinks so the knowledge graph can traverse them later.
- If the user keeps a shared vault, standardize on `workspace/knowledge-graph/processes`.

## Example Walkthrough
1. Ask: `What is this process called?`
2. Ask follow-up questions until you have purpose, scope, owner, steps, exceptions, escalation path, related documents, review frequency, and notes.
3. Save the interview payload:

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
      "details": "Check passport or driving licence and log the outcome in CRM.",
      "responsible": "LPE",
      "tools": "Creatio CRM",
      "time": "5 mins"
    }
  ],
  "exceptions": [
    "If the client is a PEP, stop the workflow and escalate to compliance."
  ],
  "escalation": "Escalate blocked or high-risk cases to Compliance Team lead in the compliance portal.",
  "related_docs": [
    "AML Policy",
    "Client Onboarding Checklist"
  ],
  "review_frequency": "Quarterly",
  "additional_notes": "New joiners should shadow one onboarding case before owning the process."
}
```

4. Create and validate:

```bash
python3 skills/sop-creator/scripts/sop.py create-from-interview "Onboarding New Client" \
  --answers /tmp/onboarding-new-client.json \
  --vault workspace/knowledge-graph/processes
python3 skills/sop-creator/scripts/sop.py validate onboarding-new-client.md \
  --vault workspace/knowledge-graph/processes
```
