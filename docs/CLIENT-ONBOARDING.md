# OpsClaw Client Onboarding

Internal deployment playbook for taking a paid OpsClaw client from discovery to go-live and monthly support.

Use this document as the default operating sequence unless the client has unusual security, procurement, or hosting constraints.

## Core Rule

Do not promise bespoke automation in the sale if it is not already covered by:

- a built-in skill under `skills/`
- a built-in role pack under `role-packs/`
- an existing deployment/config path in `scripts/`

If something needs custom code, custom channel plumbing, or unusual data mapping, position it as Phase 2 or paid follow-on implementation.

## Standard Deployment Inputs

Collect these before starting setup:

- Legal company name
- Preferred product/assistant name
- Primary operator name
- Primary operator email
- Timezone of truth
- Roles being deployed
- Preferred user channels: web, Slack, WhatsApp, or mixed
- CRM provider
- Email provider
- Calendar provider
- Task provider
- Drive/docs provider
- Branding assets: logo URL or file, primary color, secondary color, font
- Client champion name, email, and Slack/WhatsApp details
- Target go-live date
- Hosting location: local machine, VPS, or Docker host

## Phase 0: Pre-Sale (Before They Pay)

### Discovery Call Checklist

Ask these questions on the call and capture answers in one note:

- Who will use OpsClaw first: founder, sales, support, admin, finance, marketing?
- What is the operational pain right now: inbox overload, missed follow-ups, support backlog, founder chaos, reporting, onboarding?
- What systems are already source-of-truth for clients, tasks, meetings, and docs?
- What channels do employees actually live in: Slack, browser, WhatsApp, Telegram, email?
- Which actions are safe for draft-only versus truly automated?
- Who approves external sends, calendar writes, and CRM stage changes?
- Who is the internal champion for testing and rollout?
- How many users need access at go-live versus later?
- What does a successful first 30 days look like?

### Scope Which Roles They Need

Map the client’s needs to the built-in role packs:

- `founder`: best default for owner-led businesses needing one high-leverage operating partner.
- `sales`: use when pipeline follow-up, meeting prep, and CRM hygiene are primary.
- `support`: use when inbound issue triage, SLA control, and reply drafting matter.
- `admin`: use for scheduling, document chasing, onboarding, and coordination.
- `finance`: use for invoice follow-up, finance reporting, and document collection. It does not move money.
- `marketing`: use for campaign coordination, social monitoring, KPI reporting, and lead scoring support.

Scoping rule:

- Start with 1-2 roles unless the client already has clear owners and clean systems.
- Add `founder` first if the founder is the main buyer.
- Add `sales` or `support` second only if there is a real operator who will use it weekly.
- Avoid deploying six roles just because they exist. Empty roles create support overhead and weak adoption.

### Identify Existing Tools

Record the exact vendor and admin owner for each category:

- CRM: HubSpot, Pipedrive, GoHighLevel, or other internal API.
- Email: Google Workspace or Microsoft 365.
- Calendar: Google Calendar or Microsoft 365.
- Task management: Linear, Notion, Asana, or none.
- Docs: Google Drive/Docs, Notion, SharePoint, local folders.
- Channels: Web UI, Slack, WhatsApp.

Capture these specifics:

- Workspace/domain name
- Admin contact
- Whether API access is enabled
- Whether test/sandbox access exists
- Whether read-only credentials are possible for first pass

### Pricing Calculator

Use a simple quote model:

- Base deployment fee: covers discovery, setup, one primary channel, one primary role, core branding, and go-live.
- Per-role fee: add for each additional deployed role pack.
- Integration fee: add per non-trivial integration after the first core stack.

Practical structure:

- Base: company config, role deployment, branding, KB initialization, one training session.
- Per-role: role-pack deployment, `SOUL.md` customization, role testing.
- Integrations:
  - Standard: Gmail/Calendar, HubSpot/Pipedrive/GoHighLevel, Linear/Notion/Asana.
  - Premium: custom API wrapper, Slack app setup, WhatsApp Business setup, Microsoft 365 workaround/manual integration path.

Pricing rule:

- Charge extra for anything requiring custom API mapping, app review, phone number setup, OAuth app creation, or document migration.

### What To Promise vs What Is Phase 2

Promise in initial deployment only what the repo already supports cleanly:

- Role-based OpsClaw workspaces
- Chat backend company config
- Web chat UI
- Gmail and Google Calendar via `gws`
- CRM sync for HubSpot, Pipedrive, GoHighLevel
- Task tracking for Linear, Notion, Asana
- Knowledge graph vault setup
- Drive/docs access
- Basic reporting and briefings

Push to Phase 2:

- Microsoft 365 parity if the client is not on Google Workspace
- Deep Slack bot workflows beyond simple channel routing and bot install
- WhatsApp production hardening and template approval
- Custom internal API wrappers
- Data migration from messy legacy tools
- Fine-tuned role prompts beyond first-pass `SOUL.md` customization

## Phase 1: Setup (Day 1-2 After Payment)

### 1. Create Internal Working Folder

Create a client deployment area:

```bash
mkdir -p deployments/<client-slug>
```

Keep all client-specific configs, notes, exports, and deployment outputs under that folder.

### 2. Create Chat Backend Company Config

Initialize the company:

```bash
python3 skills/chat-backend/scripts/config-manager.py init "Client Legal Name"
```

If you need an explicit stable slug:

```bash
python3 skills/chat-backend/scripts/config-manager.py init "Client Legal Name" --company-id client-slug
```

Verify:

```bash
python3 skills/chat-backend/scripts/config-manager.py list
python3 skills/chat-backend/scripts/config-manager.py export client-slug
```

Result:

- config file is written under `skills/chat-backend/configs/company-configs/<company_id>.json`

### 3. Set Branding

Apply brand settings:

```bash
python3 skills/chat-backend/scripts/config-manager.py set-branding client-slug \
  --name "Client Ops" \
  --color "#0b6e4f" \
  --secondary-color "#edf6f2" \
  --logo "/assets/client-logo.png" \
  --font "Inter"
```

Minimum required:

- product name
- primary color
- secondary color
- logo path or hosted URL

Verify:

```bash
python3 skills/chat-backend/scripts/config-manager.py export client-slug
```

### 4. Select Roles

Review built-in packs in `role-packs/` and choose only the roles sold.

Fast rule of thumb:

- founder-led client: `founder`
- heavy outbound or pipeline team: add `sales`
- service business with client tickets: add `support`
- operations-heavy business: add `admin`
- invoice-heavy business: add `finance`
- campaign-heavy business: add `marketing`

### 5. Create Company Deployment Config

Start from the template:

```bash
cp templates/company-config.json deployments/<client-slug>/company-config.json
```

Edit:

- `company.name`
- `company.timezone`
- `company.owner`
- `company.deployment_mode`
- `shared.crm`
- `shared.channels.primary`
- `shared.channels.enabled`
- `roles[]`

Example deploy:

```bash
python3 scripts/deploy-company.py \
  --config deployments/<client-slug>/company-config.json \
  --output deployments/<client-slug>/runtime
```

Single-role alternative:

```bash
python3 scripts/deploy-role.py \
  --role founder \
  --company "Client Legal Name" \
  --user "Austin" \
  --channel slack \
  --crm hubspot \
  --timezone America/New_York \
  --deployment-mode docker-compose \
  --output deployments/<client-slug>/founder
```

Verify output:

- `deployments/<client-slug>/runtime/roles/<role>/`
- `deployments/<client-slug>/runtime/shared/client-db.json`
- `deployments/<client-slug>/runtime/channel-bindings.json`
- `deployments/<client-slug>/runtime/deployment-manifest.json`
- `deployments/<client-slug>/runtime/docker-compose.yml`

### 6. Register Each Role In The Chat Backend Config

Add each deployed role so the web chat UI can present the correct role list:

```bash
python3 skills/chat-backend/scripts/config-manager.py add-role client-slug founder \
  --name "Client Founder Ops" \
  --greeting "I handle founder priorities, pipeline, calendar risk, and operating briefs." \
  --description "Founder operating partner for company-wide visibility." \
  --avatar "FD"
```

