#!/usr/bin/env python3
import argparse
import base64
import csv
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import error, parse, request


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = SCRIPT_DIR.parent / "configs"
USER_AGENT = "opsclaw-api-cli/1.0"


class CLIError(Exception):
    pass


def parse_value(raw: str, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CLIError(f"Invalid JSON for {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise CLIError(f"{label} must decode to a JSON object")
    return value


def parse_flags(argv: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    positionals: List[str] = []
    flags: Dict[str, Any] = {
        "params": {},
        "json_body": None,
        "format": "json",
        "output": None,
        "raw": False,
        "dry_run": False,
        "verbose": False,
        "page_all": False,
        "page_limit": 10,
        "config_dir": str(DEFAULT_CONFIG_DIR),
        "header": [],
    }
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--params":
            i += 1
            flags["params"] = parse_value(argv[i], "--params")
        elif token == "--json":
            i += 1
            flags["json_body"] = parse_value(argv[i], "--json")
        elif token == "--format":
            i += 1
            flags["format"] = argv[i]
        elif token == "--output":
            i += 1
            flags["output"] = argv[i]
        elif token == "--raw":
            flags["raw"] = True
        elif token == "--dry-run":
            flags["dry_run"] = True
        elif token == "--verbose":
            flags["verbose"] = True
        elif token == "--page-all":
            flags["page_all"] = True
        elif token == "--page-limit":
            i += 1
            flags["page_limit"] = int(argv[i])
        elif token == "--config-dir":
            i += 1
            flags["config_dir"] = argv[i]
        elif token == "--header":
            i += 1
            flags["header"].append(argv[i])
        elif token in ("-h", "--help"):
            raise CLIError(usage_text())
        else:
            positionals.append(token)
        i += 1
    return positionals, flags


def usage_text() -> str:
    return "\n".join(
        [
            "Usage:",
            "  python3 api.py <service> <resource> [sub-resource ...] <method> [flags]",
            "  python3 api.py schema <service>",
            "  python3 api.py schema <service.resource.method>",
            "  python3 api.py services",
            "",
            "Flags:",
            "  --params '{...}'      Query and path params as JSON",
            "  --json '{...}'        Request body as JSON",
            "  --format json|table|csv|yaml",
            "  --output PATH         Write formatted output to file",
            "  --raw                 Print raw response body",
            "  --dry-run             Show request without executing it",
            "  --verbose             Show request and response headers",
            "  --page-all            Auto-paginate supported APIs",
            "  --page-limit N        Maximum pages to fetch, default 10",
            "  --config-dir PATH     Override service config directory",
            "  --header 'K: V'       Add a request header",
        ]
    )


def load_service_configs(config_dir: Path) -> Dict[str, Dict[str, Any]]:
    if not config_dir.exists():
        raise CLIError(f"Config directory not found: {config_dir}")
    configs: Dict[str, Dict[str, Any]] = {}
    for path in sorted(config_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CLIError(f"Invalid JSON in {path}: {exc}") from exc
        service = data.get("service")
        if not service:
            raise CLIError(f"Missing 'service' in {path}")
        data["_path"] = str(path)
        configs[service] = data
    return configs


def list_services(configs: Dict[str, Dict[str, Any]]) -> str:
    rows = []
    for service, config in sorted(configs.items()):
        rows.append(
            {
                "service": service,
                "name": config.get("name", ""),
                "base_url": config.get("base_url", ""),
                "auth": config.get("auth", {}).get("type", "none"),
            }
        )
    return format_output(rows, "table")


def flatten_resources(resources: Dict[str, Any], prefix: Optional[List[str]] = None) -> List[Tuple[List[str], Dict[str, Any]]]:
    prefix = prefix or []
    items: List[Tuple[List[str], Dict[str, Any]]] = []
    for name, config in resources.items():
        path = prefix + [name]
        items.append((path, config))
        nested = config.get("resources", {})
        if isinstance(nested, dict) and nested:
            items.extend(flatten_resources(nested, path))
    return items


def resolve_resource_and_method(config: Dict[str, Any], parts: List[str]) -> Tuple[List[str], Dict[str, Any], str, Dict[str, Any]]:
    if len(parts) < 2:
        raise CLIError("Expected at least <resource> <method>")
    resources = config.get("resources", {})
    flattened = flatten_resources(resources)
    for length in range(len(parts) - 1, 0, -1):
        resource_parts = parts[:length]
        method = parts[length]
        for candidate_parts, resource in flattened:
            if candidate_parts == resource_parts or ".".join(candidate_parts) == ".".join(resource_parts):
                methods = resource.get("methods", {})
                if method in methods:
                    return candidate_parts, resource, method, methods[method]
    raise CLIError(f"Could not resolve resource/method from: {' '.join(parts)}")


def schema_for_service(config: Dict[str, Any]) -> str:
    lines = [
        f"service: {config.get('service')}",
        f"name: {config.get('name', '')}",
        f"base_url: {config.get('base_url', '')}",
        f"auth: {config.get('auth', {}).get('type', 'none')}",
        "",
    ]
    for parts, resource in flatten_resources(config.get("resources", {})):
        resource_name = ".".join(parts)
        lines.append(f"{resource_name}:")
        methods = resource.get("methods", {})
        for method_name, method_config in sorted(methods.items()):
            http_method = method_config.get("http", "GET")
            path = build_method_path(resource, method_config)
            lines.append(f"  - {method_name}: {http_method} {path}")
    return "\n".join(lines)


def schema_for_method(config: Dict[str, Any], selector: str) -> str:
    parts = selector.split(".")
    if len(parts) < 3:
        raise CLIError("Method schema selector must be service.resource.method")
    service = parts[0]
    if service != config.get("service"):
        raise CLIError(f"Service '{service}' not found in selector")
    resource_path, resource, method_name, method_config = resolve_resource_and_method(config, parts[1:])
    payload = {
        "service": service,
        "resource": ".".join(resource_path),
        "method": method_name,
        "http": method_config.get("http", "GET"),
        "path": build_method_path(resource, method_config),
        "params": method_config.get("params", []),
        "body": method_config.get("body", False),
        "description": method_config.get("description", ""),
        "pagination": method_config.get("pagination", config.get("pagination")),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def build_method_path(resource: Dict[str, Any], method: Dict[str, Any]) -> str:
    return f"{resource.get('base_path', '')}{method.get('path', '')}"


def normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return path


def extract_path_params(path_template: str, params: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    remaining = dict(params)
    path = path_template
    for segment in list(params.keys()):
        placeholder = "{" + segment + "}"
        if placeholder in path:
            value = str(remaining.pop(segment))
            path = path.replace(placeholder, parse.quote(value, safe=""))
    if "{" in path and "}" in path:
        raise CLIError(f"Missing path parameters for {path}")
    return path, remaining


def build_auth_headers(auth_config: Dict[str, Any]) -> Dict[str, str]:
    auth_type = auth_config.get("type", "none")
    if auth_type == "none":
        return {}
    env_var = auth_config.get("env_var")
    if not env_var:
        raise CLIError("Auth config missing env_var")
    secret = os.environ.get(env_var)
    if not secret:
        raise CLIError(f"Set {env_var} before calling this service")
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {secret}"}
    if auth_type == "api-key":
        header_name = auth_config.get("header", "X-API-Key")
        return {header_name: secret}
    if auth_type == "basic":
        encoded = base64.b64encode(secret.encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
    raise CLIError(f"Unsupported auth type: {auth_type}")


def parse_extra_headers(header_pairs: Iterable[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for pair in header_pairs:
        if ":" not in pair:
            raise CLIError(f"Invalid header format: {pair}")
        key, value = pair.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def build_request_parts(
    service_config: Dict[str, Any],
    resource: Dict[str, Any],
    method_config: Dict[str, Any],
    params: Dict[str, Any],
    body: Optional[Dict[str, Any]],
    extra_headers: Dict[str, str],
) -> Tuple[str, str, Dict[str, str], Optional[bytes], Dict[str, Any]]:
    base_url = service_config.get("base_url", "").rstrip("/")
    full_path = normalize_path(build_method_path(resource, method_config))
    path, query_params = extract_path_params(full_path, params)
    if query_params:
        path = f"{path}?{parse.urlencode(flatten_query(query_params), doseq=True)}"
    url = f"{base_url}{path}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    headers.update(build_auth_headers(service_config.get("auth", {})))
    headers.update(extra_headers)
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    return method_config.get("http", "GET").upper(), url, headers, data, query_params


def flatten_query(params: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for key, value in params.items():
        if isinstance(value, list):
            for item in value:
                pairs.append((key, str(item)))
        elif value is None:
            continue
        else:
            pairs.append((key, str(value)))
    return pairs


def execute_request(http_method: str, url: str, headers: Dict[str, str], data: Optional[bytes], verbose: bool) -> Tuple[int, Dict[str, str], bytes]:
    req = request.Request(url=url, data=data, headers=headers, method=http_method)
    if verbose:
        print_request(http_method, url, headers, data)
    try:
        with request.urlopen(req) as response:
            status = response.status
            response_headers = dict(response.headers.items())
            body = response.read()
    except error.HTTPError as exc:
        body = exc.read()
        response_headers = dict(exc.headers.items())
        status = exc.code
    except error.URLError as exc:
        raise CLIError(f"Request failed: {exc}") from exc
    if verbose:
        print_response(status, response_headers, body)
    return status, response_headers, body


def print_request(http_method: str, url: str, headers: Dict[str, str], data: Optional[bytes]) -> None:
    print(f"> {http_method} {url}", file=sys.stderr)
    for key, value in headers.items():
        print(f"> {key}: {value}", file=sys.stderr)
    if data:
        print(f">", file=sys.stderr)
        print(data.decode("utf-8"), file=sys.stderr)


def print_response(status: int, headers: Dict[str, str], body: bytes) -> None:
    print(f"< HTTP {status}", file=sys.stderr)
    for key, value in headers.items():
        print(f"< {key}: {value}", file=sys.stderr)
    if body:
        print("<", file=sys.stderr)
        preview = body.decode("utf-8", errors="replace")
        print(preview, file=sys.stderr)


def decode_response_body(body: bytes) -> Any:
    if not body:
        return None
    text = body.decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def paginate_if_needed(
    service_config: Dict[str, Any],
    resource: Dict[str, Any],
    method_config: Dict[str, Any],
    flags: Dict[str, Any],
    base_params: Dict[str, Any],
    body: Optional[Dict[str, Any]],
    extra_headers: Dict[str, str],
) -> Tuple[int, Dict[str, str], Any]:
    http_method = method_config.get("http", "GET").upper()
    if not flags["page_all"] or http_method != "GET":
        method, url, headers, data, _ = build_request_parts(service_config, resource, method_config, base_params, body, extra_headers)
        status, response_headers, raw_body = execute_request(method, url, headers, data, flags["verbose"])
        return status, response_headers, decode_response_body(raw_body)

    pagination = method_config.get("pagination") or service_config.get("pagination") or {}
    page_limit = max(flags["page_limit"], 1)
    current_params = dict(base_params)
    pages: List[Any] = []
    final_headers: Dict[str, str] = {}
    last_status = 200
    for _ in range(page_limit):
        method, url, headers, data, _ = build_request_parts(service_config, resource, method_config, current_params, body, extra_headers)
        status, response_headers, raw_body = execute_request(method, url, headers, data, flags["verbose"])
        payload = decode_response_body(raw_body)
        last_status = status
        final_headers = response_headers
        pages.append(payload)
        next_params, done = next_page_params(pagination, payload, response_headers, current_params)
        if done:
            break
        current_params = next_params
    merged = merge_pages(pages, pagination)
    return last_status, final_headers, merged


def merge_pages(pages: List[Any], pagination: Dict[str, Any]) -> Any:
    if not pages:
        return []
    results_field = pagination.get("results_field", "data")
    merged_items: List[Any] = []
    for page in pages:
        if isinstance(page, dict) and isinstance(page.get(results_field), list):
            merged_items.extend(page[results_field])
        elif isinstance(page, list):
            merged_items.extend(page)
        else:
            merged_items.append(page)
    if isinstance(pages[0], dict):
        merged = dict(pages[-1])
        merged[results_field] = merged_items
        merged["_pages_fetched"] = len(pages)
        return merged
    return merged_items


def next_page_params(
    pagination: Dict[str, Any],
    payload: Any,
    headers: Dict[str, str],
    current_params: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool]:
    kind = pagination.get("type")
    if kind == "cursor":
        cursor_field = pagination.get("cursor_field", "next_cursor")
        param_name = pagination.get("cursor_param", "cursor")
        next_cursor = deep_get(payload, cursor_field)
        if not next_cursor:
            return current_params, True
        next_params = dict(current_params)
        next_params[param_name] = next_cursor
        return next_params, False
    if kind == "offset":
        offset_param = pagination.get("offset_param", "offset")
        limit_param = pagination.get("limit_param", "limit")
        step = int(current_params.get(limit_param) or pagination.get("page_size") or 100)
        next_offset = deep_get(payload, pagination.get("next_offset_field", "next_offset"))
        if next_offset is None:
            items = extract_results(payload, pagination)
            if not items:
                return current_params, True
            next_offset = int(current_params.get(offset_param, 0)) + step
        has_more = deep_get(payload, pagination.get("has_more_field", "has_more"))
        if has_more is False:
            return current_params, True
        next_params = dict(current_params)
        next_params[offset_param] = next_offset
        return next_params, False
    if kind == "link":
        next_link = parse_link_header(headers.get("Link", ""))
        if not next_link:
            next_link = deep_get(payload, pagination.get("next_link_field", "next"))
        if not next_link:
            return current_params, True
        parsed = parse.urlparse(next_link)
        next_params = dict(parse.parse_qsl(parsed.query))
        return next_params, False

    inferred = infer_next_page(payload, current_params, headers)
    return inferred


def infer_next_page(payload: Any, current_params: Dict[str, Any], headers: Dict[str, str]) -> Tuple[Dict[str, Any], bool]:
    next_link = parse_link_header(headers.get("Link", ""))
    if next_link:
        parsed = parse.urlparse(next_link)
        return dict(parse.parse_qsl(parsed.query)), False
    if isinstance(payload, dict):
        if payload.get("next_page"):
            next_params = dict(current_params)
            next_params["page"] = payload["next_page"]
            return next_params, False
        if payload.get("next_cursor"):
            next_params = dict(current_params)
            next_params["cursor"] = payload["next_cursor"]
            return next_params, False
        if payload.get("next_offset") is not None:
            next_params = dict(current_params)
            next_params["offset"] = payload["next_offset"]
            return next_params, False
        if payload.get("has_more") is False:
            return current_params, True
    return current_params, True


def parse_link_header(value: str) -> Optional[str]:
    for chunk in value.split(","):
        text = chunk.strip()
        if 'rel="next"' in text and text.startswith("<") and ">" in text:
            return text[1:text.index(">")]
    return None


def deep_get(payload: Any, dotted_key: str) -> Any:
    value = payload
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def extract_results(payload: Any, pagination: Dict[str, Any]) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    results_field = pagination.get("results_field", "data")
    results = payload.get(results_field, [])
    return results if isinstance(results, list) else []


def format_output(payload: Any, output_format: str) -> str:
    if output_format == "json":
        return json.dumps(payload, indent=2, sort_keys=True)
    if output_format == "yaml":
        return to_yaml(payload).rstrip()
    rows = rows_from_payload(payload)
    if output_format == "table":
        return render_table(rows)
    if output_format == "csv":
        return render_csv(rows)
    raise CLIError(f"Unsupported format: {output_format}")


def rows_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [flatten_row(item) if isinstance(item, dict) else {"value": item} for item in payload]
    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            if isinstance(payload.get(key), list):
                return [flatten_row(item) if isinstance(item, dict) else {"value": item} for item in payload[key]]
        return [flatten_row(payload)]
    return [{"value": payload}]


def flatten_row(data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for key, value in data.items():
        column = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            row.update(flatten_row(value, column))
        elif isinstance(value, list):
            row[column] = json.dumps(value, separators=(",", ":"))
        else:
            row[column] = value
    return row


def render_table(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "(no rows)"
    headers = sorted({key for row in rows for key in row.keys()})
    widths = {header: max(len(header), *(len(str(row.get(header, ""))) for row in rows)) for header in headers}
    lines = [
        " | ".join(header.ljust(widths[header]) for header in headers),
        "-+-".join("-" * widths[header] for header in headers),
    ]
    for row in rows:
        lines.append(" | ".join(str(row.get(header, "")).ljust(widths[header]) for header in headers))
    return "\n".join(lines)


def render_csv(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    headers = sorted({key for row in rows for key in row.keys()})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow({header: row.get(header, "") for header in headers})
    return buffer.getvalue().rstrip()


def to_yaml(payload: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(payload, dict):
        lines = []
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(to_yaml(value, indent + 1))
            else:
                lines.append(f"{pad}{key}: {yaml_scalar(value)}")
        return "\n".join(lines)
    if isinstance(payload, list):
        lines = []
        for item in payload:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(to_yaml(item, indent + 1))
            else:
                lines.append(f"{pad}- {yaml_scalar(item)}")
        return "\n".join(lines)
    return f"{pad}{yaml_scalar(payload)}"


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in [":", "#", "\n", '"', "'"]):
        return json.dumps(text)
    return text


def write_output(text: str, output_path: Optional[str]) -> None:
    if output_path:
        Path(output_path).write_text(text + ("\n" if not text.endswith("\n") else ""))
        return
    print(text)


def main(argv: List[str]) -> int:
    try:
        positionals, flags = parse_flags(argv)
        config_dir = Path(flags["config_dir"]).expanduser().resolve()
        configs = load_service_configs(config_dir)
        if not positionals:
            raise CLIError(usage_text())

        command = positionals[0]
        if command == "services":
            write_output(list_services(configs), flags["output"])
            return 0

        if command == "schema":
            if len(positionals) < 2:
                raise CLIError("Usage: python3 api.py schema <service>|<service.resource.method>")
            selector = positionals[1]
            service_name = selector.split(".", 1)[0]
            if service_name not in configs:
                raise CLIError(f"Unknown service: {service_name}")
            config = configs[service_name]
            if "." in selector:
                write_output(schema_for_method(config, selector), flags["output"])
            else:
                write_output(schema_for_service(config), flags["output"])
            return 0

        service_name = command
        if service_name not in configs:
            raise CLIError(f"Unknown service: {service_name}")
        config = configs[service_name]
        resource_path, resource, method_name, method_config = resolve_resource_and_method(config, positionals[1:])
        extra_headers = parse_extra_headers(flags["header"])
        http_method, url, headers, data, _ = build_request_parts(
            config,
            resource,
            method_config,
            flags["params"],
            flags["json_body"],
            extra_headers,
        )
        if flags["dry_run"]:
            preview = {
                "service": service_name,
                "resource": ".".join(resource_path),
                "method": method_name,
                "http": http_method,
                "url": url,
                "headers": headers,
                "body": flags["json_body"],
            }
            write_output(json.dumps(preview, indent=2, sort_keys=True), flags["output"])
            return 0

        status, response_headers, payload = paginate_if_needed(
            config,
            resource,
            method_config,
            flags,
            flags["params"],
            flags["json_body"],
            extra_headers,
        )
        if status >= 400:
            raise CLIError(format_output({"status": status, "headers": response_headers, "error": payload}, "json"))

        if flags["raw"]:
            text = payload if isinstance(payload, str) else json.dumps(payload)
        else:
            text = format_output(payload, flags["format"])
        write_output(text, flags["output"])
        return 0
    except CLIError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (IndexError, ValueError) as exc:
        print(f"Argument error: {exc}", file=sys.stderr)
        print(usage_text(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
