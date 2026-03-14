#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DIR="$ROOT_DIR/demo/api-bridge-demo"
SERVER_LOG="$DEMO_DIR/.demo-api.log"
PORT="${PORT:-8765}"

cyan() { printf '\033[1;36m%s\033[0m\n' "$1"; }
green() { printf '\033[1;32m%s\033[0m\n' "$1"; }
yellow() { printf '\033[1;33m%s\033[0m\n' "$1"; }
magenta() { printf '\033[1;35m%s\033[0m\n' "$1"; }

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

wait_for_server() {
  python3 - "$PORT" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.request

port = int(sys.argv[1])
url = f"http://127.0.0.1:{port}/api/v1/reports/summary"
request = urllib.request.Request(url, headers={"Authorization": "Bearer demo-token"})

deadline = time.time() + 10
while time.time() < deadline:
    try:
        with urllib.request.urlopen(request, timeout=1) as response:
            payload = json.load(response)
            if payload.get("contacts"):
                sys.exit(0)
    except Exception:
        time.sleep(0.2)
sys.exit(1)
PY
}

run_example() {
  local label="$1"
  shift
  magenta "▶ $label"
  printf '  %s\n' "$*"
  "$@"
  printf '\n'
}

export DEMO_API_TOKEN="demo-token"

cyan "Starting demo CRM API on port $PORT"
python3 "$DEMO_DIR/demo-api-server.py" --port "$PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!
if ! wait_for_server; then
  yellow "Demo API failed to start. Server log:"
  cat "$SERVER_LOG"
  exit 1
fi
green "Demo API is live"

cyan "Generating API bridge artifacts"
python3 "$ROOT_DIR/scripts/api-bridge/generator.py" \
  --config "$DEMO_DIR/demo-api-config.json" \
  --output-dir "$ROOT_DIR/generated"

green "Generated files"
printf '  %s\n' "$ROOT_DIR/generated/demo-crm/cli.py"
printf '  %s\n' "$ROOT_DIR/generated/demo-crm/SKILL.md"
printf '  %s\n\n' "$ROOT_DIR/generated/demo-crm/config.json"

cyan "Generated CLI help"
python3 "$ROOT_DIR/generated/demo-crm/cli.py" --help
printf '\n'

yellow "Running live examples against the demo API"
run_example "List contacts" \
  python3 "$ROOT_DIR/generated/demo-crm/cli.py" contacts list --format table
run_example "Get a specific contact" \
  python3 "$ROOT_DIR/generated/demo-crm/cli.py" contacts get --id c-1002
run_example "Create a new contact" \
  python3 "$ROOT_DIR/generated/demo-crm/cli.py" contacts create \
  --name "Riley Mercer" \
  --email "riley@granitemetrics.com" \
  --phone "+1-212-555-0155" \
  --company "Granite Metrics" \
  --title "Director of Ops" \
  --status lead
run_example "List deals" \
  python3 "$ROOT_DIR/generated/demo-crm/cli.py" deals list --format table
run_example "Get summary report" \
  python3 "$ROOT_DIR/generated/demo-crm/cli.py" reports summary --format table

cleanup
trap - EXIT
green "Demo complete!"
