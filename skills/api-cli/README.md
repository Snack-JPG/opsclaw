# Universal API CLI

`api.py` is a gws-style universal REST client for OpsClaw. Instead of writing one wrapper per client, you define one JSON config per API and call it with:

```bash
python3 skills/api-cli/scripts/api.py <service> <resource> <method> [flags]
```

Examples:

```bash
python3 skills/api-cli/scripts/api.py demo-crm contacts list --params '{"limit": 10}'
python3 skills/api-cli/scripts/api.py demo-crm contacts get --params '{"id": "ct-001"}'
python3 skills/api-cli/scripts/api.py demo-crm deals create --json '{"name": "Expansion", "value": 5000, "contact_id": "ct-001"}'
python3 skills/api-cli/scripts/api.py demo-inventory items search --params '{"query": "widget"}'
```

## Why This Exists

Google's `gws` CLI gives agents a stable command grammar for many APIs:

```bash
gws drive files list --params '{"pageSize": 10}'
gws gmail users messages list --params '{"userId": "me"}'
gws schema drive.files.list
```

This skill mirrors that model for arbitrary REST APIs:

- One command shape across all services
- Declarative configs instead of client-specific code
- Predictable output for agents
- Zero external dependencies beyond Python stdlib

## Commands

Root commands:

```bash
python3 skills/api-cli/scripts/api.py services
python3 skills/api-cli/scripts/api.py schema demo-crm
python3 skills/api-cli/scripts/api.py schema demo-crm.contacts.list
```

Execution:

```bash
python3 skills/api-cli/scripts/api.py <service> <resource> [sub-resource ...] <method> [flags]
```

Flags:

- `--params '{...}'`: Query params and path params
- `--json '{...}'`: JSON request body
- `--format json|table|csv|yaml`: Output format
- `--output path`: Write response to file
- `--raw`: Print raw response
- `--dry-run`: Print resolved HTTP request without sending it
- `--verbose`: Print request and response headers
- `--page-all`: Auto-paginate
- `--page-limit N`: Max pages, default `10`
- `--config-dir path`: Override config directory
- `--header 'Name: value'`: Add a custom header

## Config Format

Each service lives in one JSON file under [`skills/api-cli/configs/`](/Users/austin/Desktop/opsclaw/skills/api-cli/configs).

Example:

```json
{
  "service": "crm",
  "name": "Client CRM",
  "base_url": "https://api.clientcrm.com/v1",
  "auth": {
    "type": "bearer",
    "env_var": "CRM_API_TOKEN"
  },
  "pagination": {
    "type": "offset",
    "offset_param": "offset",
    "limit_param": "limit",
    "results_field": "data",
    "next_offset_field": "next_offset"
  },
  "resources": {
    "contacts": {
      "base_path": "/contacts",
      "methods": {
        "list": {
          "http": "GET",
          "path": "/",
          "params": ["limit", "offset", "search"]
        },
        "get": {
          "http": "GET",
          "path": "/{id}",
          "params": ["id"]
        },
        "create": {
          "http": "POST",
          "path": "/",
          "body": true
        }
      }
    }
  }
}
```

Notes:

- Path placeholders like `{id}` are filled from `--params`.
- Values used in the path are removed from the query string automatically.
- `auth.type` supports `bearer`, `api-key`, `basic`, and `none`.
- Pagination can be configured per service or per method with `cursor`, `offset`, or `link`.

## Config Generator

[`api-config-generator.py`](/Users/austin/Desktop/opsclaw/skills/api-cli/scripts/api-config-generator.py) creates config JSON from three inputs:

```bash
python3 skills/api-cli/scripts/api-config-generator.py --openapi path/to/openapi.json
python3 skills/api-cli/scripts/api-config-generator.py --openapi https://client.example.com/openapi.json
python3 skills/api-cli/scripts/api-config-generator.py --fastapi http://127.0.0.1:8000
python3 skills/api-cli/scripts/api-config-generator.py --interactive --service client-crm
```

What it does:

- Reads an OpenAPI/Swagger file or URL and extracts paths into resources/methods
- Pulls `/openapi.json` from a FastAPI app
- Builds a config interactively when no spec exists

The generated file lands in `skills/api-cli/configs/<service>.json` unless `--output` is provided.

## Demo

[`demo-server.py`](/Users/austin/Desktop/opsclaw/skills/api-cli/scripts/demo-server.py) serves three fake APIs so the CLI can be shown live with no external systems:

- `demo-crm`: bearer auth + offset pagination
- `demo-inventory`: API key auth + cursor pagination
- `demo-hr`: basic auth + link-header pagination

Start the server:

```bash
python3 skills/api-cli/scripts/demo-server.py
```

Export demo credentials:

```bash
export DEMO_CRM_TOKEN=demo-crm-token
export DEMO_INVENTORY_KEY=demo-inventory-key
export DEMO_HR_BASIC=demo-hr-user:demo-hr-pass
```

Try it:

```bash
python3 skills/api-cli/scripts/api.py services
python3 skills/api-cli/scripts/api.py schema demo-inventory.items.search
python3 skills/api-cli/scripts/api.py demo-crm contacts list --params '{"limit": 3}' --format table
python3 skills/api-cli/scripts/api.py demo-inventory items search --params '{"query": "widget", "limit": 2}' --page-all
python3 skills/api-cli/scripts/api.py demo-hr employees list --params '{"limit": 4}' --page-all --format csv
```

## Client Deployment Workflow

This is the intended OpsClaw rollout model:

1. The client already has an API, or OpsClaw builds them a FastAPI app.
2. Run `api-config-generator.py` against the OpenAPI spec or FastAPI base URL.
3. Review and save the generated config JSON.
4. Set the client auth env vars on the agent host.
5. Agents use `api <service> <resource> <method>` commands.
6. No per-client Python wrappers or custom `curl` scripts are required.

That means onboarding a new API usually becomes config review, not code writing.
