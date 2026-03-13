#!/usr/bin/env python3
"""Deterministic email classification for OpsClaw Email Intelligence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any


URGENCY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def extract_sender(email_doc: dict[str, Any]) -> tuple[str, str]:
    raw = normalize_text(email_doc.get("from") or email_doc.get("sender"))
    name, address = parseaddr(raw)
    return name.strip() or address, address.lower()


@dataclass
class VipMatch:
    matched: bool
    tier: str | None = None
    reason: str | None = None
    source: str | None = None


def find_vip(address: str, vip_doc: dict[str, Any]) -> VipMatch:
    if not address:
        return VipMatch(False)
    domain = address.split("@")[-1]
    for sender in vip_doc.get("senders", []):
        if sender.get("email", "").lower() == address:
            return VipMatch(True, sender.get("tier"), sender.get("reason"), "sender")
    for entry in vip_doc.get("domains", []):
        if entry.get("domain", "").lower() == domain:
            return VipMatch(True, entry.get("tier"), entry.get("reason"), "domain")
    return VipMatch(False)


def contains_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in text


def score_keywords(text: str, keywords: list[str], weight: int) -> tuple[int, list[str]]:
    hits: list[str] = []
    total = 0
    for keyword in keywords:
        if contains_phrase(text, keyword):
            total += weight
            hits.append(keyword)
    return total, hits


def score_sender_rules(address: str, rules: dict[str, Any]) -> tuple[dict[str, int], dict[str, list[str]]]:
    scores = defaultdict(int)
    reasons: dict[str, list[str]] = defaultdict(list)
    lowered = address.lower()

    for pattern in rules.get("noreplyPatterns", []):
        if pattern in lowered:
            scores["marketing"] += 2
            reasons["marketing"].append(f"sender matches {pattern}")

    domain = lowered.split("@")[-1] if "@" in lowered else ""
    for billing_domain in rules.get("billingDomains", []):
        if domain == billing_domain.lower():
            scores["billing"] += 4
            reasons["billing"].append(f"sender domain {domain} is billing-focused")

    for marketing_domain in rules.get("marketingDomains", []):
        if domain == marketing_domain.lower():
            scores["marketing"] += 4
            reasons["marketing"].append(f"sender domain {domain} is marketing-focused")

    for spam_domain in rules.get("spamDomains", []):
        if domain == spam_domain.lower():
            scores["spam"] += 6
            reasons["spam"].append(f"sender domain {domain} is on the spam list")

    return dict(scores), dict(reasons)


def classify(email_doc: dict[str, Any], categories_doc: dict[str, Any], vip_doc: dict[str, Any]) -> dict[str, Any]:
    sender_name, sender_email = extract_sender(email_doc)
    subject = normalize_text(email_doc.get("subject"))
    body = normalize_text(email_doc.get("body") or email_doc.get("textBody") or email_doc.get("snippet"))
    combined_text = f"{subject}\n{body}".lower()
    received_at = normalize_text(email_doc.get("receivedAt") or email_doc.get("date")) or iso_now()

    vip_match = find_vip(sender_email, vip_doc)

    urgency_score = 0
    urgency_reasons: list[str] = []
    for bucket, weight in [("critical", 5), ("high", 3), ("medium", 1), ("low", -2)]:
        score, hits = score_keywords(combined_text, categories_doc["urgencyKeywords"].get(bucket, []), weight)
        urgency_score += score
        for hit in hits:
            urgency_reasons.append(f"{bucket} keyword: {hit}")

    impact_hits = [
        term for term in categories_doc.get("businessImpactTerms", []) if contains_phrase(combined_text, term)
    ]
    if impact_hits:
        urgency_score += min(4, len(impact_hits))
        urgency_reasons.append("business impact terms: " + ", ".join(impact_hits[:4]))

    if vip_match.matched:
        urgency_score += 4
        urgency_reasons.append(f"VIP {vip_match.source} match: {vip_match.reason or vip_match.tier}")

    category_scores = defaultdict(int)
    category_reasons: dict[str, list[str]] = defaultdict(list)
    for category, keywords in categories_doc["categoryKeywords"].items():
        for keyword in keywords:
            if contains_phrase(combined_text, keyword):
                category_scores[category] += 2
                category_reasons[category].append(f"keyword: {keyword}")

    sender_scores, sender_reasons = score_sender_rules(sender_email, categories_doc.get("senderRules", {}))
    for category, value in sender_scores.items():
        category_scores[category] += value
    for category, reasons in sender_reasons.items():
        category_reasons[category].extend(reasons)

    sender_domain = sender_email.split("@")[-1] if "@" in sender_email else ""
    if sender_domain in {domain.lower() for domain in categories_doc.get("internalDomains", [])}:
        category_scores["internal"] += 4
        category_reasons["internal"].append(f"sender domain {sender_domain} is internal")
    elif vip_match.matched:
        category_scores["client"] += 3
        category_reasons["client"].append("VIP sender treated as client-facing")

    defaults = categories_doc.get("defaults", {})
    if category_scores.get("marketing", 0) >= defaults.get("lowSignalMarketingThreshold", 4):
        urgency_score -= 2
        urgency_reasons.append("marketing signal reduced urgency")
    if category_scores.get("spam", 0) >= defaults.get("lowSignalSpamThreshold", 6):
        urgency_score -= 4
        urgency_reasons.append("spam signal reduced urgency")

    if category_scores:
        category = sorted(
            category_scores.items(),
            key=lambda item: (item[1], -["client", "internal", "billing", "marketing", "spam"].index(item[0])),
            reverse=True,
        )[0][0]
    else:
        category = "client"
        category_reasons["client"].append("fallback default category")

    if category == "spam":
        urgency = "low"
        urgency_reasons.append("spam is always low urgency")
    elif urgency_score >= defaults.get("criticalUrgencyThreshold", 10):
        urgency = "critical"
    elif urgency_score >= defaults.get("highUrgencyThreshold", 6):
        urgency = "high"
    elif urgency_score >= defaults.get("mediumUrgencyThreshold", 3):
        urgency = "medium"
    else:
        urgency = "low"

    if category == "billing" and URGENCY_ORDER[urgency] < URGENCY_ORDER["high"]:
        urgency = "high"
        urgency_reasons.append("billing mail is at least high priority by policy")
    if vip_match.matched and category not in {"marketing", "spam"} and URGENCY_ORDER[urgency] < URGENCY_ORDER["high"]:
        urgency = "high"
        urgency_reasons.append("VIP mail elevated to at least high")

    summary = body[:280] + ("..." if len(body) > 280 else "")
    return {
        "messageId": email_doc.get("messageId") or email_doc.get("id"),
        "threadId": email_doc.get("threadId"),
        "receivedAt": received_at,
        "from": {"name": sender_name, "email": sender_email},
        "to": email_doc.get("to", []),
        "subject": subject,
        "snippet": normalize_text(email_doc.get("snippet")) or summary,
        "body": body,
        "classification": {
            "urgency": urgency,
            "category": category,
            "vip": vip_match.matched,
            "vipTier": vip_match.tier,
            "score": urgency_score,
            "reasons": urgency_reasons[:10],
            "categoryReasons": {key: value[:8] for key, value in category_reasons.items()},
        },
        "recommendedAction": recommend_action(urgency, category, vip_match.matched),
        "classifiedAt": iso_now(),
    }


def recommend_action(urgency: str, category: str, is_vip: bool) -> str:
    if urgency == "critical":
        return "Alert the owner immediately and prepare a response path."
    if category == "billing":
        return "Review billing context, verify account status, and queue an approval-safe acknowledgement."
    if is_vip:
        return "Notify the owner promptly and prepare context for a fast reply."
    if urgency == "high":
        return "Surface in the next active window and prepare a draft if the request is routine."
    if category in {"marketing", "spam"}:
        return "Batch or filter from active attention unless the owner requested monitoring."
    return "Include in the next briefing and draft a reply only if a response is expected."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email-path", type=Path, help="Path to a normalized email JSON document.")
    parser.add_argument("--categories", type=Path, required=True, help="Path to categories.json.")
    parser.add_argument("--vip", type=Path, required=True, help="Path to vip-senders.json.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def read_email_payload(path: Path | None) -> dict[str, Any]:
    if path is None:
        return json.load(sys.stdin)
    return load_json(path)


def main() -> int:
    args = parse_args()
    email_doc = read_email_payload(args.email_path)
    categories_doc = load_json(args.categories)
    vip_doc = load_json(args.vip)
    result = classify(email_doc, categories_doc, vip_doc)
    json.dump(result, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
