#!/usr/bin/env python3
"""Generate approval-safe Gmail drafts using gws."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from gws_gmail import create_draft, get_message, iso_now, send_draft


URGENCY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_mustache(text: str, values: dict[str, str]) -> str:
    rendered = text
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return re.sub(r"{{[^}]+}}", "", rendered)


def summarize(email_doc: dict[str, Any]) -> str:
    body = (email_doc.get("body") or email_doc.get("snippet") or "").strip().replace("\n", " ")
    short = body[:140] + ("..." if len(body) > 140 else "")
    if not short:
        short = "I'm reviewing the details you sent."
    if not short.endswith("."):
        short += "."
    return short


def follow_up_eta(email_doc: dict[str, Any]) -> str:
    classification = email_doc.get("classification", {})
    urgency = classification.get("urgency", "medium")
    now = datetime.now(timezone.utc)
    if urgency in {"critical", "high"}:
        eta = now + timedelta(hours=2)
    else:
        eta = now + timedelta(hours=24)
    return eta.strftime("%A %H:%M %Z")


def sender_name(email_doc: dict[str, Any]) -> str:
    sender = email_doc.get("from", {})
    return sender.get("name") or sender.get("email") or "there"


def rule_matches(rule: dict[str, Any], email_doc: dict[str, Any]) -> bool:
    if not rule.get("enabled", True):
        return False

    classification = email_doc.get("classification", {})
    match = rule.get("match", {})
    text = " ".join(
        [
            (email_doc.get("subject") or ""),
            (email_doc.get("body") or ""),
            (email_doc.get("snippet") or ""),
        ]
    ).lower()

    if match.get("categories") and classification.get("category") not in match["categories"]:
        return False
    if match.get("urgencies") and classification.get("urgency") not in match["urgencies"]:
        return False
    keywords_any = [term.lower() for term in match.get("keywordsAny", [])]
    if keywords_any and not any(term in text for term in keywords_any):
        return False
    if any(term.lower() in text for term in match.get("keywordsNone", [])):
        return False

    if match.get("receivedOutsideHours"):
        received_at = email_doc.get("receivedAt")
        if not received_at:
            return False
        dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        if 7 <= dt.hour < 18:
            return False

    return True


def choose_rule(email_doc: dict[str, Any], rules_doc: dict[str, Any]) -> dict[str, Any] | None:
    defaults = rules_doc.get("defaults", {})
    classification = email_doc.get("classification", {})
    text = " ".join(
        [email_doc.get("subject") or "", email_doc.get("body") or "", email_doc.get("snippet") or ""]
    ).lower()

    if classification.get("category") in defaults.get("blockedCategories", []):
        return None
    if any(term.lower() in text for term in defaults.get("blockedTerms", [])):
        return None
    if URGENCY_ORDER.get(classification.get("urgency", "low"), 0) > URGENCY_ORDER.get(
        defaults.get("maxAutoDraftUrgency", "medium"), 1
    ):
        return None

    for rule in rules_doc.get("rules", []):
        if rule_matches(rule, email_doc):
            return rule
    return None


def build_draft(email_doc: dict[str, Any], rule: dict[str, Any], templates_dir: Path, owner_name: str) -> dict[str, Any]:
    template_path = templates_dir / rule["template"]
    template_text = read_template(template_path)
    rendered = render_mustache(
        template_text,
        {
            "sender_name": sender_name(email_doc),
            "subject": email_doc.get("subject") or "(no subject)",
            "summary_sentence": summarize(email_doc),
            "follow_up_eta": follow_up_eta(email_doc),
            "owner_name": owner_name,
        },
    ).strip()
    return {
        "template": rule["template"],
        "body": rendered,
        "recommendedAction": rule.get("recommendedAction"),
        "approvalRequired": rule.get("approvalRequired", True),
        "generatedAt": iso_now(),
    }


def queue_entry(email_doc: dict[str, Any], draft: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    classification = email_doc.get("classification", {})
    sender = email_doc.get("from", {})
    return {
        "id": f"draft:{email_doc.get('messageId') or email_doc.get('id')}",
        "source": "email-intel",
        "system": "gmail",
        "requestedAt": iso_now(),
        "actionClass": rule.get("actionClass", "auto_draft"),
        "status": "pending_approval",
        "riskLevel": classification.get("urgency", "medium"),
        "messageId": email_doc.get("messageId") or email_doc.get("id"),
        "threadId": email_doc.get("threadId"),
        "sender": sender.get("email"),
        "subject": email_doc.get("subject"),
        "template": draft.get("template"),
        "recommendedAction": draft.get("recommendedAction"),
        "draftPreview": draft.get("body", "")[:280],
        "context": {
            "category": classification.get("category"),
            "urgency": classification.get("urgency"),
            "vip": classification.get("vip", False),
        },
    }


def update_ops_state(ops_state: dict[str, Any], entry: dict[str, Any], email_doc: dict[str, Any]) -> None:
    pending_drafts = ops_state.setdefault("email", {}).setdefault("pendingDrafts", [])
    if not any(item.get("id") == entry["id"] for item in pending_drafts):
        pending_drafts.append(
            {
                "id": entry["id"],
                "messageId": entry["messageId"],
                "threadId": entry["threadId"],
                "sender": entry["sender"],
                "subject": entry["subject"],
                "status": entry["status"],
                "template": entry["template"],
                "requestedAt": entry["requestedAt"],
            }
        )

    approvals = ops_state.setdefault("approvals", {}).setdefault("pending", [])
    if not any(item.get("id") == entry["id"] for item in approvals):
        approvals.append(entry)

    ops_state["lastUpdated"] = iso_now()
    ops_state.setdefault("email", {})["lastChecked"] = iso_now()


def target_recipients(email_doc: dict[str, Any]) -> list[str]:
    sender = email_doc.get("from", {})
    address = sender.get("email")
    return [address] if address else []


def maybe_sync_gmail_draft(email_doc: dict[str, Any], draft: dict[str, Any], *, send_now: bool) -> dict[str, Any] | None:
    recipients = target_recipients(email_doc)
    if not recipients:
        return None

    created = create_draft(
        to=recipients,
        subject=f"Re: {email_doc.get('subject') or '(no subject)'}",
        body=draft["body"],
        thread_id=email_doc.get("threadId"),
    )
    result = {"draftId": created.get("id"), "message": created.get("message")}
    if send_now and created.get("id"):
        result["sent"] = send_draft(created["id"])
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email-path", type=Path, help="Path to a classified email JSON file.")
    parser.add_argument("--message-id", help="Fetch a Gmail message via gws before generating the draft.")
    parser.add_argument("--rules", type=Path, required=True, help="Path to rules.json.")
    parser.add_argument("--templates-dir", type=Path, required=True, help="Directory of response templates.")
    parser.add_argument("--ops-state", type=Path, required=True, help="Path to workspace/ops-state.json.")
    parser.add_argument("--owner-name", default="Owner", help="Displayed sender name for drafts.")
    parser.add_argument("--write-state", action="store_true", help="Persist queue changes into ops-state.json.")
    parser.add_argument("--skip-gmail-draft", action="store_true", help="Do not create a Gmail draft via gws.")
    parser.add_argument("--send", action="store_true", help="Send the created Gmail draft immediately.")
    return parser.parse_args()


def load_email(args: argparse.Namespace) -> dict[str, Any]:
    if args.email_path is not None:
        return load_json(args.email_path)
    if args.message_id:
        return get_message(args.message_id)
    return json.load(sys.stdin)


def main() -> int:
    args = parse_args()
    email_doc = load_email(args)
    rules_doc = load_json(args.rules)
    rule = choose_rule(email_doc, rules_doc)
    if rule is None:
        json.dump({"matched": False, "reason": "No eligible auto-response rule matched."}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    draft = build_draft(email_doc, rule, args.templates_dir, args.owner_name)
    approval = queue_entry(email_doc, draft, rule)
    gmail_draft = None
    if not args.skip_gmail_draft:
        gmail_draft = maybe_sync_gmail_draft(email_doc, draft, send_now=args.send)
        if gmail_draft:
            approval["gmailDraft"] = gmail_draft

    if args.write_state:
        ops_state = load_json(args.ops_state)
        update_ops_state(ops_state, approval, email_doc)
        save_json(args.ops_state, ops_state)

    json.dump(
        {"matched": True, "rule": rule["id"], "draft": draft, "approval": approval, "gmailDraft": gmail_draft},
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
