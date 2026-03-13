#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_HOME="${OPENCLAW_HOME:-${HOME}/.openclaw}"
TARGET_WORKSPACE="${OPENCLAW_HOME}/workspace"
TARGET_SUPPORT="${OPENCLAW_HOME}/opsclaw"
DRY_RUN=false
FROM_VERSION="unknown"
TO_VERSION="Phase 7"

usage() {
  cat <<'EOF'
Usage: ./scripts/migrate.sh [--dry-run] [--from VERSION] [--to VERSION]

Syncs repo assets into an existing OpsClaw installation while preserving
deployment-specific state such as memory, .env, and generated config.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --from)
      FROM_VERSION="$2"
      shift 2
      ;;
    --to)
      TO_VERSION="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

log() {
  printf '%s\n' "$1"
}

copy_dir() {
  local source_dir="$1"
  local target_dir="$2"

  if [[ "${DRY_RUN}" == true ]]; then
    log "[DRY RUN] mkdir -p ${target_dir}"
    log "[DRY RUN] rsync -a --delete ${source_dir}/ ${target_dir}/"
  else
    mkdir -p "${target_dir}"
    rsync -a --delete "${source_dir}/" "${target_dir}/"
    log "Synced ${source_dir} -> ${target_dir}"
  fi
}

copy_workspace_baseline() {
  local source_workspace="$1"
  local target_workspace="$2"

  if [[ "${DRY_RUN}" == true ]]; then
    log "[DRY RUN] mkdir -p ${target_workspace}"
  else
    mkdir -p "${target_workspace}"
  fi

  local baseline_files=(
    AGENTS.md
    SOUL.md
    USER.md
    HEARTBEAT.md
    IDENTITY.md
    TOOLS.md
  )

  local state_files=(
    heartbeat-state.json
    client-db.json
    ops-state.json
  )

  for file_name in "${baseline_files[@]}"; do
    if [[ "${DRY_RUN}" == true ]]; then
      log "[DRY RUN] install -m 0644 ${source_workspace}/${file_name} ${target_workspace}/${file_name}"
    else
      install -m 0644 "${source_workspace}/${file_name}" "${target_workspace}/${file_name}"
      log "Updated workspace baseline file ${file_name}"
    fi
  done

  if [[ ! -d "${target_workspace}/memory" ]]; then
    if [[ "${DRY_RUN}" == true ]]; then
      log "[DRY RUN] mkdir -p ${target_workspace}/memory"
    else
      mkdir -p "${target_workspace}/memory"
      log "Created ${target_workspace}/memory"
    fi
  fi

  for file_name in "${state_files[@]}"; do
    if [[ -f "${target_workspace}/${file_name}" ]]; then
      log "Preserved existing state file ${file_name}"
    else
      if [[ "${DRY_RUN}" == true ]]; then
        log "[DRY RUN] install -m 0644 ${source_workspace}/${file_name} ${target_workspace}/${file_name}"
      else
        install -m 0644 "${source_workspace}/${file_name}" "${target_workspace}/${file_name}"
        log "Seeded missing state file ${file_name}"
      fi
    fi
  done
}

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required for migration" >&2
  exit 1
fi

log "OpsClaw migration"
log "From: ${FROM_VERSION}"
log "To: ${TO_VERSION}"
log "Repo: ${ROOT_DIR}"
log "Target: ${OPENCLAW_HOME}"

copy_workspace_baseline "${ROOT_DIR}/workspace" "${TARGET_WORKSPACE}"
copy_dir "${ROOT_DIR}/templates" "${TARGET_SUPPORT}/templates"
copy_dir "${ROOT_DIR}/docs" "${TARGET_SUPPORT}/docs"
copy_dir "${ROOT_DIR}/scripts" "${TARGET_SUPPORT}/scripts"
copy_dir "${ROOT_DIR}/skills" "${TARGET_SUPPORT}/skills"

if [[ "${DRY_RUN}" == true ]]; then
  log "[DRY RUN] Preserved ${TARGET_WORKSPACE}/memory, ${TARGET_WORKSPACE}/config.json5, and ${TARGET_SUPPORT}/.env"
else
  log "Preserved deployment-specific state: memory directory, config.json5, and .env"
fi

log "Migration complete"