Repeat for each sold role:

```bash
python3 skills/chat-backend/scripts/config-manager.py add-role client-slug sales ...
python3 skills/chat-backend/scripts/config-manager.py add-role client-slug support ...
python3 skills/chat-backend/scripts/config-manager.py add-role client-slug admin ...
python3 skills/chat-backend/scripts/config-manager.py add-role client-slug finance ...
python3 skills/chat-backend/scripts/config-manager.py add-role client-slug marketing ...
```

Verify:

```bash
python3 skills/chat-backend/scripts/config-manager.py export client-slug
```

### 7. Customize Each Role’s `SOUL.md`

For each deployed role workspace, open:

- `deployments/<client-slug>/runtime/roles/<role>/SOUL.md`
- `deployments/<client-slug>/runtime/roles/<role>/USER.md`
- `deployments/<client-slug>/runtime/roles/<role>/AGENTS.md`

Customize `SOUL.md` with:

- company description
- business model
- main offer lines
- tone expectations
- escalation keywords
- VIP names
- recurring deadlines
- internal taboo actions

Minimum edits for every role:

- replace generic company framing with the client’s actual business
- insert named leaders and functional owners
- define what “urgent” means for that role
- define what must always be escalated

Do not put secrets into `SOUL.md` or `USER.md`.

### 8. Initialize The Knowledge Graph Vault

Each deployed workspace includes the knowledge-graph skill only if you copy it manually; the repo’s default role deployment does not auto-enable it in built-in packs. If you want KB-backed onboarding, copy or use the root skill directly and target the role workspace vault path.

Initialize a vault for the main workspace you plan to enrich first:

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  init
```

Add initial notes:

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  add person "Jane Smith"
```

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  add process "Lead Handoff"
```

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  add client "Top Customer"
```

Rebuild the index:

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  index
```

Populate first with:

- key people
- org structure
- top clients
- core processes
- active projects
- policies
- tools

## Phase 2: Integrations (Day 2-4)

General rule:

- collect credentials in a secure password manager or secret store
- keep tokens in environment variables, not committed JSON
- test reads before writes
- capture one known-good command output for each integration

### Email

#### Google Workspace

What you need from client:

- Google Workspace account login for the service user or owner
- permission to complete OAuth login in browser
- confirmation which inboxes matter

Commands:

```bash
./skills/email-intel/scripts/gws-auth-setup.sh
gws auth status
```

Test classification:

```bash
python3 skills/email-intel/scripts/classify.py \
  --query "in:inbox newer_than:1d" \
  --max-results 5 \
  --categories skills/email-intel/config/categories.json \
  --vip skills/email-intel/config/vip-senders.json \
  --pretty
```

Test briefing:

```bash
python3 skills/email-intel/scripts/briefing.py \
  --ops-state workspace/ops-state.json \
  --categories skills/email-intel/config/categories.json \
  --vip skills/email-intel/config/vip-senders.json
```

Verify:

- `gws auth status` shows authenticated session
- inbox fetch returns live messages
- VIP sender test is classified correctly
- no duplicate queue entries on repeated fetch

#### Microsoft 365

Current repo status:

- there is no first-party Microsoft 365 email integration script in this repo

Handle it this way:

- treat Microsoft 365 as Phase 2 custom work
- if the client needs it immediately, quote custom API integration using `skills/api-cli` or `scripts/api-bridge/generator.py`
- do not sell Microsoft mail/calendar parity as same-speed setup unless custom scope is already agreed

### Calendar

#### Google Calendar

What you need from client:

- same Google auth as email
- which calendars to watch
- timezone of truth
- scheduling rules: buffers, prep windows, personal calendars included or not

Commands:

```bash
gws auth setup --login
gws auth status
```

Configure calendars:

```bash
$EDITOR skills/calendar-ops/config/calendars.json
```

List events:

```bash
python3 skills/calendar-ops/scripts/gcal-client.py list-events \
  --calendars-path skills/calendar-ops/config/calendars.json \
  --window today
