#!/usr/bin/env python3
"""Stdlib demo CRM API for the OpsClaw API Bridge demo."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


CONTACTS = [
    {
        "id": "c-1001",
        "name": "Maya Chen",
        "email": "maya.chen@northstarlogistics.com",
        "phone": "+1-415-555-0111",
        "company": "Northstar Logistics",
        "title": "COO",
        "status": "customer",
    },
    {
        "id": "c-1002",
        "name": "Jordan Alvarez",
        "email": "jordan@latticeworks.io",
        "phone": "+1-646-555-0193",
        "company": "LatticeWorks",
        "title": "Founder",
        "status": "lead",
    },
    {
        "id": "c-1003",
        "name": "Priya Raman",
        "email": "priya@horizonbiotech.com",
        "phone": "+1-617-555-0182",
        "company": "Horizon Biotech",
        "title": "VP Operations",
        "status": "opportunity",
    },
    {
        "id": "c-1004",
        "name": "Sam Brooks",
        "email": "sam@brightforge.co",
        "phone": "+1-303-555-0127",
        "company": "BrightForge",
        "title": "Revenue Lead",
        "status": "customer",
    },
    {
        "id": "c-1005",
        "name": "Elena Petrov",
        "email": "elena@foundryone.com",
        "phone": "+1-206-555-0175",
        "company": "Foundry One",
        "title": "Chief of Staff",
        "status": "lead",
    },
]

DEALS = [
    {
        "id": "d-2001",
        "name": "Northstar Expansion Rollout",
        "stage": "proposal",
        "value": 42000,
        "currency": "USD",
        "contactId": "c-1001",
        "owner": "Avery Stone",
    },
    {
        "id": "d-2002",
        "name": "LatticeWorks Onboarding",
        "stage": "discovery",
        "value": 18000,
        "currency": "USD",
        "contactId": "c-1002",
        "owner": "Avery Stone",
    },
    {
        "id": "d-2003",
        "name": "Horizon Analytics Migration",
        "stage": "negotiation",
        "value": 76000,
        "currency": "USD",
        "contactId": "c-1003",
        "owner": "Casey Ng",
    },
]


class DemoState:
    def __init__(self) -> None:
        self.contacts = deepcopy(CONTACTS)
        self.deals = deepcopy(DEALS)

    def next_id(self, prefix: str, items: list[dict]) -> str:
        numbers = [int(item["id"].split("-")[1]) for item in items]
        return f"{prefix}-{max(numbers, default=0) + 1}"


STATE = DemoState()


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "OpsClawDemoAPI/1.0"

    def do_GET(self) -> None:  # noqa: N802
        self.route("GET")

    def do_POST(self) -> None:  # noqa: N802
        self.route("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self.route("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self.route("DELETE")

    def log_message(self, format: str, *args) -> None:
        return

    def route(self, method: str) -> None:
        if not self.authorized():
            return

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if method == "GET" and path == "/api/v1/contacts":
            return self.handle_list_contacts(query)
        if method == "GET" and path.startswith("/api/v1/contacts/"):
            return self.handle_get_contact(path.rsplit("/", 1)[-1])
        if method == "POST" and path == "/api/v1/contacts":
            return self.handle_create_contact()
        if method == "PUT" and path.startswith("/api/v1/contacts/"):
            return self.handle_update_contact(path.rsplit("/", 1)[-1])
        if method == "DELETE" and path.startswith("/api/v1/contacts/"):
            return self.handle_delete_contact(path.rsplit("/", 1)[-1])
        if method == "GET" and path == "/api/v1/deals":
            return self.handle_list_deals()
        if method == "GET" and path.startswith("/api/v1/deals/"):
            return self.handle_get_deal(path.rsplit("/", 1)[-1])
        if method == "POST" and path == "/api/v1/deals":
            return self.handle_create_deal()
        if method == "GET" and path == "/api/v1/reports/summary":
            return self.handle_summary()

        self.write_json(404, {"error": "Not found", "path": path})

    def authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if header.startswith("Bearer ") and header.split(" ", 1)[1].strip():
            return True
        self.write_json(401, {"error": "Missing bearer token"})
        return False

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def handle_list_contacts(self, query: dict) -> None:
        page = int(query.get("page", ["1"])[0])
        limit = int(query.get("limit", ["20"])[0])
        start = max(page - 1, 0) * limit
        items = STATE.contacts[start : start + limit]
        self.write_json(
            200,
            {
                "items": items,
                "page": page,
                "limit": limit,
                "total": len(STATE.contacts),
            },
        )

    def handle_get_contact(self, contact_id: str) -> None:
        contact = find_by_id(STATE.contacts, contact_id)
        if not contact:
            self.write_json(404, {"error": "Contact not found", "id": contact_id})
            return
        self.write_json(200, contact)

    def handle_create_contact(self) -> None:
        payload = self.read_json()
        for field in ("name", "email"):
            if not payload.get(field):
                self.write_json(400, {"error": f"Missing field: {field}"})
                return
        contact = {
            "id": STATE.next_id("c", STATE.contacts),
            "name": payload["name"],
            "email": payload["email"],
            "phone": payload.get("phone", ""),
            "company": payload.get("company", "Unassigned"),
            "title": payload.get("title", "Unknown"),
            "status": payload.get("status", "lead"),
        }
        STATE.contacts.append(contact)
        self.write_json(201, contact)

    def handle_update_contact(self, contact_id: str) -> None:
        contact = find_by_id(STATE.contacts, contact_id)
        if not contact:
            self.write_json(404, {"error": "Contact not found", "id": contact_id})
            return
        payload = self.read_json()
        for key in ("name", "email", "phone", "company", "title", "status"):
            if key in payload:
                contact[key] = payload[key]
        self.write_json(200, contact)

    def handle_delete_contact(self, contact_id: str) -> None:
        contact = find_by_id(STATE.contacts, contact_id)
        if not contact:
            self.write_json(404, {"error": "Contact not found", "id": contact_id})
            return
        STATE.contacts = [item for item in STATE.contacts if item["id"] != contact_id]
        self.write_json(200, {"deleted": True, "id": contact_id})

    def handle_list_deals(self) -> None:
        self.write_json(
            200,
            {
                "items": STATE.deals,
                "total": len(STATE.deals),
            },
        )

    def handle_get_deal(self, deal_id: str) -> None:
        deal = find_by_id(STATE.deals, deal_id)
        if not deal:
            self.write_json(404, {"error": "Deal not found", "id": deal_id})
            return
        self.write_json(200, deal)

    def handle_create_deal(self) -> None:
        payload = self.read_json()
        for field in ("name", "value", "contactId"):
            if payload.get(field) in (None, ""):
                self.write_json(400, {"error": f"Missing field: {field}"})
                return
        deal = {
            "id": STATE.next_id("d", STATE.deals),
            "name": payload["name"],
            "stage": payload.get("stage", "discovery"),
            "value": payload["value"],
            "currency": payload.get("currency", "USD"),
            "contactId": payload["contactId"],
            "owner": payload.get("owner", "OpsClaw Demo"),
        }
        STATE.deals.append(deal)
        self.write_json(201, deal)

    def handle_summary(self) -> None:
        total_pipeline = sum(deal["value"] for deal in STATE.deals)
        self.write_json(
            200,
            {
                "contacts": len(STATE.contacts),
                "deals": len(STATE.deals),
                "pipelineValue": total_pipeline,
                "avgDealValue": round(total_pipeline / len(STATE.deals), 2) if STATE.deals else 0,
                "topStage": most_common_stage(STATE.deals),
            },
        )

    def write_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def find_by_id(items: list[dict], item_id: str) -> dict | None:
    for item in items:
        if item["id"] == item_id:
            return item
    return None


def most_common_stage(deals: list[dict]) -> str:
    counts: dict[str, int] = {}
    for deal in deals:
        counts[deal["stage"]] = counts.get(deal["stage"], 0) + 1
    return max(counts, key=counts.get) if counts else "none"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the stdlib OpsClaw API Bridge demo API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DemoHandler)
    print(f"Demo API listening on http://{args.host}:{args.port}/api/v1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
