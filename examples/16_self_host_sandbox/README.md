# 16. Self-hosted Managed Agents

[中文版](README.zh.md)

VeADK runs the model loop; native tool execution may run locally in an isolated
worker or dispatch through a Managed Agents gateway. The reusable implementation
ships in `veadk.runtime.managed_agents` and `veadk.integrations.mpa`. This directory
contains launchers and acceptance scripts, not production library code.

## Install and run

```bash
uv sync --extra sandbox --extra extensions
cp examples/16_self_host_sandbox/.env.example examples/16_self_host_sandbox/.env
# Configure the private .env before starting a worker.
bash examples/16_self_host_sandbox/run.sh --managed-agent-worker
```

The launcher loads `.env` as defaults; exported variables take precedence. The
library never loads example configuration or creates a remote Session at import.
Run an installed package directly without this example directory:

```bash
python -m veadk.runtime.managed_agents.worker --managed-agent-worker
python -m veadk.runtime.managed_agents.worker --managed-agent-work-item
```

Worker mode continuously polls Work. Claimed mode requires injected Work/Session
IDs and lease state from the external dispatcher. The Session snapshot owns model,
permissions, tools, Skills, MCP and Identity bindings. Account scope selects the
configured execution pool; environment scope additionally needs an Environment ID.
Local conversation mode creates one Managed Session for each VeADK Session; the
Runner releases it to idle when overlapping local turns finish.

## Execution and state

Native Anthropic tools run through their tool context, retaining file-edit/read
semantics. MCP tools keep their actual MCP transport. Tools requiring confirmation
wait for correlated permission events; custom tools wait for correlated results.
The gateway event ledger reconciles completed inputs and Ark response IDs across
worker replacement. The worker always uses process-local ADK bookkeeping and ignores legacy database
environment variables; durable recovery comes from the event ledger and Ark response IDs.

A worker drains on SIGTERM, retains per-Session ordering, and bounds concurrent
Work using `MANAGED_AGENT_WORK_CONCURRENCY`. File tools confine paths to their
workspace. Bash requires OS isolation supplied by the worker deployment.
Cancellation/failure closes runners, MCP/native tool contexts and temporary Skills.
Runtime and Session credentials remain in process memory.

## Feishu channel

Configure the bot credentials privately and enable the desired optional streaming,
thinking, tool detail, card and topic settings from `.env.example`, then run:

```bash
bash examples/16_self_host_sandbox/run.sh --feishu
```

This starts a long-running channel, reconnects WebSocket transport, and drains
in-flight replies on shutdown. Channel settings are opt-in outside this demo.

## Tests and acceptance scripts

```bash
uv run --extra dev --extra sandbox pytest tests/runtime/managed_agents tests/integrations/mpa
python examples/16_self_host_sandbox/local_agent_loop_test.py
python examples/16_self_host_sandbox/anthropic_gateway_e2e.py --help
python examples/16_self_host_sandbox/soak_load_test.py --help
```

Unit tests use synthetic services. `anthropic_gateway_e2e.py` offers an official
SDK conversation check and sandbox lifecycle modes; conversation mode does not
require an AgentKit inspector. Optional cloud inspection requires explicit
`AGENTKIT_TOOL_DEPLOY_SCRIPT` and `AGENTKIT_TOOL_ID` inputs. No personal helper path
or deployment ID is supplied. Soak, fault, distributed-worker and Kubernetes
scripts are operator-triggered live checks; examine their required configuration
before running them. Keep local result files and full event logs private.

The distributed helper requires `ANTHROPIC_BASE_URL`, `ANTHROPIC_ENVIRONMENT_ID`,
`ANTHROPIC_ENVIRONMENT_KEY` and `SANDBOX_AGENT_ID` for existing isolated test
resources. Its Agent must enable Ark Session credentials and native bash. It
checks canonical Session history/continuation and archives only its own Session.
`ark_session_e2e.py` likewise requires explicit gateway and Agent configuration.

Image build, dependency pitfalls, readiness, writable mounts and the Kubernetes
worker template are covered in the [build guide](../../docker/managed-agents/README.md).
Building, local tests, publication, deployment and cloud E2E are separate outcomes.
The migration deliberately excludes the source's standalone Managed Agents UI.

Legacy imports `sandbox_client`, `managed_agent_loop`, `runtime_identity`,
`managed_session_resources` and `event_debug` remain example compatibility adapters.
Use packaged imports for new code. See the [runtime contract](../../specs/managed-agent-runtime/README.md)
and [migration design](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.md).