```

Check availability:

```bash
python3 skills/calendar-ops/scripts/gcal-client.py availability \
  --calendars-path skills/calendar-ops/config/calendars.json \
  --start 2026-03-20T15:00:00+00:00 \
  --end 2026-03-20T16:00:00+00:00
```

Generate briefing:

```bash
python3 skills/calendar-ops/scripts/briefing.py \
  --calendars-path skills/calendar-ops/config/calendars.json \
  --ops-state workspace/ops-state.json \
  --prep-rules skills/calendar-ops/config/prep-rules.json
```

Verify:

- events match Google Calendar UI
- busy slots return blocked
- free slots return available
- briefing highlights prep-needed meetings

#### Microsoft 365 Calendar

Same rule as email:

- no first-party Microsoft 365 calendar setup path exists in this repo
- scope as custom API work if required

### CRM

What you need from client:

- confirmed provider: HubSpot, Pipedrive, or GoHighLevel
- admin with permission to create token/app
- sandbox or test contact if possible
- agreement on what writes are allowed

#### HubSpot

Need:

- private app token with contacts, companies, deals, notes, tasks scopes

Commands:

```bash
export HUBSPOT_ACCESS_TOKEN="..."
```

Edit config:

```bash
$EDITOR skills/crm-sync/config/crm-config.json
```

Test:

```bash
python3 skills/crm-sync/scripts/hubspot-client.py search-contacts \
  --config skills/crm-sync/config/crm-config.json \
  --query "Acme"
```

Lookup:

```bash
python3 skills/crm-sync/scripts/hubspot-client.py lookup \
  --config skills/crm-sync/config/crm-config.json \
  --query "Acme"
```

Verify:

- can find a known contact/company
- add-note works only after read path is proven
- rate limits and scope errors are understood

#### Pipedrive

Need:

- API token
- company domain, for example `acme`

Commands:

```bash
export PIPEDRIVE_API_TOKEN="..."
```

Edit config with correct base URL:

```bash
$EDITOR skills/crm-sync/config/crm-config.json
```

Test:

```bash
python3 skills/crm-sync/scripts/pipedrive-client.py search-contacts \
  --config skills/crm-sync/config/crm-config.json \
  --query "Acme"
```

Verify:

- correct tenant base URL
- known person/deal is returned
- notes can be added when approved

#### GoHighLevel

Need:

- private integration token or OAuth app
- location ID
- pipeline ID
- calendar ID if calendar-linked workflows matter

Commands:

```bash
export GOHIGHLEVEL_ACCESS_TOKEN="..."
```

Optional OAuth:

```bash
export GOHIGHLEVEL_CLIENT_ID="..."
export GOHIGHLEVEL_CLIENT_SECRET="..."
```

Edit config:

```bash
$EDITOR skills/crm-sync/config/gohighlevel-config.json
```

Test:

```bash
python3 skills/crm-sync/scripts/gohighlevel-client.py list-contacts \
  --config skills/crm-sync/config/gohighlevel-config.json \
  --limit 5
```

OAuth flow if needed:

```bash
python3 skills/crm-sync/scripts/gohighlevel-client.py oauth-authorize-url \
  --config skills/crm-sync/config/gohighlevel-config.json \
  --state opsclaw-ghl
```

```bash
python3 skills/crm-sync/scripts/gohighlevel-client.py oauth-exchange-code \
  --config skills/crm-sync/config/gohighlevel-config.json \
  --code "<oauth-code>"
```

Verify:

- list/search returns real contacts
- default location and pipeline IDs are correct
- token persistence or secret handling is documented

### Task Tracking

What you need from client:

- provider choice: Linear, Notion, or Asana
- workspace/database/project to use
- whether OpsClaw may create tasks or only read

#### Linear

Need:

- `LINEAR_API_KEY`
- team/project defaults

Commands:

```bash
export LINEAR_API_KEY="lin_api_..."
```

```bash
$EDITOR skills/task-tracker/config/tracker-config.json
```

```bash
python3 skills/task-tracker/scripts/linear-client.py list-issues \
  --config skills/task-tracker/config/tracker-config.json \
  --limit 10
