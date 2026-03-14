# OpsClaw Chat Backend

`skills/chat-backend/` is a white-label, stdlib-only chat backend for OpsClaw role agents. It exposes REST endpoints for config, roles, auth, and history, plus a raw WebSocket server for live chat with role-specific template responses or real Claude responses when configured.

No pip dependencies are required. The runtime uses:

- `http.server` for REST
- `asyncio` streams for WebSocket handshake and frames
- `json`, `pathlib`, `uuid`, and `hmac` for config, persistence, and sessions

## Files

- [`scripts/server.py`](/Users/austin/Desktop/opsclaw/skills/chat-backend/scripts/server.py): starts the REST server and WebSocket server
- [`scripts/config-manager.py`](/Users/austin/Desktop/opsclaw/skills/chat-backend/scripts/config-manager.py): company config CLI
- [`scripts/message-store.py`](/Users/austin/Desktop/opsclaw/skills/chat-backend/scripts/message-store.py): message history CLI
- [`scripts/chat_backend_core.py`](/Users/austin/Desktop/opsclaw/skills/chat-backend/scripts/chat_backend_core.py): shared config, auth, storage, and response logic
- [`configs/company-configs/demo.json`](/Users/austin/Desktop/opsclaw/skills/chat-backend/configs/company-configs/demo.json): preloaded AcmeCorp demo company

## Quick Start

Start the backend:

```bash
python3 skills/chat-backend/scripts/server.py
```

Defaults:

- REST: `http://127.0.0.1:8000`
- WebSocket: `ws://127.0.0.1:8765`

Optional flags:

```bash
python3 skills/chat-backend/scripts/server.py \
  --host 0.0.0.0 \
  --http-port 8000 \
  --ws-port 8765 \
  --verbose
```

Environment variables:

- `ANTHROPIC_API_KEY`: required for real AI responses. If unset, the backend silently falls back to the built-in templates.
- `OPSCLAW_MODEL`: optional Claude model override. Defaults to `claude-sonnet-4-20250514`.
- `OPSCLAW_MAX_TOKENS`: optional max tokens for Claude responses. Defaults to `500`.

## Company Configs

Each company lives in `configs/company-configs/<company_id>.json`.

Shape:

```json
{
  "company_id": "demo",
  "company_name": "AcmeCorp",
  "branding": {
    "product_name": "AcmeOps",
    "logo_url": "/assets/acme-logo.png",
    "primary_color": "#0b6e4f",
    "secondary_color": "#edf6f2",
    "font": "Inter"
  },
  "roles": {
    "finance": {
      "display_name": "Acme Finance",
      "avatar_emoji": "💰",
      "greeting": "Hey, I'm Acme Finance.",
      "description": "Handles invoices, expenses, budgets, approvals, and payment timing."
    }
  },
  "auth": {
    "type": "simple",
    "allowed_domains": ["acmecorp.com"]
  }
}
```

The server resolves company config in this order:

1. `company_id` query parameter
2. `X-Company-Id` header
3. the bundled `demo` config if present
4. the first config file on disk

## Config CLI

Create a new config:

```bash
python3 skills/chat-backend/scripts/config-manager.py init "ForgeWorks Manufacturing"
```

Set branding:

```bash
python3 skills/chat-backend/scripts/config-manager.py set-branding demo \
  --name "AcmeOps" \
  --color "#0b6e4f" \
  --secondary-color "#edf6f2" \
  --logo "/assets/acme-logo.png"
```

Add or update a role:

```bash
python3 skills/chat-backend/scripts/config-manager.py add-role demo finance \
  --name "Acme Finance" \
  --greeting "Hey, I'm Acme Finance. I can help with budgets and invoices." \
  --description "Handles invoices, expenses, budgets, approvals, and payment timing."
```

List or export:

```bash
python3 skills/chat-backend/scripts/config-manager.py list
python3 skills/chat-backend/scripts/config-manager.py export demo
```

## REST API

All REST endpoints return CORS headers:

