#!/usr/bin/env python3
"""Notion API wrapper for OpsClaw task tracking."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]


def load_module(module_name: str, relative_path: str) -> Any:
    """Load a repo-local module from a file path."""
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LOGGER_MODULE = load_module("opsclaw_shared_logger", "scripts/logger.py")
LOG = LOGGER_MODULE.get_logger("opsclaw.tasks.notion")


class NotionError(RuntimeError):
    """Base Notion client error."""


class RateLimitError(NotionError):
    """Raised when Notion rate limits the request."""


@dataclass(frozen=True)
class RetryConfig:
    """Retry settings for transient Notion failures."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 20.0
    jitter: float = 0.5


@dataclass(frozen=True)
class NotionSettings:
    """Resolved Notion settings."""

    base_url: str
    token: str
    version: str
    database_id: str | None
    properties: dict[str, str]
    done_statuses: list[str]
    blocked_statuses: list[str]
    retry: RetryConfig


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_settings(config_path: Path) -> NotionSettings:
    """Load Notion settings from the tracker config."""
    config = load_json(config_path)
    notion_doc = config.get("notion", {})
    retry_doc = config.get("retry", {})
    token_env = str(notion_doc.get("tokenEnv") or "NOTION_API_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise NotionError(f"Missing Notion API token. Export {token_env}.")
    return NotionSettings(
        base_url=str(notion_doc.get("baseUrl") or "https://api.notion.com/v1").rstrip("/"),
        token=token,
        version=str(notion_doc.get("version") or "2022-06-28"),
        database_id=str(notion_doc.get("databaseId") or "") or None,
        properties={str(key): str(value) for key, value in (notion_doc.get("properties") or {}).items()},
        done_statuses=[str(item) for item in notion_doc.get("doneStatuses", ["Done"])],
        blocked_statuses=[str(item) for item in notion_doc.get("blockedStatuses", ["Blocked"])],
        retry=RetryConfig(
            max_retries=int(retry_doc.get("maxRetries", 3)),
            base_delay=float(retry_doc.get("baseDelaySeconds", 1.0)),
            max_delay=float(retry_doc.get("maxDelaySeconds", 20.0)),
            jitter=float(retry_doc.get("jitterSeconds", 0.5)),
        ),
    )


def notion_request(
    settings: NotionSettings,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> Any:
    """Execute a Notion API request with bounded retries."""
    url = settings.base_url + path
    if query:
        filtered = {key: value for key, value in query.items() if value is not None}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered, doseq=True)
    body = None
    headers = {
        "Authorization": f"Bearer {settings.token}",
        "Notion-Version": settings.version,
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    for attempt in range(settings.retry.max_retries + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429:
                if attempt >= settings.retry.max_retries:
                    raise RateLimitError(f"Notion API returned 429: {raw_error}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "notion rate limited, retrying",
                    extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2)}},
                )
                time.sleep(delay)
                continue
            if 500 <= exc.code < 600:
                if attempt >= settings.retry.max_retries:
                    raise NotionError(f"Notion API failed after retries: {raw_error}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "notion transient server error, retrying",
                    extra={"event": {"attempt": attempt + 1, "status": exc.code, "delaySeconds": round(delay, 2)}},
                )
                time.sleep(delay)
                continue
            raise NotionError(f"Notion API returned {exc.code}: {raw_error}") from exc
        except urllib.error.URLError as exc:
            if attempt >= settings.retry.max_retries:
                raise NotionError(f"Notion network error: {exc.reason}") from exc
            delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
            delay += random.uniform(0, settings.retry.jitter)
            LOG.warning(
                "notion network error, retrying",
                extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "error": str(exc.reason)}},
            )
            time.sleep(delay)
    raise NotionError("Notion retry loop exhausted unexpectedly.")


def normalize_rich_text(items: list[dict[str, Any]]) -> str:
    """Collapse a Notion rich text array into one string."""
    return "".join(item.get("plain_text", "") for item in items)


