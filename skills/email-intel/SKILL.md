---
name: email_intel
description: Email intelligence for OpsClaw: triage Gmail or Outlook inbox activity, classify urgency and category, generate daily briefings, maintain email state, and prepare approval-safe response drafts.
---

# Email Intelligence Skill

Use this skill whenever the user asks to check email, summarize inbox activity, classify incoming mail, draft a reply, maintain a VIP sender list, or operate the Gmail / briefing flow through the Google Workspace CLI (`gws`). It also applies to scheduled heartbeat and daily briefing runs when email is enabled.

## Load Order
1. Read `workspace/SOUL.md`, `workspace/USER.md`, `workspace/AGENTS.md`, and `workspace/ops-state.json`.
2. Read today's memory note in `workspace/memory/YYYY-MM-DD.md` and yesterday's note if continuity matters.
3. Read this skill's config files before classifying or drafting:
   - `config/vip-senders.json`
   - `config/categories.json`
   - `config/rules.json`
4. Use the bundled scripts for deterministic work instead of re-implementing logic inline:
   - `scripts/classify.py`
   - `scripts/briefing.py`
   - `scripts/auto_responder.py`

## Triggers
- `Webhook`: Gmail change detection or polling flow mapped through OpenClaw's inbox automation.
- `Heartbeat`: urgent unread scan and stale draft / queue review.
- `Cron`: daily inbox briefing at the owner's configured briefing time.
- `Manual`: commands such as `Check email`, `Email summary`, `Draft reply to <sender>`, `Mark <email> as handled`, or `Add <sender> to VIP list`.

## Core Responsibilities
- Classify each inbound email by urgency: `critical`, `high`, `medium`, or `low`.
- Categorize each inbound email as `client`, `internal`, `billing`, `marketing`, or `spam`.
- Surface VIP senders immediately.
- Create approval-safe drafts for routine emails that match configured rules.
- Maintain a clean audit trail in memory and `workspace/ops-state.json`.
- Produce concise briefings that reduce inbox noise without hiding risk.

## Classification Rules

### Urgency
- `critical`
  - Security incident, legal request, outage, data-loss risk, chargeback/fraud, same-day deadline, cancellation/churn threat, or explicit escalation from a VIP.
  - Any email requiring owner awareness inside 15 minutes.
- `high`
  - Revenue-sensitive client issue, payment failure, contract or invoice problem, partner dependency, meeting or deliverable due today, or direct blocker on active work.
- `medium`
  - Routine client requests, internal coordination, non-urgent approvals, scheduling, normal follow-ups, and information requests that should be handled today or this week.
- `low`
  - Newsletters, marketing, cold outreach, automated notifications with no action, and low-signal FYI messages.

Escalate upward when multiple signals stack: VIP sender, explicit urgency terms, overdue context from memory, or financially / legally sensitive language.

### Category
- `client`: customers, prospects, partners, delivery stakeholders, or account communications.
- `internal`: owner, employees, contractors, or internal tools using company domains.
- `billing`: invoices, receipts, payment failures, subscriptions, renewals, refunds, taxes.
- `marketing`: newsletters, product announcements, cold outreach, webinars, promotional content.
- `spam`: obvious junk, malicious, phishing, irrelevant mass mail, repeated unsubscribe-worthy mail.

When category is ambiguous, prefer the most operationally meaningful category over `spam`.

## Webhook Flow: New Email
When a Gmail-triggered email workflow runs:

1. Treat the ingress as `internal_query` until parsing succeeds.
2. Enforce idempotency using the message ID or webhook event ID. Skip duplicates and log them as duplicate receipts, not failures.
3. If only a Gmail message ID is available, fetch the full message via `gws gmail users messages get`.
4. Normalize the email payload into:
   - message ID
   - thread ID
   - timestamp
   - sender name/email
   - recipients
   - subject
   - plain-text body
   - snippet / preview
5. Run `scripts/classify.py` with the normalized payload plus config files, or let it fetch directly from Gmail with `gws`.
6. Update `workspace/ops-state.json`:
   - increment / refresh `email.unreadCount`
   - append urgent items to `email.urgentQueue`
   - append draft approvals to `email.pendingDrafts` and `approvals.pending`
   - update `email.lastChecked` and `lastUpdated`