```

Verify:

- issue list works
- create-issue works in test project if writes are allowed

#### Notion

Need:

- `NOTION_API_TOKEN`
- shared task database
- database ID and property mapping

Commands:

```bash
export NOTION_API_TOKEN="secret_..."
```

```bash
python3 skills/task-tracker/scripts/notion-client.py query-database \
  --config skills/task-tracker/config/tracker-config.json \
  --limit 10
```

Verify:

- DB is shared with integration
- properties map correctly
- test task appears in Notion if writes are enabled

#### Asana

Need:

- `ASANA_ACCESS_TOKEN`
- workspace/project/section defaults

Commands:

```bash
export ASANA_ACCESS_TOKEN="..."
```

```bash
python3 skills/task-tracker/scripts/asana-client.py list-tasks \
  --config skills/task-tracker/config/tracker-config.json \
  --limit 10
```

Verify:

- tasks list successfully
- correct project is targeted
- create task works only after confirming placement

### Custom APIs

Use this when the client has an internal API, an unsupported SaaS, or Microsoft 365 work needs to be wrapped.

#### Option 1: Generate A Universal API Config

Best when the goal is a config-driven service under `skills/api-cli`.

Need from client:

- OpenAPI spec URL/file, FastAPI base URL, or endpoint list
- auth type
- credential env var name
- test endpoint

Commands:

```bash
python3 skills/api-cli/scripts/api-config-generator.py \
  --openapi path/to/openapi.json \
  --service client-api \
  --output skills/api-cli/configs/client-api.json
```

Or:

```bash
python3 skills/api-cli/scripts/api-config-generator.py \
  --fastapi https://api.client.com \
  --service client-api \
  --output skills/api-cli/configs/client-api.json
```

Or interactive:

```bash
python3 skills/api-cli/scripts/api-config-generator.py \
  --interactive \
  --service client-api \
  --auth-type bearer \
  --env-var CLIENT_API_TOKEN
```

Test service:

```bash
python3 skills/api-cli/scripts/api.py services
python3 skills/api-cli/scripts/api.py schema client-api
```

#### Option 2: Generate A Dedicated API Bridge CLI + Skill

Best when the client needs a generated wrapper under `generated/<api-name>/`.

Commands:

```bash
python3 scripts/api-bridge/generator.py --openapi path/to/openapi.yaml
```

Or:

```bash
python3 scripts/api-bridge/generator.py --config path/to/manual-api-config.json
```

Verify:

- `generated/<api-name>/cli.py` exists
- `generated/<api-name>/SKILL.md` exists
- test command runs against sandbox endpoint

### Integration Verification Checklist

For every integration, do all of these before moving on:

- confirm credential source and owner
- confirm read path works
- confirm at least one known object is returned
- confirm timezone, tenant, and base URL are right
- confirm write behavior is approval-gated where needed
- store one “known good” command in client notes

## Phase 3: Channels (Day 3-5)

Choose one or more delivery channels based on how the client actually works.

### Option A: Web UI

This is the fastest path because the repo already includes both frontend and backend.

#### What You Need

- client branding
- backend host/domain
- whether users authenticate by company email domain

#### Backend Setup

Start backend locally:

```bash
python3 skills/chat-backend/scripts/server.py --host 0.0.0.0 --http-port 8000 --ws-port 8765 --verbose
```

Set production secret:

```bash
export OPSCLAW_CHAT_SECRET='replace-this-in-production'
```

Test config endpoint:

```bash
curl "http://127.0.0.1:8000/api/config?company_id=client-slug"
```

Test auth:

```bash
curl -X POST http://127.0.0.1:8000/api/auth \
  -H 'Content-Type: application/json' \
  -d '{"company_id":"client-slug","employee_name":"Test User","employee_email":"test@client.com"}'
```

#### Frontend Setup

Serve locally:

```bash
cd skills/chat-ui/frontend
python3 -m http.server 8080
```

Open:

- `http://127.0.0.1:8080/?company_id=client-slug`
- add `&api_base=http://127.0.0.1:8000` if needed

Testing checklist:

- branding loads correctly
- only sold roles appear
- auth succeeds with test user
- chat connects to the correct role
- message history persists
- mobile layout is usable

