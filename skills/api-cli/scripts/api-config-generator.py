#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import parse, request


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR.parent / "configs"


class GeneratorError(Exception):
    pass


def fetch_text(source: str) -> str:
    if source.startswith("http://") or source.startswith("https://"):
        with request.urlopen(source) as response:
            return response.read().decode("utf-8")
    return Path(source).read_text()


def parse_json_or_yaml(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return parse_simple_yaml(text)


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    lines = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))
    if not lines:
        return {}
    parsed, index = parse_yaml_block(lines, 0, lines[0][0])
    if index != len(lines):
        raise GeneratorError("Could not parse entire YAML document")
    if not isinstance(parsed, dict):
        raise GeneratorError("YAML root must be a mapping")
    return parsed


def parse_yaml_block(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[Any, int]:
    if lines[start][1].startswith("- "):
        return parse_yaml_list(lines, start, indent)
    return parse_yaml_mapping(lines, start, indent)


def parse_yaml_mapping(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[Dict[str, Any], int]:
    mapping: Dict[str, Any] = {}
    index = start
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise GeneratorError(f"Unexpected indentation near: {text}")
        if text.startswith("- "):
            break
        key, _, value = text.partition(":")
        if _ == "":
            raise GeneratorError(f"Unable to parse YAML line: {text}")
        key = key.strip()
        value = value.strip()
        index += 1
        if value:
            mapping[key] = parse_scalar(value)
            continue
        if index >= len(lines) or lines[index][0] <= current_indent:
            mapping[key] = {}
            continue
        child, index = parse_yaml_block(lines, index, lines[index][0])
        mapping[key] = child
    return mapping, index


def parse_yaml_list(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[List[Any], int]:
    items: List[Any] = []
    index = start
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not text.startswith("- "):
            break
        item_text = text[2:].strip()
        index += 1
        if not item_text:
            if index >= len(lines) or lines[index][0] <= current_indent:
                items.append(None)
                continue
            child, index = parse_yaml_block(lines, index, lines[index][0])
            items.append(child)
            continue
        if ":" in item_text:
            key, _, value = item_text.partition(":")
            item: Dict[str, Any] = {}
            key = key.strip()
            value = value.strip()
            if value:
                item[key] = parse_scalar(value)
            elif index < len(lines) and lines[index][0] > current_indent:
                child, index = parse_yaml_block(lines, index, lines[index][0])
                item[key] = child
            else:
                item[key] = {}
            while index < len(lines) and lines[index][0] > current_indent:
                extra, index = parse_yaml_mapping(lines, index, lines[index][0])
                item.update(extra)
            items.append(item)
            continue
        items.append(parse_scalar(item_text))
    return items, index


def parse_scalar(value: str) -> Any:
    if value in ("null", "~"):
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def slugify(text: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "-" for ch in text]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "service"


def choose_auth_config(args: argparse.Namespace) -> Dict[str, Any]:
    auth_type = args.auth_type or prompt("Auth type [none|bearer|api-key|basic]", "none")
    auth: Dict[str, Any] = {"type": auth_type}
    if auth_type != "none":
        env_var = args.env_var or prompt("Env var for credentials", f"{slugify(args.service).upper().replace('-', '_')}_API_TOKEN")
        auth["env_var"] = env_var
    if auth_type == "api-key":
        auth["header"] = args.api_key_header or prompt("API key header", "X-API-Key")
    return auth


def prompt(label: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or (default or "")


def generate_from_openapi(spec: Dict[str, Any], service: Optional[str], name: Optional[str]) -> Dict[str, Any]:
    service_name = service or slugify(spec.get("info", {}).get("title", "api"))
    display_name = name or spec.get("info", {}).get("title", service_name)
    servers = spec.get("servers") or [{"url": "http://127.0.0.1:8000"}]
    base_url = servers[0].get("url", "http://127.0.0.1:8000").rstrip("/")
    resources: Dict[str, Any] = {}

    for path, path_item in spec.get("paths", {}).items():
        segments = [segment for segment in path.strip("/").split("/") if segment and not segment.startswith("{")]
        resource_name = segments[0] if segments else "root"
        resource = resources.setdefault(resource_name, {"base_path": f"/{resource_name}" if resource_name != "root" else "", "methods": {}})
        method_path = path
        if resource_name != "root" and method_path.startswith(resource["base_path"]):
            method_path = method_path[len(resource["base_path"]):] or "/"
        for http_method, operation in path_item.items():
            if http_method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            method_name = infer_method_name(http_method.lower(), method_path, operation)
            params = []
            for parameter in operation.get("parameters", []):
                params.append(parameter.get("name"))
            request_body = "requestBody" in operation
            resource["methods"][method_name] = {
                "http": http_method.upper(),
                "path": method_path or "/",
                "params": [p for p in params if p],
                "body": request_body,
                "description": operation.get("summary") or operation.get("operationId", ""),
            }

    return {
        "service": service_name,
        "name": display_name,
        "base_url": base_url,
        "auth": {"type": "none"},
        "resources": resources,
    }


def infer_method_name(http_method: str, path: str, operation: Dict[str, Any]) -> str:
    if operation.get("operationId"):
        return slugify(operation["operationId"]).replace("-", "_")
    cleaned = path.strip("/")
    if http_method == "get" and cleaned in ("",):
        return "list"
    if http_method == "get" and "{" in path:
        return "get"
    if http_method == "get":
        return "list"
    if http_method == "post":
        return "create"
    if http_method == "patch":
        return "update"
    if http_method == "put":
        return "replace"
    if http_method == "delete":
        return "delete"
    return http_method


def interactive_config(service: str, name: Optional[str], base_url: Optional[str], args: argparse.Namespace) -> Dict[str, Any]:
    display_name = name or prompt("Service display name", service)
    resolved_base_url = base_url or prompt("Base URL", "http://127.0.0.1:8000")
    config: Dict[str, Any] = {
        "service": service,
        "name": display_name,
        "base_url": resolved_base_url.rstrip("/"),
        "auth": choose_auth_config(args),
        "resources": {},
    }
    while True:
        resource_name = prompt("Resource name (blank to finish)")
        if not resource_name:
            break
        resource = {
            "base_path": prompt("Base path", f"/{resource_name}"),
            "methods": {},
        }
        while True:
            method_name = prompt(f"Method for {resource_name} (blank to finish)")
            if not method_name:
                break
            http_method = prompt("HTTP verb", "GET").upper()
            path = prompt("Method path", "/")
            params_raw = prompt("Params (comma-separated)", "")
            body = prompt("Has JSON body? [y/N]", "n").lower() == "y"
            resource["methods"][method_name] = {
                "http": http_method,
                "path": path,
            }
            if params_raw:
                resource["methods"][method_name]["params"] = [item.strip() for item in params_raw.split(",") if item.strip()]
            if body:
                resource["methods"][method_name]["body"] = True
        config["resources"][resource_name] = resource
    return config


def generate_from_fastapi(url: str, service: Optional[str], name: Optional[str]) -> Dict[str, Any]:
    spec_url = url.rstrip("/") + "/openapi.json"
    text = fetch_text(spec_url)
    return generate_from_openapi(parse_json_or_yaml(text), service, name)


def save_config(config: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate OpsClaw API CLI configs")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--openapi", help="OpenAPI/Swagger file path or URL")
    source.add_argument("--fastapi", help="FastAPI app base URL")
    source.add_argument("--interactive", action="store_true", help="Create config via prompts")
    parser.add_argument("--service", help="Service slug")
    parser.add_argument("--name", help="Display name")
    parser.add_argument("--base-url", help="Base URL override")
    parser.add_argument("--auth-type", choices=["none", "bearer", "api-key", "basic"], help="Auth type")
    parser.add_argument("--env-var", help="Credential env var")
    parser.add_argument("--api-key-header", help="API key header name")
    parser.add_argument("--output", help="Output JSON path")
    return parser


def main(argv: List[str]) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    service = args.service or "service"
    if args.openapi:
        spec = parse_json_or_yaml(fetch_text(args.openapi))
        config = generate_from_openapi(spec, args.service, args.name)
    elif args.fastapi:
        config = generate_from_fastapi(args.fastapi, args.service, args.name)
    else:
        if not args.service:
            raise GeneratorError("--service is required with --interactive")
        config = interactive_config(args.service, args.name, args.base_url, args)

    if args.base_url:
        config["base_url"] = args.base_url.rstrip("/")
    if args.auth_type:
        config["auth"] = choose_auth_config(args)

    output = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR / f"{config['service']}.json"
    save_config(config, output)
    print(json.dumps({"written": str(output), "service": config["service"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except GeneratorError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
