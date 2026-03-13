#!/usr/bin/env python3
"""Asana API wrapper for OpsClaw task tracking."""

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
LOG = LOGGER_MODULE.get_logger("opsclaw.tasks.asana")


class AsanaError(RuntimeError):
    """Base Asana client error."""


class RateLimitError(AsanaError):
    """Raised when Asana rate limits the request."""


@dataclass(frozen=True)
class RetryConfig:
    """Retry settings for transient Asana failures."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 20.0
    jitter: float = 0.5


@dataclass(frozen=True)
class AsanaSettings:
    """Resolved Asana settings."""

    base_url: str
    token: str
    workspace_gid: str | None
    project_gid: str | None
    default_section_gid: str | None
    blocked_section_gid: str | None
    done_section_gid: str | None
    retry: RetryConfig


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_settings(config_path: Path) -> AsanaSettings:
    """Load Asana settings from the tracker config."""
    config = load_json(config_path)
    asana_doc = config.get("asana", {})
    retry_doc = config.get("retry", {})
    token_env = str(asana_doc.get("tokenEnv") or "ASANA_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise AsanaError(f"Missing Asana access token. Export {token_env}.")
    return AsanaSettings(
        base_url=str(asana_doc.get("baseUrl") or "https://app.asana.com/api/1.0").rstrip("/"),
        token=token,
        workspace_gid=str(asana_doc.get("workspaceGid") or "") or None,
        project_gid=str(asana_doc.get("projectGid") or "") or None,
        default_section_gid=str(asana_doc.get("defaultSectionGid") or "") or None,
        blocked_section_gid=str(asana_doc.get("blockedSectionGid") or "") or None,
        done_section_gid=str(asana_doc.get("doneSectionGid") or "") or None,
        retry=RetryConfig(
            max_retries=int(retry_doc.get("maxRetries", 3)),
            base_delay=float(retry_doc.get("baseDelaySeconds", 1.0)),
            max_delay=float(retry_doc.get("maxDelaySeconds", 20.0)),
            jitter=float(retry_doc.get("jitterSeconds", 0.5)),
        ),
    )


def asana_request(
    settings: AsanaSettings,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> Any:
    """Execute an Asana API request with bounded retries."""
    url = settings.base_url + path
    if query:
        filtered = {key: value for key, value in query.items() if value is not None}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered, doseq=True)
    body = None
    headers = {
        "Authorization": f"Bearer {settings.token}",
        "Accept": "application/json",
    }
    if payload is not None:
        body = json.dumps({"data": payload}).encode("utf-8")
        headers["Content-Type"] = "application/json"
    for attempt in range(settings.retry.max_retries + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                doc = json.loads(raw) if raw else {}
                return doc.get("data", doc)
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429:
                if attempt >= settings.retry.max_retries:
                    raise RateLimitError(f"Asana API returned 429: {raw_error}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "asana rate limited, retrying",
                    extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2)}},
                )
                time.sleep(delay)
                continue
            if 500 <= exc.code < 600:
                if attempt >= settings.retry.max_retries:
                    raise AsanaError(f"Asana API failed after retries: {raw_error}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "asana transient server error, retrying",
                    extra={"event": {"attempt": attempt + 1, "status": exc.code, "delaySeconds": round(delay, 2)}},
                )
                time.sleep(delay)
                continue
            raise AsanaError(f"Asana API returned {exc.code}: {raw_error}") from exc
        except urllib.error.URLError as exc:
            if attempt >= settings.retry.max_retries:
                raise AsanaError(f"Asana network error: {exc.reason}") from exc
            delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
            delay += random.uniform(0, settings.retry.jitter)
            LOG.warning(
                "asana network error, retrying",
                extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "error": str(exc.reason)}},
            )
            time.sleep(delay)
    raise AsanaError("Asana retry loop exhausted unexpectedly.")


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    """Normalize an Asana task resource."""
    assignee = task.get("assignee") or {}
    memberships = task.get("memberships") or []
    first_membership = memberships[0] if memberships else {}
    section = first_membership.get("section") or {}
    project = first_membership.get("project") or {}
    return {
        "gid": task.get("gid"),
        "title": task.get("name"),
        "notes": task.get("notes"),
        "completed": bool(task.get("completed")),
        "dueDate": task.get("due_on"),
        "dueAt": task.get("due_at"),
        "assignee": assignee.get("name"),
        "assigneeGid": assignee.get("gid"),
        "project": project.get("name"),
        "projectGid": project.get("gid"),
        "section": section.get("name"),
        "sectionGid": section.get("gid"),
        "permalinkUrl": task.get("permalink_url"),
        "createdAt": task.get("created_at"),
        "modifiedAt": task.get("modified_at"),
    }


def normalize_project(project: dict[str, Any]) -> dict[str, Any]:
    """Normalize an Asana project resource."""
    return {
        "gid": project.get("gid"),
        "name": project.get("name"),
        "archived": bool(project.get("archived")),
        "permalinkUrl": project.get("permalink_url"),
    }


def normalize_section(section: dict[str, Any]) -> dict[str, Any]:
    """Normalize an Asana section resource."""
    return {
        "gid": section.get("gid"),
        "name": section.get("name"),
        "createdAt": section.get("created_at"),
    }


def normalize_user(user: dict[str, Any]) -> dict[str, Any]:
    """Normalize an Asana user resource."""
    return {
        "gid": user.get("gid"),
        "name": user.get("name"),
        "email": user.get("email"),
    }


class AsanaClient:
    """Thin Asana wrapper with normalized JSON output."""

    TASK_FIELDS = ",".join(
        [
            "gid",
            "name",
            "notes",
            "completed",
            "due_on",
            "due_at",
            "created_at",
            "modified_at",
            "permalink_url",
            "assignee.gid",
            "assignee.name",
            "memberships.project.gid",
            "memberships.project.name",
            "memberships.section.gid",
            "memberships.section.name",
        ]
    )

    def __init__(self, settings: AsanaSettings) -> None:
        self.settings = settings

    def list_tasks(self, *, project_gid: str | None, limit: int) -> list[dict[str, Any]]:
        """List tasks for a project."""
        target_project = project_gid or self.settings.project_gid
        if not target_project:
            raise AsanaError("Missing projectGid. Set asana.projectGid in the config or provide --project-gid.")
        response = asana_request(
            self.settings,
            "GET",
            f"/projects/{target_project}/tasks",
            query={"limit": limit, "opt_fields": self.TASK_FIELDS},
        )
        return [normalize_task(item) for item in response]

    def search_tasks(self, *, text: str, project_gid: str | None, limit: int) -> list[dict[str, Any]]:
        """Search tasks inside a workspace."""
        workspace_gid = self.settings.workspace_gid
        if not workspace_gid:
            raise AsanaError("Missing workspaceGid. Set asana.workspaceGid in the config before using search.")
        query: dict[str, Any] = {"text": text, "limit": limit, "opt_fields": self.TASK_FIELDS}
        if project_gid or self.settings.project_gid:
            query["projects.any"] = project_gid or self.settings.project_gid
        response = asana_request(self.settings, "GET", f"/workspaces/{workspace_gid}/tasks/search", query=query)
        return [normalize_task(item) for item in response]

    def create_task(
        self,
        *,
        title: str,
        notes: str | None,
        due_date: str | None,
        assignee_gid: str | None,
        project_gid: str | None,
        section_gid: str | None,
        completed: bool | None,
    ) -> dict[str, Any]:
        """Create a task."""
        workspace_gid = self.settings.workspace_gid
        target_project = project_gid or self.settings.project_gid
        if not workspace_gid:
            raise AsanaError("Missing workspaceGid. Set asana.workspaceGid in the config or provide one.")
        payload: dict[str, Any] = {"name": title, "workspace": workspace_gid}
        if notes:
            payload["notes"] = notes
        if due_date:
            payload["due_on"] = due_date
        if assignee_gid:
            payload["assignee"] = assignee_gid
        if completed is not None:
            payload["completed"] = completed
        if target_project:
            payload["projects"] = [target_project]
        target_section = section_gid or self.settings.default_section_gid
        if target_project and target_section:
            payload["memberships"] = [{"project": target_project, "section": target_section}]
        created = asana_request(self.settings, "POST", "/tasks", payload=payload)
        return self.get_task(created["gid"])

    def update_task(
        self,
        *,
        task_gid: str,
        title: str | None,
        notes: str | None,
        due_date: str | None,
        assignee_gid: str | None,
        completed: bool | None,
    ) -> dict[str, Any]:
        """Update a task."""
        payload: dict[str, Any] = {}
        if title is not None:
            payload["name"] = title
        if notes is not None:
            payload["notes"] = notes
        if due_date is not None:
            payload["due_on"] = due_date
        if assignee_gid is not None:
            payload["assignee"] = assignee_gid
        if completed is not None:
            payload["completed"] = completed
        if not payload:
            raise AsanaError("No update fields provided.")
        asana_request(self.settings, "PUT", f"/tasks/{task_gid}", payload=payload)
        return self.get_task(task_gid)

    def get_task(self, task_gid: str) -> dict[str, Any]:
        """Retrieve one task."""
        task = asana_request(self.settings, "GET", f"/tasks/{task_gid}", query={"opt_fields": self.TASK_FIELDS})
        return normalize_task(task)

    def list_projects(self, *, limit: int) -> list[dict[str, Any]]:
        """List projects in the configured workspace."""
        workspace_gid = self.settings.workspace_gid
        if not workspace_gid:
            raise AsanaError("Missing workspaceGid. Set asana.workspaceGid in the config or provide one.")
        response = asana_request(
            self.settings,
            "GET",
            f"/workspaces/{workspace_gid}/projects",
            query={"limit": limit, "opt_fields": "gid,name,archived,permalink_url"},
        )
        return [normalize_project(item) for item in response]

    def list_sections(self, *, project_gid: str | None) -> list[dict[str, Any]]:
        """List sections for a project."""
        target_project = project_gid or self.settings.project_gid
        if not target_project:
            raise AsanaError("Missing projectGid. Set asana.projectGid in the config or provide --project-gid.")
        response = asana_request(
            self.settings,
            "GET",
            f"/projects/{target_project}/sections",
            query={"opt_fields": "gid,name,created_at"},
        )
        return [normalize_section(item) for item in response]

    def list_assignees(self, *, limit: int) -> list[dict[str, Any]]:
        """List users in the configured workspace."""
        workspace_gid = self.settings.workspace_gid
        if not workspace_gid:
            raise AsanaError("Missing workspaceGid. Set asana.workspaceGid in the config or provide one.")
        response = asana_request(
            self.settings,
            "GET",
            f"/workspaces/{workspace_gid}/users",
            query={"limit": limit, "opt_fields": "gid,name,email"},
        )
        return [normalize_user(item) for item in response]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Asana API wrapper for OpsClaw task tracking.")
    parser.add_argument("--config", required=True, help="Path to tracker-config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_tasks = subparsers.add_parser("list-tasks", help="List tasks for a project.")
    list_tasks.add_argument("--project-gid")
    list_tasks.add_argument("--limit", type=int, default=25)

    search_tasks = subparsers.add_parser("search-tasks", help="Search tasks by text.")
    search_tasks.add_argument("--text", required=True)
    search_tasks.add_argument("--project-gid")
    search_tasks.add_argument("--limit", type=int, default=25)

    create_task = subparsers.add_parser("create-task", help="Create a task.")
    create_task.add_argument("--title", required=True)
    create_task.add_argument("--notes")
    create_task.add_argument("--due-date")
    create_task.add_argument("--assignee-gid")
    create_task.add_argument("--project-gid")
    create_task.add_argument("--section-gid")
    create_task.add_argument("--completed", action="store_true")

    update_task = subparsers.add_parser("update-task", help="Update a task.")
    update_task.add_argument("--task-gid", required=True)
    update_task.add_argument("--title")
    update_task.add_argument("--notes")
    update_task.add_argument("--due-date")
    update_task.add_argument("--assignee-gid")
    completion = update_task.add_mutually_exclusive_group()
    completion.add_argument("--complete", action="store_true")
    completion.add_argument("--incomplete", action="store_true")

    list_projects = subparsers.add_parser("list-projects", help="List projects.")
    list_projects.add_argument("--limit", type=int, default=50)

    list_sections = subparsers.add_parser("list-sections", help="List sections for a project.")
    list_sections.add_argument("--project-gid")

    list_assignees = subparsers.add_parser("list-assignees", help="List users in the workspace.")
    list_assignees.add_argument("--limit", type=int, default=50)

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings(Path(args.config))
    client = AsanaClient(settings)

    if args.command == "list-tasks":
        result = client.list_tasks(project_gid=args.project_gid, limit=args.limit)
    elif args.command == "search-tasks":
        result = client.search_tasks(text=args.text, project_gid=args.project_gid, limit=args.limit)
    elif args.command == "create-task":
        result = client.create_task(
            title=args.title,
            notes=args.notes,
            due_date=args.due_date,
            assignee_gid=args.assignee_gid,
            project_gid=args.project_gid,
            section_gid=args.section_gid,
            completed=True if args.completed else None,
        )
    elif args.command == "update-task":
        completed: bool | None = None
        if args.complete:
            completed = True
        elif args.incomplete:
            completed = False
        result = client.update_task(
            task_gid=args.task_gid,
            title=args.title,
            notes=args.notes,
            due_date=args.due_date,
            assignee_gid=args.assignee_gid,
            completed=completed,
        )
    elif args.command == "list-projects":
        result = client.list_projects(limit=args.limit)
    elif args.command == "list-sections":
        result = client.list_sections(project_gid=args.project_gid)
    elif args.command == "list-assignees":
        result = client.list_assignees(limit=args.limit)
    else:
        parser.error(f"Unsupported command {args.command}")
        return 2

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AsanaError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc
