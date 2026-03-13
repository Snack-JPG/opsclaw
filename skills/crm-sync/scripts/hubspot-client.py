#!/usr/bin/env python3
"""HubSpot CRM API wrapper for OpsClaw CRM Sync."""

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
LOG = LOGGER_MODULE.get_logger("opsclaw.crm.hubspot")


class CRMError(RuntimeError):
    """Base HubSpot client error."""


class RateLimitError(CRMError):
    """Raised when HubSpot returns a rate limit response."""


@dataclass(frozen=True)
class RetryConfig:
    """Retry settings for transient HubSpot failures."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 20.0
    jitter: float = 0.5


@dataclass(frozen=True)
class HubSpotSettings:
    """Resolved HubSpot runtime configuration."""

    base_url: str
    token: str
    contact_properties: list[str]
    company_properties: list[str]
    deal_properties: list[str]
    default_pipeline_id: str
    retry: RetryConfig


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def utc_now() -> str:
    """Return the current UTC timestamp as ISO 8601."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO datetime or return None."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_settings(config_path: Path) -> HubSpotSettings:
    """Load HubSpot settings from the CRM config template."""
    config = load_json(config_path)
    retry_doc = config.get("retry", {})
    hubspot_doc = config.get("hubspot", {})
    token_env = str(hubspot_doc.get("tokenEnv") or "HUBSPOT_ACCESS_TOKEN")
    token = os.environ.get(token_env)
    if not token:
        raise CRMError(f"Missing HubSpot access token. Export {token_env}.")
    return HubSpotSettings(
        base_url=str(hubspot_doc.get("baseUrl") or "https://api.hubapi.com").rstrip("/"),
        token=token,
        contact_properties=[str(item) for item in hubspot_doc.get("contactProperties", [])],
        company_properties=[str(item) for item in hubspot_doc.get("companyProperties", [])],
        deal_properties=[str(item) for item in hubspot_doc.get("dealProperties", [])],
        default_pipeline_id=str(hubspot_doc.get("defaultPipelineId") or "default"),
        retry=RetryConfig(
            max_retries=int(retry_doc.get("maxRetries", 3)),
            base_delay=float(retry_doc.get("baseDelaySeconds", 1.0)),
            max_delay=float(retry_doc.get("maxDelaySeconds", 20.0)),
            jitter=float(retry_doc.get("jitterSeconds", 0.5)),
        ),
    )


def request_with_retry(
    settings: HubSpotSettings,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
) -> Any:
    """Execute a HubSpot API request with bounded retries."""
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
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    for attempt in range(settings.retry.max_retries + 1):
        request = urllib.request.Request(url=url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            try:
                error_doc = json.loads(raw_error) if raw_error else {}
            except json.JSONDecodeError:
                error_doc = {"message": raw_error}
            if exc.code == 429:
                if attempt >= settings.retry.max_retries:
                    raise RateLimitError(f"HubSpot API returned 429: {error_doc}") from exc
                retry_after = float(exc.headers.get("Retry-After", "0") or 0)
                delay = max(retry_after, min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay))
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "hubspot rate limited, retrying",
                    extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "path": path}},
                )
                time.sleep(delay)
                continue
            if 500 <= exc.code < 600:
                if attempt >= settings.retry.max_retries:
                    raise CRMError(f"HubSpot API failed after retries: {error_doc}") from exc
                delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
                delay += random.uniform(0, settings.retry.jitter)
                LOG.warning(
                    "hubspot transient server error, retrying",
                    extra={
                        "event": {"attempt": attempt + 1, "status": exc.code, "delaySeconds": round(delay, 2), "path": path}
                    },
                )
                time.sleep(delay)
                continue
            raise CRMError(f"HubSpot API returned {exc.code}: {error_doc}") from exc
        except urllib.error.URLError as exc:
            if attempt >= settings.retry.max_retries:
                raise CRMError(f"HubSpot network error: {exc.reason}") from exc
            delay = min(settings.retry.base_delay * (2**attempt), settings.retry.max_delay)
            delay += random.uniform(0, settings.retry.jitter)
            LOG.warning(
                "hubspot network error, retrying",
                extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "path": path}},
            )
            time.sleep(delay)
    raise CRMError("HubSpot retry loop exhausted unexpectedly.")


