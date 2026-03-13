#!/usr/bin/env python3
"""Pipedrive CRM API wrapper for OpsClaw CRM Sync."""

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
from datetime import datetime, timezone
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
LOG = LOGGER_MODULE.get_logger("opsclaw.crm.pipedrive")


class CRMError(RuntimeError):
    """Base Pipedrive client error."""


class RateLimitError(CRMError):
    """Raised when Pipedrive returns a rate limit response."""


@dataclass(frozen=True)
class RetryConfig:
    """Retry settings for transient Pipedrive failures."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 20.0
    jitter: float = 0.5


@dataclass(frozen=True)
class PipedriveSettings:
    """Resolved Pipedrive runtime configuration."""

    base_url: str
    api_token: str
    default_pipeline_id: int
    person_fields: list[str]
    organization_fields: list[str]
    deal_fields: list[str]
    retry: RetryConfig


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def utc_now() -> str:
    """Return the current UTC timestamp as ISO 8601."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_settings(config_path: Path) -> PipedriveSettings:
    """Load Pipedrive settings from the CRM config template."""
    config = load_json(config_path)
    retry_doc = config.get("retry", {})
    pipedrive_doc = config.get("pipedrive", {})
    token_env = str(pipedrive_doc.get("tokenEnv") or "PIPEDRIVE_API_TOKEN")
    api_token = os.environ.get(token_env)
    if not api_token:
        raise CRMError(f"Missing Pipedrive API token. Export {token_env}.")
    return PipedriveSettings(
        base_url=str(pipedrive_doc.get("baseUrl") or "").rstrip("/"),
        api_token=api_token,
        default_pipeline_id=int(pipedrive_doc.get("defaultPipelineId", 1)),
        person_fields=[str(item) for item in pipedrive_doc.get("personFields", [])],
        organization_fields=[str(item) for item in pipedrive_doc.get("organizationFields", [])],
        deal_fields=[str(item) for item in pipedrive_doc.get("dealFields", [])],
        retry=RetryConfig(
            max_retries=int(retry_doc.get("maxRetries", 3)),
            base_delay=float(retry_doc.get("baseDelaySeconds", 1.0)),
            max_delay=float(retry_doc.get("maxDelaySeconds", 20.0)),
            jitter=float(retry_doc.get("jitterSeconds", 0.5)),
        ),
    )


def request_with_retry(
    settings: PipedriveSettings,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> Any:
    """Execute a Pipedrive API request with bounded retries."""
    url = settings.base_url + path
    filtered_query = {key: value for key, value in (query or {}).items() if value is not None}
    filtered_query["api_token"] = settings.api_token
    url += "?" + urllib.parse.urlencode(filtered_query, doseq=True)

    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    for attempt in range(settings.retry.max_retries + 1):
        request = urllib.request.Request(url=url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                doc = json.loads(raw) if raw else {}
                if doc.get("success") is False:
                    raise CRMError(str(doc.get("error") or "Pipedrive request failed."))
                return doc.get("data", doc)
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            try:
                error_doc = json.loads(raw_error) if raw_error else {}
            except json.JSONDecodeError:
                error_doc = {"error": raw_error}
            if exc.code == 429:
                if attempt >= settings.retry.max_retries:
                    raise RateLimitError(f"Pipedrive API returned 429: {error_doc}") from exc
                retry_after = float(exc.headers.get("Retry-After", "0") or 0)
                delay = max(retry_after, min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay))
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "pipedrive rate limited, retrying",
                    extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "path": path}},
                )
                time.sleep(delay)
                continue
            if 500 <= exc.code < 600:
                if attempt >= settings.retry.max_retries:
                    raise CRMError(f"Pipedrive API failed after retries: {error_doc}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "pipedrive transient server error, retrying",
                    extra={
                        "event": {"attempt": attempt + 1, "status": exc.code, "delaySeconds": round(delay, 2), "path": path}
                    },
                )
                time.sleep(delay)
                continue
            raise CRMError(f"Pipedrive API returned {exc.code}: {error_doc}") from exc
        except urllib.error.URLError as exc:
            if attempt >= settings.retry.max_retries:
                raise CRMError(f"Pipedrive network error: {exc.reason}") from exc
            delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
            delay += random.uniform(0, settings.retry.jitter)
            LOG.warning(
                "pipedrive network error, retrying",
                extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "path": path}},
            )
            time.sleep(delay)
    raise CRMError("Pipedrive retry loop exhausted unexpectedly.")


def first_value(values: Any) -> Any:
    """Return the first useful Pipedrive field value."""
    if isinstance(values, list) and values:
        item = values[0]
        if isinstance(item, dict):
            return item.get("value")
        return item
    return values


