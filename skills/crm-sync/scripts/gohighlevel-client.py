#!/usr/bin/env python3
"""GoHighLevel CRM API wrapper for OpsClaw CRM Sync."""

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
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent


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
LOG = LOGGER_MODULE.get_logger("opsclaw.crm.gohighlevel")


class CRMError(RuntimeError):
    """Base GoHighLevel client error."""


class RateLimitError(CRMError):
    """Raised when GoHighLevel returns a rate limit response."""


@dataclass(frozen=True)
class RetryConfig:
    """Retry settings for transient GoHighLevel failures."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 20.0
    jitter: float = 0.5


@dataclass(frozen=True)
class OAuthSettings:
    """Resolved OAuth2 settings for GoHighLevel."""

    client_id: str
    client_secret: str
    redirect_uri: str
    authorize_url: str
    token_url: str
    scopes: list[str]
    token_store: Path | None


@dataclass(frozen=True)
class GoHighLevelSettings:
    """Resolved GoHighLevel runtime configuration."""

    base_url: str
    api_version: str
    token: str
    token_env: str
    default_location_id: str | None
    default_pipeline_id: str | None
    default_calendar_id: str | None
    retry: RetryConfig
    oauth: OAuthSettings | None
    webhook_target_url: str | None
    webhook_events: list[str]
    source_config: Path


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: Any) -> None:
    """Write JSON to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def resolve_path(base_path: Path, raw_value: str | None) -> Path | None:
    """Resolve a possibly relative path against the config location."""
    if not raw_value:
        return None
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return (base_path.parent / candidate).resolve()


