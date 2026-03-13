# USER.md — Client Profile Template

Complete this file during onboarding. Keep it current; OpsClaw uses it to make prioritization and escalation decisions.

## Business Snapshot
- Company: `Your Company Name`
- Industry: `Industry / niche`
- Primary offer: `What the business sells`
- Team size: `1-50`
- Business stage: `solo`, `growing team`, `established SMB`
- Revenue motion: `services`, `retainer`, `ecommerce`, `software`, `mixed`
- Timezone of truth: `Europe/London`

## Owner
- Name: `Owner Name`
- Role: `Founder / COO / Director`
- Primary contact channel: `Telegram`
- Backup contact channel: `Email or phone`
- Preferred briefing style: `concise`
- Working hours: `07:00-18:00 local time`
- Quiet hours override for urgent alerts: `true`

## Operational Priorities
- Never miss urgent client emails or calendar obligations.
- Keep all follow-ups visible and current.
- Prepare the owner for meetings with recent context and risks.
- Flag revenue-impacting delays before they become escalations.
- Preserve a clear audit trail for approvals and external communications.

## Approval Policy
### Execute immediately
- Internal logging and state updates
- Read-only API lookups
- Owner briefings and internal summaries
- Draft creation that is shown but not sent
- Internal task creation where policy allows
- CRM notes that do not alter pipeline value or stage

### Queue for approval
- External emails and messages
- Calendar changes
- CRM deal-stage or forecast changes
- Any action affecting customers, partners, or vendors externally

### Always block
- Payments, refunds, transfers, invoices, payroll actions
- Deleting data permanently
- Sharing credentials or secrets

## VIP Contacts
List people whose messages should bypass normal batching and trigger urgent review.

| Name | Company | Email | Reason |
| --- | --- | --- | --- |
| `Example VIP` | `Strategic Client Co` | `vip@example.com` | `Top account / high escalation risk` |
| `Legal Counsel` | `External` | `legal@example.com` | `Legal or contractual exposure` |
| `Key Partner` | `Channel Partner` | `partner@example.com` | `Revenue-sensitive partnership` |

## Core Systems
- Email provider: `Gmail / Outlook`
- Calendar provider: `Google Calendar / Microsoft 365`
- CRM: `HubSpot / Pipedrive / none`
- Task tracker: `Linear / Notion / Asana / none`
- Reporting destination: `Telegram / Slack / Email`
- Hosting model: `client machine / VPS / Docker Compose`

## Business Rhythms
### Daily
- Morning briefing time: `07:30`
- End-of-day summary: `18:00`
- Typical email peaks: `09:00-11:00`, `14:00-16:00`
- Deep work blocks to avoid interrupting: `10:30-12:00`

### Weekly
- Weekly planning: `Monday 08:30`
- Team standup: `Monday-Friday 09:00`
- Client review window: `Thursday afternoon`
- Weekly review delivery: `Monday 08:00`

### Monthly
- Invoicing / finance review: `Last business day`
- Client health review: `First Monday`
- Operations cleanup: `Second Friday`

## Classification Rules
- Treat invoices, security notices, legal requests, and contract changes as at least high priority.
- Treat newsletters and low-signal notifications as low priority unless the sender is on a VIP list.
- Escalate mentions of churn risk, delay, cancellation, outage, fraud, data request, or chargeback.
- Drafts should mirror the owner's tone: direct, warm, and commercially aware.

## Task Rules
- Default task priority: `medium`
- Default due-date assumption when omitted: `end of current week`
- Create tasks in the owner's name unless another assignee is explicit.
- Mark tasks blocked when an approval, dependency, or missing information prevents progress.

## CRM Rules
- Log meaningful client interactions the same day.
- Consider health score at risk below `50`.
- Escalate follow-ups overdue by more than `7` days for active opportunities.
- Do not change stages or pipeline values without approval.

## Compliance Notes
- Redact payment card numbers, national IDs, passwords, and API secrets from all logs.
- Respect GDPR / local privacy obligations for customer data.
- Keep approval evidence for all external communications.

## Success Metrics
- Urgent email acknowledgement path under `15 minutes`
- Morning brief sent on time `100%`
- Overdue follow-up backlog trending downward week-over-week
- Fewer than `5%` false-positive urgent escalations
- At least `2` hours/day of owner time saved

## Freeform Notes
Add nuanced business context here: major accounts, seasonal events, product launches, risky customers, hiring activity, or anything OpsClaw should treat as important background.
