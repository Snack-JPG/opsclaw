#!/usr/bin/env python3
"""Generated CLI wrapper for Demo CRM."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


CONFIG = {'api': {'auth': {'envVar': 'DEMO_API_TOKEN', 'header': 'Authorization', 'type': 'bearer'},
         'baseUrl': 'http://127.0.0.1:8765/api/v1',
         'displayName': 'Demo CRM',
         'name': 'demo-crm'},
 'endpoints': [{'body': [{'default': None,
                          'description': 'Full name',
                          'location': 'body',
                          'name': 'name',
                          'required': True,
                          'type': 'string'},
                         {'default': None,
                          'description': 'Email address',
                          'location': 'body',
                          'name': 'email',
                          'required': True,
                          'type': 'string'},
                         {'default': None,
                          'description': 'Phone number',
                          'location': 'body',
                          'name': 'phone',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': 'Company name',
                          'location': 'body',
                          'name': 'company',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': 'Job title',
                          'location': 'body',
                          'name': 'title',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': 'CRM status',
                          'location': 'body',
                          'name': 'status',
                          'required': False,
                          'type': 'string'}],
                'description': 'Create a contact',
                'method': 'POST',
                'name': 'contacts.create',
                'params': [],
                'path': '/contacts'},
               {'body': [],
                'description': 'Delete a contact',
                'method': 'DELETE',
                'name': 'contacts.delete',
                'params': [{'default': None,
                            'description': 'Contact ID',
                            'location': 'path',
                            'name': 'id',
                            'required': True,
                            'type': 'string'}],
                'path': '/contacts/{id}'},
               {'body': [],
                'description': 'Get one contact',
                'method': 'GET',
                'name': 'contacts.get',
                'params': [{'default': None,
                            'description': 'Contact ID',
                            'location': 'path',
                            'name': 'id',
                            'required': True,
                            'type': 'string'}],
                'path': '/contacts/{id}'},
               {'body': [],
                'description': 'List CRM contacts',
                'method': 'GET',
                'name': 'contacts.list',
                'params': [{'default': 1,
                            'description': 'Page number',
                            'location': 'query',
                            'name': 'page',
                            'required': False,
                            'type': 'int'},
                           {'default': 20,
                            'description': 'Items per page',
                            'location': 'query',
                            'name': 'limit',
                            'required': False,
                            'type': 'int'}],
                'path': '/contacts'},
               {'body': [{'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'name',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'email',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'phone',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'company',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'title',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'status',
                          'required': False,
                          'type': 'string'}],
                'description': 'Update a contact',
                'method': 'PUT',
                'name': 'contacts.update',
                'params': [{'default': None,
                            'description': 'Contact ID',
                            'location': 'path',
                            'name': 'id',
                            'required': True,
                            'type': 'string'}],
                'path': '/contacts/{id}'},
               {'body': [{'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'name',
                          'required': True,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'value',
                          'required': True,
                          'type': 'int'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'contactId',
                          'required': True,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'stage',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'currency',
                          'required': False,
                          'type': 'string'},
                         {'default': None,
                          'description': '',
                          'location': 'body',
                          'name': 'owner',
                          'required': False,
                          'type': 'string'}],
                'description': 'Create a deal',
                'method': 'POST',
                'name': 'deals.create',
                'params': [],
                'path': '/deals'},
               {'body': [],
                'description': 'Get one deal',
                'method': 'GET',
                'name': 'deals.get',
                'params': [{'default': None,
                            'description': 'Deal ID',
                            'location': 'path',
                            'name': 'id',
                            'required': True,
                            'type': 'string'}],
                'path': '/deals/{id}'},
               {'body': [],
                'description': 'List deals',
                'method': 'GET',
                'name': 'deals.list',
                'params': [],
                'path': '/deals'},
               {'body': [],
                'description': 'Get dashboard summary',
                'method': 'GET',
                'name': 'reports.summary',
                'params': [],
                'path': '/reports/summary'}],
 'meta': {'sourceType': 'manual'}}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    endpoint = getattr(args, "_endpoint", None)
    if endpoint is None:
        parser.print_help()
        return 1

    try:
        response = invoke_endpoint(args, endpoint)
        emit_output(response, args.format)
    except Exception as exc:  # pylint: disable=broad-except
        error = {"ok": False, "error": str(exc), "endpoint": endpoint["name"]}
        print(json.dumps(error, indent=2), file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Agent-friendly CLI for {CONFIG['api']['displayName']}"
    )
    add_global_arguments(parser)
    register_commands(parser, CONFIG["endpoints"])
    return parser


def add_global_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=CONFIG["api"]["baseUrl"],
        help="Override the configured API base URL.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "table", "csv"],
        default="json",
        help="Output format.",
    )
    parser.add_argument(
        "--auth-token",
        help="Override bearer or OAuth2 token.",
    )
    parser.add_argument(
        "--api-key",
        help="Override API key.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--body-json",
        help="Raw JSON request body. Overrides field-level body flags.",
    )


def register_commands(parser: argparse.ArgumentParser, endpoints: list[dict]) -> None:
    root_subparsers = parser.add_subparsers(dest="_command")
    command_nodes = {}

    for endpoint in endpoints:
        parts = endpoint["name"].split(".")
        current_subparsers = root_subparsers
        path_key = []

        for index, part in enumerate(parts):
            path_key.append(part)
            key = tuple(path_key)
            is_leaf = index == len(parts) - 1

            if key not in command_nodes:
                cmd_parser = current_subparsers.add_parser(
                    part,
                    help=endpoint["description"] if is_leaf else f"{part} commands",
                    description=endpoint["description"] if is_leaf else None,
                )
                command_nodes[key] = cmd_parser
                add_global_arguments(cmd_parser)
                if not is_leaf:
                    cmd_parser.set_defaults(_endpoint=None)
                    current_subparsers = cmd_parser.add_subparsers(dest=f"_subcommand_{index}")
                else:
                    configure_endpoint_parser(cmd_parser, endpoint)
                    cmd_parser.set_defaults(_endpoint=endpoint)
            else:
                cmd_parser = command_nodes[key]
                if not is_leaf:
                    current_subparsers = find_or_create_subparsers(cmd_parser, index)


def find_or_create_subparsers(parser: argparse.ArgumentParser, index: int):
    for action in parser._actions:  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return action
    return parser.add_subparsers(dest=f"_subcommand_{index}")


def configure_endpoint_parser(parser: argparse.ArgumentParser, endpoint: dict) -> None:
    parser.epilog = f"{endpoint['method']} {endpoint['path']}"
    for param in endpoint.get("params", []):
        add_field_argument(parser, param)
    for field in endpoint.get("body", []):
        add_field_argument(parser, field, body=True)


def add_field_argument(parser: argparse.ArgumentParser, field: dict, body: bool = False) -> None:
    argument = f"--{field['name'].replace('_', '-')}"
    kwargs = {
        "dest": field["name"],
        "help": build_field_help(field, body),
    }
    if field["type"] == "bool":
        kwargs["type"] = parse_bool
    elif field["type"] == "int":
        kwargs["type"] = int
    elif field["type"] == "float":
        kwargs["type"] = float
    elif field["type"] in {"array", "object"}:
        kwargs["type"] = json.loads
    else:
        kwargs["type"] = str

    if field.get("required"):
        kwargs["required"] = True
    elif field.get("default") is not None:
        kwargs["default"] = field["default"]

    parser.add_argument(argument, **kwargs)


def build_field_help(field: dict, body: bool) -> str:
    location = "request body" if body else field.get("location", "query")
    suffix = f" [{location}]"
    if field.get("default") is not None:
        suffix += f" default={field['default']}"
    return (field.get("description") or field["name"]) + suffix


def parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def invoke_endpoint(args: argparse.Namespace, endpoint: dict) -> dict:
    path = endpoint["path"]
    query_params = {}
    body_data = {}
    headers = {"Accept": "application/json"}

    for param in endpoint.get("params", []):
        value = getattr(args, param["name"], None)
        if value is None:
            continue
        if param.get("location") == "path":
            path = path.replace("{" + param["name"] + "}", urllib.parse.quote(str(value), safe=""))
        elif param.get("location") == "header":
            headers[param["name"]] = str(value)
        else:
            query_params[param["name"]] = normalize_value(value)

    if args.body_json:
        body_data = json.loads(args.body_json)
    else:
        for field in endpoint.get("body", []):
            value = getattr(args, field["name"], None)
            if value is not None:
                body_data[field["name"]] = normalize_value(value)

    apply_auth(headers, query_params, args)

    url = args.base_url.rstrip("/") + path
    if query_params:
        url += "?" + urllib.parse.urlencode(flatten_query(query_params), doseq=True)

    body = None
    if endpoint["method"] in {"POST", "PUT", "PATCH"}:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body_data).encode("utf-8")

    request = urllib.request.Request(url=url, data=body, method=endpoint["method"], headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return {
                "ok": True,
                "status": response.status,
                "endpoint": endpoint["name"],
                "method": endpoint["method"],
                "url": url,
                "data": payload,
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        data = None
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"raw": raw}
        raise RuntimeError(
            json.dumps(
                {
                    "status": exc.code,
                    "reason": exc.reason,
                    "url": url,
                    "data": data,
                },
                indent=2,
            )
        ) from exc


def apply_auth(headers: dict, query_params: dict, args: argparse.Namespace) -> None:
    auth = CONFIG["api"].get("auth", {"type": "none"})
    auth_type = auth.get("type", "none")
    if auth_type == "none":
        return

    if auth_type in {"bearer", "oauth2"}:
        token = args.auth_token or read_env(auth.get("envVar"))
        if not token:
            raise RuntimeError(
                f"Missing auth token. Export {auth.get('envVar') or 'API_TOKEN'} or pass --auth-token."
            )
        headers[auth.get("header", "Authorization")] = f"Bearer {token}"
        return

    if auth_type == "apiKey":
        api_key = args.api_key or read_env(auth.get("envVar"))
        if not api_key:
            raise RuntimeError(
                f"Missing API key. Export {auth.get('envVar') or 'API_KEY'} or pass --api-key."
            )
        header_name = auth.get("header", "X-API-Key")
        if auth.get("location", "header") == "query":
            query_params[header_name] = api_key
        else:
            headers[header_name] = api_key


def read_env(name: str | None) -> str | None:
    if not name:
        return None
    return os.environ.get(name)


def normalize_value(value):
    if isinstance(value, (dict, list, bool, int, float)):
        return value
    return str(value)


def flatten_query(params: dict) -> dict:
    flattened = {}
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            flattened[key] = [json.dumps(item) if isinstance(item, (dict, list)) else item for item in value]
        elif isinstance(value, dict):
            flattened[key] = json.dumps(value)
        else:
            flattened[key] = value
    return flattened


def emit_output(response: dict, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(response, indent=2))
        return

    rows = rows_for_output(response["data"])
    if output_format == "csv":
        write_csv(rows)
        return
    write_table(rows)


def rows_for_output(data):
    if isinstance(data, list):
        return [flatten_item(item) for item in data]
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return [flatten_item(item) for item in data["items"]]
        return [flatten_item(data)]
    return [{"value": data}]


def flatten_item(item, prefix=""):
    if isinstance(item, dict):
        flat = {}
        for key, value in item.items():
            new_prefix = f"{prefix}.{key}" if prefix else key
            flat.update(flatten_item(value, new_prefix))
        return flat
    if isinstance(item, list):
        return {prefix or "value": json.dumps(item)}
    return {prefix or "value": item}


def write_csv(rows):
    if not rows:
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def write_table(rows):
    if not rows:
        print("(no rows)")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    widths = {field: max(len(field), *(len(str(row.get(field, ""))) for row in rows)) for field in fieldnames}
    header = " | ".join(field.ljust(widths[field]) for field in fieldnames)
    divider = "-+-".join("-" * widths[field] for field in fieldnames)
    print(header)
    print(divider)
    for row in rows:
        print(" | ".join(str(row.get(field, "")).ljust(widths[field]) for field in fieldnames))


if __name__ == "__main__":
    sys.exit(main())
