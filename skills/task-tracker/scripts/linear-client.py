#!/usr/bin/env python3
"""Linear API wrapper for OpsClaw task tracking."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import random
import sys
import time
import urllib.error
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
LOG = LOGGER_MODULE.get_logger("opsclaw.tasks.linear")


class LinearError(RuntimeError):
    """Base Linear client error."""


class RateLimitError(LinearError):
    """Raised when Linear rate limits the request."""


@dataclass(frozen=True)
class RetryConfig:
    """Retry settings for transient Linear failures."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 20.0
    jitter: float = 0.5


@dataclass(frozen=True)
class LinearSettings:
    """Resolved Linear settings."""

    base_url: str
    api_key: str
    team_id: str | None
    default_project_id: str | None
    default_state_id: str | None
    blocked_state_name: str
    done_state_names: list[str]
    retry: RetryConfig


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_settings(config_path: Path) -> LinearSettings:
    """Load Linear settings from the tracker config."""
    config = load_json(config_path)
    provider_doc = config.get("linear", {})
    retry_doc = config.get("retry", {})
    token_env = str(provider_doc.get("tokenEnv") or "LINEAR_API_KEY")
    api_key = os.environ.get(token_env)
    if not api_key:
        raise LinearError(f"Missing Linear API key. Export {token_env}.")
    return LinearSettings(
        base_url=str(provider_doc.get("baseUrl") or "https://api.linear.app/graphql"),
        api_key=api_key,
        team_id=str(provider_doc.get("teamId") or "") or None,
        default_project_id=str(provider_doc.get("defaultProjectId") or "") or None,
        default_state_id=str(provider_doc.get("defaultStateId") or "") or None,
        blocked_state_name=str(provider_doc.get("blockedStateName") or "Blocked"),
        done_state_names=[str(item) for item in provider_doc.get("doneStateNames", ["Done"])],
        retry=RetryConfig(
            max_retries=int(retry_doc.get("maxRetries", 3)),
            base_delay=float(retry_doc.get("baseDelaySeconds", 1.0)),
            max_delay=float(retry_doc.get("maxDelaySeconds", 20.0)),
            jitter=float(retry_doc.get("jitterSeconds", 0.5)),
        ),
    )


def graphql_request(settings: LinearSettings, query: str, variables: dict[str, Any] | None = None) -> Any:
    """Execute a Linear GraphQL request with bounded retries."""
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    headers = {
        "Authorization": settings.api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    for attempt in range(settings.retry.max_retries + 1):
        request = urllib.request.Request(settings.base_url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                doc = json.loads(raw)
                if doc.get("errors"):
                    raise LinearError(f"Linear GraphQL returned errors: {doc['errors']}")
                return doc.get("data", {})
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429:
                if attempt >= settings.retry.max_retries:
                    raise RateLimitError(f"Linear API returned 429: {raw_error}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "linear rate limited, retrying",
                    extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2)}},
                )
                time.sleep(delay)
                continue
            if 500 <= exc.code < 600:
                if attempt >= settings.retry.max_retries:
                    raise LinearError(f"Linear API failed after retries: {raw_error}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "linear transient server error, retrying",
                    extra={"event": {"attempt": attempt + 1, "status": exc.code, "delaySeconds": round(delay, 2)}},
                )
                time.sleep(delay)
                continue
            raise LinearError(f"Linear API returned {exc.code}: {raw_error}") from exc
        except urllib.error.URLError as exc:
            if attempt >= settings.retry.max_retries:
                raise LinearError(f"Linear network error: {exc.reason}") from exc
            delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
            delay += random.uniform(0, settings.retry.jitter)
            LOG.warning(
                "linear network error, retrying",
                extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "error": str(exc.reason)}},
            )
            time.sleep(delay)
            continue
    raise LinearError("Linear retry loop exhausted unexpectedly.")


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Linear issue object."""
    labels = [node.get("name") for node in ((issue.get("labels") or {}).get("nodes") or []) if node.get("name")]
    project = issue.get("project") or {}
    cycle = issue.get("cycle") or {}
    state = issue.get("state") or {}
    assignee = issue.get("assignee") or {}
    team = issue.get("team") or {}
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "description": issue.get("description"),
        "priority": normalize_priority(issue.get("priority")),
        "dueDate": issue.get("dueDate"),
        "status": state.get("name"),
        "stateId": state.get("id"),
        "assignee": assignee.get("name") or assignee.get("displayName") or assignee.get("email"),
        "assigneeId": assignee.get("id"),
        "project": project.get("name"),
        "projectId": project.get("id"),
        "team": team.get("name"),
        "teamId": team.get("id"),
        "cycle": cycle.get("name"),
        "cycleId": cycle.get("id"),
        "labels": labels,
        "url": issue.get("url"),
        "createdAt": issue.get("createdAt"),
        "updatedAt": issue.get("updatedAt"),
        "completedAt": issue.get("completedAt"),
    }


def normalize_label(label: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Linear label object."""
    return {
        "id": label.get("id"),
        "name": label.get("name"),
        "color": label.get("color"),
        "description": label.get("description"),
        "isGroup": bool(label.get("isGroup")),
    }


