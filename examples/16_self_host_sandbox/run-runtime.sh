#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    export MANAGED_AGENTS_PYTHON="$REPO_ROOT/.venv/bin/python"
fi
exec bash "$REPO_ROOT/docker/managed-agents/run-runtime.sh" "$@"
