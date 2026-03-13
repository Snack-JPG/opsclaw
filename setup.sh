#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ROOT="${HOME}/.openclaw"
TARGET_WORKSPACE="${TARGET_ROOT}/workspace"
TARGET_SUPPORT="${TARGET_ROOT}/opsclaw"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

copy_tree() {
  local source_dir="$1"
  local target_dir="$2"
  mkdir -p "$target_dir"
  cp -R "${source_dir}/." "$target_dir/"
}

echo "OpsClaw Setup v1.0"
echo "Repository: ${ROOT_DIR}"

require_command node
require_command npm
require_command python3

NODE_MAJOR="$(node -p 'process.versions.node.split(\".\")[0]')"
if [[ "${NODE_MAJOR}" -lt 20 ]]; then
  echo "Node.js 20+ is required. Found $(node --version)." >&2
  exit 1
fi

if ! command -v openclaw >/dev/null 2>&1; then
  echo "Installing OpenClaw globally via npm..."
  npm i -g openclaw
else
  echo "OpenClaw already available at $(command -v openclaw)"
fi

if ! command -v gws >/dev/null 2>&1; then
  echo "Installing Google Workspace CLI globally via npm..."
  npm i -g @googleworkspace/cli
else
  echo "Google Workspace CLI already available at $(command -v gws)"
fi

mkdir -p "${TARGET_WORKSPACE}" "${TARGET_SUPPORT}"
mkdir -p "${TARGET_WORKSPACE}/memory/dead-letters"

copy_tree "${ROOT_DIR}/workspace" "${TARGET_WORKSPACE}"
copy_tree "${ROOT_DIR}/templates" "${TARGET_SUPPORT}/templates"
copy_tree "${ROOT_DIR}/docs" "${TARGET_SUPPORT}/docs"
copy_tree "${ROOT_DIR}/scripts" "${TARGET_SUPPORT}/scripts"
copy_tree "${ROOT_DIR}/skills" "${TARGET_SUPPORT}/skills"

if [[ ! -f "${TARGET_SUPPORT}/.env.example" ]]; then
  cat > "${TARGET_SUPPORT}/.env.example" <<'EOF'
OPSCLAW_GATEWAY_TOKEN=replace-me
OPSCLAW_HOOKS_TOKEN=replace-me
OPSCLAW_OWNER_CHANNEL=telegram
OPSCLAW_TIMEZONE=Europe/London
EOF
fi

echo "Workspace installed to ${TARGET_WORKSPACE}"
echo "Support assets installed to ${TARGET_SUPPORT}"
echo
echo "Next steps:"
echo "  1. Run ${ROOT_DIR}/config-wizard.sh"
echo "  2. Run gws auth setup --login"
echo "  3. Add secrets to ${TARGET_SUPPORT}/.env or your secret manager"
echo "  4. Run ${ROOT_DIR}/scripts/health-check.sh"
echo "  5. Run openclaw security audit --deep"
echo "  6. Start with openclaw gateway start"