### Option B: Slack

Current repo status:

- there is no dedicated Slack deployment script in this repo
- channel setup is manual SaaS configuration plus OpsClaw routing/config

#### What You Need

- Slack workspace admin
- app creation permission
- bot token scopes approved
- channels for each role or a single entry channel

#### Manual Setup Steps

1. Create a Slack app in the client workspace.
2. Add bot scopes needed for message read/write for the agreed setup.
3. Install the app to the workspace.
4. Capture bot token and signing secret in secret storage.
5. Decide routing model:
   - one Slack channel per role
   - one shared channel with human routing discipline
6. Update deployment notes and `channel-bindings.json` expectations accordingly.

Practical use inside OpsClaw:

- set Slack as `shared.channels.primary` or role `channel`
- keep alerts/briefings aligned with where the client already works

Testing checklist:

- bot can join target channels
- app can read and post in target channel
- each role maps to the intended Slack destination
- no cross-role confusion in channel naming

If the client expects deep Slack interactivity, modals, or slash commands:

- quote it as custom Phase 2 work

### Option C: WhatsApp

Current repo status:

- there is no first-party WhatsApp deployment script in this repo
- setup is external via Twilio or Meta plus custom integration/config work

#### What You Need

- Twilio or Meta Business account
- approved WhatsApp Business number
- message template approval if outbound templates are needed
- webhook hosting plan

#### Manual Setup Steps

1. Create or use existing WhatsApp Business sender.
2. Complete phone number verification.
3. Configure webhook target on the chosen provider.
4. Store credentials and webhook secrets securely.
5. Decide whether WhatsApp is inbound only, outbound only, or both.

Testing checklist:

- inbound message reaches the target integration
- outbound test message succeeds to approved test device
- template approval status is confirmed
- opt-in and compliance expectations are documented

If the client wants WhatsApp from day one:

- treat it as premium/custom unless you already have a proven wrapper deployed

### Option D: All Of The Above

Only do multi-channel at first deployment if:

- there is one clear champion
- the client already knows which teams use each channel
- you have time budget for duplicated testing

Default safe approach:

- launch web UI first
- add Slack second
- add WhatsApp only if there is a hard business reason

## Phase 4: Knowledge Base Population (Day 3-7)

This is where the deployment becomes useful instead of generic.

### Populate The Knowledge Graph

Target a single vault first, usually the founder or primary workspace:

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  add person "CEO Name"
```

Add notes for:

- executives
- managers
- key ICs
- major clients
- active projects
- recurring processes
- policies
- tools
- major decisions

After every batch:

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  index
```

Audit the vault:

```bash
python3 skills/knowledge-graph/scripts/kb.py \
  --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph \
  stats
```

### What To Capture First

Priority order:

1. org chart and who owns what
2. core service delivery process
3. sales pipeline stages and definitions
4. support escalation rules
5. top 20 clients and current status
6. recurring deadlines and compliance dates
7. glossary of company terms and acronyms

### Import From Existing Docs

The repo does not include a one-command Notion or SharePoint import pipeline for the knowledge graph. Handle this manually and systematically:

- export source docs
- extract the high-signal material
- turn it into KB notes by type
- index after each import batch

Sources to mine:

- Notion exports
- Google Docs and Drive folders
- SharePoint exports
- onboarding docs
- SOPs
- sales playbooks
- support macros/runbooks

### Train Roles On Company Terminology And Workflows

Do this in two places:

- edit each role’s `SOUL.md` with company vocabulary and escalation rules
- add KB notes covering terms, workflows, and examples

Minimum company-specific concepts to encode:

- product names
- pricing plans
- client tiers
- SLA language
- pipeline stage definitions
- names of internal systems
- names of recurring meetings and reports

## Phase 5: Testing & Handoff (Day 5-7)

### Internal Testing Checklist

For every deployed role:

- open the workspace files and confirm `SOUL.md`, `USER.md`, and `config.json5` are client-specific
- verify role appears in backend config export
- verify the role can be selected in web UI if web channel is enabled
- run at least one realistic prompt through that role

