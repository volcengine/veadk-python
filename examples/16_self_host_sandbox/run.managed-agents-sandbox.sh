#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MANAGED_AGENT_ENTRYPOINT_MODE=claimed
export MANAGED_AGENT_TOOL_EXECUTION="${MANAGED_AGENT_TOOL_EXECUTION:-local}"
exec bash "$SCRIPT_DIR/run-runtime.sh" "$@"
