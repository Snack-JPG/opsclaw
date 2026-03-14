---
name: demo-crm-api-bridge
description: Use the generated Demo CRM API bridge to call the client REST API through a structured CLI with JSON, table, or CSV output.
---

# Demo CRM API Bridge

Use this generated skill whenever the user needs data from the `Demo CRM` API or wants to perform one of its supported REST operations through a deterministic CLI wrapper.

## Load Order
1. Read `generated/demo-crm/config.json` for the normalized endpoint map.
2. Read this file for command examples and auth expectations.
3. Run `python3 generated/demo-crm/cli.py --help` or endpoint help before using an unfamiliar command.

## Connection
- Base URL: `http://127.0.0.1:8765/api/v1`
- Auth: Bearer token auth. Export `DEMO_API_TOKEN` before running commands, or pass `--auth-token`.

## Usage Rules
- Prefer the generated CLI instead of hand-writing raw `curl` commands.
- Default to `--format json` unless the user explicitly wants a table or CSV.
- Use endpoint help for the exact flags: `python3 generated/demo-crm/cli.py <command> --help`.
- If an endpoint has path parameters, pass them as flags, for example `--id 123`.
- For body payloads, use the generated field flags or `--body-json '{"key":"value"}'`.

## Commands
- `python3 generated/demo-crm/cli.py contacts create --name <name> --email <email>`: Create a contact
- `python3 generated/demo-crm/cli.py contacts delete --id <id>`: Delete a contact
- `python3 generated/demo-crm/cli.py contacts get --id <id>`: Get one contact
- `python3 generated/demo-crm/cli.py contacts list`: List CRM contacts
- `python3 generated/demo-crm/cli.py contacts update --id <id>`: Update a contact
- `python3 generated/demo-crm/cli.py deals create --name <name> --value 1 --contactId <contactId>`: Create a deal
- `python3 generated/demo-crm/cli.py deals get --id <id>`: Get one deal
- `python3 generated/demo-crm/cli.py deals list`: List deals
- `python3 generated/demo-crm/cli.py reports summary`: Get dashboard summary