def utc_now() -> str:
    """Return the current UTC timestamp as ISO 8601."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp when present."""
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def split_name(name: str | None) -> tuple[str, str]:
    """Split a full name into first and last name components."""
    if not name:
        return "", ""
    parts = [part for part in name.strip().split(" ") if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def first_present(record: dict[str, Any], *keys: str) -> Any:
    """Return the first present value from a record."""
    for key in keys:
        value = record.get(key)
        if value not in {None, ""}:
            return value
    return None


def extract_items(payload: Any, *keys: str) -> list[dict[str, Any]]:
    """Extract a list of records from a GoHighLevel API response."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if "data" in payload and isinstance(payload["data"], list):
        return [item for item in payload["data"] if isinstance(item, dict)]
    if all(key not in payload for key in keys) and any(isinstance(value, dict) for value in payload.values()):
        return [value for value in payload.values() if isinstance(value, dict)]
    return []


def extract_record(payload: Any, *keys: str) -> dict[str, Any]:
    """Extract a single record from a GoHighLevel API response."""
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload
    raise CRMError("Expected a JSON object in the GoHighLevel response.")


def normalize_contact(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GoHighLevel contact object."""
    first_name = first_present(record, "firstName", "first_name")
    last_name = first_present(record, "lastName", "last_name")
    full_name = " ".join(part for part in [str(first_name or ""), str(last_name or "")] if part).strip()
    return {
        "id": str(first_present(record, "id", "_id") or ""),
        "name": full_name or first_present(record, "name") or first_present(record, "email") or "Unknown contact",
        "firstName": first_name,
        "lastName": last_name,
        "email": first_present(record, "email"),
        "phone": first_present(record, "phone"),
        "companyName": first_present(record, "companyName", "company_name"),
        "locationId": first_present(record, "locationId", "location_id"),
        "tags": record.get("tags") or [],
        "source": first_present(record, "source"),
        "createdAt": first_present(record, "dateAdded", "createdAt"),
        "updatedAt": first_present(record, "dateUpdated", "updatedAt"),
        "raw": record,
    }


def normalize_pipeline(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GoHighLevel pipeline object."""
    return {
        "id": str(first_present(record, "id", "_id") or ""),
        "name": first_present(record, "name") or "Untitled pipeline",
        "locationId": first_present(record, "locationId", "location_id"),
        "stages": [
            {
                "id": str(first_present(stage, "id", "_id") or ""),
                "name": first_present(stage, "name") or "Unnamed stage",
                "position": first_present(stage, "position"),
                "raw": stage,
            }
            for stage in record.get("stages", [])
            if isinstance(stage, dict)
        ],
        "raw": record,
    }


def normalize_opportunity(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GoHighLevel opportunity object."""
    return {
        "id": str(first_present(record, "id", "_id") or ""),
        "name": first_present(record, "name", "title") or "Untitled opportunity",
        "contactId": first_present(record, "contactId", "contact_id"),
        "locationId": first_present(record, "locationId", "location_id"),
        "pipelineId": first_present(record, "pipelineId", "pipeline_id"),
        "pipelineStageId": first_present(record, "pipelineStageId", "pipeline_stage_id"),
        "status": first_present(record, "status"),
        "monetaryValue": first_present(record, "monetaryValue", "value"),
        "assignedTo": first_present(record, "assignedTo"),
        "createdAt": first_present(record, "createdAt"),
        "updatedAt": first_present(record, "updatedAt"),
        "raw": record,
    }


def normalize_conversation(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GoHighLevel conversation object."""
    return {
        "id": str(first_present(record, "id", "_id") or ""),
        "contactId": first_present(record, "contactId", "contact_id"),
        "locationId": first_present(record, "locationId", "location_id"),
        "type": first_present(record, "type"),
        "status": first_present(record, "status"),
        "unreadCount": first_present(record, "unreadCount"),
        "lastMessageBody": first_present(record, "lastMessageBody", "lastMessageType"),
        "updatedAt": first_present(record, "dateUpdated", "updatedAt"),
        "raw": record,
    }


def normalize_message(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GoHighLevel conversation message object."""
    return {
        "id": str(first_present(record, "id", "_id") or ""),
        "conversationId": first_present(record, "conversationId", "conversation_id"),
        "contactId": first_present(record, "contactId", "contact_id"),
        "type": first_present(record, "type", "messageType", "direction"),
        "status": first_present(record, "status"),
        "body": first_present(record, "body", "message"),
        "emailMessageId": first_present(record, "emailMessageId"),
        "createdAt": first_present(record, "dateAdded", "createdAt"),
        "raw": record,
    }


def normalize_calendar(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GoHighLevel calendar object."""
    return {
        "id": str(first_present(record, "id", "_id") or ""),
        "name": first_present(record, "name") or "Untitled calendar",
        "locationId": first_present(record, "locationId", "location_id"),
        "groupId": first_present(record, "groupId", "calendarGroupId"),
        "isActive": first_present(record, "isActive", "active"),
        "raw": record,
    }


def normalize_appointment(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a GoHighLevel appointment or booking object."""
    return {
        "id": str(first_present(record, "id", "_id") or ""),
        "calendarId": first_present(record, "calendarId", "calendar_id"),
        "contactId": first_present(record, "contactId", "contact_id"),
        "locationId": first_present(record, "locationId", "location_id"),
        "title": first_present(record, "title", "appointmentTitle") or "Appointment",
        "status": first_present(record, "appointmentStatus", "status"),
        "startTime": first_present(record, "startTime", "start_time"),
        "endTime": first_present(record, "endTime", "end_time"),
        "assignedUserId": first_present(record, "assignedUserId"),
        "raw": record,
    }


def load_settings(config_path: Path) -> GoHighLevelSettings:
    """Load GoHighLevel settings from a config template."""
    config = load_json(config_path)
    config_doc = config.get("gohighlevel", config) if isinstance(config, dict) else {}
    retry_doc = config.get("retry", {}) if isinstance(config, dict) else {}
    auth_doc = config_doc.get("auth", {}) if isinstance(config_doc, dict) else {}
    oauth_doc = auth_doc.get("oauth2", {}) if isinstance(auth_doc, dict) else {}
    token_env = str(auth_doc.get("accessTokenEnv") or config_doc.get("tokenEnv") or "GOHIGHLEVEL_ACCESS_TOKEN")
    token_store = resolve_path(config_path, str(oauth_doc.get("tokenStore") or "")) if oauth_doc else None
    token = os.environ.get(token_env)
    if not token and token_store and token_store.exists():
        token_payload = load_json(token_store)
        token = str(token_payload.get("access_token") or "")
    if not token:
        raise CRMError(
            f"Missing GoHighLevel access token. Export {token_env} or populate the OAuth token store."
        )

    oauth_settings: OAuthSettings | None = None
    client_id_env = str(oauth_doc.get("clientIdEnv") or "GOHIGHLEVEL_CLIENT_ID")
    client_secret_env = str(oauth_doc.get("clientSecretEnv") or "GOHIGHLEVEL_CLIENT_SECRET")
    redirect_uri = str(oauth_doc.get("redirectUri") or "")
    client_id = os.environ.get(client_id_env, "")
    client_secret = os.environ.get(client_secret_env, "")
    if client_id and client_secret and redirect_uri:
        oauth_settings = OAuthSettings(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            authorize_url=str(oauth_doc.get("authorizeUrl") or "https://marketplace.gohighlevel.com/oauth/chooselocation"),
            token_url=str(oauth_doc.get("tokenUrl") or "https://services.leadconnectorhq.com/oauth/token"),
            scopes=[str(scope) for scope in oauth_doc.get("scopes", [])],
            token_store=token_store,
        )

    webhook_doc = config_doc.get("webhooks", {}) if isinstance(config_doc, dict) else {}
    return GoHighLevelSettings(
        base_url=str(config_doc.get("baseUrl") or "https://services.leadconnectorhq.com").rstrip("/"),
        api_version=str(config_doc.get("version") or "2021-07-28"),
        token=token,
        token_env=token_env,
        default_location_id=str(config_doc.get("defaultLocationId") or "") or None,
        default_pipeline_id=str(config_doc.get("defaultPipelineId") or "") or None,
        default_calendar_id=str(config_doc.get("defaultCalendarId") or "") or None,
        retry=RetryConfig(
            max_retries=int(retry_doc.get("maxRetries", 3)),
            base_delay=float(retry_doc.get("baseDelaySeconds", 1.0)),
            max_delay=float(retry_doc.get("maxDelaySeconds", 20.0)),
            jitter=float(retry_doc.get("jitterSeconds", 0.5)),
        ),
        oauth=oauth_settings,
        webhook_target_url=str(webhook_doc.get("targetUrl") or "") or None,
        webhook_events=[str(event) for event in webhook_doc.get("events", [])],
        source_config=config_path.resolve(),
    )


def encode_query(params: dict[str, Any] | None) -> str:
    """Encode query parameters while omitting empty values."""
    filtered = {key: value for key, value in (params or {}).items() if value not in {None, "", []}}
    return urllib.parse.urlencode(filtered, doseq=True)


def read_token_store(settings: GoHighLevelSettings) -> dict[str, Any] | None:
    """Load token metadata from disk when configured."""
    if settings.oauth is None or settings.oauth.token_store is None or not settings.oauth.token_store.exists():
        return None
    return load_json(settings.oauth.token_store)


def persist_token_store(settings: GoHighLevelSettings, payload: dict[str, Any]) -> None:
    """Persist OAuth token metadata to the configured token store."""
    if settings.oauth is None or settings.oauth.token_store is None:
        return
    dump_json(settings.oauth.token_store, payload)


def _raw_request(
    settings: GoHighLevelSettings,
    method: str,
    path: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
    content_type: str | None = None,
) -> Any:
    """Execute a single HTTP request against GoHighLevel."""
    url = settings.base_url + path
    query_string = encode_query(query)
    if query_string:
        url += "?" + query_string
    body: bytes | None = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Version": settings.api_version,
    }
    if form is not None:
        headers["Content-Type"] = content_type or "application/x-www-form-urlencoded"
        body = urllib.parse.urlencode(form).encode("utf-8")
    elif payload is not None:
        headers["Content-Type"] = content_type or "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url=url, data=body, headers=headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def refresh_access_token(settings: GoHighLevelSettings) -> tuple[GoHighLevelSettings, dict[str, Any]]:
    """Refresh the OAuth access token using the stored refresh token."""
    if settings.oauth is None:
        raise CRMError("OAuth2 is not configured for this GoHighLevel client.")
    token_state = read_token_store(settings) or {}
    refresh_token = str(token_state.get("refresh_token") or "")
    if not refresh_token:
        raise CRMError("OAuth token store does not contain a refresh token.")
    payload = {
        "grant_type": "refresh_token",
        "client_id": settings.oauth.client_id,
        "client_secret": settings.oauth.client_secret,
        "refresh_token": refresh_token,
        "redirect_uri": settings.oauth.redirect_uri,
    }
    request = urllib.request.Request(
        url=settings.oauth.token_url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            token_doc = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise CRMError(f"GoHighLevel OAuth refresh failed with {exc.code}: {raw_error}") from exc
    if "access_token" not in token_doc:
        raise CRMError("GoHighLevel OAuth refresh did not return an access_token.")
    merged_token_doc = {**token_state, **token_doc, "refreshed_at": utc_now()}
    persist_token_store(settings, merged_token_doc)
    updated_settings = replace(settings, token=str(token_doc["access_token"]))
    return updated_settings, merged_token_doc


def request_with_retry(
    settings: GoHighLevelSettings,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    form: dict[str, Any] | None = None,
) -> tuple[GoHighLevelSettings, Any]:
    """Execute a GoHighLevel API request with bounded retries."""
    current_settings = settings
    refreshed = False
    for attempt in range(current_settings.retry.max_retries + 1):
        try:
            response = _raw_request(
                current_settings,
                method,
                path,
                token=current_settings.token,
                payload=payload,
                query=query,
                form=form,
            )
            return current_settings, response
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            try:
                error_doc = json.loads(raw_error) if raw_error else {}
            except json.JSONDecodeError:
                error_doc = {"message": raw_error}
            if exc.code == 401 and current_settings.oauth is not None and not refreshed:
                current_settings, token_state = refresh_access_token(current_settings)
                refreshed = True
                LOG.info("gohighlevel oauth token refreshed", extra={"event": {"tokenState": token_state.get("refreshed_at")}})
                continue
            if exc.code == 429:
                if attempt >= current_settings.retry.max_retries:
                    raise RateLimitError(f"GoHighLevel API returned 429: {error_doc}") from exc
                retry_after = float(exc.headers.get("Retry-After", "0") or 0)
                delay = max(retry_after, min(current_settings.retry.base_delay * (2**attempt), current_settings.retry.max_delay))
                delay += random.uniform(0, current_settings.retry.jitter)
                LOG.warning(
                    "gohighlevel rate limited, retrying",
                    extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "path": path}},
                )
                time.sleep(delay)
                continue
            if 500 <= exc.code < 600:
                if attempt >= current_settings.retry.max_retries:
                    raise CRMError(f"GoHighLevel API failed after retries: {error_doc}") from exc
                delay = min(current_settings.retry.base_delay * (2**attempt), current_settings.retry.max_delay)
                delay += random.uniform(0, current_settings.retry.jitter)
                LOG.warning(
                    "gohighlevel transient server error, retrying",
                    extra={
                        "event": {"attempt": attempt + 1, "status": exc.code, "delaySeconds": round(delay, 2), "path": path}
                    },
                )
                time.sleep(delay)
                continue
            raise CRMError(f"GoHighLevel API returned {exc.code}: {error_doc}") from exc
        except urllib.error.URLError as exc:
            if attempt >= current_settings.retry.max_retries:
                raise CRMError(f"GoHighLevel network error: {exc.reason}") from exc
            delay = min(current_settings.retry.base_delay * (2**attempt), current_settings.retry.max_delay)
            delay += random.uniform(0, current_settings.retry.jitter)
            LOG.warning(
                "gohighlevel network error, retrying",
                extra={"event": {"attempt": attempt + 1, "delaySeconds": round(delay, 2), "path": path}},
            )
            time.sleep(delay)
    raise CRMError("GoHighLevel retry loop exhausted unexpectedly.")


class GoHighLevelClient:
    """Thin GoHighLevel wrapper with deterministic JSON output."""

    def __init__(self, settings: GoHighLevelSettings) -> None:
        self.settings = settings

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a request and keep settings in sync after token refresh."""
        self.settings, response = request_with_retry(self.settings, method, path, payload=payload, query=query, form=form)
        return response

    def build_authorization_url(self, state: str, *, user_type: str = "Location", redirect_uri: str | None = None) -> dict[str, Any]:
        """Build the OAuth authorization URL for a marketplace app install flow."""
        if self.settings.oauth is None:
            raise CRMError("OAuth2 is not configured for this GoHighLevel client.")
        resolved_redirect = redirect_uri or self.settings.oauth.redirect_uri
        params = {
            "response_type": "code",
            "redirect_uri": resolved_redirect,
            "client_id": self.settings.oauth.client_id,
            "scope": " ".join(self.settings.oauth.scopes),
            "state": state,
            "user_type": user_type,
        }
        return {
            "provider": "gohighlevel",
            "authorizationUrl": self.settings.oauth.authorize_url + "?" + urllib.parse.urlencode(params),
            "state": state,
            "userType": user_type,
            "redirectUri": resolved_redirect,
            "scopes": self.settings.oauth.scopes,
        }

    def exchange_oauth_code(self, code: str, *, user_type: str = "Location", redirect_uri: str | None = None) -> dict[str, Any]:
        """Exchange an OAuth authorization code for tokens."""
        if self.settings.oauth is None:
            raise CRMError("OAuth2 is not configured for this GoHighLevel client.")
        payload = {
            "client_id": self.settings.oauth.client_id,
            "client_secret": self.settings.oauth.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or self.settings.oauth.redirect_uri,
            "user_type": user_type,
        }
        request = urllib.request.Request(
            url=self.settings.oauth.token_url,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                token_doc = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise CRMError(f"GoHighLevel OAuth token exchange failed with {exc.code}: {raw_error}") from exc
        token_doc["obtained_at"] = utc_now()
        persist_token_store(self.settings, token_doc)
        if "access_token" in token_doc:
            self.settings = replace(self.settings, token=str(token_doc["access_token"]))
        return token_doc

    def refresh_oauth_token(self) -> dict[str, Any]:
        """Refresh an OAuth token and persist the result."""
        self.settings, token_doc = refresh_access_token(self.settings)
        return token_doc

    def list_contacts(self, *, location_id: str | None = None, limit: int = 100, start_after: str | None = None) -> dict[str, Any]:
        """List contacts for a location."""
        response = self._request(
            "GET",
            "/contacts/",
            query={"locationId": location_id or self.settings.default_location_id, "limit": limit, "startAfter": start_after},
        )
        records = extract_items(response, "contacts")
        return {
            "provider": "gohighlevel",
            "contacts": [normalize_contact(item) for item in records],
            "count": len(records),
            "startAfter": response.get("meta", {}).get("startAfter") if isinstance(response, dict) else None,
            "listedAt": utc_now(),
        }

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        """Fetch a single contact."""
        response = self._request("GET", f"/contacts/{contact_id}")
        return normalize_contact(extract_record(response, "contact"))

    def create_contact(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a GoHighLevel contact."""
        payload = dict(properties)
        if not payload.get("locationId") and self.settings.default_location_id:
            payload["locationId"] = self.settings.default_location_id
        response = self._request("POST", "/contacts/", payload=payload)
        return normalize_contact(extract_record(response, "contact"))

    def update_contact(self, contact_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Update a GoHighLevel contact."""
        response = self._request("PUT", f"/contacts/{contact_id}", payload=properties)
        return normalize_contact(extract_record(response, "contact"))

    def search_contacts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Search contacts using the documented advanced search endpoint."""
        request_payload = dict(payload)
        if not request_payload.get("locationId") and self.settings.default_location_id:
            request_payload["locationId"] = self.settings.default_location_id
        response = self._request("POST", "/contacts/search", payload=request_payload)
        records = extract_items(response, "contacts")
        return {
            "provider": "gohighlevel",
            "contacts": [normalize_contact(item) for item in records],
            "count": len(records),
            "searchedAt": utc_now(),
            "raw": response,
        }

    def add_tags(self, contact_id: str, tags: list[str]) -> dict[str, Any]:
        """Add one or more tags to a contact."""
        response = self._request("POST", f"/contacts/{contact_id}/tags", payload={"tags": tags})
        record = extract_record(response, "contact")
        return {
            "provider": "gohighlevel",
            "contactId": contact_id,
            "tagsAdded": tags,
            "contact": normalize_contact(record),
            "updatedAt": utc_now(),
        }

    def remove_tags(self, contact_id: str, tags: list[str]) -> dict[str, Any]:
        """Remove one or more tags from a contact."""
        response = self._request("DELETE", f"/contacts/{contact_id}/tags", payload={"tags": tags})
        record = extract_record(response, "contact")
        return {
            "provider": "gohighlevel",
            "contactId": contact_id,
            "tagsRemoved": tags,
            "contact": normalize_contact(record),
            "updatedAt": utc_now(),
        }

    def list_pipelines(self, *, location_id: str | None = None) -> dict[str, Any]:
        """List pipelines for a location."""
        response = self._request("GET", "/opportunities/pipelines", query={"locationId": location_id or self.settings.default_location_id})
        records = extract_items(response, "pipelines")
        return {
            "provider": "gohighlevel",
            "pipelines": [normalize_pipeline(item) for item in records],
            "count": len(records),
            "listedAt": utc_now(),
        }

    def list_opportunities(
        self,
        *,
        location_id: str | None = None,
        pipeline_id: str | None = None,
        pipeline_stage_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """List opportunities via the documented search endpoint."""
        payload: dict[str, Any] = {
            "locationId": location_id or self.settings.default_location_id,
            "pipelineId": pipeline_id or self.settings.default_pipeline_id,
            "pipelineStageId": pipeline_stage_id,
            "status": status,
            "limit": limit,
        }
        response = self._request("POST", "/opportunities/search", payload=payload)
        records = extract_items(response, "opportunities")
        return {
            "provider": "gohighlevel",
            "opportunities": [normalize_opportunity(item) for item in records],
            "count": len(records),
            "listedAt": utc_now(),
            "raw": response,
        }

    def create_opportunity(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create an opportunity."""
        payload = dict(properties)
        if not payload.get("locationId") and self.settings.default_location_id:
            payload["locationId"] = self.settings.default_location_id
        if not payload.get("pipelineId") and self.settings.default_pipeline_id:
            payload["pipelineId"] = self.settings.default_pipeline_id
        response = self._request("POST", "/opportunities/", payload=payload)
        return normalize_opportunity(extract_record(response, "opportunity"))

    def update_opportunity_stage(
        self,
        opportunity_id: str,
        pipeline_stage_id: str,
        *,
        status: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update the pipeline stage for an opportunity."""
        payload = {"pipelineStageId": pipeline_stage_id}
        if status:
            payload["status"] = status
        if extra_fields:
            payload.update(extra_fields)
        response = self._request("PUT", f"/opportunities/{opportunity_id}", payload=payload)
        normalized = normalize_opportunity(extract_record(response, "opportunity"))
        normalized["updatedStage"] = pipeline_stage_id
        if status:
            normalized["updatedStatus"] = status
        return normalized

    def add_opportunity_note(self, contact_id: str, body: str, *, opportunity_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        """Create a note on the related contact and attach opportunity context in the payload."""
        payload: dict[str, Any] = {"body": body}
        if opportunity_id:
            payload["opportunityId"] = opportunity_id
        if user_id:
            payload["userId"] = user_id
        response = self._request("POST", f"/contacts/{contact_id}/notes", payload=payload)
        note_doc = extract_record(response, "note")
        return {
            "provider": "gohighlevel",
            "contactId": contact_id,
            "opportunityId": opportunity_id,
            "noteId": first_present(note_doc, "id", "_id"),
            "createdAt": first_present(note_doc, "dateAdded", "createdAt") or utc_now(),
            "raw": response,
        }

    def list_conversations(
        self,
        *,
        location_id: str | None = None,
        limit: int = 100,
        query_text: str | None = None,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        """List conversations for a location."""
        response = self._request(
            "GET",
            "/conversations/search",
            query={
                "locationId": location_id or self.settings.default_location_id,
                "limit": limit,
                "query": query_text,
                "contactId": contact_id,
            },
        )
        records = extract_items(response, "conversations")
        return {
            "provider": "gohighlevel",
            "conversations": [normalize_conversation(item) for item in records],
            "count": len(records),
            "listedAt": utc_now(),
        }

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        """Fetch a single conversation."""
        response = self._request("GET", f"/conversations/{conversation_id}")
        return normalize_conversation(extract_record(response, "conversation"))

    def get_messages(self, conversation_id: str, *, limit: int = 100, last_message_id: str | None = None) -> dict[str, Any]:
        """List messages for a conversation."""
        response = self._request(
            "GET",
            f"/conversations/{conversation_id}/messages",
            query={"limit": limit, "lastMessageId": last_message_id},
        )
        records = extract_items(response, "messages")
        return {
            "provider": "gohighlevel",
            "conversationId": conversation_id,
            "messages": [normalize_message(item) for item in records],
            "count": len(records),
            "listedAt": utc_now(),
        }

    def send_message(
        self,
        contact_id: str,
        body: str,
        *,
        channel: str,
        conversation_id: str | None = None,
        location_id: str | None = None,
        subject: str | None = None,
        html: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send an SMS, email, or WhatsApp message."""
        normalized_channel = channel.lower()
        channel_map = {"sms": "SMS", "email": "Email", "whatsapp": "WhatsApp"}
        if normalized_channel not in channel_map:
            raise CRMError("channel must be one of: sms, email, whatsapp")
        payload: dict[str, Any] = {
            "type": channel_map[normalized_channel],
            "contactId": contact_id,
            "message": body,
            "locationId": location_id or self.settings.default_location_id,
        }
        if conversation_id:
            payload["conversationId"] = conversation_id
        if subject:
            payload["subject"] = subject
        if html:
            payload["html"] = html
        if attachments:
            payload["attachments"] = attachments
        response = self._request("POST", "/conversations/messages", payload=payload)
        return {
            "provider": "gohighlevel",
            "channel": normalized_channel,
            "contactId": contact_id,
            "message": normalize_message(extract_record(response, "message")),
            "sentAt": utc_now(),
        }

    def list_calendars(self, *, location_id: str | None = None, group_id: str | None = None) -> dict[str, Any]:
        """List calendars for a location."""
        response = self._request(
            "GET",
            "/calendars/",
            query={"locationId": location_id or self.settings.default_location_id, "groupId": group_id},
        )
        records = extract_items(response, "calendars")
        return {
            "provider": "gohighlevel",
            "calendars": [normalize_calendar(item) for item in records],
            "count": len(records),
            "listedAt": utc_now(),
        }

    def get_appointments(
        self,
        *,
        calendar_id: str | None = None,
        location_id: str | None = None,
        contact_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        """List calendar appointments."""
        response = self._request(
            "GET",
            "/calendars/events/appointments",
            query={
                "calendarId": calendar_id or self.settings.default_calendar_id,
                "locationId": location_id or self.settings.default_location_id,
                "contactId": contact_id,
                "startTime": start_time,
                "endTime": end_time,
            },
        )
        records = extract_items(response, "events", "appointments")
        return {
            "provider": "gohighlevel",
            "appointments": [normalize_appointment(item) for item in records],
            "count": len(records),
            "listedAt": utc_now(),
        }

    def create_booking(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a booking using the service booking endpoint."""
        request_payload = dict(payload)
        if not request_payload.get("locationId") and self.settings.default_location_id:
            request_payload["locationId"] = self.settings.default_location_id
        if not request_payload.get("calendarId") and self.settings.default_calendar_id:
            request_payload["calendarId"] = self.settings.default_calendar_id
        response = self._request("POST", "/calendars/events/appointments", payload=request_payload)
        return {
            "provider": "gohighlevel",
            "booking": normalize_appointment(extract_record(response, "event", "appointment", "booking")),
            "createdAt": utc_now(),
        }

    def trigger_workflow(self, contact_id: str, workflow_id: str) -> dict[str, Any]:
        """Trigger a workflow for a contact."""
        response = self._request("POST", f"/contacts/{contact_id}/workflow/{workflow_id}")
        return {
            "provider": "gohighlevel",
            "contactId": contact_id,
            "workflowId": workflow_id,
            "triggeredAt": utc_now(),
            "raw": response,
        }

    def list_webhooks(self) -> dict[str, Any]:
        """Return webhook subscriptions defined in local config.

        GoHighLevel documents webhook subscriptions through Marketplace app configuration.
        No public REST endpoint for listing subscriptions is documented in the referenced docs.
        """
        return {
            "provider": "gohighlevel",
            "mode": "config-helper",
            "targetUrl": self.settings.webhook_target_url,
            "events": self.settings.webhook_events,
            "count": len(self.settings.webhook_events),
            "listedAt": utc_now(),
        }

    def register_webhook(self, target_url: str | None = None, events: list[str] | None = None) -> dict[str, Any]:
        """Return a normalized webhook subscription payload for Marketplace app setup.

        This is a helper because the official docs do not expose a public REST endpoint for
        programmatic webhook registration.
        """
        resolved_target_url = target_url or self.settings.webhook_target_url
        resolved_events = events or self.settings.webhook_events
        if not resolved_target_url:
            raise CRMError("A webhook target URL is required.")
        if not resolved_events:
            raise CRMError("At least one webhook event is required.")
        return {
            "provider": "gohighlevel",
            "mode": "config-helper",
            "targetUrl": resolved_target_url,
            "events": resolved_events,
            "instructions": "Configure these events in your GoHighLevel Marketplace app webhook settings.",
            "generatedAt": utc_now(),
        }


def load_payload(path: Path | None) -> dict[str, Any]:
    """Load a JSON payload from a file path or stdin."""
    if path is not None:
        payload = load_json(path)
    else:
        payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise CRMError("Expected a JSON object payload.")
    return payload


def dump_output(payload: Any, *, pretty: bool) -> None:
    """Write JSON payload to stdout."""
    json.dump(payload, sys.stdout, indent=2 if pretty else None)
    sys.stdout.write("\n")


def parse_tags(value: str) -> list[str]:
    """Parse a comma-separated tag list."""
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Path to the GoHighLevel config JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_url = subparsers.add_parser("oauth-authorize-url")
    auth_url.add_argument("--state", required=True, help="Opaque state value for the OAuth flow.")
    auth_url.add_argument("--user-type", default="Location", choices=["Location", "Company"], help="OAuth install user type.")

    oauth_exchange = subparsers.add_parser("oauth-exchange-code")
    oauth_exchange.add_argument("--code", required=True, help="OAuth authorization code.")
    oauth_exchange.add_argument("--user-type", default="Location", choices=["Location", "Company"], help="OAuth install user type.")

    subparsers.add_parser("oauth-refresh-token")

    list_contacts = subparsers.add_parser("list-contacts")
    list_contacts.add_argument("--location-id", help="Location ID. Defaults to config.")
    list_contacts.add_argument("--limit", type=int, default=100, help="Maximum number of contacts.")
    list_contacts.add_argument("--start-after", help="Pagination cursor.")

    get_contact = subparsers.add_parser("get-contact")
    get_contact.add_argument("--contact-id", required=True, help="Contact ID.")

    for name in ["create-contact", "update-contact", "search-contacts", "create-opportunity", "create-booking"]:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--input", type=Path, help="Path to a JSON payload file. Reads stdin if omitted.")

    update_contact = subparsers.add_parser("update-contact-fields")
    update_contact.add_argument("--contact-id", required=True, help="Contact ID.")
    update_contact.add_argument("--input", type=Path, help="Path to a JSON payload file. Reads stdin if omitted.")

    for name in ["add-tags", "remove-tags"]:
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--contact-id", required=True, help="Contact ID.")
        subparser.add_argument("--tags", required=True, help="Comma-separated list of tags.")

    pipelines = subparsers.add_parser("list-pipelines")
    pipelines.add_argument("--location-id", help="Location ID. Defaults to config.")

    list_opps = subparsers.add_parser("list-opportunities")
    list_opps.add_argument("--location-id", help="Location ID. Defaults to config.")
    list_opps.add_argument("--pipeline-id", help="Pipeline ID.")
    list_opps.add_argument("--pipeline-stage-id", help="Pipeline stage ID.")
    list_opps.add_argument("--status", help="Opportunity status.")
    list_opps.add_argument("--limit", type=int, default=100, help="Maximum number of opportunities.")

    update_stage = subparsers.add_parser("update-opportunity-stage")
    update_stage.add_argument("--opportunity-id", required=True, help="Opportunity ID.")
    update_stage.add_argument("--pipeline-stage-id", required=True, help="Target pipeline stage ID.")
    update_stage.add_argument("--status", help="Optional new status.")
    update_stage.add_argument("--input", type=Path, help="Optional extra fields JSON payload.")

    add_note = subparsers.add_parser("add-opportunity-note")
    add_note.add_argument("--contact-id", required=True, help="Related contact ID.")
    add_note.add_argument("--body", required=True, help="Note body.")
    add_note.add_argument("--opportunity-id", help="Opportunity ID to include in the note payload.")
    add_note.add_argument("--user-id", help="User ID for the note.")

    list_conversations = subparsers.add_parser("list-conversations")
    list_conversations.add_argument("--location-id", help="Location ID. Defaults to config.")
    list_conversations.add_argument("--limit", type=int, default=100, help="Maximum number of conversations.")
    list_conversations.add_argument("--query", help="Optional free-text query.")
    list_conversations.add_argument("--contact-id", help="Optional contact ID filter.")

    get_conversation = subparsers.add_parser("get-conversation")
    get_conversation.add_argument("--conversation-id", required=True, help="Conversation ID.")

    get_messages = subparsers.add_parser("get-messages")
    get_messages.add_argument("--conversation-id", required=True, help="Conversation ID.")
    get_messages.add_argument("--limit", type=int, default=100, help="Maximum number of messages.")
    get_messages.add_argument("--last-message-id", help="Pagination cursor.")

    send_message = subparsers.add_parser("send-message")
    send_message.add_argument("--contact-id", required=True, help="Contact ID.")
    send_message.add_argument("--channel", required=True, choices=["sms", "email", "whatsapp"], help="Message channel.")
    send_message.add_argument("--body", required=True, help="Message body.")
    send_message.add_argument("--conversation-id", help="Conversation ID.")
    send_message.add_argument("--subject", help="Email subject.")
    send_message.add_argument("--html", help="HTML body for email messages.")
    send_message.add_argument("--input", type=Path, help="Optional JSON payload file containing attachments.")

    list_calendars = subparsers.add_parser("list-calendars")
    list_calendars.add_argument("--location-id", help="Location ID. Defaults to config.")
    list_calendars.add_argument("--group-id", help="Calendar group ID.")

    appointments = subparsers.add_parser("get-appointments")
    appointments.add_argument("--calendar-id", help="Calendar ID. Defaults to config.")
    appointments.add_argument("--location-id", help="Location ID. Defaults to config.")
    appointments.add_argument("--contact-id", help="Contact ID filter.")
    appointments.add_argument("--start-time", help="ISO 8601 start time filter.")
    appointments.add_argument("--end-time", help="ISO 8601 end time filter.")

    workflow = subparsers.add_parser("trigger-workflow")
    workflow.add_argument("--contact-id", required=True, help="Contact ID.")
    workflow.add_argument("--workflow-id", required=True, help="Workflow ID.")

    webhooks_list = subparsers.add_parser("list-webhooks")

    webhooks_register = subparsers.add_parser("register-webhook")
    webhooks_register.add_argument("--target-url", help="Webhook target URL. Defaults to config.")
    webhooks_register.add_argument("--events", help="Comma-separated webhook events. Defaults to config.")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings(args.config)
    client = GoHighLevelClient(settings)

    try:
        if args.command == "oauth-authorize-url":
            payload = client.build_authorization_url(args.state, user_type=args.user_type)
        elif args.command == "oauth-exchange-code":
            payload = client.exchange_oauth_code(args.code, user_type=args.user_type)
        elif args.command == "oauth-refresh-token":
            payload = client.refresh_oauth_token()
        elif args.command == "list-contacts":
            payload = client.list_contacts(location_id=args.location_id, limit=args.limit, start_after=args.start_after)
        elif args.command == "get-contact":
            payload = client.get_contact(args.contact_id)
        elif args.command == "create-contact":
            payload = client.create_contact(load_payload(args.input))
        elif args.command == "update-contact":
            input_payload = load_payload(args.input)
            contact_id = str(input_payload.get("id") or input_payload.get("contactId") or "")
            if not contact_id:
                raise CRMError("update-contact requires an input payload containing id or contactId.")
            payload = client.update_contact(contact_id, input_payload)
        elif args.command == "update-contact-fields":
            payload = client.update_contact(args.contact_id, load_payload(args.input))
        elif args.command == "search-contacts":
            payload = client.search_contacts(load_payload(args.input))
        elif args.command == "add-tags":
            payload = client.add_tags(args.contact_id, parse_tags(args.tags))
        elif args.command == "remove-tags":
            payload = client.remove_tags(args.contact_id, parse_tags(args.tags))
        elif args.command == "list-pipelines":
            payload = client.list_pipelines(location_id=args.location_id)
        elif args.command == "list-opportunities":
            payload = client.list_opportunities(
                location_id=args.location_id,
                pipeline_id=args.pipeline_id,
                pipeline_stage_id=args.pipeline_stage_id,
                status=args.status,
                limit=args.limit,
            )
        elif args.command == "create-opportunity":
            payload = client.create_opportunity(load_payload(args.input))
        elif args.command == "update-opportunity-stage":
            payload = client.update_opportunity_stage(
                args.opportunity_id,
                args.pipeline_stage_id,
                status=args.status,
                extra_fields=load_payload(args.input) if args.input else None,
            )
        elif args.command == "add-opportunity-note":
            payload = client.add_opportunity_note(
                args.contact_id,
                args.body,
                opportunity_id=args.opportunity_id,
                user_id=args.user_id,
            )
        elif args.command == "list-conversations":
            payload = client.list_conversations(
                location_id=args.location_id,
                limit=args.limit,
                query_text=args.query,
                contact_id=args.contact_id,
            )
        elif args.command == "get-conversation":
            payload = client.get_conversation(args.conversation_id)
        elif args.command == "get-messages":
            payload = client.get_messages(args.conversation_id, limit=args.limit, last_message_id=args.last_message_id)
        elif args.command == "send-message":
            extra_payload = load_payload(args.input) if args.input else {}
            payload = client.send_message(
                args.contact_id,
                args.body,
                channel=args.channel,
                conversation_id=args.conversation_id,
                subject=args.subject,
                html=args.html,
                attachments=extra_payload.get("attachments"),
            )
        elif args.command == "list-calendars":
            payload = client.list_calendars(location_id=args.location_id, group_id=args.group_id)
        elif args.command == "get-appointments":
            payload = client.get_appointments(
                calendar_id=args.calendar_id,
                location_id=args.location_id,
                contact_id=args.contact_id,
                start_time=args.start_time,
                end_time=args.end_time,
            )
        elif args.command == "create-booking":
            payload = client.create_booking(load_payload(args.input))
        elif args.command == "trigger-workflow":
            payload = client.trigger_workflow(args.contact_id, args.workflow_id)
        elif args.command == "list-webhooks":
            payload = client.list_webhooks()
        elif args.command == "register-webhook":
            payload = client.register_webhook(args.target_url, parse_tags(args.events) if args.events else None)
        else:
            parser.error(f"Unsupported command: {args.command}")
            return 2
    except CRMError as exc:
        LOG.error("gohighlevel command failed", extra={"event": {"command": args.command, "error": str(exc)}})
        sys.stderr.write(f"{exc}\n")
        return 1

    dump_output(payload, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