def normalize_project(project: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Linear project object."""
    return {
        "id": project.get("id"),
        "name": project.get("name"),
        "description": project.get("description"),
        "state": project.get("state"),
        "startDate": project.get("startDate"),
        "targetDate": project.get("targetDate"),
        "progress": project.get("progress"),
        "url": project.get("url"),
    }


def normalize_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Linear cycle object."""
    return {
        "id": cycle.get("id"),
        "name": cycle.get("name"),
        "number": cycle.get("number"),
        "startsAt": cycle.get("startsAt"),
        "endsAt": cycle.get("endsAt"),
        "completedIssueCountHistory": cycle.get("completedIssueCountHistory"),
        "isCurrent": bool(cycle.get("isCurrent")),
    }


def normalize_priority(priority_value: Any) -> str | None:
    """Convert Linear numeric priority to a readable value."""
    mapping = {
        0: None,
        1: "urgent",
        2: "high",
        3: "medium",
        4: "low",
    }
    if priority_value is None:
        return None
    return mapping.get(int(priority_value), str(priority_value))


def encode_priority(priority: str | None) -> int | None:
    """Convert a readable priority into Linear's numeric scale."""
    if priority is None:
        return None
    mapping = {
        "urgent": 1,
        "high": 2,
        "medium": 3,
        "normal": 3,
        "low": 4,
    }
    normalized = priority.strip().lower()
    if normalized not in mapping:
        raise LinearError(f"Unsupported priority '{priority}'. Expected urgent/high/medium/low.")
    return mapping[normalized]


class LinearClient:
    """Thin Linear wrapper with normalized JSON output."""

    ISSUE_FIELDS = """
        id
        identifier
        title
        description
        priority
        dueDate
        url
        createdAt
        updatedAt
        completedAt
        state { id name type }
        assignee { id name displayName email }
        project { id name }
        team { id name }
        cycle { id name number startsAt endsAt completedIssueCountHistory isCurrent }
        labels { nodes { id name color description } }
    """

    def __init__(self, settings: LinearSettings) -> None:
        self.settings = settings

    def list_issues(
        self,
        *,
        limit: int,
        team_id: str | None = None,
        project_id: str | None = None,
        state_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List issues with optional filters."""
        query = f"""
        query ListIssues($limit: Int!, $teamId: String, $projectId: String, $stateName: String) {{
          issues(
            first: $limit
            filter: {{
              team: {{ id: {{ eq: $teamId }} }}
              project: {{ id: {{ eq: $projectId }} }}
              state: {{ name: {{ eq: $stateName }} }}
            }}
            orderBy: updatedAt
          ) {{
            nodes {{
              {self.ISSUE_FIELDS}
            }}
          }}
        }}
        """
        data = graphql_request(
            self.settings,
            query,
            {
                "limit": limit,
                "teamId": team_id,
                "projectId": project_id,
                "stateName": state_name,
            },
        )
        return [normalize_issue(item) for item in (data.get("issues") or {}).get("nodes", [])]

    def search_issues(self, query_text: str, *, limit: int) -> list[dict[str, Any]]:
        """Search issues by title text."""
        query = f"""
        query SearchIssues($query: String!, $limit: Int!, $teamId: String) {{
          issues(
            first: $limit
            filter: {{
              title: {{ containsIgnoreCase: $query }}
              team: {{ id: {{ eq: $teamId }} }}
            }}
            orderBy: updatedAt
          ) {{
            nodes {{
              {self.ISSUE_FIELDS}
            }}
          }}
        }}
        """
        data = graphql_request(
            self.settings,
            query,
            {"query": query_text, "limit": limit, "teamId": self.settings.team_id},
        )
        return [normalize_issue(item) for item in (data.get("issues") or {}).get("nodes", [])]

    def create_issue(
        self,
        *,
        title: str,
        description: str | None,
        due_date: str | None,
        priority: str | None,
        assignee_id: str | None,
        project_id: str | None,
        team_id: str | None,
        state_id: str | None,
        label_ids: list[str],
    ) -> dict[str, Any]:
        """Create an issue."""
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue {
              id
              identifier
            }
          }
        }
        """
        issue_input: dict[str, Any] = {
            "title": title,
            "teamId": team_id or self.settings.team_id,
        }
        if not issue_input["teamId"]:
            raise LinearError("Missing teamId. Set linear.teamId in the config or provide --team-id.")
        if description:
            issue_input["description"] = description
        if due_date:
            issue_input["dueDate"] = due_date
        if priority:
            issue_input["priority"] = encode_priority(priority)
        if assignee_id:
            issue_input["assigneeId"] = assignee_id
        if project_id or self.settings.default_project_id:
            issue_input["projectId"] = project_id or self.settings.default_project_id
        if state_id or self.settings.default_state_id:
            issue_input["stateId"] = state_id or self.settings.default_state_id
        if label_ids:
            issue_input["labelIds"] = label_ids
        data = graphql_request(self.settings, mutation, {"input": issue_input})
        response = data.get("issueCreate") or {}
        issue = response.get("issue") or {}
        return {
            "success": bool(response.get("success")),
            "issueId": issue.get("id"),
            "identifier": issue.get("identifier"),
        }

    def update_issue(
        self,
        *,
        issue_id: str,
        title: str | None,
        description: str | None,
        due_date: str | None,
        priority: str | None,
        assignee_id: str | None,
        project_id: str | None,
        state_id: str | None,
        label_ids: list[str] | None,
    ) -> dict[str, Any]:
        """Update a Linear issue."""
        mutation = """
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
          issueUpdate(id: $id, input: $input) {
            success
          }
        }
        """
        issue_input: dict[str, Any] = {}
        if title is not None:
            issue_input["title"] = title
        if description is not None:
            issue_input["description"] = description
        if due_date is not None:
            issue_input["dueDate"] = due_date
        if priority is not None:
            issue_input["priority"] = encode_priority(priority)
        if assignee_id is not None:
            issue_input["assigneeId"] = assignee_id
        if project_id is not None:
            issue_input["projectId"] = project_id
        if state_id is not None:
            issue_input["stateId"] = state_id
        if label_ids is not None:
            issue_input["labelIds"] = label_ids
        if not issue_input:
            raise LinearError("No update fields provided.")
        data = graphql_request(self.settings, mutation, {"id": issue_id, "input": issue_input})
        return {"success": bool((data.get("issueUpdate") or {}).get("success"))}

    def list_labels(self, *, limit: int) -> list[dict[str, Any]]:
        """List labels."""
        query = """
        query ListLabels($limit: Int!) {
          issueLabels(first: $limit) {
            nodes {
              id
              name
              color
              description
              isGroup
            }
          }
        }
        """
        data = graphql_request(self.settings, query, {"limit": limit})
        return [normalize_label(item) for item in (data.get("issueLabels") or {}).get("nodes", [])]

    def list_projects(self, *, limit: int) -> list[dict[str, Any]]:
        """List projects."""
        query = """
        query ListProjects($limit: Int!) {
          projects(first: $limit, orderBy: updatedAt) {
            nodes {
              id
              name
              description
              state
              startDate
              targetDate
              progress
              url
            }
          }
        }
        """
        data = graphql_request(self.settings, query, {"limit": limit})
        return [normalize_project(item) for item in (data.get("projects") or {}).get("nodes", [])]

    def list_cycles(self, *, limit: int, team_id: str | None = None) -> list[dict[str, Any]]:
        """List cycles for a team."""
        query = """
        query ListCycles($limit: Int!, $teamId: String) {
          cycles(first: $limit, filter: { team: { id: { eq: $teamId } } }, orderBy: startsAt) {
            nodes {
              id
              name
              number
              startsAt
              endsAt
              completedIssueCountHistory
              isCurrent
            }
          }
        }
        """
        data = graphql_request(self.settings, query, {"limit": limit, "teamId": team_id or self.settings.team_id})
        return [normalize_cycle(item) for item in (data.get("cycles") or {}).get("nodes", [])]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Linear API wrapper for OpsClaw task tracking.")
    parser.add_argument("--config", required=True, help="Path to tracker-config.json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_issues = subparsers.add_parser("list-issues", help="List issues.")
    list_issues.add_argument("--limit", type=int, default=25)
    list_issues.add_argument("--team-id")
    list_issues.add_argument("--project-id")
    list_issues.add_argument("--state-name")

    search_issues = subparsers.add_parser("search-issues", help="Search issues by title.")
    search_issues.add_argument("--query", required=True)
    search_issues.add_argument("--limit", type=int, default=25)

    create_issue = subparsers.add_parser("create-issue", help="Create a Linear issue.")
    create_issue.add_argument("--title", required=True)
    create_issue.add_argument("--description")
    create_issue.add_argument("--due-date")
    create_issue.add_argument("--priority")
    create_issue.add_argument("--assignee-id")
    create_issue.add_argument("--project-id")
    create_issue.add_argument("--team-id")
    create_issue.add_argument("--state-id")
    create_issue.add_argument("--label-id", action="append", default=[])

    update_issue = subparsers.add_parser("update-issue", help="Update a Linear issue.")
    update_issue.add_argument("--issue-id", required=True)
    update_issue.add_argument("--title")
    update_issue.add_argument("--description")
    update_issue.add_argument("--due-date")
    update_issue.add_argument("--priority")
    update_issue.add_argument("--assignee-id")
    update_issue.add_argument("--project-id")
    update_issue.add_argument("--state-id")
    update_issue.add_argument("--label-id", action="append")

    list_labels = subparsers.add_parser("list-labels", help="List labels.")
    list_labels.add_argument("--limit", type=int, default=50)

    list_projects = subparsers.add_parser("list-projects", help="List projects.")
    list_projects.add_argument("--limit", type=int, default=50)

    list_cycles = subparsers.add_parser("list-cycles", help="List cycles.")
    list_cycles.add_argument("--limit", type=int, default=25)
    list_cycles.add_argument("--team-id")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings(Path(args.config))
    client = LinearClient(settings)

    if args.command == "list-issues":
        result = client.list_issues(
            limit=args.limit,
            team_id=args.team_id or settings.team_id,
            project_id=args.project_id,
            state_name=args.state_name,
        )
    elif args.command == "search-issues":
        result = client.search_issues(args.query, limit=args.limit)
    elif args.command == "create-issue":
        result = client.create_issue(
            title=args.title,
            description=args.description,
            due_date=args.due_date,
            priority=args.priority,
            assignee_id=args.assignee_id,
            project_id=args.project_id,
            team_id=args.team_id,
            state_id=args.state_id,
            label_ids=list(args.label_id),
        )
    elif args.command == "update-issue":
        result = client.update_issue(
            issue_id=args.issue_id,
            title=args.title,
            description=args.description,
            due_date=args.due_date,
            priority=args.priority,
            assignee_id=args.assignee_id,
            project_id=args.project_id,
            state_id=args.state_id,
            label_ids=args.label_id,
        )
    elif args.command == "list-labels":
        result = client.list_labels(limit=args.limit)
    elif args.command == "list-projects":
        result = client.list_projects(limit=args.limit)
    elif args.command == "list-cycles":
        result = client.list_cycles(limit=args.limit, team_id=args.team_id)
    else:
        parser.error(f"Unsupported command {args.command}")
        return 2

    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LinearError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc
