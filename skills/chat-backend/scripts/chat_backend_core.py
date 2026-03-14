#!/usr/bin/env python3
"""Shared primitives for the OpsClaw chat backend."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import hmac
import json
import os
import random
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "configs" / "company-configs"
DATA_DIR = ROOT_DIR / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
MAX_MESSAGES_PER_FILE = 1000
TOKEN_ENV_VAR = "OPSCLAW_CHAT_SECRET"
DEFAULT_SECRET = "opsclaw-chat-backend-dev-secret"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    return cleaned.strip("-") or "company"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def role_template(role: str, display_name: Optional[str] = None, greeting: Optional[str] = None) -> Dict[str, Any]:
    default_templates = {
        "finance": {
            "display_name": "Finance Agent",
            "avatar_emoji": "💰",
            "greeting": "Hi, I can help with budgets, invoices, and expenses.",
            "description": "Handles invoices, expenses, budgets, and financial queries",
        },
        "ops": {
            "display_name": "Ops Agent",
            "avatar_emoji": "⚙️",
            "greeting": "Hi, I can help with operations, inventory, and logistics.",
            "description": "Manages inventory, logistics, scheduling, and operations",
        },
        "hr": {
            "display_name": "People Agent",
            "avatar_emoji": "👥",
            "greeting": "Hello, I can help with leave, policies, and onboarding.",
            "description": "Handles leave requests, policies, onboarding, and people queries",
        },
        "admin": {
            "display_name": "Admin Agent",
            "avatar_emoji": "📋",
            "greeting": "Hi, I handle admin, facilities, and office support.",
            "description": "Office management, facilities, supplies, and general admin",
        },
    }
    payload = copy.deepcopy(default_templates.get(role, default_templates["ops"]))
    if display_name:
        payload["display_name"] = display_name
    if greeting:
        payload["greeting"] = greeting
    return payload


def build_company_config(company_name: str, company_id: Optional[str] = None) -> Dict[str, Any]:
    resolved_company_id = company_id or slugify(company_name)
    return {
        "company_id": resolved_company_id,
        "company_name": company_name,
        "branding": {
            "product_name": f"{company_name} Ops",
            "logo_url": "",
            "primary_color": "#1f5eff",
            "secondary_color": "#eef3ff",
            "font": "Inter",
        },
        "roles": {
            "finance": role_template("finance"),
            "ops": role_template("ops"),
            "hr": role_template("hr"),
            "admin": role_template("admin"),
        },
        "auth": {
            "type": "simple",
            "allowed_domains": [],
        },
    }


class ConfigManager:
    def __init__(self, config_dir: Path = CONFIG_DIR) -> None:
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def path_for_company(self, company_id: str) -> Path:
        return self.config_dir / f"{slugify(company_id)}.json"

    def list_configs(self) -> List[Dict[str, Any]]:
        configs = []
        for path in sorted(self.config_dir.glob("*.json")):
            configs.append(read_json(path, {}))
        return configs

    def load(self, company_id: str) -> Dict[str, Any]:
        path = self.path_for_company(company_id)
        if not path.exists():
            raise FileNotFoundError(f"Company config not found: {company_id}")
        return read_json(path, {})

    def save(self, config: Dict[str, Any]) -> Path:
        path = self.path_for_company(config["company_id"])
        write_json(path, config)
        return path

    def init_company(self, company_name: str, company_id: Optional[str] = None) -> Dict[str, Any]:
        config = build_company_config(company_name, company_id=company_id)
        if self.path_for_company(config["company_id"]).exists():
            raise FileExistsError(f"Company already exists: {config['company_id']}")
        self.save(config)
        return config

    def set_branding(
        self,
        company_id: str,
        *,
        product_name: Optional[str] = None,
        color: Optional[str] = None,
        logo: Optional[str] = None,
        secondary_color: Optional[str] = None,
        font: Optional[str] = None,
    ) -> Dict[str, Any]:
        config = self.load(company_id)
        branding = config.setdefault("branding", {})
        if product_name is not None:
            branding["product_name"] = product_name
        if color is not None:
            branding["primary_color"] = color
        if logo is not None:
            branding["logo_url"] = logo
        if secondary_color is not None:
            branding["secondary_color"] = secondary_color
        if font is not None:
            branding["font"] = font
        self.save(config)
        return config

    def add_role(
        self,
        company_id: str,
        role: str,
        *,
        name: Optional[str] = None,
        greeting: Optional[str] = None,
        description: Optional[str] = None,
        avatar: Optional[str] = None,
    ) -> Dict[str, Any]:
        config = self.load(company_id)
        role_data = role_template(role, display_name=name, greeting=greeting)
        if description is not None:
            role_data["description"] = description
        if avatar is not None:
            role_data["avatar_emoji"] = avatar
        config.setdefault("roles", {})[role] = role_data
        self.save(config)
        return config

    def resolve_company(self, company_id: Optional[str]) -> Dict[str, Any]:
        configs = self.list_configs()
        if not configs:
            raise FileNotFoundError("No company configs found.")
        if company_id:
            return self.load(company_id)
        for config in configs:
            if config.get("company_id") == "demo":
                return config
        return configs[0]


class MessageStore:
    def __init__(self, base_dir: Path = DATA_DIR, max_messages: int = MAX_MESSAGES_PER_FILE) -> None:
        self.base_dir = base_dir
        self.max_messages = max_messages
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, company_id: str, role: str, user_id: str) -> Path:
        safe_company = slugify(company_id)
        safe_role = slugify(role)
        safe_user = slugify(user_id)
        return self.base_dir / safe_company / safe_role / f"{safe_user}.json"

    def load_messages(self, company_id: str, role: str, user_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        path = self._path(company_id, role, user_id)
        messages = read_json(path, [])
        if limit is None or limit >= len(messages):
            return messages
        return messages[-limit:]

    def append_message(
        self,
        company_id: str,
        role: str,
        user_id: str,
        *,
        sender: str,
        text: str,
        agent_name: Optional[str] = None,
        message_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        path = self._path(company_id, role, user_id)
        messages = read_json(path, [])
        payload = {
            "id": message_id or str(uuid.uuid4()),
            "sender": sender,
            "text": text,
            "timestamp": timestamp or utc_now_iso(),
        }
        if agent_name:
            payload["agent_name"] = agent_name
        messages.append(payload)
        if len(messages) > self.max_messages:
            messages = messages[-self.max_messages :]
        write_json(path, messages)
        return payload


class SessionManager:
    def __init__(self, sessions_file: Path = SESSIONS_FILE, secret: Optional[str] = None) -> None:
        self.sessions_file = sessions_file
        self.secret = (secret or os.environ.get(TOKEN_ENV_VAR) or DEFAULT_SECRET).encode("utf-8")
        self.sessions_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_sessions(self) -> Dict[str, Dict[str, Any]]:
        return read_json(self.sessions_file, {})

    def _save_sessions(self, sessions: Dict[str, Dict[str, Any]]) -> None:
        write_json(self.sessions_file, sessions)

    def create_session(self, company_id: str, employee_name: str, employee_email: Optional[str] = None) -> Dict[str, Any]:
        issued_at = utc_now_iso()
        session_id = str(uuid.uuid4())
        raw = f"{company_id}:{employee_name}:{session_id}:{issued_at}"
        signature = hmac.new(self.secret, raw.encode("utf-8"), hashlib.sha256).digest()
        token = base64.urlsafe_b64encode(raw.encode("utf-8") + b"." + signature).decode("ascii").rstrip("=")
        session = {
            "session_id": session_id,
            "company_id": company_id,
            "employee_name": employee_name,
            "employee_email": employee_email or "",
            "user_id": slugify(employee_email or employee_name),
            "issued_at": issued_at,
            "token": token,
        }
        sessions = self._load_sessions()
        sessions[token] = session
        self._save_sessions(sessions)
        return session

    def validate(self, token: str) -> Optional[Dict[str, Any]]:
        sessions = self._load_sessions()
        return sessions.get(token)


@dataclass(frozen=True)
class ResponseTemplate:
    keywords: Tuple[str, ...]
    responses: Tuple[str, ...]


ROLE_RESPONSE_TEMPLATES: Dict[str, List[ResponseTemplate]] = {
    "finance": [
        ResponseTemplate(("budget", "spend", "forecast"), (
            "The current operating budget is tracking at 92 percent of plan, with software spend slightly ahead because of annual renewals landing this month.",
            "Budget-wise we still have room in the quarter, but contractor spend is the line item getting closest to the ceiling.",
            "Forecast view looks stable: recurring costs are on target and the only variance I see is a higher-than-expected travel run rate.",
            "I can confirm the budget is still green overall, though marketing tooling and event costs are the two areas worth watching.",
        )),
        ResponseTemplate(("invoice", "bill", "payment", "vendor"), (
            "I found the invoice queue and the oldest unpaid vendor item is currently four business days old, which is still inside the standard processing window.",
            "For vendor payments, the next batch run is scheduled for tomorrow morning and anything approved today will be included.",
            "The invoice status looks normal from a finance operations perspective: nothing appears overdue, but two submissions are still waiting on manager approval.",
            "If this is about a bill, the usual blocker is missing PO detail. Once that is attached, finance can clear it in the next review cycle.",
        )),
        ResponseTemplate(("expense", "receipt", "reimburse", "card"), (
            "Expense reimbursements submitted before Friday are usually paid in the next payroll cycle, assuming the receipt and cost center are attached.",
            "The expense queue is manageable right now. The items taking longest are mostly missing receipts or unclear client attribution.",
            "Corporate card spend is trending normally this week, with travel and software renewals driving most of the activity.",
            "If you need a reimbursement fast, make sure the receipt image is legible and the business reason is explicit. That removes most approval delays.",
        )),
        ResponseTemplate(("payroll", "salary", "comp"), (
            "Payroll is currently locked for processing, so compensation changes submitted now would typically land in the next cycle.",
            "Salary and payroll questions usually depend on whether the change is before or after the payroll cutoff. Right now we are in the post-cutoff window.",
            "From a payroll standpoint everything looks routine this week, with no exception batches flagged.",
            "If this relates to compensation, finance can confirm timing and approvals, but HR usually owns the policy side.",
        )),
        ResponseTemplate((), (
            "From a finance view, I can help with budgets, invoices, expenses, and payment timing. If you share the specific item, I’ll narrow it down.",
            "Finance summary: cash timing looks steady, approvals are moving, and the only slowdowns I’m seeing are on items missing documentation.",
            "I can work through that with you. The fastest path is usually checking budget owner, approval status, and whether the record has a PO or receipt attached.",
            "That sounds finance-related. I’d start by confirming the vendor, amount, and cost center so we can trace it cleanly.",
        )),
    ],
    "ops": [
        ResponseTemplate(("inventory", "stock", "warehouse", "sku"), (
            "Inventory is healthy on the top-moving SKUs, but the west warehouse is getting tight on one packaging component.",
            "Current stock levels look stable overall. The only item below reorder threshold is the medium carton run used in outbound kits.",
            "Warehouse coverage is fine for this week, though we should replenish safety stock on fast-moving accessories before the next promo lands.",
            "I checked the inventory pattern and there is no broad shortage, just one pocket of low stock that procurement is already watching.",
        )),
        ResponseTemplate(("schedule", "shift", "roster", "timeline"), (
            "The operations schedule is intact, but the late Wednesday slot is under capacity by one person right now.",
            "Timeline-wise we’re still on track. The main risk is a compressed handoff between receiving and fulfillment at the end of the week.",
            "The current roster covers the baseline workload, though any additional same-day requests would put pressure on the afternoon team.",
            "Schedule status is mostly clean. If this is urgent, I’d move one cross-trained operator into the bottleneck window and keep the rest steady.",
        )),
        ResponseTemplate(("logistics", "shipment", "delivery", "carrier"), (
            "Carrier performance is normal this week, with average delivery timing holding close to SLA.",
            "Logistics looks manageable. There’s a slight delay on one inbound lane, but it hasn’t cascaded into customer orders yet.",
            "Shipment flow is stable overall, although the Friday pickup window is getting crowded.",
            "If this is about delivery timing, the most likely issue is carrier cutoff rather than internal handling.",
        )),
        ResponseTemplate(("incident", "delay", "blocked", "issue"), (
            "Operationally the issue sounds containable. The first step is isolating whether the delay is inventory, labor, or carrier-related.",
            "I’d classify that as a workflow interruption rather than a systemic outage for now. We can usually recover the queue within the same shift.",
            "The best ops move is to protect the customer-facing deadlines first, then rebalance internal work around the blockage.",
            "That kind of delay usually clears once the handoff owner is explicit. I’d assign one person to own the next update and recovery plan.",
        )),
        ResponseTemplate((), (
            "I can help with inventory, scheduling, logistics, and workflow bottlenecks. Share the constraint and I’ll give you an ops read quickly.",
            "Operations view: throughput is steady, but anything tied to late-day pickups or low-stock packaging deserves attention.",
            "That sounds operational. I’d want to know the site, timeline, and whether the blocker is inventory, staffing, or carrier capacity.",
            "From an ops standpoint, the goal is keeping flow predictable. I can help trace the bottleneck if you give me the affected process.",
        )),
    ],
    "hr": [
        ResponseTemplate(("leave", "vacation", "holiday", "pto"), (
            "Based on the standard leave model, most employees still have enough balance for a short request this month unless they already booked a long trip recently.",
            "Leave requests are moving normally. The main approval check is usually team coverage rather than balance.",
            "For PTO, the cleanest path is submitting dates early enough for manager approval and making sure there isn’t a staffing conflict on the team calendar.",
            "Holiday and leave questions usually come down to local policy plus coverage. HR can confirm both once the dates are clear.",
        )),
        ResponseTemplate(("policy", "handbook", "benefit", "benefits"), (
            "The handbook policy approach is usually straightforward: confirm the written rule first, then check whether there’s a local or role-specific exception.",
            "Benefits and policy questions often have a standard answer unless there’s a country-specific variation. I’d verify location before giving a final read.",
            "Policy-wise, the default is consistency. If something looks unusual, HR would normally ask whether the case has prior precedent.",
            "For handbook questions, I’d expect HR to reference the latest policy version and then confirm any manager discretion separately.",
        )),
        ResponseTemplate(("onboarding", "new hire", "training", "ramp"), (
            "Onboarding is usually healthiest when access, manager check-ins, and week-one goals are all confirmed before the start date.",
            "For a new hire, the biggest risk is tool access lag. HR can usually coordinate with IT and the hiring manager to close that quickly.",
            "Ramp plans work best when the first two weeks are structured around role context, key systems, and one clear early win.",
            "If this is about onboarding, I’d first check paperwork completion, equipment status, and whether the 30-day plan has been shared.",
        )),
        ResponseTemplate(("performance", "review", "manager", "feedback"), (
            "Performance conversations are usually easiest when the manager anchors on observable examples, expectations, and a clear next review point.",
            "For review cycles, HR generally wants consistency in documentation and calibration before anything is finalized.",
            "If feedback feels urgent, the best practice is a direct manager conversation first, followed by HR support if policy or fairness concerns show up.",
            "That sounds like a people-manager topic. HR can help frame the process, but the quality of the outcome usually depends on specific documented examples.",
        )),
        ResponseTemplate((), (
            "I can help with leave, policies, onboarding, benefits, and people processes. If you share the case, I’ll give you the likely HR path.",
            "HR view: most questions resolve fastest once we know the employee location, manager, and whether a written policy already covers it.",
            "That sounds HR-related. I’d want to know whether this is policy interpretation, a leave request, or a manager support issue.",
            "People operations usually comes down to consistency, documentation, and timing. I can help map the next step if you give me more detail.",
        )),
    ],
    "admin": [
        ResponseTemplate(("office", "desk", "facility", "facilities"), (
            "Facilities-wise the office is operating normally, and most requests are being cleared within the same business day unless outside vendors are needed.",
            "Office support looks steady. The only delays I’d expect are for anything requiring building management approval.",
            "For facilities requests, the key detail is whether this is urgent, safety-related, or just a normal workplace fix.",
            "Building operations are stable right now. If this needs facilities, I’d log the exact room or floor so the admin team can route it properly.",
        )),
        ResponseTemplate(("supply", "supplies", "order", "stationery"), (
            "Office supplies are in decent shape this week, though printer toner and notebook stock are usually the first items to run low.",
            "Supply orders are typically bundled twice a week, so anything non-urgent can usually ride the next batch.",
            "For supplies, I’d expect a quick turnaround unless the request is specialized equipment rather than standard office stock.",
            "The admin path is straightforward here: confirm quantity, location, and whether this is a recurring need or a one-off order.",
        )),
        ResponseTemplate(("meeting", "room", "conference", "booking"), (
            "Meeting room availability is usually tight mid-morning, but early afternoon tends to have more flexibility.",
            "Conference room issues are often solvable by shifting one slot or moving to a smaller room if attendance is uncertain.",
            "If this is a room booking problem, the first thing I’d check is whether the room needs AV setup or just seats and a screen.",
            "For meetings, admin can usually help fastest when the attendee count, office location, and timing are all explicit.",
        )),
        ResponseTemplate(("access", "badge", "visitor", "parking"), (
            "Badge and access requests usually move quickly once identity and start date are confirmed.",
            "Visitor handling is straightforward as long as reception has the guest list and expected arrival time in advance.",
            "Parking and access matters tend to depend on site rules, but the admin team can usually resolve them the same day.",
            "For access-related issues, the cleanest route is to include the person’s name, site, and whether they need temporary or permanent access.",
        )),
        ResponseTemplate((), (
            "I can help with facilities, supplies, rooms, access, and day-to-day office admin. Share the request and I’ll route it in a practical way.",
            "Admin view: routine office requests are moving fine, and anything urgent mostly depends on location and vendor involvement.",
            "That sounds like a workplace support question. I’d want to know the site, urgency, and whether it’s facilities, supplies, or access.",
            "General admin usually resolves fastest when the exact location and desired timing are clear from the start.",
        )),
    ],
}


def select_template(role: str, text: str) -> str:
    normalized = text.lower()
    templates = ROLE_RESPONSE_TEMPLATES.get(role, ROLE_RESPONSE_TEMPLATES["ops"])
    for template in templates:
        if template.keywords and any(keyword in normalized for keyword in template.keywords):
            return random.choice(template.responses)
    fallback = next(template for template in templates if not template.keywords)
    return random.choice(fallback.responses)


def generate_agent_response(config: Dict[str, Any], role: str, message_text: str, employee_name: str) -> Dict[str, str]:
    role_data = config.get("roles", {}).get(role) or role_template(role)
    agent_name = role_data.get("display_name", role.title())
    prefix_options = [
        f"{employee_name}, ",
        "Quick read: ",
        "Here’s the latest: ",
        "",
    ]
    text = f"{random.choice(prefix_options)}{select_template(role, message_text)}".strip()
    return {
        "type": "response",
        "text": text,
        "agent_name": agent_name,
        "timestamp": utc_now_iso(),
    }


def sanitize_config_for_client(config: Dict[str, Any]) -> Dict[str, Any]:
    role_map: Dict[str, Dict[str, Any]] = {}
    role_list: List[Dict[str, Any]] = []
    for role_key, role_data in sorted(config.get("roles", {}).items()):
        entry = {
            "display_name": role_data.get("display_name", role_key.title()),
            "avatar_emoji": role_data.get("avatar_emoji", ""),
            "greeting": role_data.get("greeting", ""),
            "description": role_data.get("description", ""),
        }
        role_map[role_key] = entry
        role_list.append({"role": role_key, **entry})
    payload = {
        "company_id": config.get("company_id"),
        "company_name": config.get("company_name"),
        "branding": config.get("branding", {}),
        "roles": role_map,
        "role_list": role_list,
    }
    return payload


def parse_args(parser: argparse.ArgumentParser, argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    return parser.parse_args(list(argv) if argv is not None else None)
