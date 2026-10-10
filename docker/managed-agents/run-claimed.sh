#!/usr/bin/env bash
set -euo pipefail
# AgentKit Tool dispatchers start this path for one already claimed Work.
export MANAGED_AGENT_ENTRYPOINT_MODE=claimed
export MANAGED_AGENT_TOOL_EXECUTION="${MANAGED_AGENT_TOOL_EXECUTION:-local}"
exec bash /app/run-runtime.sh "$@"
