# VeADK (veadk-python) Repository Index

A retrieval map of **github.com/volcengine/veadk-python** so you can jump straight to
the source for any API. Don't guess signatures — locate the file here, then read it.

## How to retrieve

- **Browse a dir:** `https://github.com/volcengine/veadk-python/tree/main/<path>`
- **Read a file (raw):** `https://raw.githubusercontent.com/volcengine/veadk-python/main/<path>`
  — use WebFetch on the raw URL.
- **If a local clone exists:** `grep -rn "<symbol>" <clone>/veadk` / read the file directly.
- **Find the installed copy:** `python -c "import veadk, os; print(os.path.dirname(veadk.__file__))"`
  then grep/read under that directory (fastest, matches your installed version).

Prefer reading `examples/` for idiomatic, copy-pasteable usage; read `veadk/<module>` for
exact parameters and behavior.

## Core (read these first)

| Path | What's there | Key symbols |
|---|---|---|
| `veadk/__init__.py` | Public exports | `Agent`, `Runner`, `VERSION` |
| `veadk/agent.py` | The Agent class + all its fields | `Agent(name, description, instruction, model_name, model_provider, model_api_base, tools, runtime, knowledgebase, short_term_memory, long_term_memory, skills, sub_agents)` |
| `veadk/runner.py` | Drives an agent | `Runner(agent, short_term_memory?, app_name)`, `run(messages, user_id, session_id)` (async), `run_async` |
| `veadk/agent_builder.py` | Programmatic agent construction | agent factory helpers |
| `veadk/config.py`, `consts.py` | Settings + defaults (default model, instruction) | `settings.model.*`, `DEFAULT_MODEL_AGENT_NAME`, `DEFAULT_INSTRUCTION` |
| `veadk/types.py` | Shared types | `ToolUnion`, message types |

## Tools

| Path | What's there |
|---|---|
| `veadk/tools/__init__.py` | `get_builtin_tool(name)`, `list_builtin_tools()`, `ToolUnion` |
| `veadk/tools/builtin_tools/` | One file per built-in: `web_search.py`, `web_fetch.py`, `run_code.py`, `coding.py`, `parallel_web_search.py`, `vesearch.py`, `link_reader.py`, `image_generate.py`, `image_edit.py`, `tts.py`, `video_generate.py`, `playwright.py`, `web_scraper.py`, `mobile_run.py`, `load_knowledgebase.py`, `lark.py`, `supabase_toolset.py`, … |
| `veadk/tools/mcp_tool/` | MCP tool integration |
| `veadk/tools/sandbox/` | Sandbox execution tools |
| `veadk/tools/skills_tools/` | Skill-hub tools (`execute_skills`) |

## Memory & Knowledge

| Path | What's there |
|---|---|
| `veadk/memory/short_term_memory.py` | `ShortTermMemory(backend=...)` — session store |
| `veadk/memory/short_term_memory_backends/` | `sqlite_backend.py`, `mysql_backend.py`, `postgresql_backend.py` (+ local/in-memory) |
| `veadk/memory/long_term_memory.py` | `LongTermMemory(backend=..., app_name=...)` — cross-session |
| `veadk/memory/long_term_memory_backends/` | `vikingdb_memory_backend.py`, `opensearch_backend.py`, `redis_backend.py`, `mem0_backend.py`, `in_memory_backend.py` |
| `veadk/knowledgebase/__init__.py` | `KnowledgeBase(backend=..., app_name=...)` |
| `veadk/knowledgebase/backends/` | `vikingdb_knowledge_backend.py`, `opensearch_backend.py`, `redis_backend.py`, `tos_vector_backend.py`, `context_search_backend.py`, `in_memory_backend.py` |
| `veadk/configs/` | Backend connection config (env var names, e.g. `DATABASE_<BACKEND>_*`) — read `database_configs.py` for exact env keys |

## Models

| Path | What's there |
|---|---|
| `veadk/models/` | Model providers, base URLs, catalog; how `model_name` / `model_provider` resolve |
| `veadk/auth/veauth/` | Ark token resolution (env `MODEL_AGENT_API_KEY` or VeFaaS IAM file on the runtime) |

## Serving & Deployment

| Path | What's there |
|---|---|
| `veadk/cloud/harness_app/` | The reference config-driven harness server (env → agent). NOTE: this is `veadk.cloud`; agentkit-cli ships its **own decoupled** copy |
| `veadk/cli/` | The `veadk` CLI (incl. `harness` commands, templates under `cli/templates/`) |
| `veadk/runtime/`, `veadk/runtime/codex/` | Agent runtime backends (`runtime="adk"` default, `"codex"`) |
| (external pkg) `agentkit.apps` | `AgentkitSimpleApp`, `AgentkitAgentServerApp` (ADK API server); serve on `0.0.0.0:8000` |

## Evaluation, Tracing, Advanced

| Path | What's there |
|---|---|
| `veadk/evaluation/` | Eval framework: `adk_evaluator/`, `deepeval_evaluator/` |
| `veadk/tracing/`, `veadk/tracing/telemetry/` | Observability (Cloud Trace / TLS / CozeLoop) |
| `veadk/a2a/`, `veadk/a2ui/` | Agent-to-agent + A2A UI |
| `veadk/agents/`, `veadk/flows/`, `veadk/processors/` | Multi-agent, flows, run processors |
| `veadk/skills/`, `veadk/tools/skills_tools/` | Skill hub loading |
| `veadk/tunnel/` | Local MCP tunneling into a cloud app |
| `veadk/integrations/ve_*` | Volcengine service SDK wrappers: `ve_apig`, `ve_code_pipeline`, `ve_cr`, `ve_faas`, `ve_identity`, `ve_tos`, `ve_tls`, `ve_viking_db_memory`, `ve_cozeloop`, `ve_prompt_pilot` |
| `veadk/prompts/` | Default prompts / instructions |

## Runnable examples (best for vibe coding — copy these)

Path: `examples/<name>/main.py`

| Example | Shows |
|---|---|
| `01_quickstart` | Minimal Agent + Runner |
| `02_custom_tools` | Your own function tools |
| `03_short_term_memory` | Session memory |
| `04_web_search` | Built-in `web_search` tool |
| `05_knowledgebase_rag` | RAG with a KnowledgeBase (+ `docs/`) |
| `06_multi_agent` | Multi-agent / sub-agents |
| `07_structured_output` | Structured/typed output |
| `08_model_config` | Overriding model / provider |
| `09_long_term_memory` | Cross-session memory |
| `10_agent_routing` | Routing between agents |
| `11_tracing` | Observability wiring |
| `12_mcp-tunnel` | MCP tools via tunnel (`app.py`, `connector.py`, `local_mcp_server.py`) |
| `14_harness_server_on_agentkit` | Config-driven harness deploy |
| `basic-app` | A full servable app (`app.py` + `agents/`) |

## Retrieval recipes

- **"What params does X take?"** → read `veadk/<module>.py` (e.g. Agent → `veadk/agent.py`).
- **"How does built-in tool `foo` work / what args?"** → `veadk/tools/builtin_tools/foo.py`.
- **"What env vars does the `viking` memory backend read?"** → `veadk/configs/database_configs.py` and `veadk/memory/long_term_memory_backends/vikingdb_memory_backend.py`.
- **"Show me a working example of RAG"** → `examples/05_knowledgebase_rag/main.py`.
- **"How is the harness server assembled from env?"** → `veadk/cloud/harness_app/` (agent.py / utils.py).
- **"Which models/providers are supported?"** → `veadk/models/` + `examples/08_model_config/main.py`.