def normalize_property(prop: dict[str, Any]) -> Any:
    """Normalize one Notion property value."""
    kind = prop.get("type")
    if kind == "title":
        return normalize_rich_text(prop.get("title", []))
    if kind == "rich_text":
        return normalize_rich_text(prop.get("rich_text", []))
    if kind == "date":
        return (prop.get("date") or {}).get("start")
    if kind == "select":
        return ((prop.get("select") or {}).get("name"))
    if kind == "status":
        return ((prop.get("status") or {}).get("name"))
    if kind == "multi_select":
        return [item.get("name") for item in prop.get("multi_select", []) if item.get("name")]
    if kind == "people":
        return [{"id": person.get("id"), "name": (person.get("name") or "")} for person in prop.get("people", [])]
    if kind == "relation":
        return [item.get("id") for item in prop.get("relation", []) if item.get("id")]
    if kind == "checkbox":
        return bool(prop.get("checkbox"))
    if kind == "number":
        return prop.get("number")
    return prop.get(kind)


def normalize_page(page: dict[str, Any], settings: NotionSettings) -> dict[str, Any]:
    """Normalize a Notion page into the task-tracking shape."""
    properties = page.get("properties", {})
    normalized: dict[str, Any] = {
        "id": page.get("id"),
        "url": page.get("url"),
        "archived": bool(page.get("archived")),
        "createdTime": page.get("created_time"),
        "lastEditedTime": page.get("last_edited_time"),
        "properties": {name: normalize_property(value) for name, value in properties.items()},
    }
    title_name = settings.properties.get("title", "Name")
    status_name = settings.properties.get("status", "Status")
    due_name = settings.properties.get("dueDate", "Due")
    priority_name = settings.properties.get("priority", "Priority")
    assignee_name = settings.properties.get("assignee", "Assignee")
    project_name = settings.properties.get("project", "Project")
    labels_name = settings.properties.get("labels", "Tags")
    block_reason_name = settings.properties.get("blockReason", "Block Reason")
    normalized.update(
        {
            "title": normalized["properties"].get(title_name),
            "status": normalized["properties"].get(status_name),
            "dueDate": normalized["properties"].get(due_name),
            "priority": normalized["properties"].get(priority_name),
            "assignee": normalized["properties"].get(assignee_name),
            "project": normalized["properties"].get(project_name),
            "labels": normalized["properties"].get(labels_name),
            "blockReason": normalized["properties"].get(block_reason_name),
        }
    )
    return normalized


def build_property_value(schema_prop: dict[str, Any], value: Any) -> dict[str, Any]:
    """Build a Notion property payload that matches the database schema."""
    prop_type = schema_prop.get("type")
    if value is None:
        raise NotionError(f"Cannot build a Notion property payload for missing value and type '{prop_type}'.")
    if prop_type == "title":
        return {"title": [{"text": {"content": str(value)}}]}
    if prop_type == "rich_text":
        return {"rich_text": [{"text": {"content": str(value)}}]}
    if prop_type == "date":
        return {"date": {"start": str(value)}}
    if prop_type == "select":
        return {"select": {"name": str(value)}}
    if prop_type == "status":
        return {"status": {"name": str(value)}}
    if prop_type == "multi_select":
        items = value if isinstance(value, list) else [item.strip() for item in str(value).split(",") if item.strip()]
        return {"multi_select": [{"name": str(item)} for item in items]}
    if prop_type == "people":
        items = value if isinstance(value, list) else [item.strip() for item in str(value).split(",") if item.strip()]
        return {"people": [{"id": str(item)} for item in items]}
    if prop_type == "relation":
        items = value if isinstance(value, list) else [item.strip() for item in str(value).split(",") if item.strip()]
        return {"relation": [{"id": str(item)} for item in items]}
    if prop_type == "checkbox":
        return {"checkbox": bool(value)}
    if prop_type == "number":
        return {"number": float(value)}
    raise NotionError(f"Unsupported Notion property type '{prop_type}'.")