- `Access-Control-Allow-Origin: *`
- `Access-Control-Allow-Methods: GET, POST, OPTIONS`
- `Access-Control-Allow-Headers: Content-Type, Authorization, X-Company-Id`

### `GET /api/config`

Returns company branding and role metadata.

Example:

```bash
curl http://127.0.0.1:8000/api/config?company_id=demo
```

### `GET /api/roles`

Returns just the role list for the selected company.

```bash
curl http://127.0.0.1:8000/api/roles?company_id=demo
```

### `POST /api/auth`

Authenticates a user with simple company-scoped identity and returns a session token.

```bash
curl -X POST http://127.0.0.1:8000/api/auth \
  -H 'Content-Type: application/json' \
  -d '{"company_id":"demo","employee_name":"Alex Carter","employee_email":"alex@acmecorp.com"}'
```

Response:

```json
{
  "token": "<session-token>",
  "session": {
    "company_id": "demo",
    "employee_name": "Alex Carter",
    "employee_email": "alex@acmecorp.com",
    "user_id": "alex-acmecorp-com",
    "issued_at": "2026-03-14T11:00:00Z"
  },
  "websocket_base_url": "ws://127.0.0.1:8765/ws"
}
```

### `GET /api/history?role=<role>&limit=20`

Returns stored chat history for the authenticated user. Provide the token either as `Authorization: Bearer ...` or `?token=...`.

```bash
curl "http://127.0.0.1:8000/api/history?role=finance&limit=20&token=<session-token>"
```

History is loaded from `data/<company_id>/<role>/<user_id>.json` and capped to the most recent `1000` messages per file. The WebSocket responder uses the last `10` messages as Claude conversation context when AI mode is enabled.

## WebSocket Protocol

Connect to a role:

```text
ws://127.0.0.1:8765/ws/<role>?token=<session-token>
```

The server sends an initial connected payload:

```json
{
  "type": "connected",
  "role": "finance",
  "agent_name": "Acme Finance",
  "timestamp": "2026-03-14T11:00:00Z",
  "greeting": "Hey, I'm Acme Finance. I can help with budgets, invoices, and expenses."
}
```

Client message:

```json
{
  "type": "message",
  "text": "What is our travel budget looking like?",
  "role": "finance"
}
```

Typing indicator:

```json
{
  "type": "typing",
  "agent_name": "Acme Finance",
  "timestamp": "2026-03-14T11:00:01Z"
}
```

Agent response:

```json
{
  "type": "response",
  "text": "Quick read: Budget-wise we still have room in the quarter, but contractor spend is the line item getting closest to the ceiling.",
  "agent_name": "Acme Finance",
  "timestamp": "2026-03-14T11:00:01Z"
}
```

## Smart Responses

The backend ships with role-specific template banks and keyword matching for:

- finance
- ops
- hr
- admin

Each role has 15 to 20 natural response variants across common topics, plus fallback responses when the message is more general.

If `ANTHROPIC_API_KEY` is set, the backend calls the Anthropic Messages API with:

- the last `10` chat messages as conversation context
- a role-specific system prompt loaded from `configs/role-prompts/<role>.txt` when present
- a generated prompt from the role config when no custom prompt file exists

If the API call fails for any reason, the backend logs a warning and returns the existing template response instead.

## Message Store CLI

Read history:

```bash
python3 skills/chat-backend/scripts/message-store.py history demo finance alex-acmecorp-com --limit 20
```

Append a test message:

```bash
python3 skills/chat-backend/scripts/message-store.py append demo finance alex-acmecorp-com user "Need the invoice status for Vertex Labs."
```

## Sessions And Secrets

Session tokens are stored in `skills/chat-backend/data/sessions.json`.

For local development the server uses a default signing secret. Override it in real deployments:

```bash
export OPSCLAW_CHAT_SECRET='replace-this-in-production'
```

## Deployment Notes

- Use a reverse proxy if you want REST and WebSocket traffic on a single public port.
- Persist `skills/chat-backend/data/` across restarts if you want sessions and chat history to survive redeploys.
- Assets referenced by `logo_url` can be served by the frontend or by a separate static asset host.
