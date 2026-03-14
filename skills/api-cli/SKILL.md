---
name: api_cli
description: Use a gws-style universal API CLI to call any configured REST API with declarative service -> resource -> method commands, generate new service configs from OpenAPI or prompts, and demo the flow against bundled fake APIs.
---

# API CLI Skill

Use this skill when the user wants one CLI that can talk to many REST APIs without writing custom Python or `curl`.

## Load Order
1. Read `scripts/api.py` for runtime behavior and supported flags.
2. Read `configs/*.json` only for the service you need.
3. Read `scripts/api-config-generator.py` when adding a new client API from OpenAPI, FastAPI, or prompts.
4. Read `scripts/demo-server.py` only if you need the bundled local demo.

## Command Pattern
- Use `python3 skills/api-cli/scripts/api.py <service> <resource> [sub-resource ...] <method>`.
- Think in `service -> resource -> method`, mirroring `gws`.
- Put query and path inputs in `--params '{"...": "..."}'`.
- Put request bodies in `--json '{"...": "..."}'`.

Examples:

```bash
python3 skills/api-cli/scripts/api.py demo-crm contacts list --params '{"limit": 5}'
python3 skills/api-cli/scripts/api.py demo-crm contacts get --params '{"id": "ct-001"}'
python3 skills/api-cli/scripts/api.py demo-inventory items search --params '{"query": "widget", "limit": 3}'
python3 skills/api-cli/scripts/api.py demo-hr leave-requests approve --params '{"id": "lv-002"}' --json '{"approved_by": "ops-manager"}'
```

## Discovery
- `python3 skills/api-cli/scripts/api.py services`
- `python3 skills/api-cli/scripts/api.py schema <service>`
- `python3 skills/api-cli/scripts/api.py schema <service.resource.method>`

## Flags
- `--params '{...}'`: Query params and path params.
- `--json '{...}'`: JSON request body.
- `--format json|table|csv|yaml`: Output format. Default is `json`.
- `--output path`: Write formatted output to a file.
- `--raw`: Print raw response body.
- `--dry-run`: Show the HTTP request without sending it.
- `--verbose`: Print request and response headers to stderr.
- `--page-all`: Auto-follow cursor, offset, link, or inferred next-page patterns.
- `--page-limit N`: Cap auto-pagination. Default `10`.
- `--config-dir path`: Override the config directory.

## Adding A New API
1. Generate a starter config:
   - `python3 skills/api-cli/scripts/api-config-generator.py --openapi path/to/openapi.json`
   - `python3 skills/api-cli/scripts/api-config-generator.py --fastapi http://127.0.0.1:8000`
   - `python3 skills/api-cli/scripts/api-config-generator.py --interactive --service client-crm`
2. Review the generated JSON in `skills/api-cli/configs/`.
3. Set auth env vars for the service config.
4. Call the API with `api.py` using `service resource method`.

## Config Rules
- One JSON file per API under `configs/`.
- Top-level keys: `service`, `name`, `base_url`, `auth`, `resources`.
- Each resource needs `base_path` and `methods`.
- Each method declares `http`, `path`, optional `params`, and optional `body`.
- Supported auth types: `bearer`, `api-key`, `basic`, `none`.
- Path placeholders such as `{id}` are filled from `--params` and removed from query params.

## Auth Setup
- `bearer`: export the configured token env var and the CLI sends `Authorization: Bearer ...`
- `api-key`: export the configured key env var and the CLI sends the configured header
- `basic`: export `user:pass` in the configured env var and the CLI sends a Basic auth header
- `none`: no auth header is added

Bundled demo env vars:

```bash
export DEMO_CRM_TOKEN=demo-crm-token
export DEMO_INVENTORY_KEY=demo-inventory-key
export DEMO_HR_BASIC=demo-hr-user:demo-hr-pass
```

## Demo Flow
1. Start `python3 skills/api-cli/scripts/demo-server.py`.
2. Export the three demo credentials above.
3. Run `api.py services` and inspect schemas.
4. Execute live commands against `demo-crm`, `demo-inventory`, and `demo-hr`.

## Guardrails
- Prefer config JSON over ad hoc API code so new clients do not require custom wrappers.
- Use `--dry-run` before destructive methods if the config is new or hand-edited.
- Review generated OpenAPI configs before using write operations; naming and body inference may need cleanup.
