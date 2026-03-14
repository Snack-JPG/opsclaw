#!/usr/bin/env python3
import base64
import json
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import count
from typing import Any, Dict, List, Optional, Tuple
from urllib import parse


HOST = "127.0.0.1"
PORT = 8765


def make_records(prefix: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    records = []
    for index, row in enumerate(rows, start=1):
        item = {"id": f"{prefix}-{index:03d}"}
        item.update(row)
        records.append(item)
    return records


DATA: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "demo-crm": {
        "contacts": make_records(
            "ct",
            [
                {"name": "Ava Patel", "email": "ava@northstar.io", "company_id": "co-001", "title": "VP Sales"},
                {"name": "Marcus Lee", "email": "marcus@northstar.io", "company_id": "co-001", "title": "RevOps Lead"},
                {"name": "Nina Gomez", "email": "nina@blueharbor.co", "company_id": "co-002", "title": "CEO"},
                {"name": "Jules Carter", "email": "jules@blueharbor.co", "company_id": "co-002", "title": "Buyer"},
                {"name": "Owen Reed", "email": "owen@sunline.ai", "company_id": "co-003", "title": "CFO"},
                {"name": "Mia Chen", "email": "mia@sunline.ai", "company_id": "co-003", "title": "Finance Manager"},
                {"name": "Ethan Boyd", "email": "ethan@forgeworks.com", "company_id": "co-004", "title": "COO"},
                {"name": "Priya Das", "email": "priya@forgeworks.com", "company_id": "co-004", "title": "Plant Director"},
                {"name": "Lena Brooks", "email": "lena@everfield.io", "company_id": "co-005", "title": "Founder"},
                {"name": "Isaac Hall", "email": "isaac@everfield.io", "company_id": "co-005", "title": "CTO"},
                {"name": "Sofia Turner", "email": "sofia@redcanyon.dev", "company_id": "co-006", "title": "Head of Ops"},
                {"name": "Noah Wright", "email": "noah@redcanyon.dev", "company_id": "co-006", "title": "Procurement Lead"}
            ],
        ),
        "deals": make_records(
            "dl",
            [
                {"name": "Northstar Expansion", "value": 24000, "stage": "proposal", "contact_id": "ct-001"},
                {"name": "BlueHarbor Renewal", "value": 12000, "stage": "won", "contact_id": "ct-003"},
                {"name": "Sunline Pilot", "value": 8000, "stage": "discovery", "contact_id": "ct-005"},
                {"name": "ForgeWorks ERP", "value": 56000, "stage": "negotiation", "contact_id": "ct-007"},
                {"name": "Everfield Seat Add-on", "value": 9000, "stage": "won", "contact_id": "ct-009"},
                {"name": "RedCanyon Rollout", "value": 31000, "stage": "proposal", "contact_id": "ct-011"},
                {"name": "Sunline Services", "value": 14000, "stage": "won", "contact_id": "ct-006"},
                {"name": "Northstar Analytics", "value": 17000, "stage": "discovery", "contact_id": "ct-002"},
                {"name": "ForgeWorks Support", "value": 6000, "stage": "qualified", "contact_id": "ct-008"},
                {"name": "BlueHarbor Integration", "value": 22000, "stage": "proposal", "contact_id": "ct-004"}
            ],
        ),
        "companies": make_records(
            "co",
            [
                {"name": "Northstar Logistics", "industry": "Logistics", "employees": 420},
                {"name": "BlueHarbor Supply", "industry": "Distribution", "employees": 180},
                {"name": "Sunline AI", "industry": "Software", "employees": 65},
                {"name": "ForgeWorks Manufacturing", "industry": "Manufacturing", "employees": 900},
                {"name": "Everfield Health", "industry": "Healthcare", "employees": 120},
                {"name": "RedCanyon Energy", "industry": "Energy", "employees": 310},
                {"name": "Quartz Retail Group", "industry": "Retail", "employees": 540},
                {"name": "Summit Freight", "industry": "Logistics", "employees": 220}
            ],
        ),
    },
    "demo-inventory": {
        "items": make_records(
            "it",
            [
                {"sku": "WID-100", "name": "Widget Core", "category": "widget", "quantity": 148, "warehouse_id": "wh-001"},
                {"sku": "WID-110", "name": "Widget Mini", "category": "widget", "quantity": 88, "warehouse_id": "wh-001"},
                {"sku": "WID-200", "name": "Widget Pro", "category": "widget", "quantity": 24, "warehouse_id": "wh-002"},
                {"sku": "GAD-300", "name": "Gadget Prime", "category": "gadget", "quantity": 52, "warehouse_id": "wh-003"},
                {"sku": "GAD-310", "name": "Gadget Lite", "category": "gadget", "quantity": 76, "warehouse_id": "wh-003"},
                {"sku": "KIT-400", "name": "Starter Kit", "category": "bundle", "quantity": 33, "warehouse_id": "wh-002"},
                {"sku": "PAR-410", "name": "Power Adapter", "category": "parts", "quantity": 203, "warehouse_id": "wh-004"},
                {"sku": "PAR-420", "name": "Mounting Bracket", "category": "parts", "quantity": 167, "warehouse_id": "wh-005"},
                {"sku": "ACC-500", "name": "Travel Case", "category": "accessory", "quantity": 61, "warehouse_id": "wh-005"},
                {"sku": "ACC-510", "name": "Docking Tray", "category": "accessory", "quantity": 44, "warehouse_id": "wh-004"},
                {"sku": "WID-210", "name": "Widget Max", "category": "widget", "quantity": 18, "warehouse_id": "wh-006"},
                {"sku": "KIT-430", "name": "Field Repair Kit", "category": "bundle", "quantity": 14, "warehouse_id": "wh-002"},
                {"sku": "GAD-320", "name": "Gadget Ultra", "category": "gadget", "quantity": 9, "warehouse_id": "wh-006"},
                {"sku": "PAR-430", "name": "Sensor Pack", "category": "parts", "quantity": 119, "warehouse_id": "wh-003"},
                {"sku": "ACC-520", "name": "Label Set", "category": "accessory", "quantity": 280, "warehouse_id": "wh-001"}
            ],
        ),
        "warehouses": make_records(
            "wh",
            [
                {"name": "London DC", "region": "emea", "capacity": 1200},
                {"name": "Chicago Hub", "region": "na", "capacity": 2200},
                {"name": "Berlin Overflow", "region": "emea", "capacity": 800},
                {"name": "Austin West", "region": "na", "capacity": 950},
                {"name": "Singapore Node", "region": "apac", "capacity": 1100},
                {"name": "Sydney Reserve", "region": "apac", "capacity": 700}
            ],
        ),
        "orders": make_records(
            "or",
            [
                {"customer": "Northstar Logistics", "status": "packed", "item_id": "it-001", "quantity": 10},
                {"customer": "BlueHarbor Supply", "status": "shipped", "item_id": "it-004", "quantity": 4},
                {"customer": "Everfield Health", "status": "queued", "item_id": "it-007", "quantity": 25},
                {"customer": "RedCanyon Energy", "status": "queued", "item_id": "it-003", "quantity": 2},
                {"customer": "Sunline AI", "status": "delivered", "item_id": "it-006", "quantity": 3},
                {"customer": "Quartz Retail Group", "status": "packed", "item_id": "it-009", "quantity": 8},
                {"customer": "ForgeWorks Manufacturing", "status": "queued", "item_id": "it-013", "quantity": 1},
                {"customer": "Summit Freight", "status": "shipped", "item_id": "it-011", "quantity": 6},
                {"customer": "Orchard Labs", "status": "delivered", "item_id": "it-014", "quantity": 12},
                {"customer": "Pinegate Systems", "status": "packed", "item_id": "it-015", "quantity": 20},
                {"customer": "Vela Health", "status": "queued", "item_id": "it-002", "quantity": 7},
                {"customer": "Helix Ops", "status": "shipped", "item_id": "it-012", "quantity": 5}
            ],
        ),
    },
    "demo-hr": {
        "employees": make_records(
            "em",
            [
                {"name": "Harper Stone", "department_id": "dp-001", "title": "People Partner", "location": "London"},
                {"name": "Theo Morgan", "department_id": "dp-002", "title": "Platform Engineer", "location": "Remote"},
                {"name": "Grace Silva", "department_id": "dp-003", "title": "Finance Manager", "location": "Austin"},
                {"name": "Daniel Kim", "department_id": "dp-004", "title": "Recruiter", "location": "London"},
                {"name": "Ariana Shah", "department_id": "dp-005", "title": "Operations Analyst", "location": "Berlin"},
                {"name": "Ben Foster", "department_id": "dp-006", "title": "Support Lead", "location": "Chicago"},
                {"name": "Lucy Grant", "department_id": "dp-002", "title": "Senior Engineer", "location": "Remote"},
                {"name": "Samir Rao", "department_id": "dp-002", "title": "Staff Engineer", "location": "London"},
                {"name": "Isla Ward", "department_id": "dp-005", "title": "Program Manager", "location": "Austin"},
                {"name": "Jacob Price", "department_id": "dp-003", "title": "Controller", "location": "Austin"},
                {"name": "Amelia Hart", "department_id": "dp-001", "title": "HR Coordinator", "location": "London"},
                {"name": "Leo Brooks", "department_id": "dp-006", "title": "Support Specialist", "location": "Berlin"}
            ],
        ),
        "departments": make_records(
            "dp",
            [
                {"name": "People", "head": "Harper Stone"},
                {"name": "Engineering", "head": "Theo Morgan"},
                {"name": "Finance", "head": "Grace Silva"},
                {"name": "Talent", "head": "Daniel Kim"},
                {"name": "Operations", "head": "Ariana Shah"},
                {"name": "Support", "head": "Ben Foster"}
            ],
        ),
        "leave-requests": make_records(
            "lv",
            [
                {"employee_id": "em-001", "status": "approved", "days": 5, "start_date": "2026-04-02"},
                {"employee_id": "em-002", "status": "pending", "days": 2, "start_date": "2026-04-07"},
                {"employee_id": "em-003", "status": "approved", "days": 3, "start_date": "2026-04-14"},
                {"employee_id": "em-004", "status": "pending", "days": 1, "start_date": "2026-04-15"},
                {"employee_id": "em-005", "status": "rejected", "days": 4, "start_date": "2026-04-18"},
                {"employee_id": "em-006", "status": "pending", "days": 2, "start_date": "2026-04-21"},
                {"employee_id": "em-007", "status": "approved", "days": 6, "start_date": "2026-05-01"},
                {"employee_id": "em-008", "status": "pending", "days": 5, "start_date": "2026-05-09"},
                {"employee_id": "em-009", "status": "approved", "days": 2, "start_date": "2026-05-12"},
                {"employee_id": "em-010", "status": "pending", "days": 3, "start_date": "2026-05-16"}
            ],
        ),
    },
}

COUNTERS = {service: {resource: count(len(records) + 1) for resource, records in resources.items()} for service, resources in DATA.items()}
AUTH = {
    "demo-crm": ("bearer", "demo-crm-token"),
    "demo-inventory": ("api-key", "demo-inventory-key"),
    "demo-hr": ("basic", "demo-hr-user:demo-hr-pass"),
}


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any, headers: Optional[Dict[str, str]] = None) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    for key, value in (headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def parse_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if not length:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw)


def paginate_offset(rows: List[Dict[str, Any]], query: Dict[str, List[str]]) -> Dict[str, Any]:
    limit = int(query.get("limit", ["5"])[0])
    offset = int(query.get("offset", ["0"])[0])
    page = rows[offset:offset + limit]
    next_offset = offset + limit if offset + limit < len(rows) else None
    return {"data": page, "count": len(rows), "has_more": next_offset is not None, "next_offset": next_offset}


def paginate_cursor(rows: List[Dict[str, Any]], query: Dict[str, List[str]]) -> Dict[str, Any]:
    limit = int(query.get("limit", ["5"])[0])
    cursor_raw = query.get("cursor", ["0"])[0]
    offset = int(cursor_raw or "0")
    page = rows[offset:offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(rows) else None
    return {"items": page, "next_cursor": next_cursor}


def paginate_link(service: str, resource: str, rows: List[Dict[str, Any]], query: Dict[str, List[str]]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    limit = int(query.get("limit", ["5"])[0])
    page = int(query.get("page", ["1"])[0])
    start = (page - 1) * limit
    result = rows[start:start + limit]
    headers: Dict[str, str] = {}
    if start + limit < len(rows):
        next_page = page + 1
        next_url = f"http://{HOST}:{PORT}/{service}/v1/{resource}?page={next_page}&limit={limit}"
        headers["Link"] = f'<{next_url}>; rel="next"'
    return {"data": result, "page": page, "count": len(rows)}, headers


def require_auth(handler: BaseHTTPRequestHandler, service: str) -> Optional[Tuple[int, Dict[str, Any]]]:
    auth_type, secret = AUTH[service]
    if auth_type == "bearer":
        actual = handler.headers.get("Authorization", "")
        expected = f"Bearer {secret}"
        if actual != expected:
            return 401, {"error": "invalid bearer token"}
    elif auth_type == "api-key":
        if handler.headers.get("X-Demo-Key") != secret:
            return 401, {"error": "invalid api key"}
    elif auth_type == "basic":
        expected = "Basic " + base64.b64encode(secret.encode("utf-8")).decode("ascii")
        if handler.headers.get("Authorization") != expected:
            return 401, {"error": "invalid basic auth"}
    return None


def find_record(service: str, resource: str, record_id: str) -> Optional[Dict[str, Any]]:
    for record in DATA[service][resource]:
        if record["id"] == record_id:
            return record
    return None


def next_id(service: str, resource: str) -> str:
    prefixes = {"contacts": "ct", "deals": "dl", "companies": "co", "items": "it", "warehouses": "wh", "orders": "or", "employees": "em", "departments": "dp", "leave-requests": "lv"}
    return f"{prefixes[resource]}-{next(COUNTERS[service][resource]):03d}"


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "OpsClawDemo/1.0"

    def do_GET(self) -> None:
        self.handle_request("GET")

    def do_POST(self) -> None:
        self.handle_request("POST")

    def do_PATCH(self) -> None:
        self.handle_request("PATCH")

    def do_DELETE(self) -> None:
        self.handle_request("DELETE")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def handle_request(self, method: str) -> None:
        parsed = parse.urlparse(self.path)
        segments = [segment for segment in parsed.path.split("/") if segment]
        if len(segments) < 3 or segments[1] != "v1":
            return json_response(self, 404, {"error": "not found"})
        service = segments[0]
        if service not in DATA:
            return json_response(self, 404, {"error": "unknown service"})
        auth_error = require_auth(self, service)
        if auth_error:
            status, payload = auth_error
            return json_response(self, status, payload)

        resource = segments[2]
        if resource not in DATA[service]:
            return json_response(self, 404, {"error": "unknown resource"})
        record_id = segments[3] if len(segments) >= 4 else None
        action = segments[4] if len(segments) >= 5 else None
        query = parse.parse_qs(parsed.query)

        if method == "GET" and record_id == "search":
            record_id = None

        try:
            if method == "GET" and record_id:
                record = find_record(service, resource, record_id)
                if not record:
                    return json_response(self, 404, {"error": "not found"})
                return json_response(self, 200, record)

            if method == "DELETE" and record_id:
                record = find_record(service, resource, record_id)
                if not record:
                    return json_response(self, 404, {"error": "not found"})
                DATA[service][resource] = [row for row in DATA[service][resource] if row["id"] != record_id]
                return json_response(self, 200, {"deleted": record_id})

            if method == "PATCH" and record_id:
                record = find_record(service, resource, record_id)
                if not record:
                    return json_response(self, 404, {"error": "not found"})
                record.update(parse_body(self))
                return json_response(self, 200, record)

            if method == "POST" and action == "approve" and resource == "leave-requests":
                record = find_record(service, resource, record_id or "")
                if not record:
                    return json_response(self, 404, {"error": "not found"})
                body = parse_body(self)
                record["status"] = "approved"
                record["approved_by"] = body.get("approved_by", "manager")
                return json_response(self, 200, record)

            if method == "POST":
                body = parse_body(self)
                body["id"] = next_id(service, resource)
                DATA[service][resource].append(body)
                return json_response(self, 201, body)

            rows = deepcopy(DATA[service][resource])
            rows = apply_filters(service, resource, rows, query)
            if service == "demo-crm":
                return json_response(self, 200, paginate_offset(rows, query))
            if service == "demo-inventory":
                return json_response(self, 200, paginate_cursor(rows, query))
            payload, headers = paginate_link(service, resource, rows, query)
            return json_response(self, 200, payload, headers=headers)
        except json.JSONDecodeError:
            return json_response(self, 400, {"error": "invalid json body"})


def apply_filters(service: str, resource: str, rows: List[Dict[str, Any]], query: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    if service == "demo-crm":
        if "search" in query:
            search = query["search"][0].lower()
            rows = [row for row in rows if search in json.dumps(row).lower()]
        if "company_id" in query:
            rows = [row for row in rows if row.get("company_id") == query["company_id"][0]]
        if "stage" in query:
            rows = [row for row in rows if row.get("stage") == query["stage"][0]]
    elif service == "demo-inventory":
        if resource == "items" and "query" in query:
            term = query["query"][0].lower()
            rows = [row for row in rows if term in row.get("name", "").lower() or term in row.get("category", "").lower()]
        if resource == "warehouses" and "region" in query:
            rows = [row for row in rows if row.get("region") == query["region"][0]]
        if resource == "orders" and "status" in query:
            rows = [row for row in rows if row.get("status") == query["status"][0]]
    elif service == "demo-hr":
        if resource == "employees" and "department_id" in query:
            rows = [row for row in rows if row.get("department_id") == query["department_id"][0]]
        if resource == "leave-requests" and "status" in query:
            rows = [row for row in rows if row.get("status") == query["status"][0]]
    return rows


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), DemoHandler)
    print(f"Demo API server running on http://{HOST}:{PORT}")
    print("Export DEMO_CRM_TOKEN=demo-crm-token")
    print("Export DEMO_INVENTORY_KEY=demo-inventory-key")
    print("Export DEMO_HR_BASIC=demo-hr-user:demo-hr-pass")
    server.serve_forever()


if __name__ == "__main__":
    main()
