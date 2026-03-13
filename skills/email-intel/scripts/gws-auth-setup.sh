#!/usr/bin/env bash
set -euo pipefail

if ! command -v gws >/dev/null 2>&1; then
  echo "Missing required command: gws" >&2
  echo "Install it with: npm install -g @googleworkspace/cli" >&2
  exit 1
fi

exec gws auth setup --login "$@"
