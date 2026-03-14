# Chat UI

`skills/chat-ui/frontend/` is a pure HTML, CSS, and JavaScript white-label chat frontend for OpsClaw role agents. It is built for product demos and internal employee use: landing flow, role selection, responsive chat, live WebSocket transport, theme persistence, and a demo fallback if the backend is unavailable.

## Files

- `frontend/index.html`: single-page shell and font loading
- `frontend/styles.css`: premium visual system, responsive layout, motion, and theme variables
- `frontend/app.js`: config/auth boot flow, chat state, WebSocket handling, and demo simulation
- `SKILL.md`: skill usage instructions for future Codex runs

## Run

Serve the frontend with any static file server.

```bash
cd /Users/austin/Desktop/opsclaw/skills/chat-ui/frontend
python3 -m http.server 8080
```

Open:

- `http://127.0.0.1:8080`
- Optional company override: `?company_id=demo`
- Optional API override: `?api_base=http://127.0.0.1:8000`

The app defaults to:

- `GET http://localhost:8000/api/config?company_id=demo`
- `POST http://localhost:8000/api/auth`
- `ws://localhost:8765/ws/<role>?token=<token>`

## API Contract

Expected config response:

```json
{
  "branding": {
    "product_name": "AcmeOps Pulse",
    "primary_color": "#14685c",
    "secondary_color": "#e8f5f0"
  },
  "roles": {
    "finance": {
      "emoji": "💸",
      "name": "Finance Lead",
      "description": "Budgets, approvals, reimbursement timing, and spend sanity checks."
    }
  },
  "role_list": ["finance"]
}
```

Expected auth request and response:

```json
{"company_id":"demo","employee_name":"Jordan Lee"}
```

```json
{"token":"...","session":{"company_id":"demo","employee_name":"Jordan Lee"}}
```

Expected WebSocket events:

```json
{"type":"message","text":"...","role":"finance"}
{"type":"typing","agent_name":"Finance Lead"}
{"type":"response","text":"...","agent_name":"Finance Lead"}
{"type":"connected","text":"Welcome","agent_name":"Finance Lead"}
```

## Notes

- Dark and light mode are stored in `localStorage`.
- Theme colors are applied through `--primary`, `--secondary`, `--text`, and `--bg`.
- If config or auth fails, the UI falls back to a built-in AcmeCorp demo so sales demos can keep moving.
