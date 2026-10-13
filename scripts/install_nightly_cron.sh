#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${REPO_ROOT}/services/api/.venv/bin/python"
JOB_SCRIPT="${REPO_ROOT}/scripts/nightly_export.py"
MARKER="# nightly_export managed by ${REPO_ROOT}"
CRON_LINE="0 2 * * * cd '${REPO_ROOT}' && '${PYTHON}' '${JOB_SCRIPT}' >> '${REPO_ROOT}/data/raw/nightly_export.log' 2>&1 ${MARKER}"

if [[ ! -x "${PYTHON}" ]]; then
  printf 'Expected project Python interpreter not found: %s\n' "${PYTHON}" >&2
  exit 1
fi

CURRENT="$(crontab -l 2>/dev/null || true)"
WITHOUT_OWN="$(printf '%s\n' "${CURRENT}" | awk -v marker="${MARKER}" 'index($0, marker) == 0 && NF { print }')"
if [[ -n "${WITHOUT_OWN}" ]]; then
  printf '%s\n%s\n' "${WITHOUT_OWN}" "${CRON_LINE}" | crontab -
else
  printf '%s\n' "${CRON_LINE}" | crontab -
fi
printf 'Installed nightly cron entry: %s\n' "${CRON_LINE}"
