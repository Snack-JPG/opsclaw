---
name: ${skill_name}
description: Use the generated ${api_name} API bridge to call the client REST API through a structured CLI with JSON, table, or CSV output.
---

# ${api_name} API Bridge

Use this generated skill whenever the user needs data from the `${api_name}` API or wants to perform one of its supported REST operations through a deterministic CLI wrapper.

## Load Order
1. Read `generated/${api_slug}/config.json` for the normalized endpoint map.
2. Read this file for command examples and auth expectations.
3. Run `python3 generated/${api_slug}/cli.py --help` or endpoint help before using an unfamiliar command.

## Connection
- Base URL: `${base_url}`
- Auth: ${auth_notes}

## Usage Rules
- Prefer the generated CLI instead of hand-writing raw `curl` commands.
- Default to `--format json` unless the user explicitly wants a table or CSV.
- Use endpoint help for the exact flags: `python3 generated/${api_slug}/cli.py <command> --help`.
- If an endpoint has path parameters, pass them as flags, for example `--id 123`.
- For body payloads, use the generated field flags or `--body-json '{"key":"value"}'`.

## Commands
${commands}