For every integration:

- auth works
- read path works
- known-good object returns
- write path is gated correctly

For every channel:

- inbound works
- outbound/test reply works if supported
- branding is correct
- role routing is correct

Health checks:

```bash
bash scripts/health-check.sh
python3 -m compileall scripts
python3 -m compileall skills
```

If the target machine has OpenClaw installed:

```bash
openclaw security audit --deep
```

### UAT With Client Champion

Run a live test session with the client champion and make them verify:

- one prompt per role
- one email-related use case
- one calendar-related use case
- one CRM lookup
- one task lookup/create flow
- one knowledge question from internal docs

Collect:

- broken expectations
- missing terminology
- missing clients/contacts
- wrong escalation behavior

### Training Session

Standard session length:

- 30 minutes

Agenda:

1. what OpsClaw does
2. which roles exist
3. how to ask for help
4. what it can draft versus what still needs approval
5. what to do when answers are incomplete

### Go-Live Checklist

- all sold roles deployed
- core integrations authenticated
- primary channel tested
- client champion signed off
- KB has minimum viable company context
- alerts and briefings go to the right place
- secret storage documented
- support plan agreed

### Handoff Doc For The Client

Send a short handoff document covering:

- deployed roles
- enabled integrations
- live channels
- approval boundaries
- champion contact path
- support cadence
- how to request changes

## Phase 6: Ongoing Support (Monthly)

### What Monthly Support Includes

- credential drift checks
- integration health checks
- light KB maintenance
- small prompt/`SOUL.md` tuning
- adding minor config updates
- monthly or weekly client reporting

Does not include by default:

- custom new integration builds
- large-scale KB migrations
- new channel implementations
- heavy analytics or dashboard work

### Monitoring

Check at least weekly:

- `gws auth status`
- chat backend availability
- role/channel routing still correct
- CRM and task provider auth still valid
- KB index freshness if notes changed

Useful commands:

```bash
gws auth status
python3 skills/chat-backend/scripts/config-manager.py list
python3 skills/knowledge-graph/scripts/kb.py --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph stats
bash scripts/health-check.sh
```

### Adding New Roles Or Integrations

New role:

1. update `deployments/<client-slug>/company-config.json`
2. rerun company deploy or deploy single role
3. add role to backend config
4. customize `SOUL.md`
5. test role end to end

New integration:

1. collect credentials
2. configure skill config
3. test reads
4. test writes only if approved
5. update handoff doc

### Knowledge Base Maintenance

Monthly minimum:

- add new clients
- archive stale notes
- update org changes
- capture major decisions
- refresh active process docs

Commands:

```bash
python3 skills/knowledge-graph/scripts/kb.py --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph list
python3 skills/knowledge-graph/scripts/kb.py --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph search "old term"
python3 skills/knowledge-graph/scripts/kb.py --vault deployments/<client-slug>/runtime/roles/founder/knowledge-graph index
```

### Billing And Upsell Triggers

Upsell when you see:

- repeated requests for another role
- repeated requests for unsupported channels
- Microsoft 365 client asks for parity
- internal API integration becomes a blocker
- client has messy docs and wants structured migration
- support team wants SLA dashboards or custom reports

## Appendix

### Full List Of Available Skills

- `email-intel`: Gmail inbox triage, classification, briefings, and approval-safe draft generation.
- `calendar-ops`: Google Calendar event visibility, availability checks, conflict detection, and prep generation.
- `crm-sync`: HubSpot, Pipedrive, and GoHighLevel lookup, note logging, health scoring, onboarding, and follow-up support.
- `task-tracker`: Linear, Notion, and Asana task access, creation, standups, and weekly reports.
- `ops-reporting`: KPI tracking, daily briefings, anomaly detection, weekly review formatting.
- `knowledge-graph`: markdown knowledge base with indexing, search, and graph traversal.
- `api-cli`: config-driven universal REST CLI for unsupported services.
- `chat-ui`: white-label web chat frontend.
- `chat-backend`: stdlib-only chat config/auth/history/WebSocket backend.
- `onboarding`: first-week onboarding guidance flows.
- `drive-docs`: Google Drive and Docs access through `gws`.
- `api-bridge`: generated CLI and `SKILL.md` wrapper from manual config or OpenAPI.

