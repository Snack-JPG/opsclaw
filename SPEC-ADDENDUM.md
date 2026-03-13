# SPEC Addendum — Structural Improvements (from Codex Review)

*These additions harden the spec without cutting any features. Applied to full build.*

---

## 1. State Schemas

All JSON state files have defined schemas for consistency and migration support.

### ops-state.json
```json
{
  "$schema": "opsclaw/ops-state/v1",
  "version": 1,
  "lastUpdated": "2026-03-12T14:00:00Z",
  "email": {
    "unreadCount": 0,
    "urgentQueue": [],
    "pendingDrafts": [],
    "lastChecked": null
  },
  "calendar": {
    "todayEvents": [],
    "nextMeeting": null,
    "prepStatus": {},
    "lastChecked": null
  },
  "tasks": {
    "dueToday": [],
    "overdue": [],
    "blocked": [],
    "lastChecked": null
  },
  "crm": {
    "followUpsDue": [],
    "atRiskClients": [],
    "lastChecked": null
  },
  "briefing": {
    "lastMorningBrief": null,
    "lastWeeklyReview": null
  }
}
```

### client-db.json
```json
{
  "$schema": "opsclaw/client-db/v1",
  "version": 1,
  "clients": {
    "<client_id>": {
      "name": "string",
      "company": "string",
      "email": "string",
      "phone": "string | null",
      "crmId": "string | null",
      "tier": "vip | standard | low",
      "tags": ["string"],
      "lastContact": "ISO-8601 | null",
      "healthScore": "number (0-100) | null",
      "notes": "string",
      "createdAt": "ISO-8601",
      "updatedAt": "ISO-8601"
    }
  }
}
```

### heartbeat-state.json
```json
{
  "$schema": "opsclaw/heartbeat-state/v1",
  "version": 1,
  "lastChecks": {
    "email": "ISO-8601 | null",
    "calendar": "ISO-8601 | null",
    "tasks": "ISO-8601 | null",
    "crm": "ISO-8601 | null",
    "reporting": "ISO-8601 | null"
  },
  "lastBriefingSent": "ISO-8601 | null",
  "consecutiveErrors": {
    "email": 0,
    "calendar": 0,
    "tasks": 0,
    "crm": 0
  }
}
```

---

## 2. Reliability Architecture

### Webhook Idempotency
```python
# Every webhook handler checks for duplicate processing
class WebhookProcessor:
    def __init__(self):
        self.processed_ids = {}  # id -> timestamp, TTL 24h
    
    def process(self, event_id: str, payload: dict) -> bool:
        if event_id in self.processed_ids:
            log.info(f"Duplicate webhook {event_id}, skipping")
            return False
        self.processed_ids[event_id] = time.time()
        self._cleanup_old_entries()
        return True
```

### Retry with Backoff
```python
# All API calls use exponential backoff
import time
import random

def retry_with_backoff(fn, max_retries=3, base_delay=1.0):
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except (ConnectionError, TimeoutError, RateLimitError) as e:
            if attempt == max_retries:
                log.error(f"Failed after {max_retries} retries: {e}")
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            log.warning(f"Attempt {attempt + 1} failed, retrying in {delay:.1f}s")
            time.sleep(delay)
```

### Dead Letter Capture
Failed events are logged to `memory/dead-letters/YYYY-MM-DD.json` for manual review:
```json
{
  "id": "evt_123",
  "source": "gmail_webhook",
  "payload": { "...": "..." },
  "error": "HubSpot API returned 429",
  "attempts": 3,
  "firstAttempt": "2026-03-12T14:00:00Z",
  "lastAttempt": "2026-03-12T14:03:12Z"
}
```

### Reconciliation Cron
Daily at 2:00 AM — scan for missed events:
```json5
{
  name: "Reconciliation Check",
  schedule: { kind: "cron", expr: "0 2 * * *" },
  payload: { kind: "agentTurn", message: "Run reconciliation: check for missed emails (compare inbox vs processed count), orphaned tasks, and stale CRM follow-ups. Report any gaps to memory/dead-letters/." },
  sessionTarget: "isolated",
}
```

---

## 3. Acceptance Criteria (per Phase)

### Phase 1: Core Infrastructure ✅ when:
- [ ] `setup.sh` runs clean on fresh Ubuntu 22.04 + macOS
- [ ] Gateway starts with no errors
- [ ] Telegram channel sends + receives messages
- [ ] Heartbeat fires at configured interval
- [ ] HEARTBEAT.md checklist executes without errors
- [ ] Security audit (`openclaw security audit`) passes clean

