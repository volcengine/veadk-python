#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${MANAGED_AGENTS_PYTHON:-python}"
listener_pid=""
worker_pid=""
cleanup() {
    trap - EXIT INT TERM
    for child_pid in "$listener_pid" "$worker_pid"; do
        if [[ -n "$child_pid" ]]; then
            kill "$child_pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export MANAGED_AGENT_WORK_SCOPE="${MANAGED_AGENT_WORK_SCOPE:-account}"
export MA_AGENT_LOOP_RUNTIME_TYPE="${MA_AGENT_LOOP_RUNTIME_TYPE:-agentkit_runtime}"
export MANAGED_AGENT_TOOL_EXECUTION="${MANAGED_AGENT_TOOL_EXECUTION:-remote}"

case "${MANAGED_AGENT_ENTRYPOINT_MODE:-worker}" in
    worker) mode="--managed-agent-worker" ;;
    claimed) mode="--managed-agent-work-item" ;;
    *) echo "MANAGED_AGENT_ENTRYPOINT_MODE must be worker or claimed" >&2; exit 2 ;;
esac

"$PYTHON_BIN" -m veadk.runtime.managed_agents.health &
listener_pid=$!
"$PYTHON_BIN" -m veadk.runtime.managed_agents.worker "$mode" "$@" &
worker_pid=$!

# Failure or completion of either process must stop its sibling.
wait -n "$listener_pid" "$worker_pid"
