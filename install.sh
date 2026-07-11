#!/usr/bin/env bash
# AgentAuditAI Phase 1 — pre-commit hook installer
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SRC="${ROOT_DIR}/hooks/pre-commit"
HOOK_DEST="${ROOT_DIR}/.git/hooks/pre-commit"

if [[ ! -d "${ROOT_DIR}/.git" ]]; then
  echo "error: .git directory not found. Run this script from the repository root." >&2
  exit 1
fi

if [[ ! -f "${HOOK_SRC}" ]]; then
  echo "error: hook template not found at ${HOOK_SRC}" >&2
  exit 1
fi

cp "${HOOK_SRC}" "${HOOK_DEST}"
chmod +x "${HOOK_DEST}"

echo "Installed AgentAuditAI pre-commit hook:"
echo "  ${HOOK_DEST}"
