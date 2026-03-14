---
name: api_bridge
description: Generate agent-ready CLI wrappers and OpenClaw skills from OpenAPI specs or simple manual REST endpoint configs, then use the generated commands safely.
---

# API Bridge Skill

Use this skill when the user wants to wrap a REST API in a deterministic CLI, generate a matching OpenClaw skill, or stand up the included API bridge demo.

## Load Order
1. Read `scripts/api-bridge/config_schema.json` for the manual config shape.
2. Read `scripts/api-bridge/generator.py` only if you need to extend generation behavior.
3. Read the templates in `scripts/api-bridge/templates/` only if the generated CLI or skill wording needs to change.
4. Read `demo/api-bridge-demo/demo-api-config.json` for a working example config.

## Core Workflow
1. Create a manual config JSON or provide an OpenAPI JSON or YAML spec.
2. Run:
   - `python3 scripts/api-bridge/generator.py --config path/to/api.json`
   - or `python3 scripts/api-bridge/generator.py --openapi path/to/openapi.yaml`
3. The generator writes:
   - `generated/<api-name>/cli.py`
   - `generated/<api-name>/SKILL.md`
   - `generated/<api-name>/config.json`
4. Inspect endpoint help with `python3 generated/<api-name>/cli.py --help`.
5. Run commands using split endpoint names, for example `contacts.list` becomes `contacts list`.

## Manual Config Rules
- Put API metadata under `api`.
- Put each endpoint under `endpoints`.
- Use dotted names such as `contacts.list` or `reports.summary`.
- Put path or query parameters in `params`.
- Put JSON request body fields in `body`.
- Supported auth types: `none`, `bearer`, `apiKey`, `oauth2`.
- Supported methods: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`.

## Generated CLI Behavior
- Structured JSON output by default.
- `--format json|table|csv` on every generated command.
- Central auth handling for bearer tokens, API keys, and OAuth2 bearer access tokens.
- Automatic `--help` for root commands and endpoint commands.
- Pretty-printed JSON responses.

## Demo
- Start the included screen-recording-friendly demo with:
  - `bash demo/api-bridge-demo/run-demo.sh`
- The demo runs a local stdlib API server, generates the bridge, exercises live commands, then cleans up.

## Guardrails
- Prefer environment variables for credentials; do not hardcode secrets into configs.
- If a client gives only partial OpenAPI schemas, verify the generated body fields before relying on write commands.
- For OAuth2, the generated CLI expects a current access token from the configured env var; token refresh is not automatic.
