# API Bridge Skill

The API Bridge turns a REST API into two artifacts:

- a generated Python CLI wrapper with clean JSON, table, or CSV output
- a generated OpenClaw `SKILL.md` that tells an agent what commands exist

## Generator

Run the generator with either a manual config or an OpenAPI spec:

```bash
python3 scripts/api-bridge/generator.py --config path/to/api-config.json
python3 scripts/api-bridge/generator.py --openapi path/to/openapi.yaml
```

Generated output lands in:

```text
generated/<api-name>/
  cli.py
  SKILL.md
  config.json
```

## Manual Config

Schema: [scripts/api-bridge/config_schema.json](/Users/austin/Desktop/opsclaw/scripts/api-bridge/config_schema.json)

Key fields:

- `api.name`: short API slug
- `api.baseUrl`: base URL used by the generated CLI
- `api.auth`: `none`, `bearer`, `apiKey`, or `oauth2`
- `endpoints[].name`: dotted command name such as `contacts.list`
- `endpoints[].params`: path/query/header flags
- `endpoints[].body`: JSON request body flags

Minimal example:

```json
{
  "api": {
    "name": "acme",
    "baseUrl": "https://api.acme.com/v1",
    "auth": { "type": "bearer", "envVar": "ACME_API_TOKEN" }
  },
  "endpoints": [
    {
      "name": "contacts.list",
      "method": "GET",
      "path": "/contacts"
    }
  ]
}
```

## Using a Generated CLI

If the config uses `contacts.list`, the command becomes:

```bash
python3 generated/acme/cli.py contacts list
```

Useful flags:

- `--format json|table|csv`
- `--auth-token`
- `--api-key`
- `--base-url`
- `--body-json`

Each endpoint also exposes endpoint-specific `--help`.

## Demo

The included demo shows the full flow against a local CRM-like API:

```bash
bash demo/api-bridge-demo/run-demo.sh
```

Files:

- [demo/api-bridge-demo/demo-api-server.py](/Users/austin/Desktop/opsclaw/demo/api-bridge-demo/demo-api-server.py)
- [demo/api-bridge-demo/demo-api-config.json](/Users/austin/Desktop/opsclaw/demo/api-bridge-demo/demo-api-config.json)
- [demo/api-bridge-demo/run-demo.sh](/Users/austin/Desktop/opsclaw/demo/api-bridge-demo/run-demo.sh)
