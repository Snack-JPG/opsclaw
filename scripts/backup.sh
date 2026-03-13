#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE_STAMP="$(date +"%Y%m%d-%H%M%S")"
BACKUP_DIR="${OPSCLAW_BACKUP_DIR:-${ROOT_DIR}/backups}"
OPENCLAW_HOME="${OPENCLAW_HOME:-${HOME}/.openclaw}"
INSTALLED_WORKSPACE="${OPENCLAW_HOME}/workspace"
INSTALLED_SUPPORT="${OPENCLAW_HOME}/opsclaw"
CODEX_MEMORIES="${CODEX_HOME:-${HOME}/.codex}/memories"

usage() {
  cat <<'EOF'
Usage: ./scripts/backup.sh [--output-dir PATH]

Creates a compressed backup of the repository workspace, installed OpenClaw workspace,
support assets, and Codex memories when present.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      BACKUP_DIR="$2"
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

mkdir -p "${BACKUP_DIR}"
ARCHIVE_PATH="${BACKUP_DIR}/opsclaw-backup-${DATE_STAMP}.tar.gz"

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

manifest="${tmpdir}/MANIFEST.txt"
touch "${manifest}"

include_path() {
  local source_path="$1"
  local target_name="$2"

  if [[ -e "${source_path}" ]]; then
    printf '%s -> %s\n' "${source_path}" "${target_name}" >> "${manifest}"
    cp -R "${source_path}" "${tmpdir}/${target_name}"
  else
    printf 'MISSING %s\n' "${source_path}" >> "${manifest}"
  fi
}

include_path "${ROOT_DIR}/workspace" "repo-workspace"
include_path "${ROOT_DIR}/templates" "repo-templates"
include_path "${ROOT_DIR}/docs" "repo-docs"
include_path "${ROOT_DIR}/skills" "repo-skills"
include_path "${ROOT_DIR}/scripts" "repo-scripts"
include_path "${INSTALLED_WORKSPACE}" "installed-workspace"
include_path "${INSTALLED_SUPPORT}" "installed-support"
include_path "${CODEX_MEMORIES}" "codex-memories"

cat > "${tmpdir}/README.txt" <<EOF
OpsClaw backup created at ${DATE_STAMP}

Contents:
- Repository workspace and support assets
- Installed OpenClaw workspace under ${OPENCLAW_HOME}
- Codex memories when present

Restore strategy:
1. Extract the archive onto the target machine.
2. Review MANIFEST.txt for included paths.
3. Restore workspace and support assets into ${OPENCLAW_HOME} as needed.
4. Run ./scripts/migrate.sh --dry-run before overwriting an existing install.
EOF

tar -C "${tmpdir}" -czf "${ARCHIVE_PATH}" .

echo "Backup created: ${ARCHIVE_PATH}"
