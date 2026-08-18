# VeADK Repository Index

Use this map to locate exact APIs; do not treat the map itself as an API contract.

This navigation snapshot was reviewed against `github.com/volcengine/veadk-python` branch
`main`, commit `3be05c48a0360b86003f6f67808c943b5a33c4d3` (2026-08-15). It is not the
required project version: inspect the installed or pinned VeADK source before using an API.
The `veadk/evaluation/` entries are navigation references only; do not add Datasets,
Evaluators, Experiments, or LLM scoring unless the accepted intent requires them.

## Retrieval order

1. If the target project pins or installs VeADK, inspect that version first:

   ```bash
   python -c "import os, veadk; print(os.path.dirname(veadk.__file__))"
   ```

2. If a local clone exists and a branch is requested, use Git object reads such as
   `git show main:<path>` and `git grep <pattern> main -- <paths>`; do not trust a worktree on
   another branch.
3. Use matching tests and examples to confirm lifecycle and composition.
4. Use remote `main` only when the user explicitly targets `main` or no pinned version exists.

## Core

| Path | Key responsibility |
|---|---|
| `veadk/__init__.py` | lazy public exports: `Agent`, `Runner`, version |
| `veadk/agent.py` | `Agent`, model/tool/callback assembly, runtime and flow selection |
| `veadk/runner.py` | session/memory services, `run`, event execution, multimodal processing |
| `veadk/config.py`, `veadk/configs/` | environment and YAML-backed configuration |
| `veadk/types.py` | shared message and tool types |

Read `Agent.model_post_init`, `Agent._llm_flow`, `Agent._run_async_impl`, `Runner.__init__`, and
`Runner.run` before changing lifecycle behavior.

## Control flow and runtimes

| Path | Key responsibility |
|---|---|
| `veadk/agents/sequential_agent.py` | ordered workflow wrapper |
| `veadk/agents/parallel_agent.py` | parallel workflow wrapper |
| `veadk/agents/loop_agent.py` | bounded loop wrapper |
| `veadk/agents/supervise_agent.py`, `veadk/flows/` | supervisor Agent and flow extensions |
| `veadk/runtime/base_runtime.py` | alternate runtime Event contract |
| `veadk/runtime/piagent/` | PiAgent runtime implementation |
| `veadk/a2a/` | A2A server, remote Agent, registry, and hub integration |

At the reviewed commit, `Agent.runtime` accepts `adk`, `codex`, and `piagent`.

## Tools and Skills

| Path | Key responsibility |
|---|---|
| `veadk/tools/__init__.py` | `_BUILTIN_TOOLS`, `list_builtin_tools`, `get_builtin_tool` |
| `veadk/tools/builtin_tools/` | directly imported built-ins and system tools |
| `veadk/tools/mcp_tool/` | MCP and Trusted MCP integration |
| `veadk/tools/skills_tools/` | Skill discovery, registration, file, and shell tools |
| `veadk/skills/` | Skill model, registry, callbacks, and materialization |

Do not infer registry support from a module filename. Inspect `_BUILTIN_TOOLS` for names
accepted by `get_builtin_tool` in the target version.

## State and knowledge

| Path | Key responsibility |
|---|---|
| `veadk/memory/short_term_memory.py` | session-service factory and session reuse |
| `veadk/memory/short_term_memory_backends/` | SQLite, MySQL, and PostgreSQL paths |
| `veadk/memory/long_term_memory.py` | ADK MemoryService and backend dispatch |
| `veadk/memory/long_term_memory_backends/` | in-memory, VikingDB, OpenSearch, Redis, mem0, OpenViking, and TOS context implementations |
| `veadk/knowledgebase/knowledgebase.py` | KnowledgeBase facade and backend dispatch |
| `veadk/knowledgebase/backends/` | in-memory, VikingDB, OpenSearch, Redis, Milvus, TOS vector, context search, and OpenViking implementations |

Inspect constructor validation and optional dependency checks in the target version before
recommending a backend.

## Models, quality, and security

| Path | Key responsibility |
|---|---|
| `veadk/models/ark_llm.py` | Ark Responses API adapter, streaming, and fallback behavior |
| `veadk/models/ark_embedding.py` | Ark embedding adapter |
| `veadk/tracing/` | OpenTelemetry and exporters |
| `veadk/evaluation/` | ADK and DeepEval evaluation paths |
| `veadk/auth/` | credential services and service authentication |
| `veadk/processors/` | Runner event-generator interception |

## Serving and delivery

| Path | Key responsibility |
|---|---|
| `veadk/integrations/agentkit/app.py` | `create_agentkit_app`, `run_agentkit_app` |
| `veadk/cli/cli.py` | top-level `veadk` commands |
| `veadk/cli/cli_agentkit.py` | AgentKit CLI integration |
| `veadk/cli/cli_init.py`, `veadk/cli/cli_deploy.py` | project initialization and deployment commands |
| `veadk/cloud/` | VeFaaS/cloud application and deployment engine |
| `frontend/` | web UI and server surfaces |

Use `examples/generated_agentkit_project` as the reviewed AgentKit application reference, then
verify it against the installed target release and current `ak init` output.

## Examples and tests

| Path | Demonstrates |
|---|---|
| `examples/01_quickstart` | minimal Agent and Runner |
| `examples/02_custom_tools` | typed function tools |
| `examples/03_short_term_memory` | session persistence |
| `examples/05_knowledgebase_rag` | KnowledgeBase RAG |
| `examples/06_multi_agent` | deterministic workflow Agents |
| `examples/07_structured_output` | structured output |
| `examples/08_model_config` | model, provider, and fallback configuration |
| `examples/09_long_term_memory` | cross-session memory |
| `examples/10_agent_routing` | dynamic Agent routing |
| `examples/11_tracing` | tracing setup |
| `examples/12_mcp-tunnel` | MCP tunnel |
| `examples/13_openviking` | OpenViking integration |
| `examples/generated_agentkit_project` | current AgentKit application structure |
| `tests/agent`, `tests/runner`, `tests/memory`, `tests/integrations/agentkit` | selected core contracts |

When docs, examples, and implementation differ, report the mismatch and follow the target
version's tested implementation rather than silently combining versions.
