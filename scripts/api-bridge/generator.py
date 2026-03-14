#!/usr/bin/env python3
"""Generate agent-friendly CLIs and OpenClaw skills from API configs."""

from __future__ import annotations

import argparse
import json
import pprint
import re
import stat
import sys
from pathlib import Path
from string import Template
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR / "templates"
DEFAULT_OUTPUT_DIR = Path("generated")
VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
TYPE_MAP = {
    "string": "string",
    "str": "string",
    "integer": "int",
    "int": "int",
    "number": "float",
    "float": "float",
    "boolean": "bool",
    "bool": "bool",
    "array": "array",
    "object": "object",
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.config and not args.openapi:
        parser.error("one of --config or --openapi is required")

    source_path = Path(args.config or args.openapi).resolve()
    source_data = load_structured_file(source_path)
    normalized = (
        normalize_manual_config(source_data)
        if args.config
        else normalize_openapi_spec(source_data, source_path)
    )

    output_root = Path(args.output_dir).resolve()
    output_dir = output_root / normalized["api"]["name"]
    output_dir.mkdir(parents=True, exist_ok=True)

    render_cli(output_dir / "cli.py", normalized)
    render_skill(output_dir / "SKILL.md", normalized)
    write_json(output_dir / "config.json", normalized)

    print(
        json.dumps(
            {
                "ok": True,
                "api": normalized["api"]["name"],
                "source": str(source_path),
                "outputDir": str(output_dir),
                "files": [
                    str(output_dir / "cli.py"),
                    str(output_dir / "SKILL.md"),
                    str(output_dir / "config.json"),
                ],
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate an OpsClaw API bridge CLI and skill from OpenAPI or manual config."
    )
    parser.add_argument(
        "--config",
        help="Path to a manual endpoint config JSON file.",
    )
    parser.add_argument(
        "--openapi",
        help="Path to an OpenAPI JSON or YAML spec.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where generated/<api-name>/ will be created.",
    )
    return parser


def load_structured_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    if suffix == ".json":
        return json.loads(text)

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "YAML input requires PyYAML to be installed. "
                "Use JSON or install PyYAML for YAML/OpenAPI support."
            ) from exc
        return yaml.safe_load(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                f"Unable to parse {path}. Use JSON, or install PyYAML for YAML support."
            ) from exc
        return yaml.safe_load(text)


def normalize_manual_config(data: dict[str, Any]) -> dict[str, Any]:
    if "api" not in data or "endpoints" not in data:
        raise SystemExit("Manual config must contain top-level 'api' and 'endpoints'.")

    api = data["api"]
    endpoints = [normalize_manual_endpoint(endpoint) for endpoint in data["endpoints"]]
    return {
        "api": normalize_api_block(api),
        "endpoints": sorted(endpoints, key=lambda item: item["name"]),
        "meta": {"sourceType": "manual"},
    }


def normalize_manual_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    method = str(endpoint.get("method", "")).upper()
    if method not in VALID_METHODS:
        raise SystemExit(f"Unsupported method for endpoint {endpoint.get('name')}: {method}")

    normalized = {
        "name": endpoint["name"],
        "method": method,
        "path": endpoint["path"],
        "description": endpoint.get("description", "").strip() or endpoint["name"],
        "params": [],
        "body": [],
    }

    path_params = {
        match.group(1)
        for match in re.finditer(r"{([^}]+)}", endpoint["path"])
    }
    for param in endpoint.get("params", []):
        normalized["params"].append(
            normalize_field(
                param,
                default_location="path" if param["name"] in path_params else "query",
            )
        )
    for field in endpoint.get("body", []):
        normalized["body"].append(normalize_field(field, default_location="body"))

    return normalized


def normalize_api_block(api: dict[str, Any]) -> dict[str, Any]:
    auth = api.get("auth", {"type": "none"})
    return {
        "name": slugify(api["name"]),
        "displayName": api.get("displayName", api["name"]),
        "baseUrl": api["baseUrl"].rstrip("/"),
        "auth": normalize_auth(auth),
    }


def normalize_auth(auth: dict[str, Any]) -> dict[str, Any]:
    auth_type = str(auth.get("type", "none")).lower()
    if auth_type not in {"none", "bearer", "apikey", "api_key", "oauth2"}:
        raise SystemExit(f"Unsupported auth type: {auth_type}")

    if auth_type in {"apikey", "api_key"}:
        return {
            "type": "apiKey",
            "envVar": auth.get("envVar"),
            "header": auth.get("header") or auth.get("keyName") or "X-API-Key",
            "location": auth.get("location", "header"),
        }
    if auth_type == "oauth2":
        return {
            "type": "oauth2",
            "envVar": auth.get("envVar") or auth.get("tokenEnv") or auth.get("accessTokenEnv"),
            "tokenUrl": auth.get("tokenUrl"),
            "scopes": auth.get("scopes", []),
        }
    if auth_type == "bearer":
        return {
            "type": "bearer",
            "envVar": auth.get("envVar"),
            "header": auth.get("header", "Authorization"),
        }
    return {"type": "none"}


def normalize_field(field: dict[str, Any], default_location: str) -> dict[str, Any]:
    return {
        "name": field["name"],
        "type": normalize_type(field.get("type", "string")),
        "description": field.get("description", ""),
        "required": bool(field.get("required", False)),
        "default": field.get("default"),
        "location": field.get("location", default_location),
    }


def normalize_type(raw_type: str) -> str:
    lowered = str(raw_type).lower()
    return TYPE_MAP.get(lowered, "string")


def normalize_openapi_spec(spec: dict[str, Any], source_path: Path) -> dict[str, Any]:
    servers = spec.get("servers", [])
    base_url = ""
    if servers:
        base_url = servers[0].get("url", "")
    if not base_url:
        raise SystemExit("OpenAPI spec must include servers[0].url.")

    title = spec.get("info", {}).get("title") or source_path.stem
    auth = infer_openapi_auth(spec)
    endpoints = []

    for path, path_item in spec.get("paths", {}).items():
        path_parameters = path_item.get("parameters", [])
        for method in VALID_METHODS:
            operation = path_item.get(method.lower())
            if not operation:
                continue
            endpoints.append(
                normalize_openapi_operation(path, method, operation, path_parameters)
            )

    return {
        "api": {
            "name": slugify(title),
            "displayName": title,
            "baseUrl": base_url.rstrip("/"),
            "auth": auth,
        },
        "endpoints": sorted(endpoints, key=lambda item: item["name"]),
        "meta": {"sourceType": "openapi"},
    }


def infer_openapi_auth(spec: dict[str, Any]) -> dict[str, Any]:
    components = spec.get("components", {})
    schemes = components.get("securitySchemes", {})
    for scheme in schemes.values():
        scheme_type = scheme.get("type")
        if scheme_type == "http" and scheme.get("scheme") == "bearer":
            return {
                "type": "bearer",
                "envVar": scheme.get("x-env-var") or "API_TOKEN",
                "header": "Authorization",
            }
        if scheme_type == "apiKey":
            return {
                "type": "apiKey",
                "envVar": scheme.get("x-env-var") or "API_KEY",
                "header": scheme.get("name", "X-API-Key"),
                "location": scheme.get("in", "header"),
            }
        if scheme_type == "oauth2":
            return {
                "type": "oauth2",
                "envVar": scheme.get("x-env-var") or "OAUTH_ACCESS_TOKEN",
                "tokenUrl": find_oauth_token_url(scheme),
                "scopes": list(find_oauth_scopes(scheme)),
            }
    return {"type": "none"}


def find_oauth_token_url(scheme: dict[str, Any]) -> str | None:
    flows = scheme.get("flows", {})
    for flow in flows.values():
        token_url = flow.get("tokenUrl")
        if token_url:
            return token_url
    return None


def find_oauth_scopes(scheme: dict[str, Any]) -> set[str]:
    scopes: set[str] = set()
    for flow in scheme.get("flows", {}).values():
        scopes.update(flow.get("scopes", {}).keys())
    return scopes


def normalize_openapi_operation(
    path: str,
    method: str,
    operation: dict[str, Any],
    inherited_parameters: list[dict[str, Any]],
) -> dict[str, Any]:
    operation_id = operation.get("operationId")
    name = operation_id_to_command(operation_id, method, path)
    description = operation.get("summary") or operation.get("description") or name

    params = []
    combined_parameters = list(inherited_parameters) + list(operation.get("parameters", []))
    for param in combined_parameters:
        schema = param.get("schema", {})
        params.append(
            normalize_field(
                {
                    "name": param["name"],
                    "type": schema.get("type", "string"),
                    "description": param.get("description", ""),
                    "required": param.get("required", False),
                    "location": param.get("in", "query"),
                },
                default_location=param.get("in", "query"),
            )
        )

    body_fields = []
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    json_body = (
        content.get("application/json")
        or content.get("application/*+json")
        or next(iter(content.values()), {})
    )
    schema = json_body.get("schema", {})
    body_fields = extract_schema_fields(schema, required=request_body.get("required", False))

    return {
        "name": name,
        "method": method,
        "path": path,
        "description": squash_whitespace(description),
        "params": params,
        "body": body_fields,
    }


def extract_schema_fields(schema: dict[str, Any], required: bool = False) -> list[dict[str, Any]]:
    if not schema:
        return []

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        required_names = set(schema.get("required", []))
        fields = []
        for name, prop in schema.get("properties", {}).items():
            fields.append(
                normalize_field(
                    {
                        "name": name,
                        "type": prop.get("type", "string"),
                        "description": prop.get("description", ""),
                        "required": name in required_names,
                    },
                    default_location="body",
                )
            )
        return fields

    if schema_type == "array":
        return [
            normalize_field(
                {
                    "name": "items",
                    "type": "array",
                    "description": "JSON array request body.",
                    "required": required,
                },
                default_location="body",
            )
        ]

    return [
        normalize_field(
            {
                "name": "value",
                "type": schema_type or "string",
                "description": "Request body value.",
                "required": required,
            },
            default_location="body",
        )
    ]


def operation_id_to_command(operation_id: str | None, method: str, path: str) -> str:
    if operation_id:
        cleaned = re.sub(r"([a-z0-9])([A-Z])", r"\1.\2", operation_id)
        cleaned = cleaned.replace("_", ".").replace("-", ".")
        return ".".join(part.lower() for part in cleaned.split(".") if part)

    parts = [segment for segment in path.strip("/").split("/") if segment]
    literal_parts = [segment for segment in parts if not (segment.startswith("{") and segment.endswith("}"))]
    if not literal_parts:
        literal_parts = ["root"]

    resource = literal_parts[-1]
    if method == "GET":
        action = "list" if not parts or not parts[-1].startswith("{") else "get"
    elif method == "POST":
        action = "create"
    elif method == "PUT":
        action = "update"
    elif method == "PATCH":
        action = "patch"
    else:
        action = "delete"
    return f"{slugify(resource).replace('-', '.')}.{action}"


def render_cli(target_path: Path, config: dict[str, Any]) -> None:
    template = Template((TEMPLATE_DIR / "cli_template.py").read_text(encoding="utf-8"))
    content = template.substitute(
        api_name=config["api"]["displayName"],
        config_json=pprint.pformat(config, sort_dicts=True, width=100),
    )
    target_path.write_text(content, encoding="utf-8")
    mode = target_path.stat().st_mode
    target_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def render_skill(target_path: Path, config: dict[str, Any]) -> None:
    template = Template((TEMPLATE_DIR / "skill_template.md").read_text(encoding="utf-8"))
    commands = command_examples(config)
    auth_block = render_auth_notes(config["api"]["auth"])
    content = template.substitute(
        skill_name=f"{config['api']['name']}-api-bridge",
        api_name=config["api"]["displayName"],
        api_slug=config["api"]["name"],
        base_url=config["api"]["baseUrl"],
        auth_notes=auth_block,
        commands=commands,
    )
    target_path.write_text(content, encoding="utf-8")


def command_examples(config: dict[str, Any]) -> str:
    api_name = config["api"]["name"]
    lines = []
    for endpoint in config["endpoints"]:
        command = " ".join(endpoint["name"].split("."))
        sample = f"python3 generated/{api_name}/cli.py {command}"
        params = []
        for field in endpoint["params"]:
            if field["required"]:
                params.append(
                    f"--{flag_name(field['name'])} "
                    f"{sample_value(flag_name(field['name']), field['type'])}"
                )
        for field in endpoint["body"]:
            if field["required"]:
                params.append(
                    f"--{flag_name(field['name'])} {sample_value(flag_name(field['name']), field['type'])}"
                )
        if params:
            sample = f"{sample} {' '.join(params)}"
        lines.append(f"- `{sample}`: {endpoint['description']}")
    return "\n".join(lines)


def sample_value(name: str, field_type: str) -> str:
    if field_type == "int":
        return "1"
    if field_type == "float":
        return "1.0"
    if field_type == "bool":
        return "true"
    if field_type == "array":
        return "'[]'"
    if field_type == "object":
        return "'{}'"
    return f"<{name}>"


def render_auth_notes(auth: dict[str, Any]) -> str:
    auth_type = auth.get("type", "none")
    if auth_type == "bearer":
        return (
            f"Bearer token auth. Export `{auth.get('envVar') or 'API_TOKEN'}` before running commands, "
            "or pass `--auth-token`."
        )
    if auth_type == "apiKey":
        location = auth.get("location", "header")
        header = auth.get("header", "X-API-Key")
        return (
            f"API key auth. Export `{auth.get('envVar') or 'API_KEY'}` before running commands, "
            f"or pass `--api-key`. The key is sent via {location} `{header}`."
        )
    if auth_type == "oauth2":
        return (
            f"OAuth2 bearer token auth. Export `{auth.get('envVar') or 'OAUTH_ACCESS_TOKEN'}` "
            "with a current access token, or pass `--auth-token`."
        )
    return "No authentication configured."


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def squash_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "api"


def flag_name(name: str) -> str:
    return name.replace("_", "-")


if __name__ == "__main__":
    sys.exit(main())
