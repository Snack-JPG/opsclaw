#!/usr/bin/env python3
"""Minimal Google Workspace CLI helpers for Gmail operations."""

from __future__ import annotations

import base64
import json
import subprocess
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def run_gws(command: list[str]) -> Any:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip() or "unknown gws error"
        raise RuntimeError(f"{' '.join(command)} failed: {stderr}")

    stdout = completed.stdout.strip()
    if not stdout:
        return {}
    return json.loads(stdout)


def gws_gmail(resource: str, method: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
    command = ["gws", "gmail", "users", resource, method]
    if params is not None:
        command.extend(["--params", json.dumps(params)])
    if body is not None:
        command.extend(["--json", json.dumps(body)])
    return run_gws(command)


def _decode_body(data: str | None) -> str:
    if not data:
        return ""
    missing = (-len(data)) % 4
    try:
        return base64.urlsafe_b64decode((data + ("=" * missing)).encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_bodies(payload: dict[str, Any]) -> list[str]:
    collected: list[str] = []
    body = payload.get("body") or {}
    data = _decode_body(body.get("data"))
    mime_type = payload.get("mimeType") or ""
    if data and (mime_type.startswith("text/plain") or mime_type.startswith("text/html") or not payload.get("parts")):
        collected.append(data)
    for part in payload.get("parts", []) or []:
        collected.extend(_extract_bodies(part))
    return collected


def _headers_map(payload: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in payload.get("headers", []) or []:
        name = header.get("name")
        value = header.get("value")
        if name and value is not None:
            headers[name.lower()] = value
    return headers


def normalize_message(raw_message: dict[str, Any]) -> dict[str, Any]:
    payload = raw_message.get("payload") or {}
    headers = _headers_map(payload)
    bodies = [body.strip() for body in _extract_bodies(payload) if body.strip()]
    body = "\n\n".join(bodies).strip()
    internal_ms = raw_message.get("internalDate")
    received_at = None
    if internal_ms:
        received_at = datetime.fromtimestamp(int(internal_ms) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "messageId": raw_message.get("id"),
        "threadId": raw_message.get("threadId"),
        "labelIds": raw_message.get("labelIds", []),
        "historyId": raw_message.get("historyId"),
        "receivedAt": received_at or iso_now(),
        "date": headers.get("date"),
        "from": headers.get("from", ""),
        "to": [item.strip() for item in headers.get("to", "").split(",") if item.strip()],
        "cc": [item.strip() for item in headers.get("cc", "").split(",") if item.strip()],
        "subject": headers.get("subject", ""),
        "snippet": raw_message.get("snippet", ""),
        "body": body,
        "rawHeaders": headers,
    }


def get_message(message_id: str, *, user_id: str = "me", format_name: str = "full") -> dict[str, Any]:
    raw = gws_gmail("messages", "get", params={"userId": user_id, "id": message_id, "format": format_name})
    return normalize_message(raw)


def list_messages(
    *,
    user_id: str = "me",
    query: str | None = None,
    max_results: int = 10,
    label_ids: list[str] | None = None,
    unread_only: bool = False,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"userId": user_id, "maxResults": max_results}
    labels = list(label_ids or [])
    if unread_only and "UNREAD" not in labels:
        labels.append("UNREAD")
    if labels:
        params["labelIds"] = labels
    if query:
        params["q"] = query

    response = gws_gmail("messages", "list", params=params)
    messages = response.get("messages", []) or []
    return [get_message(item["id"], user_id=user_id) for item in messages if item.get("id")]


def build_draft_payload(*, to: list[str], subject: str, body: str, thread_id: str | None = None) -> dict[str, Any]:
    message = EmailMessage()
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8").rstrip("=")
    payload: dict[str, Any] = {"message": {"raw": raw}}
    if thread_id:
        payload["message"]["threadId"] = thread_id
    return payload


def create_draft(*, to: list[str], subject: str, body: str, thread_id: str | None = None, user_id: str = "me") -> dict[str, Any]:
    payload = build_draft_payload(to=to, subject=subject, body=body, thread_id=thread_id)
    return gws_gmail("drafts", "create", params={"userId": user_id}, body=payload)


def send_draft(draft_id: str, *, user_id: str = "me") -> dict[str, Any]:
    return gws_gmail("drafts", "send", params={"userId": user_id}, body={"id": draft_id})