class NotionClient:
    """Thin Notion wrapper with normalized JSON output."""

    def __init__(self, settings: NotionSettings) -> None:
        self.settings = settings

    def get_database(self, database_id: str | None = None) -> dict[str, Any]:
        """Retrieve one database."""
        db_id = database_id or self.settings.database_id
        if not db_id:
            raise NotionError("Missing databaseId. Set notion.databaseId in the config or provide an override.")
        return notion_request(self.settings, "GET", f"/databases/{db_id}")

    def list_databases(self, *, query_text: str | None, limit: int) -> list[dict[str, Any]]:
        """Search for databases available to the integration."""
        payload: dict[str, Any] = {
            "page_size": limit,
            "filter": {"value": "database", "property": "object"},
        }
        if query_text:
            payload["query"] = query_text
        response = notion_request(self.settings, "POST", "/search", payload=payload)
        results = []
        for item in response.get("results", []):
            title = normalize_rich_text(item.get("title", []))
            results.append(
                {
                    "id": item.get("id"),
                    "title": title,
                    "url": item.get("url"),
                    "createdTime": item.get("created_time"),
                    "lastEditedTime": item.get("last_edited_time"),
                }
            )
        return results

    def query_database(
        self,
        *,
        database_id: str | None,
        limit: int,
        query_text: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query a task database with optional title and status filters."""
        db_id = database_id or self.settings.database_id
        if not db_id:
            raise NotionError("Missing databaseId. Set notion.databaseId in the config or provide an override.")
        title_name = self.settings.properties.get("title", "Name")
        status_name = self.settings.properties.get("status", "Status")
        filters: list[dict[str, Any]] = []
        if query_text:
            filters.append({"property": title_name, "title": {"contains": query_text}})
        if status:
            filters.append({"property": status_name, "status": {"equals": status}})
        payload: dict[str, Any] = {"page_size": limit}
        if filters:
            payload["filter"] = filters[0] if len(filters) == 1 else {"and": filters}
        response = notion_request(self.settings, "POST", f"/databases/{db_id}/query", payload=payload)
        return [normalize_page(item, self.settings) for item in response.get("results", [])]

    def get_page(self, page_id: str) -> dict[str, Any]:
        """Retrieve one page."""
        return normalize_page(notion_request(self.settings, "GET", f"/pages/{page_id}"), self.settings)

    def build_task_properties(
        self,
        *,
        schema: dict[str, Any],
        title: str,
        status: str | None,
        due_date: str | None,
        priority: str | None,
        assignee: str | None,
        project: str | None,
        labels: list[str] | None,
        block_reason: str | None,
    ) -> dict[str, Any]:
        """Build task properties using the configured property mapping and live schema."""
        property_names = self.settings.properties
        values = {
            property_names.get("title", "Name"): title,
            property_names.get("status", "Status"): status,
            property_names.get("dueDate", "Due"): due_date,
            property_names.get("priority", "Priority"): priority,
            property_names.get("assignee", "Assignee"): assignee,
            property_names.get("project", "Project"): project,
            property_names.get("labels", "Tags"): labels,
            property_names.get("blockReason", "Block Reason"): block_reason,
        }
        properties: dict[str, Any] = {}
        schema_properties = schema.get("properties", {})
        for property_name, value in values.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, list) and not value:
                continue
            schema_prop = schema_properties.get(property_name)
            if schema_prop is None:
                raise NotionError(f"Property '{property_name}' was not found in the configured Notion database.")
            properties[property_name] = build_property_value(schema_prop, value)
        return properties

    def create_task(
        self,
        *,
        database_id: str | None,
        title: str,
        status: str | None,
        due_date: str | None,
        priority: str | None,
        assignee: str | None,
        project: str | None,
        labels: list[str] | None,
        block_reason: str | None,
    ) -> dict[str, Any]:
        """Create a task page inside the configured database."""
        schema = self.get_database(database_id)
        db_id = database_id or self.settings.database_id
        payload = {
            "parent": {"database_id": db_id},
            "properties": self.build_task_properties(
                schema=schema,
                title=title,
                status=status,
                due_date=due_date,
                priority=priority,
                assignee=assignee,
                project=project,
                labels=labels,
                block_reason=block_reason,
            ),
        }
        page = notion_request(self.settings, "POST", "/pages", payload=payload)
        return normalize_page(page, self.settings)

    def update_task(
        self,
        *,
        page_id: str,
        title: str | None,
        status: str | None,
        due_date: str | None,
        priority: str | None,
        assignee: str | None,
        project: str | None,
        labels: list[str] | None,
        block_reason: str | None,
        archived: bool | None,
    ) -> dict[str, Any]:
        """Update a task page."""
        current = notion_request(self.settings, "GET", f"/pages/{page_id}")
        parent = current.get("parent") or {}
        database_id = parent.get("database_id") or self.settings.database_id
        if not database_id:
            raise NotionError("Could not determine the parent database for this page.")
        schema = self.get_database(database_id)
        title_key = self.settings.properties.get("title", "Name")
        current_title = normalize_property((current.get("properties") or {}).get(title_key, {"type": "title", "title": []}))
        properties = self.build_task_properties(
            schema=schema,
            title=title or current_title or "",
            status=status,
            due_date=due_date,
            priority=priority,
            assignee=assignee,
            project=project,
            labels=labels,
            block_reason=block_reason,
        )
        payload: dict[str, Any] = {}
        if properties:
            payload["properties"] = properties
        if archived is not None:
            payload["archived"] = archived
        if not payload:
            raise NotionError("No update fields provided.")
        page = notion_request(self.settings, "PATCH", f"/pages/{page_id}", payload=payload)
        return normalize_page(page, self.settings)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Notion API wrapper for OpsClaw task tracking.")
    parser.add_argument("--config", required=True, help="Path to tracker-config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_databases = subparsers.add_parser("list-databases", help="Search accessible databases.")
    list_databases.add_argument("--query")
    list_databases.add_argument("--limit", type=int, default=25)

    query_database = subparsers.add_parser("query-database", help="Query task pages from the configured database.")
    query_database.add_argument("--database-id")
    query_database.add_argument("--query")
    query_database.add_argument("--status")
    query_database.add_argument("--limit", type=int, default=25)

    get_page = subparsers.add_parser("get-page", help="Retrieve a page by ID.")
    get_page.add_argument("--page-id", required=True)

    create_task = subparsers.add_parser("create-task", help="Create a task page.")
    create_task.add_argument("--database-id")
    create_task.add_argument("--title", required=True)
    create_task.add_argument("--status")
    create_task.add_argument("--due-date")
    create_task.add_argument("--priority")
    create_task.add_argument("--assignee")
    create_task.add_argument("--project")
    create_task.add_argument("--label", action="append", default=[])
    create_task.add_argument("--block-reason")

    update_task = subparsers.add_parser("update-task", help="Update a task page.")
    update_task.add_argument("--page-id", required=True)
    update_task.add_argument("--title")
    update_task.add_argument("--status")
    update_task.add_argument("--due-date")
    update_task.add_argument("--priority")
    update_task.add_argument("--assignee")
    update_task.add_argument("--project")
    update_task.add_argument("--label", action="append")
    update_task.add_argument("--block-reason")
    update_task.add_argument("--archived", action="store_true")
    update_task.add_argument("--unarchive", action="store_true")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings(Path(args.config))
    client = NotionClient(settings)

    if args.command == "list-databases":
        result = client.list_databases(query_text=args.query, limit=args.limit)
    elif args.command == "query-database":
        result = client.query_database(
            database_id=args.database_id,
            limit=args.limit,
            query_text=args.query,
            status=args.status,
        )
    elif args.command == "get-page":
        result = client.get_page(args.page_id)
    elif args.command == "create-task":
        result = client.create_task(
            database_id=args.database_id,
            title=args.title,
            status=args.status,
            due_date=args.due_date,
            priority=args.priority,
            assignee=args.assignee,
            project=args.project,
            labels=list(args.label),
            block_reason=args.block_reason,
        )
    elif args.command == "update-task":
        archived: bool | None = None
        if args.archived and args.unarchive:
            parser.error("Use only one of --archived or --unarchive.")
        if args.archived:
            archived = True
        elif args.unarchive:
            archived = False
        result = client.update_task(
            page_id=args.page_id,
            title=args.title,
            status=args.status,
            due_date=args.due_date,
            priority=args.priority,
            assignee=args.assignee,
            project=args.project,
            labels=args.label,
            block_reason=args.block_reason,
            archived=archived,
        )
    else:
        parser.error(f"Unsupported command {args.command}")
        return 2

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NotionError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc
