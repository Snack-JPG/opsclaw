#!/usr/bin/env python3
"""New client onboarding checklist automation for OpsClaw CRM Sync."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def load_json(path: Path) -> Any:
    """Load JSON from disk."""
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def utc_now() -> datetime:
    """Return current UTC time without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def isoformat(value: datetime) -> str:
    """Serialize a datetime as UTC ISO 8601."""
    return value.isoformat().replace("+00:00", "Z")


def slugify(value: str) -> str:
    """Generate a filesystem-friendly slug."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "client"


def render_template(text: str, context: dict[str, Any]) -> str:
    """Replace simple {{token}} placeholders."""
    rendered = text
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def load_provider_module(provider: str) -> Any:
    """Load the requested CRM provider module by file path."""
    script_name = "hubspot-client.py" if provider == "hubspot" else "pipedrive-client.py"
    module_name = f"opsclaw_{provider}_client"
    module_path = SCRIPT_DIR / script_name
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load provider module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    """Build CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True, help="Path to an onboarding template JSON file.")
    parser.add_argument("--client", type=Path, help="Path to a client JSON payload. Reads stdin if omitted.")
    parser.add_argument("--provider", choices=["hubspot", "pipedrive"], required=True, help="CRM provider.")
    parser.add_argument("--config", type=Path, help="Path to crm-config.json. Required with --create-records.")
    parser.add_argument("--create-records", action="store_true", help="Create CRM records using provider credentials.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def load_client_payload(path: Path | None) -> dict[str, Any]:
    """Load client onboarding input."""
    if path is None:
        payload = json.load(sys.stdin)
    else:
        payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Client onboarding payload must be a JSON object.")
    return payload


def task_due(offset_days: int) -> str:
    """Return an ISO due date offset from now."""
    return isoformat(utc_now() + timedelta(days=offset_days))


def build_plan(template: dict[str, Any], client: dict[str, Any], provider: str) -> dict[str, Any]:
    """Create the onboarding plan without touching external systems."""
    company_name = str(client.get("companyName") or client.get("name") or "Unknown Client")
    primary_contact = client.get("primaryContact", {})
    service_type = client.get("serviceType") or template.get("serviceType") or "default"
    deal_doc = template.get("deal", {})
    context = {
        "companyName": company_name,
        "serviceType": service_type,
        "contactName": primary_contact.get("name") or "",
    }
    kickoff_doc = template.get("kickoff", {})
    followups = [
        {
            "label": item["label"],
            "dueAt": task_due(int(item.get("offsetDays", 0))),
        }
        for item in template.get("followUps", [])
    ]
    tasks = [
        {
            "id": f"{slugify(company_name)}-{index + 1}",
            "title": render_template(item["title"], context),
            "owner": item.get("owner", "ops"),
            "priority": item.get("priority", "medium"),
            "dueAt": task_due(int(item.get("dueOffsetDays", 0))),
        }
        for index, item in enumerate(template.get("tasks", []))
    ]
    return {
        "generatedAt": isoformat(utc_now()),
        "provider": provider,
        "templateId": template.get("templateId"),
        "serviceType": service_type,
        "client": {
            "companyName": company_name,
            "website": client.get("website"),
            "primaryContact": primary_contact,
            "internalOwner": client.get("internalOwner"),
        },
        "crmPlan": {
            "contact": {
                "name": primary_contact.get("name"),
                "email": primary_contact.get("email"),
                "phone": primary_contact.get("phone"),
            },
            "company": {
                "name": company_name,
                "domain": client.get("domain"),
                "website": client.get("website"),
            },
            "deal": {
                "title": f"{company_name} - {deal_doc.get('titleSuffix', 'Onboarding')}",
                "stage": deal_doc.get("stage"),
                "pipeline": deal_doc.get("pipeline"),
                "value": client.get("dealValue"),
            },
        },
        "welcomeEmail": {
            "subject": render_template(template.get("welcomeEmail", {}).get("subject", "Welcome"), context),
            "summary": render_template(template.get("welcomeEmail", {}).get("summary", ""), context),
            "approvalRequired": True,
        },
        "kickoff": {
            "scheduleBy": task_due(int(kickoff_doc.get("scheduleWithinDays", 5))),
            "durationMinutes": kickoff_doc.get("durationMinutes", 45),
        },
        "followUps": followups,
        "tasks": tasks,
        "memoryLog": [
            f"Started {service_type} onboarding for {company_name}.",
            f"Prepared {len(tasks)} onboarding tasks and {len(followups)} follow-up reminders.",
        ],
    }


def create_records(plan: dict[str, Any], provider: str, config_path: Path) -> dict[str, Any]:
    """Create CRM records using the provider-specific client."""
    module = load_provider_module(provider)
    settings = module.load_settings(config_path)
    client = module.HubSpotClient(settings) if provider == "hubspot" else module.PipedriveClient(settings)

    company_payload = plan["crmPlan"]["company"]
    contact_payload = plan["crmPlan"]["contact"]
    deal_payload = plan["crmPlan"]["deal"]

    if provider == "hubspot":
        created_company = client.create_company({"name": company_payload["name"], "domain": company_payload.get("domain")})
        created_contact = client.create_contact(
            {
                "firstname": (contact_payload.get("name") or "").split(" ")[0],
                "lastname": " ".join((contact_payload.get("name") or "").split(" ")[1:]),
                "email": contact_payload.get("email"),
                "phone": contact_payload.get("phone"),
                "company": company_payload["name"],
            }
        )
        created_deal = client.create_deal(
            {
                "dealname": deal_payload["title"],
                "dealstage": deal_payload["stage"],
                "pipeline": deal_payload["pipeline"] or settings.default_pipeline_id,
                "amount": deal_payload.get("value"),
            }
        )
    else:
        created_company = client.create_company({"name": company_payload["name"], "address": company_payload.get("website")})
        created_contact = client.create_contact(
            {
                "name": contact_payload.get("name"),
                "email": contact_payload.get("email"),
                "phone": contact_payload.get("phone"),
                "org_id": int(created_company["id"]),
            }
        )
        created_deal = client.create_deal(
            {
                "title": deal_payload["title"],
                "stage_id": deal_payload["stage"],
                "value": deal_payload.get("value"),
                "org_id": int(created_company["id"]),
                "person_id": int(created_contact["id"]),
            }
        )

    return {
        "company": created_company,
        "contact": created_contact,
        "deal": created_deal,
    }


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    template = load_json(args.template)
    client_payload = load_client_payload(args.client)
    plan = build_plan(template, client_payload, args.provider)
    if args.create_records:
        if args.config is None:
            raise SystemExit("--config is required with --create-records.")
        plan["crmRecords"] = create_records(plan, args.provider, args.config)
    json.dump(plan, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
