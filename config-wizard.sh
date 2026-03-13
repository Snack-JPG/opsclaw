#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="${ROOT_DIR}/workspace"
CONFIG_PATH="${WORKSPACE_DIR}/config.json5"
USER_PATH="${WORKSPACE_DIR}/USER.md"

prompt() {
  local label="$1"
  local default_value="$2"
  local value
  read -r -p "${label} [${default_value}]: " value
  if [[ -z "${value}" ]]; then
    value="${default_value}"
  fi
  printf '%s' "${value}"
}

yes_no() {
  local label="$1"
  local default_value="$2"
  local value
  read -r -p "${label} [${default_value}] (y/n): " value
  if [[ -z "${value}" ]]; then
    value="${default_value}"
  fi
  [[ "${value}" =~ ^([Yy]|yes|YES)$ ]] && printf 'true' || printf 'false'
}

generate_token() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
}

echo "OpsClaw Config Wizard"

company="$(prompt "Company name" "Example Company")"
owner_name="$(prompt "Owner name" "Owner Name")"
timezone="$(prompt "Timezone" "Europe/London")"
channel="$(prompt "Primary owner channel" "telegram")"
deployment_mode="$(prompt "Deployment mode (client-machine/vps/docker-compose)" "docker-compose")"
template_name="$(prompt "Template profile (solo-consultant/agency/ecommerce/saas-founder/professional-services)" "agency")"
morning_brief="$(prompt "Morning briefing time" "07:30")"
weekly_brief="$(prompt "Weekly review time" "Monday 08:00")"
email_enabled="$(yes_no "Enable email-intel?" "y")"
calendar_enabled="$(yes_no "Enable calendar-ops?" "y")"
crm_enabled="$(yes_no "Enable crm-sync?" "y")"
tasks_enabled="$(yes_no "Enable task-tracker?" "y")"
reporting_enabled="$(yes_no "Enable ops-reporting?" "y")"
hooks_token="$(generate_token)"

cat > "${CONFIG_PATH}" <<EOF
{
  profile: "${template_name}",
  company: "${company}",
  timezone: "${timezone}",
  deployment: {
    mode: "${deployment_mode}",
  },
  channels: {
    ${channel}: { enabled: true },
  },
  agents: {
    defaults: {
      heartbeat: {
        every: "30m",
        target: "last",
        activeHours: { start: "07:00", end: "22:00" },
      },
      sandbox: { mode: "all", scope: "agent" },
    },
  },
  hooks: {
    enabled: true,
    token: "${hooks_token}",
    path: "/hooks",
    presets: ["gmail"],
    mappings: [],
  },
  skills: {
    entries: {
      "email-intel": { enabled: ${email_enabled} },
      "calendar-ops": { enabled: ${calendar_enabled} },
      "crm-sync": { enabled: ${crm_enabled} },
      "task-tracker": { enabled: ${tasks_enabled} },
      "ops-reporting": { enabled: ${reporting_enabled} },
    },
  },
  briefing: {
    morning: "${morning_brief}",
    weekly: "${weekly_brief}",
  },
}
EOF

python3 - <<PY
from pathlib import Path

path = Path(${USER_PATH@Q})
text = path.read_text(encoding="utf-8")
replacements = {
    "Your Company Name": ${company@Q},
    "Owner Name": ${owner_name@Q},
    "Europe/London": ${timezone@Q},
    "Telegram": ${channel@Q}.capitalize(),
}
for source, target in replacements.items():
    text = text.replace(source, target, 1)
path.write_text(text, encoding="utf-8")
PY

echo "Wrote ${CONFIG_PATH}"
echo "Updated ${USER_PATH} with starter values"
echo "Generated webhook token; move it into your secure environment store before production use"
