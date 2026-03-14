---
name: chat-ui
description: Build or customize the vanilla HTML/CSS/JS white-label chat frontend for OpsClaw role agents, including branding config, employee login, responsive role navigation, WebSocket chat, theme persistence, and demo fallback.
---

# Chat UI Skill

Use this skill when the user wants a browser-openable frontend for employee chat with OpsClaw role agents and does not want a framework or build step.

## Load Order

1. Read `frontend/app.js` for runtime flow, API contract handling, and demo mode behavior.
2. Read `frontend/styles.css` for layout, theming, responsive behavior, and motion.
3. Read `README.md` only when you need local run instructions or the expected API payload shapes.

## What This Skill Provides

- Landing screen with employee name entry and role-agent grid
- Responsive chat UI with desktop sidebar and mobile bottom nav
- Dark/light mode persisted in `localStorage`
- Theme variables driven by backend branding config
- WebSocket chat transport using `ws://localhost:8765/ws/<role>?token=<token>`
- Demo fallback with AcmeCorp branding and simulated role-agent responses

## API Expectations

- `GET /api/config?company_id=<company_id>`
- `POST /api/auth` with `{"company_id":"...","employee_name":"..."}`
- `ws://localhost:8765/ws/<role>?token=<token>`

Incoming socket events:

```json
{"type":"connected","text":"...","agent_name":"..."}
{"type":"typing","agent_name":"..."}
{"type":"response","text":"...","agent_name":"..."}
```

Outgoing socket event:

```json
{"type":"message","text":"...","role":"finance"}
```

## Guardrails

- Keep the frontend framework-free. Do not add React, Vue, bundlers, or npm dependencies.
- Preserve the white-label model: branding and roles should stay config-driven.
- Maintain the offline demo path so the UI still works when backend services are unavailable.
- Keep the interface sales-demo ready: strong typography, polished motion, and distinct responsive layouts.