def normalize_person(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Pipedrive person record."""
    org = record.get("org_id")
    org_name = org.get("name") if isinstance(org, dict) else record.get("org_name")
    return {
        "id": str(record.get("id")),
        "name": record.get("name") or "Unknown contact",
        "email": first_value(record.get("email")),
        "phone": first_value(record.get("phone")),
        "company": org_name,
        "owner": (record.get("owner_id") or {}).get("name") if isinstance(record.get("owner_id"), dict) else record.get("owner_name"),
        "createdAt": record.get("add_time"),
        "updatedAt": record.get("update_time"),
    }


def normalize_organization(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Pipedrive organization record."""
    return {
        "id": str(record.get("id")),
        "name": record.get("name") or "Unknown company",
        "address": record.get("address"),
        "owner": (record.get("owner_id") or {}).get("name") if isinstance(record.get("owner_id"), dict) else record.get("owner_name"),
        "createdAt": record.get("add_time"),
        "updatedAt": record.get("update_time"),
    }


def normalize_deal(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Pipedrive deal record."""
    stage = record.get("stage_id")
    if isinstance(stage, dict):
        stage_value = stage.get("name") or stage.get("id")
    else:
        stage_value = stage
    return {
        "id": str(record.get("id")),
        "name": record.get("title") or "Untitled deal",
        "stage": stage_value,
        "status": record.get("status"),
        "pipeline": (record.get("pipeline_id") or {}).get("name") if isinstance(record.get("pipeline_id"), dict) else record.get("pipeline_id"),
        "amount": record.get("value"),
        "currency": record.get("currency"),
        "closeDate": record.get("expected_close_date"),
        "nextActivityDate": record.get("next_activity_date"),
        "updatedAt": record.get("update_time"),
        "createdAt": record.get("add_time"),
    }


class PipedriveClient:
    """Thin Pipedrive wrapper with deterministic JSON output."""

    def __init__(self, settings: PipedriveSettings) -> None:
        self.settings = settings

    def search_contacts(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search Pipedrive persons."""
        response = request_with_retry(
            self.settings,
            "GET",
            "/persons/search",
            query={"term": query, "limit": limit, "fields": "name,email,phone"},
        )
        return [normalize_person(item["item"]) for item in response.get("items", []) if "item" in item]

    def search_companies(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search Pipedrive organizations."""
        response = request_with_retry(
            self.settings,
            "GET",
            "/organizations/search",
            query={"term": query, "limit": limit, "fields": "name,address"},
        )
        return [normalize_organization(item["item"]) for item in response.get("items", []) if "item" in item]

    def search_deals(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search Pipedrive deals."""
        response = request_with_retry(
            self.settings,
            "GET",
            "/deals/search",
            query={"term": query, "limit": limit, "fields": "title"},
        )
        return [normalize_deal(item["item"]) for item in response.get("items", []) if "item" in item]

    def lookup(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        """Search persons, organizations, and deals in one call."""
        return {
            "query": query,
            "provider": "pipedrive",
            "contacts": self.search_contacts(query, limit=limit),
            "companies": self.search_companies(query, limit=limit),
            "deals": self.search_deals(query, limit=limit),
            "lookedUpAt": utc_now(),
        }

    def add_note(self, content: str, *, person_id: str | None = None, org_id: str | None = None, deal_id: str | None = None) -> dict[str, Any]:
        """Create a note associated to CRM records."""
        if not any([person_id, org_id, deal_id]):
            raise CRMError("At least one association ID is required to create a note.")
        payload = {"content": content}
        if person_id:
            payload["person_id"] = int(person_id)
        if org_id:
            payload["org_id"] = int(org_id)
        if deal_id:
            payload["deal_id"] = int(deal_id)
        response = request_with_retry(self.settings, "POST", "/notes", payload=payload)
        return {
            "provider": "pipedrive",
            "noteId": response.get("id"),
            "personId": person_id,
            "orgId": org_id,
            "dealId": deal_id,
            "createdAt": response.get("add_time") or utc_now(),
        }

    def create_contact(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a Pipedrive person."""
        response = request_with_retry(self.settings, "POST", "/persons", payload=properties)
        return normalize_person(response)

    def create_company(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a Pipedrive organization."""
        response = request_with_retry(self.settings, "POST", "/organizations", payload=properties)
        return normalize_organization(response)

    def create_deal(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a Pipedrive deal."""
        payload = {"pipeline_id": self.settings.default_pipeline_id, **properties}
        response = request_with_retry(self.settings, "POST", "/deals", payload=payload)
        return normalize_deal(response)

    def update_deal_stage(self, deal_id: str, stage: str) -> dict[str, Any]:
        """Update a Pipedrive deal stage."""
        response = request_with_retry(
            self.settings,
            "PUT",
            f"/deals/{deal_id}",
            payload={"stage_id": int(stage) if stage.isdigit() else stage},
        )
        normalized = normalize_deal(response)
        normalized["updatedStage"] = stage
        return normalized

    def list_activities(self, *, deal_id: str | None = None, person_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """List recent activities."""
        response = request_with_retry(
            self.settings,
            "GET",
            "/activities",
            query={"deal_id": deal_id, "person_id": person_id, "limit": limit},
        )
        activities: list[dict[str, Any]] = []
        for item in response or []:
            activities.append(
                {
                    "id": str(item.get("id")),
                    "type": item.get("type"),
                    "subject": item.get("subject"),
                    "status": item.get("done"),
                    "dueDate": item.get("due_date"),
                    "dueTime": item.get("due_time"),
                }
            )
        return activities

    def list_followups(self, *, due_before: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return deals that have a next activity date set."""
        response = request_with_retry(self.settings, "GET", "/deals", query={"limit": limit, "status": "open"})
        deals = [normalize_deal(item) for item in response or []]
        if due_before:
            deals = [
                deal
                for deal in deals
                if deal.get("nextActivityDate") and str(deal["nextActivityDate"]) <= due_before
            ]
        return deals

    def pipeline(self, *, pipeline_id: int | None = None) -> dict[str, Any]:
        """Fetch a pipeline and its stages."""
        resolved = pipeline_id or self.settings.default_pipeline_id
        pipeline = request_with_retry(self.settings, "GET", f"/pipelines/{resolved}")
        stages = request_with_retry(self.settings, "GET", "/stages", query={"pipeline_id": resolved})
        return {
            "provider": "pipedrive",
            "pipelineId": pipeline.get("id") or resolved,
            "label": pipeline.get("name"),
            "stages": [
                {"id": stage.get("id"), "label": stage.get("name"), "displayOrder": stage.get("order_nr")}
                for stage in stages or []
            ],
        }


def read_properties(args: argparse.Namespace) -> dict[str, Any]:
    """Load object properties from a JSON file or stdin."""
    if getattr(args, "properties", None):
        return load_json(args.properties)
    return json.load(sys.stdin)


def dump_output(payload: Any, *, pretty: bool) -> None:
    """Write JSON payload to stdout."""
    json.dump(payload, sys.stdout, indent=2 if pretty else None)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Path to crm-config.json.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ["search-contacts", "search-companies", "search-deals", "lookup"]:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--query", required=True, help="Free-text search query.")
        subparser.add_argument("--limit", type=int, default=10, help="Maximum number of records to return.")

    add_note = subparsers.add_parser("add-note")
    add_note.add_argument("--content", required=True, help="Note content.")
    add_note.add_argument("--person-id", help="Pipedrive person ID.")
    add_note.add_argument("--org-id", help="Pipedrive organization ID.")
    add_note.add_argument("--deal-id", help="Pipedrive deal ID.")

    for name in ["create-contact", "create-company", "create-deal"]:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--properties", type=Path, help="Path to a JSON document containing properties.")

    update_stage = subparsers.add_parser("update-deal-stage")
    update_stage.add_argument("--deal-id", required=True, help="Pipedrive deal ID.")
    update_stage.add_argument("--stage", required=True, help="Target stage ID or label.")

    activities = subparsers.add_parser("list-activities")
    activities.add_argument("--deal-id", help="Filter by deal ID.")
    activities.add_argument("--person-id", help="Filter by person ID.")
    activities.add_argument("--limit", type=int, default=20, help="Maximum number of activities.")

    followups = subparsers.add_parser("list-followups")
    followups.add_argument("--due-before", help="Optional YYYY-MM-DD cutoff for next activity date.")
    followups.add_argument("--limit", type=int, default=50, help="Maximum number of deals.")

    pipeline = subparsers.add_parser("pipeline")
    pipeline.add_argument("--pipeline-id", type=int, help="Pipeline ID. Defaults to config default.")
    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings(args.config)
    client = PipedriveClient(settings)

    try:
        if args.command == "search-contacts":
            payload = client.search_contacts(args.query, limit=args.limit)
        elif args.command == "search-companies":
            payload = client.search_companies(args.query, limit=args.limit)
        elif args.command == "search-deals":
            payload = client.search_deals(args.query, limit=args.limit)
        elif args.command == "lookup":
            payload = client.lookup(args.query, limit=args.limit)
        elif args.command == "add-note":
            payload = client.add_note(args.content, person_id=args.person_id, org_id=args.org_id, deal_id=args.deal_id)
        elif args.command == "create-contact":
            payload = client.create_contact(read_properties(args))
        elif args.command == "create-company":
            payload = client.create_company(read_properties(args))
        elif args.command == "create-deal":
            payload = client.create_deal(read_properties(args))
        elif args.command == "update-deal-stage":
            payload = client.update_deal_stage(args.deal_id, args.stage)
        elif args.command == "list-activities":
            payload = client.list_activities(deal_id=args.deal_id, person_id=args.person_id, limit=args.limit)
        elif args.command == "list-followups":
            payload = client.list_followups(due_before=args.due_before, limit=args.limit)
        elif args.command == "pipeline":
            payload = client.pipeline(pipeline_id=args.pipeline_id)
        else:
            parser.error(f"Unsupported command: {args.command}")
            return 2
    except CRMError as exc:
        LOG.error("pipedrive command failed", extra={"event": {"command": args.command, "error": str(exc)}})
        sys.stderr.write(f"{exc}\n")
        return 1

    dump_output(payload, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
