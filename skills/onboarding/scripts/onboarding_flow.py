#!/usr/bin/env python3
"""Generate first-week onboarding messages for a deployed role-pack workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR.parent / "config" / "onboarding-config.json"
TIPS_PATH = SCRIPT_DIR / "tips.json"


DAY_COPY = {
    0: "Welcome to your new OpsClaw agent. It is configured for this role and ready to start with a first briefing.",
    1: "Checking that the first briefing landed and reinforcing the fastest ways to use the agent.",
    2: "Teaching CRM lookups and follow-up visibility.",
    3: "Teaching email triage and draft workflows.",
    4: "Teaching meeting prep and calendar-aware requests.",
    5: "Preparing the user for the first weekly review.",
    7: "Delivering the first weekly review and asking for feedback on signal quality.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, help="Role pack name")
    parser.add_argument("--day", required=True, type=int, help="Day of onboarding")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--user", required=True, help="Operator name")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_tip_keys(role: str, day: int, config: dict) -> list[str]:
    defaults = config["defaults"]["days"].get(str(day), {})
    tip_keys = list(defaults.get("tips", []))
    role_config = config["roles"].get(role, {})
    for extra in role_config.get("extra_tips", []):
        if extra not in tip_keys:
            tip_keys.append(extra)
    disabled = set(role_config.get("disabled_tips", []))
    return [tip for tip in tip_keys if tip not in disabled]


def render_text(role: str, day: int, company: str, user: str, config: dict, tips: dict) -> str:
    headline = config["defaults"]["days"].get(str(day), {}).get("headline", f"Day {day}")
    tip_sections = []
    for tip_key in collect_tip_keys(role, day, config):
        tip = tips[tip_key]
        examples = "; ".join(tip["examples"])
        tip_sections.append(f"- {tip['title']}: {tip['body']} Try: {examples}")
    tips_block = "\n".join(tip_sections) if tip_sections else "- No role-specific tips configured for this day."
    return "\n".join(
        [
            f"# Day {day} — {headline}",
            "",
            f"Hi {user},",
            "",
            f"{DAY_COPY.get(day, 'This onboarding check-in reinforces how to use your agent effectively.')}",
            f"Your {role} agent for {company} is tuned to keep work concise and actionable.",
            "",
            "Today's prompts:",
            tips_block,
            "",
            "Reply with what feels noisy, missing, or especially useful so the setup can be tuned.",
        ]
    )


def main() -> int:
    args = parse_args()
    config = load_json(CONFIG_PATH)
    tips = load_json(TIPS_PATH)
    tip_keys = collect_tip_keys(args.role, args.day, config)

    if args.format == "json":
        print(
            json.dumps(
                {
                    "role": args.role,
                    "day": args.day,
                    "company": args.company,
                    "user": args.user,
                    "headline": config["defaults"]["days"].get(str(args.day), {}).get("headline", f"Day {args.day}"),
                    "tips": [tips[key] | {"key": key} for key in tip_keys],
                },
                indent=2,
            )
        )
        return 0

    print(render_text(args.role, args.day, args.company, args.user, config, tips))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
