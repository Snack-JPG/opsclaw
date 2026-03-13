# Email Intelligence Skill

This skill adds Gmail-based inbox triage, daily email briefings, VIP escalation, and approval-safe draft generation to OpsClaw through the Google Workspace CLI (`gws`).

## What It Does
- Fetches Gmail inbox data through `gws gmail`
- Classifies incoming mail by urgency and business category
- Flags VIP senders immediately
- Generates owner briefings for unread / recent mail
- Creates Gmail drafts for routine messages and queues them for approval

## Files
- `SKILL.md`: agent operating instructions
- `scripts/gws-auth-setup.sh`: wrapper for `gws auth setup --login`
- `scripts/classify.py`: deterministic classification engine
- `scripts/briefing.py`: email briefing generator using classified JSON or live Gmail data
- `scripts/auto_responder.py`: rule-driven draft generator with approval queue output and Gmail draft creation
- `config/*.json`: sender lists, classification settings, and response rules
- `scripts/templates/*.md`: default response templates

## Prerequisites
- Google Workspace or Gmail account with API access
- `gws`, `python3`, and `openclaw` installed locally
- OpsClaw workspace already initialized

## Quick Start
Run:

```bash
./skills/email-intel/scripts/gws-auth-setup.sh
gws auth status
```

Then test a live inbox fetch:

```bash
python3 skills/email-intel/scripts/classify.py \
  --query "in:inbox newer_than:1d" \
  --max-results 5 \
  --categories skills/email-intel/config/categories.json \
  --vip skills/email-intel/config/vip-senders.json \
  --pretty
```

## Recommended OpenClaw Hook Config
Add or merge this into your workspace config:

```json5
{
  hooks: {
    enabled: true,
    token: "${OPSCLAW_HOOKS_TOKEN}",
    path: "/hooks",
    presets: ["gmail"],
    gmail: {
      model: "anthropic/claude-sonnet-4-20250514",
      thinking: "off"
    },
    mappings: [{
      match: { path: "gmail" },
      action: "agent",
      wakeMode: "now",
      name: "Gmail",
      sessionKey: "hook:gmail:{{messages[0].id}}",
      messageTemplate: "New email from {{messages[0].from}}\\nSubject: {{messages[0].subject}}\\n\\n{{messages[0].body}}",
      deliver: true,
      channel: "last"
    }]
  },
  skills: {
    entries: {
      "email-intel": { enabled: true }
    }
  }
}
```

## Gmail Processing Flow
1. `gws gmail users messages list` fetches inbox candidates.
2. `gws gmail users messages get` fetches full message bodies.
3. The Email Intelligence skill classifies the email, updates `workspace/ops-state.json`, queues drafts, and records memory.
4. `scripts/auto_responder.py` can create Gmail drafts through `gws gmail users drafts create`.

## Local Script Usage

### Classification
```bash
python3 skills/email-intel/scripts/classify.py \
  --query "in:inbox newer_than:1d" \
  --max-results 10 \
  --categories skills/email-intel/config/categories.json \
  --vip skills/email-intel/config/vip-senders.json
```

### Briefing
```bash
python3 skills/email-intel/scripts/briefing.py \
  --ops-state workspace/ops-state.json \
  --categories skills/email-intel/config/categories.json \
  --vip skills/email-intel/config/vip-senders.json
```

### Auto Responder
```bash
python3 skills/email-intel/scripts/auto_responder.py \
  --message-id YOUR_GMAIL_MESSAGE_ID \
  --rules skills/email-intel/config/rules.json \
  --templates-dir skills/email-intel/scripts/templates \
  --ops-state workspace/ops-state.json
```

## Configuration

### `config/vip-senders.json`
Keep this aligned with the VIP contacts section in `workspace/USER.md`. Add a business reason for each sender.

### `config/categories.json`
Defines urgency keywords, category keywords, sender domain rules, and score thresholds. Tune these first if triage feels noisy.

### `config/rules.json`
Controls when drafts should be generated automatically, what template to use, whether approval is required, and what messages should be blocked from automation.

## Operational Notes
- Drafts are generated automatically when rules match, and Gmail drafts can be created automatically, but they are never sent automatically without explicit approval.
- Billing emails may be drafted only for neutral acknowledgements unless your policy says otherwise.
- Log exhausted retries to `workspace/memory/dead-letters/YYYY-MM-DD.json`.
- Keep `workspace/ops-state.json` as the source of truth for urgent items and pending approvals.

## Verification Checklist
- Send a test email from a VIP sender and confirm it lands in the urgent path.
- Send a billing email and confirm category = `billing`.
- Send a routine info request and confirm a draft is queued for approval.
- Re-run a classification fetch and confirm the queue is not duplicated when the same message is processed twice.
- Generate a briefing from live inbox data and confirm counts match the unread set.
