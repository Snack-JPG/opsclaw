# Email Intelligence Skill

This skill adds Gmail-based inbox triage, daily email briefings, VIP escalation, and approval-safe draft generation to OpsClaw.

## What It Does
- Receives Gmail change notifications through Google Pub/Sub and OpenClaw's `gmail` webhook preset
- Classifies incoming mail by urgency and business category
- Flags VIP senders immediately
- Generates owner briefings for unread / recent mail
- Creates draft replies for routine messages and queues them for approval

## Files
- `SKILL.md`: agent operating instructions
- `scripts/gmail-setup.sh`: one-command Gmail API and Pub/Sub bootstrap
- `scripts/classify.py`: deterministic classification engine
- `scripts/briefing.py`: email briefing generator
- `scripts/auto_responder.py`: rule-driven draft generator with approval queue output
- `config/*.json`: sender lists, classification settings, and response rules
- `scripts/templates/*.md`: default response templates

## Prerequisites
- Google Workspace or Gmail account with API access
- A Google Cloud project you can administer
- `gcloud`, `jq`, `python3`, and `openclaw` installed locally
- `gog` installed if you want a local Gmail watch forwarder process
- OpsClaw workspace already initialized

## Quick Start
Run:

```bash
./skills/email-intel/scripts/gmail-setup.sh \
  --project-id YOUR_GCP_PROJECT \
  --topic opsclaw-gmail \
  --subscription opsclaw-gmail-push \
  --webhook-url https://YOUR-HOST/hooks/gmail \
  --email you@yourcompany.com
```

The script:
1. Enables required Google APIs
2. Creates the Pub/Sub topic and push subscription
3. Grants Gmail publish access to the topic
4. Prints the `gog gmail watch serve` command
5. Prints the Gmail watch registration command and the matching OpenClaw hook config

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

## Gmail Watch Flow
1. Gmail posts change notifications to the Pub/Sub topic.
2. Pub/Sub delivers to your push endpoint or to a local forwarder.
3. OpenClaw's `gmail` hook preset normalizes the payload.
4. The Email Intelligence skill classifies the email, updates `workspace/ops-state.json`, queues drafts, and records memory.

If you use a local bridge instead of direct Pub/Sub push, run:

```bash
gog gmail watch serve \
  --project YOUR_GCP_PROJECT \
  --subscription opsclaw-gmail-push \
  --forward-to https://YOUR-HOST/hooks/gmail
```

## Local Script Usage

### Classification
```bash
python3 skills/email-intel/scripts/classify.py \
  --email-path /tmp/email.json \
  --categories skills/email-intel/config/categories.json \
  --vip skills/email-intel/config/vip-senders.json
```

### Briefing
```bash
python3 skills/email-intel/scripts/briefing.py \
  --emails-path /tmp/classified-emails.json \
  --ops-state workspace/ops-state.json
```

### Auto Responder
```bash
python3 skills/email-intel/scripts/auto_responder.py \
  --email-path /tmp/classified-email.json \
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
- Drafts are generated automatically when rules match, but they are never sent automatically.
- Billing emails may be drafted only for neutral acknowledgements unless your policy says otherwise.
- Log exhausted retries to `workspace/memory/dead-letters/YYYY-MM-DD.json`.
- Keep `workspace/ops-state.json` as the source of truth for urgent items and pending approvals.

## Verification Checklist
- Send a test email from a VIP sender and confirm it lands in the urgent path.
- Send a billing email and confirm category = `billing`.
- Send a routine info request and confirm a draft is queued for approval.
- Trigger the same webhook twice and confirm the queue is not duplicated.
- Generate a briefing and confirm counts match the unread set.