7. If the sender matches `config/vip-senders.json` and the message is not low-signal marketing, alert the owner immediately unless quiet-hours policy blocks it.
8. If the message matches an auto-response rule, run `scripts/auto_responder.py` to produce a draft, create a Gmail draft via `gws gmail users drafts create`, and queue it for approval. Sending remains `external_email` and always requires explicit approval.
9. Write a concise memory entry to today's note with:
   - what arrived
   - why it matters
   - classification
   - recommended next step
10. On transient failures, retry with exponential backoff. On exhausted retries, write a dead letter to `workspace/memory/dead-letters/YYYY-MM-DD.json`.

## Heartbeat Flow
During heartbeat runs:

1. Review unread / urgent email state and time since `email.lastChecked`.
2. Scan for:
   - unread critical or high items older than SLA
   - VIP messages without an owner alert
   - pending drafts awaiting approval too long
   - repeated webhook failures or rising dead-letter count
3. Update `workspace/heartbeat-state.json` counters for the email subsystem.
4. Respect quiet hours:
   - critical: alert now if allowed by `workspace/USER.md`
   - non-critical: queue for morning briefing

## Daily Briefing Format
Run `scripts/briefing.py` for the last 24 hours of unread or newly classified mail. It can consume a pre-classified JSON file or fetch fresh inbox data via `gws gmail users messages list` + `get`. Deliver a concise owner-facing brief in this structure:

```text
Email Briefing
Period: <start> -> <end>

Critical
- <sender> - <subject>: <why it matters> | Recommended: <next step>

Requires Response
- <sender> - <subject> [<urgency>/<category>]: <one-line summary>
  Draft: <template or recommendation>

FYI
- <sender> - <subject>: <one-line summary>

Filtered Out
- Marketing: <count>
- Spam: <count>

Queue Health
- Unread: <count>
- Urgent queue: <count>
- Pending drafts: <count>
- Oldest high-priority item: <age or none>
```

Rules:
- Lead with `critical`, then action-needed items, then low-signal counts.
- Never paste raw secrets, payment card numbers, passwords, or personal identifiers.
- Mention missing data or degraded email sync plainly.
- If nothing material happened, say so in one line and still report queue health.

## Manual Commands
- `Check email`
  - Scan the latest unread mail with `gws gmail users messages list`, classify, and report anything `high` or `critical`.
- `Email summary`
  - Generate an on-demand briefing for the default or requested time window from live Gmail data or a supplied JSON snapshot.
- `Draft reply to <sender or subject>`
  - Find the thread, generate a draft, store it in Gmail drafts via `gws`, summarize why the draft fits, and queue for approval.
- `Mark <email> as handled`
  - Remove it from urgent / pending lists, update state, and note the resolution in memory.
- `Add <sender> to VIP list`
  - Update `config/vip-senders.json` with a reason and source of the change.

## Drafting and Approval Policy
- Draft generation is allowed without approval.
- Gmail draft creation is allowed without approval.
- Draft sending is never allowed without explicit owner approval captured in state or the active conversation.
- Every draft queue item must include:
  - message ID / thread ID
  - sender
  - subject
  - chosen template or rationale
  - recommended action
  - risk level
- If a request touches legal, HR, compliance, refunds, or contract commitments, do not auto-draft unless the rule explicitly permits a neutral acknowledgement.

## Reliability and Observability
- Use deterministic scripts for classification, briefing, and draft generation.
- Use `gws auth setup` and `gws auth login` for shared Google Workspace authentication instead of per-skill OAuth code.
- Use `gws gmail users messages list|get` for inbox reads and `gws gmail users drafts create|send` for draft operations.
- Prefer JSON in / JSON out for script boundaries.
- Preserve correlation IDs from webhook to queue entry to memory note when possible.
- Use the addendum reliability model:
  - idempotency for duplicate events
  - retry with backoff for transient failures
  - dead-letter capture after retry exhaustion
- Log results with action class, severity, duration, and sanitized context.

## Setup and References
- Human setup instructions live in `README.md`.
- Gmail / Workspace auth bootstrap is handled by `scripts/gws-auth-setup.sh`.
- Response templates live in `scripts/templates/`.

## Acceptance Standard
This skill is considered healthy when:
- Gmail notifications process within 60 seconds.
- Duplicate webhook events do not create duplicate queue entries.
- Classification is explainable and consistent across the acceptance test cases.
- VIP senders trigger immediate owner awareness.
- Daily briefings arrive in the configured format on time.
- Auto-drafts are generated for rule-matched messages and queued for approval.
- Failures are visible in dead-letter storage rather than disappearing silently.