### Phase 2: Email Intelligence ✅ when:
- [ ] Gmail webhook receives and processes test email within 60s
- [ ] Duplicate email webhook handled (no double-processing)
- [ ] Email classified correctly for 10 test cases (2 urgent, 3 high, 3 medium, 2 low)
- [ ] VIP sender triggers immediate notification
- [ ] Daily briefing generates and delivers at configured time
- [ ] Auto-draft generates for template-matched email
- [ ] Failed webhook logged to dead-letters

### Phase 3: Calendar & Scheduling ✅ when:
- [ ] Today's events fetched correctly from Google Calendar
- [ ] Morning briefing includes all events with correct times
- [ ] Meeting prep doc generated 30min before test meeting
- [ ] "What's next?" returns correct next event
- [ ] "Am I free Friday 3pm?" returns correct availability
- [ ] Calendar conflict flagged when double-booking exists

### Phase 4: CRM Integration ✅ when:
- [ ] HubSpot/Pipedrive contact lookup returns correct data
- [ ] Email interaction auto-logged to CRM contact timeline
- [ ] Client health score calculates correctly for 5 test clients
- [ ] Follow-up reminder fires for overdue follow-up
- [ ] New client onboarding checklist creates all expected items
- [ ] CRM API rate limits handled gracefully (no crashes)

### Phase 5: Task Tracking ✅ when:
- [ ] "Add task: X by Friday" creates task with correct due date
- [ ] Daily standup includes completed/in-progress/blocked tasks
- [ ] Weekly report generates with accurate velocity metrics
- [ ] Overdue task triggers escalation alert
- [ ] Task marked done via natural language command

### Phase 6: Reporting ✅ when:
- [ ] Daily ops brief combines data from all active skills
- [ ] Brief delivered at configured time via configured channel
- [ ] Weekly review includes week-over-week comparisons
- [ ] Anomaly detection flags test anomaly (2x email volume spike)
- [ ] "Brief me" on-demand generates current state summary

### Phase 7: Docs & Showcase ✅ when:
- [ ] README renders correctly on GitHub with architecture diagram
- [ ] Setup guide tested by following it from scratch on clean machine
- [ ] Loom demo script covers all major features in <5 minutes
- [ ] At least 3 client-type templates validated
- [ ] Config wizard successfully configures a fresh deployment

---

## 4. Action Classification & Approval Policy

### Action Classes
```python
class ActionClass:
    # Internal — no approval needed
    INTERNAL_LOG = "internal_log"          # Write to memory/state files
    INTERNAL_BRIEF = "internal_brief"      # Send briefing to owner
    INTERNAL_QUERY = "internal_query"      # Read from APIs (no writes)
    
    # Requires implicit approval (configurable)
    AUTO_DRAFT = "auto_draft"              # Draft response (shown, not sent)
    TASK_CREATE = "task_create"            # Create task in tracker
    CRM_NOTE = "crm_note"                 # Add note to CRM contact
    
    # Requires explicit approval
    EXTERNAL_EMAIL = "external_email"      # Send email to external party
    EXTERNAL_MESSAGE = "external_message"  # Send message to external party
    CALENDAR_WRITE = "calendar_write"      # Create/modify/delete calendar event
    CRM_DEAL_CHANGE = "crm_deal_change"   # Change deal stage/value
    FINANCIAL = "financial"                # Any financial action (ALWAYS blocked)
```

### Approval Flow
```
Action triggered → Classify → Check policy
  → INTERNAL: Execute immediately, log
  → AUTO (configurable): Execute + notify owner, or queue for approval
  → EXPLICIT: Queue + notify owner → Owner approves/rejects → Execute or discard
  → FINANCIAL: Always blocked, alert owner
```

---

## 5. Observability

### Structured Logging
Every skill action logs:
```json
{
  "timestamp": "2026-03-12T14:00:00Z",
  "skill": "email-intel",
  "action": "triage",
  "correlationId": "evt_gmail_abc123",
  "input": { "from": "client@example.com", "subject": "Q1 Budget" },
  "output": { "urgency": "high", "category": "client", "action": "draft_queued" },
  "durationMs": 2340,
  "tokensUsed": 850,
  "success": true
}
```

