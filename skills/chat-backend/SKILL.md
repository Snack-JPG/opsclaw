---
name: chat_backend
description: Build and operate the stdlib-only OpsClaw chat backend with company config management, session auth, message persistence, and raw WebSocket chat for role agents.
---

# Chat Backend Skill

Use this skill when the user wants a white-label chat backend for OpsClaw role agents, especially when the requirement is zero Python dependencies.

## Load Order
1. Read `scripts/server.py` for runtime behavior and protocol details.
2. Read `scripts/chat_backend_core.py` for config, session, message, and response logic.
3. Read `configs/company-configs/*.json` only for the target company you need.
4. Read `README.md` when you need setup, endpoint, or deployment details.

## Runtime Model
- REST runs on `http.server` and exposes config, roles, auth, and history endpoints.
- WebSocket chat runs on raw `asyncio` streams with manual handshake and frame parsing.
- Shared state lives on disk:
  - company configs: `configs/company-configs/*.json`
  - sessions: `data/sessions.json`
  - history: `data/<company_id>/<role>/<user_id>.json`

## Start The Backend

```bash
python3 skills/chat-backend/scripts/server.py
```

Common flags:

```bash
python3 skills/chat-backend/scripts/server.py \
  --host 0.0.0.0 \
  --http-port 8000 \
  --ws-port 8765 \
  --verbose
```

## Config Management

Create a company:

```bash
python3 skills/chat-backend/scripts/config-manager.py init "ForgeWorks Manufacturing"
```

Update branding:

```bash
python3 skills/chat-backend/scripts/config-manager.py set-branding forgeworks-manufacturing \
  --name "ForgeBot" \
  --color "#1a5c3a" \
  --logo "/assets/logo.png"
```

Add or update a role:

```bash
python3 skills/chat-backend/scripts/config-manager.py add-role forgeworks-manufacturing finance \
  --name "Forge Finance" \
  --greeting "Hey! I handle finance queries."
```

Inspect configs:

```bash
python3 skills/chat-backend/scripts/config-manager.py list
python3 skills/chat-backend/scripts/config-manager.py export demo
```

## API Summary
- `GET /api/config`
- `GET /api/roles`
- `POST /api/auth`
- `GET /api/history?role=<role>&limit=20`
- `ws://<host>:<ws-port>/ws/<role>?token=<session-token>`

The REST layer supports `company_id` via query param or `X-Company-Id` header. History requires a bearer token or `token` query param.

## Message Shape

Inbound WebSocket message:

```json
{"type":"message","text":"How much PTO do I have?","role":"hr"}
```

Server events:

```json
{"type":"typing","agent_name":"Acme People","timestamp":"2026-03-14T11:00:00Z"}
{"type":"response","text":"...","agent_name":"Acme People","timestamp":"2026-03-14T11:00:01Z"}
```

## Guardrails
- Keep the runtime stdlib-only. Do not add `fastapi`, `websockets`, or other pip packages.
- Keep company customization in JSON configs, not hardcoded branches in the server.
- Preserve append-only message history semantics and the 1000-message cap.
- If REST and WebSocket need to share one public endpoint, put a reverse proxy in front rather than adding third-party dependencies.