def normalize_contact(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a HubSpot contact object."""
    props = record.get("properties", {})
    first = props.get("firstname") or ""
    last = props.get("lastname") or ""
    full_name = " ".join(part for part in [first, last] if part).strip()
    return {
        "id": str(record.get("id")),
        "name": full_name or props.get("email") or "Unknown contact",
        "email": props.get("email"),
        "phone": props.get("phone"),
        "company": props.get("company"),
        "jobTitle": props.get("jobtitle"),
        "lifecycleStage": props.get("lifecyclestage"),
        "createdAt": props.get("createdate"),
        "updatedAt": props.get("lastmodifieddate"),
    }


def normalize_company(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a HubSpot company object."""
    props = record.get("properties", {})
    return {
        "id": str(record.get("id")),
        "name": props.get("name") or "Unknown company",
        "domain": props.get("domain"),
        "industry": props.get("industry"),
        "phone": props.get("phone"),
        "city": props.get("city"),
        "country": props.get("country"),
        "createdAt": props.get("createdate"),
        "updatedAt": props.get("lastmodifieddate"),
    }


def normalize_deal(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a HubSpot deal object."""
    props = record.get("properties", {})
    return {
        "id": str(record.get("id")),
        "name": props.get("dealname") or "Untitled deal",
        "stage": props.get("dealstage"),
        "pipeline": props.get("pipeline"),
        "amount": float(props["amount"]) if props.get("amount") not in {None, ""} else None,
        "closeDate": props.get("closedate"),
        "updatedAt": props.get("hs_lastmodifieddate") or props.get("updatedAt"),
        "createdAt": props.get("createdate"),
        "ownerId": props.get("hubspot_owner_id"),
    }


class HubSpotClient:
    """Thin HubSpot CRM wrapper with deterministic JSON output."""

    def __init__(self, settings: HubSpotSettings) -> None:
        self.settings = settings

    def search_contacts(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search contacts by email, first name, last name, or company."""
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": "email", "operator": "CONTAINS_TOKEN", "value": query}]},
                {"filters": [{"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": query}]},
                {"filters": [{"propertyName": "lastname", "operator": "CONTAINS_TOKEN", "value": query}]},
                {"filters": [{"propertyName": "company", "operator": "CONTAINS_TOKEN", "value": query}]},
            ],
            "properties": self.settings.contact_properties,
            "limit": limit,
        }
        response = request_with_retry(self.settings, "POST", "/crm/v3/objects/contacts/search", payload=payload)
        return [normalize_contact(item) for item in response.get("results", [])]

    def search_companies(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search companies by name or domain."""
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": "name", "operator": "CONTAINS_TOKEN", "value": query}]},
                {"filters": [{"propertyName": "domain", "operator": "CONTAINS_TOKEN", "value": query}]},
            ],
            "properties": self.settings.company_properties,
            "limit": limit,
        }
        response = request_with_retry(self.settings, "POST", "/crm/v3/objects/companies/search", payload=payload)
        return [normalize_company(item) for item in response.get("results", [])]

    def search_deals(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search deals by deal name."""
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": "dealname", "operator": "CONTAINS_TOKEN", "value": query}]}
            ],
            "properties": self.settings.deal_properties,
            "limit": limit,
        }
        response = request_with_retry(self.settings, "POST", "/crm/v3/objects/deals/search", payload=payload)
        return [normalize_deal(item) for item in response.get("results", [])]

    def lookup(self, query: str, *, limit: int = 5) -> dict[str, Any]:
        """Search contacts, companies, and deals in one call."""
        return {
            "query": query,
            "provider": "hubspot",
            "contacts": self.search_contacts(query, limit=limit),
            "companies": self.search_companies(query, limit=limit),
            "deals": self.search_deals(query, limit=limit),
            "lookedUpAt": utc_now(),
        }

    def add_note(self, body: str, *, contact_id: str | None = None, company_id: str | None = None, deal_id: str | None = None) -> dict[str, Any]:
        """Create a note and associate it to CRM records."""
        associations: list[dict[str, Any]] = []
        if contact_id:
            associations.append({"to": {"id": str(contact_id)}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 202}]})
        if company_id:
            associations.append({"to": {"id": str(company_id)}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 190}]})
        if deal_id:
            associations.append({"to": {"id": str(deal_id)}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 214}]})
        if not associations:
            raise CRMError("At least one association ID is required to create a note.")
        payload = {"properties": {"hs_note_body": body, "hs_timestamp": utc_now()}, "associations": associations}
        response = request_with_retry(self.settings, "POST", "/crm/v3/objects/notes", payload=payload)
        return {
            "provider": "hubspot",
            "noteId": response.get("id"),
            "contactId": contact_id,
            "companyId": company_id,
            "dealId": deal_id,
            "createdAt": utc_now(),
        }

    def create_contact(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a HubSpot contact."""
        response = request_with_retry(
            self.settings,
            "POST",
            "/crm/v3/objects/contacts",
            payload={"properties": properties},
        )
        return normalize_contact(response)

    def create_company(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a HubSpot company."""
        response = request_with_retry(
            self.settings,
            "POST",
            "/crm/v3/objects/companies",
            payload={"properties": properties},
        )
        return normalize_company(response)

    def create_deal(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a HubSpot deal."""
        payload = {"properties": {"pipeline": self.settings.default_pipeline_id, **properties}}
        response = request_with_retry(self.settings, "POST", "/crm/v3/objects/deals", payload=payload)
        return normalize_deal(response)

    def update_deal_stage(self, deal_id: str, stage: str) -> dict[str, Any]:
        """Update the stage of a HubSpot deal."""
        response = request_with_retry(
            self.settings,
            "PATCH",
            f"/crm/v3/objects/deals/{deal_id}",
            payload={"properties": {"dealstage": stage}},
        )
        normalized = normalize_deal(response)
        normalized["updatedStage"] = stage
        return normalized

    def list_activities(self, *, object_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """List recent tasks as a proxy for timeline activities."""
        payload: dict[str, Any] = {"limit": limit, "properties": ["hs_task_subject", "hs_task_status", "hs_timestamp"]}
        if object_id:
            payload["filterGroups"] = [
                {"filters": [{"propertyName": "hs_object_id", "operator": "EQ", "value": object_id}]}
            ]
        response = request_with_retry(self.settings, "POST", "/crm/v3/objects/tasks/search", payload=payload)
        activities: list[dict[str, Any]] = []
        for item in response.get("results", []):
            props = item.get("properties", {})
            activities.append(
                {
                    "id": str(item.get("id")),
                    "subject": props.get("hs_task_subject"),
                    "status": props.get("hs_task_status"),
                    "timestamp": props.get("hs_timestamp"),
                    "type": "task",
                }
            )
        return activities

    def list_followups(self, *, after: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return deals ordered for follow-up review."""
        response = request_with_retry(
            self.settings,
            "GET",
            "/crm/v3/objects/deals",
            query={
                "limit": limit,
                "properties": ",".join(self.settings.deal_properties + ["dealstage", "amount", "closedate"]),
            },
        )
        deals = [normalize_deal(item) for item in response.get("results", [])]
        if after:
            threshold = parse_iso_datetime(after)
            if threshold is not None:
                deals = [deal for deal in deals if parse_iso_datetime(deal.get("closeDate")) and parse_iso_datetime(deal.get("closeDate")) <= threshold]
        return deals

    def pipeline(self, *, pipeline_id: str | None = None) -> dict[str, Any]:
        """Fetch pipeline stages."""
        resolved_pipeline = pipeline_id or self.settings.default_pipeline_id
        response = request_with_retry(self.settings, "GET", f"/crm/v3/pipelines/deals/{resolved_pipeline}")
        return {
            "provider": "hubspot",
            "pipelineId": response.get("id") or resolved_pipeline,
            "label": response.get("label"),
            "stages": [
                {"id": stage.get("id"), "label": stage.get("label"), "displayOrder": stage.get("displayOrder")}
                for stage in response.get("stages", [])
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
    add_note.add_argument("--body", required=True, help="Note body.")
    add_note.add_argument("--contact-id", help="HubSpot contact ID.")
    add_note.add_argument("--company-id", help="HubSpot company ID.")
    add_note.add_argument("--deal-id", help="HubSpot deal ID.")

    for name in ["create-contact", "create-company", "create-deal"]:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--properties", type=Path, help="Path to a JSON document containing properties.")

    update_stage = subparsers.add_parser("update-deal-stage")
    update_stage.add_argument("--deal-id", required=True, help="HubSpot deal ID.")
    update_stage.add_argument("--stage", required=True, help="Target deal stage.")

    activities = subparsers.add_parser("list-activities")
    activities.add_argument("--object-id", help="HubSpot object ID filter.")
    activities.add_argument("--limit", type=int, default=20, help="Maximum number of activities.")

    followups = subparsers.add_parser("list-followups")
    followups.add_argument("--after", help="Optional ISO 8601 close-date cutoff.")
    followups.add_argument("--limit", type=int, default=50, help="Maximum number of deals.")

    pipeline = subparsers.add_parser("pipeline")
    pipeline.add_argument("--pipeline-id", help="Pipeline ID. Defaults to config default.")
    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings(args.config)
    client = HubSpotClient(settings)

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
            payload = client.add_note(args.body, contact_id=args.contact_id, company_id=args.company_id, deal_id=args.deal_id)
        elif args.command == "create-contact":
            payload = client.create_contact(read_properties(args))
        elif args.command == "create-company":
            payload = client.create_company(read_properties(args))
        elif args.command == "create-deal":
            payload = client.create_deal(read_properties(args))
        elif args.command == "update-deal-stage":
            payload = client.update_deal_stage(args.deal_id, args.stage)
        elif args.command == "list-activities":
            payload = client.list_activities(object_id=args.object_id, limit=args.limit)
        elif args.command == "list-followups":
            payload = client.list_followups(after=args.after, limit=args.limit)
        elif args.command == "pipeline":
            payload = client.pipeline(pipeline_id=args.pipeline_id)
        else:
            parser.error(f"Unsupported command: {args.command}")
            return 2
    except CRMError as exc:
        LOG.error("hubspot command failed", extra={"event": {"command": args.command, "error": str(exc)}})
        sys.stderr.write(f"{exc}\n")
        return 1

    dump_output(payload, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
