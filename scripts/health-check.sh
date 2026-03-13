#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-${HOME}/.openclaw}"
ENV_FILE="${OPENCLAW_HOME}/opsclaw/.env"
EXIT_CODE=0

pass() {
  printf '[PASS] %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

fail() {
  printf '[FAIL] %s\n' "$1"
  EXIT_CODE=1
}

check_command() {
  local cmd="$1"
  local label="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    pass "${label}: $(command -v "${cmd}")"
  else
    fail "${label} missing (${cmd})"
  fi
}

check_optional_command() {
  local cmd="$1"
  local label="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    pass "${label}: $(command -v "${cmd}")"
  else
    warn "${label} not installed (${cmd})"
  fi
}

check_url() {
  local name="$1"
  local url="$2"

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl unavailable, skipped ${name} connectivity check"
    return
  fi

  if curl --silent --show-error --head --location --max-time 10 "${url}" >/dev/null 2>&1; then
    pass "${name} reachable (${url})"
  else
    warn "${name} unreachable or blocked (${url})"
  fi
}

disk_free_gb() {
  local dir="$1"
  df -Pk "${dir}" | awk 'NR==2 {printf "%.1f", $4 / 1024 / 1024}'
}

memory_pressure() {
  if command -v vm_stat >/dev/null 2>&1; then
    vm_stat | awk '
      /Pages free/ {gsub("\\.", "", $3); free = $3}
      /Pages speculative/ {gsub("\\.", "", $3); spec = $3}
      END {printf "%.0f", (free + spec) * 4096 / 1024 / 1024}
    '
  elif command -v free >/dev/null 2>&1; then
    free -m | awk 'NR==2 {print $7}'
  else
    printf 'unknown'
  fi
}

echo "OpsClaw Health Check"
echo "Repo: ${ROOT_DIR}"
echo "OpenClaw home: ${OPENCLAW_HOME}"

check_command node "Node.js"
check_command npm "npm"
check_command python3 "Python 3"
check_optional_command openclaw "OpenClaw CLI"
check_optional_command docker "Docker"
check_optional_command jq "jq"
check_optional_command curl "curl"

if command -v node >/dev/null 2>&1; then
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  if [[ "${node_major}" -ge 20 ]]; then
    pass "Node.js major version ${node_major}"
  else
    fail "Node.js 20+ required, found $(node --version)"
  fi
fi

if [[ -d "${OPENCLAW_HOME}/workspace" ]]; then
  pass "Installed workspace exists"
else
  warn "Installed workspace missing at ${OPENCLAW_HOME}/workspace"
fi

if [[ -d "${OPENCLAW_HOME}/opsclaw" ]]; then
  pass "Installed support assets exist"
else
  warn "Installed support assets missing at ${OPENCLAW_HOME}/opsclaw"
fi

if [[ -f "${ROOT_DIR}/workspace/ops-state.json" ]]; then
  pass "Repo ops-state.json present"
else
  fail "Repo ops-state.json missing"
fi

if [[ -f "${ENV_FILE}" ]]; then
  pass ".env file present at ${ENV_FILE}"
else
  warn ".env file missing at ${ENV_FILE}"
fi

required_env=(
  OPSCLAW_GATEWAY_TOKEN
  OPSCLAW_HOOKS_TOKEN
)

optional_env=(
  HUBSPOT_ACCESS_TOKEN
  PIPEDRIVE_API_TOKEN
  LINEAR_API_KEY
  NOTION_API_TOKEN
  ASANA_ACCESS_TOKEN
)

for var_name in "${required_env[@]}"; do
  if [[ -n "${!var_name:-}" ]]; then
    pass "Env var ${var_name} is set"
  else
    warn "Env var ${var_name} is not set in current shell"
  fi
done

for var_name in "${optional_env[@]}"; do
  if [[ -n "${!var_name:-}" ]]; then
    pass "Optional env var ${var_name} is set"
  else
    warn "Optional env var ${var_name} is not set"
  fi
done

echo "Connectivity"
check_url "npm registry" "https://registry.npmjs.org/"
check_url "OpenAI" "https://api.openai.com/"
check_url "Google APIs" "https://www.googleapis.com/"
check_url "HubSpot" "https://api.hubapi.com/"
check_url "Pipedrive" "https://api.pipedrive.com/"
check_url "Linear" "https://api.linear.app/"
check_url "Notion" "https://api.notion.com/"
check_url "Asana" "https://app.asana.com/"

echo "Capacity"
if [[ -d "${ROOT_DIR}" ]]; then
  free_gb="$(disk_free_gb "${ROOT_DIR}")"
  if awk "BEGIN {exit !(${free_gb} >= 5)}"; then
    pass "Disk free at repo volume: ${free_gb} GB"
  else
    warn "Low disk free at repo volume: ${free_gb} GB"
  fi
fi

available_mem="$(memory_pressure)"
if [[ "${available_mem}" == "unknown" ]]; then
  warn "Could not determine available memory on this host"
else
  if awk "BEGIN {exit !(${available_mem} >= 512)}"; then
    pass "Approx. available memory: ${available_mem} MB"
  else
    warn "Low available memory: ${available_mem} MB"
  fi
fi

echo "Validation"
if bash -n "${ROOT_DIR}/setup.sh" && bash -n "${ROOT_DIR}/config-wizard.sh"; then
  pass "Core shell scripts parse cleanly"
else
  fail "Shell syntax validation failed"
fi

if PYTHONPYCACHEPREFIX=/tmp/opsclaw-pycache python3 -m compileall "${ROOT_DIR}/scripts" >/dev/null 2>&1; then
  pass "Python helper scripts compile"
else
  fail "Python helper scripts failed to compile"
fi

exit "${EXIT_CODE}"