### Health Dashboard (HEARTBEAT.md check)
```
Skills Health:
  📧 Email: ✅ Last check 12m ago | 0 errors (24h)
  📅 Calendar: ✅ Last check 18m ago | 0 errors (24h)
  👥 CRM: ⚠️ Last check 45m ago | 2 errors (24h) — rate limit
  ✅ Tasks: ✅ Last check 8m ago | 0 errors (24h)
  📊 Reporting: ✅ Last brief 6h ago | 0 errors (24h)
```

### Alert Thresholds
- Skill error rate >3 in 1 hour → alert owner
- Webhook processing latency >5 minutes → alert owner
- Dead letter count >5 in 24h → alert owner
- Memory file write failure → alert owner immediately
- API auth token expiring in <24h → alert owner

---

## 6. Cost Model (per client)

### LLM Token Spend Estimate
| Activity | Frequency | ~Tokens/run | Monthly tokens | Monthly cost (Sonnet) |
|----------|-----------|-------------|----------------|----------------------|
| Email triage | 30/day | 1,500 | 1,350,000 | ~$4.05 |
| Daily briefing | 1/day | 3,000 | 90,000 | ~$0.27 |
| Meeting prep | 3/day | 2,000 | 180,000 | ~$0.54 |
| Task commands | 10/day | 500 | 150,000 | ~$0.45 |
| CRM lookups | 5/day | 800 | 120,000 | ~$0.36 |
| Weekly review | 1/week | 5,000 | 20,000 | ~$0.06 |
| Heartbeat (30m) | 48/day | 800 | 1,152,000 | ~$3.46 |
| **Total** | | | **~3,062,000** | **~$9.19/month** |

*Based on Claude Sonnet at ~$3/M input tokens. Actual varies with context length.*

### Third-Party API Costs
- Gmail API: Free (within quota)
- Google Calendar API: Free (within quota)
- HubSpot API: Free tier (most operations)
- Linear/Notion/Asana: Free tier sufficient
- VPS hosting: $5-20/month
- **Total infrastructure: ~$15-30/month per client**

### Margin Analysis
- Starter tier ($300/mo support): ~$270 margin (~90%)
- Professional tier ($500/mo): ~$470 margin (~94%)
- Enterprise tier ($1,000/mo): ~$970 margin (~97%)

*LLM costs are the seller's responsibility (included in support fee). Client pays their own VPS.*

---

## 7. Client Onboarding Checklist

### Pre-Deployment Qualification
- [ ] Client has admin access to their email (Gmail/Outlook)
- [ ] Client has admin access to their calendar
- [ ] Client has admin access to CRM (or willing to set up free tier)
- [ ] Client has admin access to task tracker (or willing to set up free tier)
- [ ] Client has chosen primary messaging channel (Telegram/Slack/WhatsApp)
- [ ] Client has a VPS or machine that can stay on (or willing to provision one)
- [ ] Client understands this is AI-assisted, not magic — approval gates exist
- [ ] Client agrees to data handling terms (their data, their server, encrypted at rest)

### Deployment Steps
1. Provision VPS / prepare client machine
2. Run `setup.sh`
3. Configure channels (create bot, link account)
4. Set up Gmail Pub/Sub (guided script)
5. Connect Calendar (OAuth flow)
6. Connect CRM (API key or OAuth)
7. Connect Task Tracker (API key or OAuth)
8. Customise SOUL.md with client's business context
9. Customise VIP senders, categories, rules
10. Test each skill end-to-end
11. Enable heartbeat + cron jobs
12. Handover call — walkthrough of what the agent does

### Post-Deployment (Week 1)
- [ ] Monitor daily for false positives/negatives in email triage
- [ ] Tune urgency classification based on client feedback
- [ ] Verify all cron jobs fire correctly
- [ ] Check dead-letter folder for missed events
- [ ] Adjust briefing format based on client preference

---

## 8. Known Limitations (v1)

To be included in client-facing documentation:

1. **Email drafts require human approval** — the agent will never send emails without explicit confirmation
2. **Calendar changes require approval** — the agent reads freely but writes only with confirmation
3. **CRM updates are logged, not strategic** — the agent records interactions but doesn't make deal stage recommendations without approval
4. **LLM outputs can be wrong** — briefings and classifications are best-effort; critical decisions should always be human-verified
5. **API rate limits** — during high-volume periods, some operations may be delayed
6. **Single timezone per deployment** — multi-timezone teams need configuration adjustment
7. **English-primary** — LLM performance is best in English; other languages work but with lower accuracy
8. **No real-time voice** — text-based channels only (no phone call handling)