### Role Pack Descriptions And Customization Guide

- `founder`: use for company-wide operating brief, high-signal alerts, and executive triage.
- `sales`: use for pipeline follow-up, CRM hygiene, meeting prep, and revenue-facing priority.
- `support`: use for ticket triage, client history lookup, SLA awareness, and response drafting.
- `admin`: use for scheduling, onboarding coordination, documents, and executive follow-through.
- `finance`: use for invoice follow-up, finance visibility, reporting, and missing document tracking.
- `marketing`: use for campaigns, KPI reporting, social monitoring, and lead-quality support.

Customization order:

1. choose the closest role pack
2. deploy it
3. edit `SOUL.md`
4. edit skill config files if the role needs different thresholds
5. test with real client prompts

### Troubleshooting Common Issues

`gws auth status` fails:

- rerun `gws auth setup --login`
- confirm the right Google account was used
- confirm browser auth completed

CRM auth fails:

- check env var names
- check tenant base URL
- check scope on token/private app

Web UI shows wrong branding or roles:

- run `python3 skills/chat-backend/scripts/config-manager.py export client-slug`
- confirm `company_id` in URL matches the config slug

Role behaves too generically:

- update `SOUL.md`
- add KB notes
- add more concrete examples to company context

Deployment output missing role:

- check `deployments/<client-slug>/company-config.json`
- rerun `python3 scripts/deploy-company.py --config ... --output ...`

### Template: Client Intake Form

Collect before setup starts:

- company legal name
- preferred assistant/product name
- website
- timezone
- owner/champion name
- owner/champion email
- purchased roles
- preferred channels
- CRM provider
- email provider
- calendar provider
- task provider
- docs provider
- branding assets
- top 10 VIPs
- top 10 clients
- list of recurring meetings
- list of approval-sensitive actions
- go-live date

### Template: Weekly Report To Client

Send this every week during managed support:

```md
# OpsClaw Weekly Report

Client: <Client Name>
Week ending: <YYYY-MM-DD>

## Status
- Overall health: Green / Amber / Red
- Live roles: <roles>
- Live integrations: <integrations>
- Live channels: <channels>

## What Changed
- <change 1>
- <change 2>

## Issues Found
- <issue 1>
- <issue 2>

## Usage Highlights
- <highlight 1>
- <highlight 2>

## Recommended Next Steps
- <next step 1>
- <next step 2>

## Open Items For Client
- <item 1>
- <item 2>
```

### Estimated Time Per Phase

Solo operator, realistic default:

- Phase 0: 1-2 hours
- Phase 1: 2-4 hours
- Phase 2: 3-8 hours depending on integrations
- Phase 3: 2-6 hours depending on channels
- Phase 4: 3-10 hours depending on doc quality
- Phase 5: 2-4 hours
- Phase 6: 1-4 hours per month for light support

With VA support:

- Phase 0: Austin 45-60 min, VA 30 min prep/follow-up
- Phase 1: Austin 1.5-3 hours, VA 1-2 hours for data entry and asset collection
- Phase 2: Austin 2-6 hours, VA 1-3 hours for credential chase and verification logging
- Phase 3: Austin 2-5 hours, VA 1-2 hours for test cases and screenshots
- Phase 4: Austin 1-3 hours, VA 3-8 hours for doc extraction and KB population
- Phase 5: Austin 1.5-3 hours, VA 30-60 min for notes and handoff prep
- Phase 6: Austin 30-90 min, VA 30-120 min per month

## Final Pre-Go-Live Command List

Run these before handing over:

```bash
python3 skills/chat-backend/scripts/config-manager.py export client-slug
python3 scripts/deploy-company.py --config deployments/<client-slug>/company-config.json --output deployments/<client-slug>/runtime
bash scripts/health-check.sh
python3 -m compileall scripts
python3 -m compileall skills
```

If OpenClaw is installed on the host:

```bash
openclaw security audit --deep
```
