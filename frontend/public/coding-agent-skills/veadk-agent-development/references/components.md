# VeADK Components

This file is a component matrix, not a project layout convention. Use it to
choose the right VeADK entrypoint, understand external resource requirements,
and decide whether a capability is automatically attached or must be explicitly
exposed to an Agent.

Source of truth: the current Mintlify VeADK component tree under
`/productions/veadk/preview/zh/components/`. For exact signatures and installed
behavior, read `veadk-python-index.md` first, then inspect the installed
`veadk` package or the linked source.

## How To Use

1. Start from the component group that matches the user request.
2. Read the linked Mintlify page for exact examples and backend-specific setup.
3. Check whether the component is auto-mounted, passed to `Agent(...)`, passed
   to `Runner(...)`, registered in `Agent.tools`, or attached as callbacks.
4. Do not treat deployment, Runtime binding, or cloud networking as VeADK
   component setup. Those belong to AgentKit delivery workflows.

## Component Matrix

| Group | Component | When to use | VeADK entrypoint | Resource/config dependency | Exposure behavior | Minimum check | Mintlify page |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Agent | Model | Pin a model, provider, base URL, API key name, fallback models, or Responses API. | `Agent(model_name=..., model_provider=..., model_api_base=..., model_api_key=..., model_api_key_name=..., enable_responses=...)` | `MODEL_AGENT_API_KEY`, `MODEL_AGENT_API_KEY_NAME`, provider/base config, model support for Responses API. | Used by the Agent at construction and model call time. | Import Agent and instantiate with placeholder-safe config; verify one local Runner call when credentials exist. | `components/agent/model.md` |
| Agent | System prompt | Set the Agent's stable behavior contract. | `Agent(instruction=...)` | None unless prompt text is loaded from files or config. | Always part of the model request. | Instantiate Agent and confirm instruction is loaded from the intended source. | `components/agent/system-prompt.md` |
| Agent | Prompt management | Load prompts dynamically or from CozeLoop without code redeploy. | `CozeloopPromptManager`, custom `BasePromptManager`, `Agent(prompt_manager=...)` | `COZELOOP_WORKSPACE_ID`, `COZELOOP_TOKEN`, prompt key, label, or custom backend config. | Prompt manager is called before handling user requests; CozeLoop has local cache and fallback behavior. | Instantiate manager with non-secret placeholders or env; verify `get_prompt` with safe inputs. | `components/agent/prompt-management.md` |
| Agent | Runtime backend | Select ADK or alternate runtime execution behavior. | `Agent(runtime=...)` | Runtime-specific dependencies, for example optional packages for non-default runtimes. | Internal Agent execution behavior. | Import and instantiate the Agent with the requested runtime. | `components/agent/runtime.md` |
| Agent | Structured output | Require typed/structured model responses. | `Agent(output_schema=...)` or current installed API. | Schema model and model compatibility. | Model response is constrained by schema; may affect Responses API cache behavior. | Run a minimal prompt and validate the returned structure. | `components/agent/structured-output.md` |
| Agent | Skills | Load reusable skill packages or cloud skill spaces. | ADK `SkillToolset`, `load_skill_from_dir`, `VeSkillRegistry`, or legacy `Agent(skills=..., skills_mode=...)` for sandbox modes. | Local skill directory, cloud skill source ID, Volcengine credentials for cloud skill spaces, optional code executor for scripts. | Local/cloud skills become toolsets; `skills_sandbox` uses `execute_skills`. | Load/list skill metadata; for sandbox mode verify tool ID and skill space before Runner use. | `components/agent/skills.md` |
| Execution | Runner | Execute an Agent and coordinate model, tools, callbacks, sessions, memory, and events. | `Runner(agent=..., app_name=..., user_id=..., short_term_memory=...)`, `run`, `run_async` | Optional short-term memory/session service. | Drives the request lifecycle; `run` returns final text, `run_async` streams Events. | Run a local smoke prompt; for `run_async`, ensure the session exists first. | `components/execution-engine/index.md` |
| Execution | Event stream | Inspect tool calls, tool responses, token usage, streaming deltas, and final responses. | `Runner.run_async(...)` Event objects: `get_function_calls`, `get_function_responses`, `is_final_response`. | Existing session for direct `run_async`. | Application code consumes event stream; not an Agent tool. | Iterate events for one safe prompt and verify final response detection. | `components/execution-engine/index.md` |
| Session | Short-term memory | Preserve conversation context within a session. | `ShortTermMemory(backend=..., db_url=..., local_database_path=...)`, passed to `Runner(short_term_memory=...)`. | Backends: `local`, `sqlite`, `mysql`, `postgresql`; DB env/config for remote DBs. | Runner uses the session service; if omitted, Runner creates a local in-memory fallback. | Create/get/list or reuse a session with explicit `app_name`, `user_id`, `session_id`. | `components/session/index.md` |
| Session | Context compaction | Compress long session history with a sliding window. | ADK `App(..., events_compaction_config=...)`, `EventsCompactionConfig`, optional `LlmEventSummarizer`. | Optional summarizer model credentials. | App/session behavior, not an Agent tool. | Configure interval and run enough turns to trigger compaction in a local smoke. | `components/session/index.md` |
| Memory | Long-term memory | Persist facts across sessions for a user/application. | `LongTermMemory(backend=..., app_name=..., index=...)`, passed to `Agent(long_term_memory=...)`; optional `auto_save_session=True`. | Backends: `local`, `viking`, `mem0`, `opensearch`, `redis`, `openviking`; embedding or service credentials depending on backend. | Passing `long_term_memory` to Agent automatically gives the Agent the `load_memory` system tool. | Save a completed session or call `search_memory` with the same `app_name` and `user_id`. | `components/memory/index.md` |
| Knowledge | KnowledgeBase | Add static product docs, FAQ, articles, or other RAG sources. | `KnowledgeBase(backend=..., app_name=..., index=..., top_k=...)`, passed to `Agent(knowledgebase=...)`. | Backends: `local`, `opensearch`, `redis`, `milvus`, `tos_vector`, `viking`, `context_search`, `openviking`; embedding or service credentials depending on backend. | Passing `knowledgebase` to Agent automatically gives the Agent the `load_knowledgebase` system tool. | Add text/files or verify the existing index, then call `search(query=..., top_k=...)`. | `components/knowledge/index.md` |
| Tools | Custom function tool | Expose local deterministic Python behavior to the Agent. | Plain Python function with type hints/docstring in `Agent(tools=[...])`. | Tool-specific dependencies and credentials only if the function calls external systems. | Explicitly exposed through `Agent.tools`. | Import function and call it directly with safe inputs before adding to Agent tools. | `components/tools/custom-function.md` |
| Tools | Built-in ordinary tools | Use VeADK-provided web, media, mobile, search, or service tools. | Imports under `veadk.tools.builtin_tools.*`, or current helper APIs. | Tool-specific API keys, Volcengine services, network access, or device/service availability. | Explicitly exposed through `Agent.tools`. | Import lazily and run the smallest safe tool/config check. | `components/tools/index.md` and specific tool pages |
| Tools | System tools | Let VeADK add retrieval tools for knowledge and memory. | `Agent(knowledgebase=...)`, `Agent(long_term_memory=...)`. | Configured KnowledgeBase or LongTermMemory. | Auto-mounted as `load_knowledgebase` or `load_memory`; do not also add them manually by default. | Verify the underlying KnowledgeBase/memory search before relying on Agent behavior. | `components/tools/load-knowledgebase.md`, `components/tools/load-memory.md` |
| Tools | Code sandbox | Run code or sandbox workflows in AgentKit sandbox tools. | `run_code`, `execute_skills`, `coding`, `run_sandbox_agent` from `veadk.tools.builtin_tools.*`. | `MODEL_AGENT_API_KEY`, Volcengine AK/SK, `AGENTKIT_TOOL_ID`, `AGENTKIT_TOOL_ID_SCRIPT`, `AGENTKIT_TOOL_ID_SKILLS`, `AGENTKIT_TOOL_ID_OPENCODE`, optional Tool host/service code. | Explicitly exposed through `Agent.tools`; sandbox execution is remote. | Check required tool ID and credentials; run a bounded read-only sandbox command or safe Runner prompt. | `components/tools/code-sandbox.md` |
| Tools | Custom MCP client | Connect the Agent to an arbitrary MCP Server. | ADK `MCPToolset` with `StreamableHTTPConnectionParams`, added to `Agent.tools`. | MCP endpoint, headers/API key, network reachability. | Explicitly exposed through `Agent.tools`; remote MCP tools are discovered at runtime. | List tools or run a safe read-only MCP call; verify reconnect behavior only when needed. | `components/tools/custom-mcp.md` |
| Tools | MCP Router | Connect to Volcengine MCP Router for multiple MCP services. | `from veadk.tools.builtin_tools.mcp_router import mcp_router`; `Agent(tools=[mcp_router])`. | `TOOL_MCP_ROUTER_URL`, `TOOL_MCP_ROUTER_API_KEY`, or `config.yaml` `tool.mcp_router`. | Explicitly exposed through `Agent.tools`. | Import only after config exists; run a list-tools/readiness smoke before business use. | `components/tools/mcp-router.md` |
| Tools | Trusted MCP tools | Use MCP tools with additional trust/security requirements. | Current trusted MCP tool docs and installed package. | Trusted MCP service, identity, and security config. | Explicitly exposed after trust checks. | Verify trust metadata and a safe tool call before use. | `components/tools/trusted-mcp.md`, `components/security/trusted-mcp.md` |
| Security | Inbound auth | Verify callers entering an Agent service. | Security/app middleware or gateway integration; map validated identity into Runner `user_id` and `session_id`. | API Key, OAuth2, SSO/JWT, Agent Identity, gateway or app config. | Protects request entrypoints; not an Agent tool. | Verify auth metadata and identity-to-session mapping with a safe request. | `components/security/inbound.md` |
| Security | Outbound auth | Let tools call third-party services without hardcoded secrets. | Agent Identity credential hosting and tool/service integration. | Hosted API keys, OAuth tokens, workload identity, user delegation. | Used by outbound tools/services; not exposed as a tool itself. | Verify credential reference resolution without printing secret values. | `components/security/outbound.md` |
| Security | Content safety guardrail | Audit and block unsafe model/tool input and output. | `content_safety` callbacks from `veadk.tools.builtin_tools.llm_shield`; attach before/after model/tool callbacks to `Agent(...)`. | `TOOL_LLM_SHIELD_APP_ID` or `config.yaml` `tool.llm_shield.app_id`; LLM firewall asset. | Callback attachment, not a normal tool. | Attach callbacks and run a safe positive case plus one expected blocked test if policy allows. | `components/security/content-safety.md` |
| Observability | Tracing | Record Agent, model, tool, memory, and knowledge spans. | `OpentelemetryTracer`, exporters, `Agent(tracers=[...])`; env auto-enable for exporters. | `ENABLE_APMPLUS`, `ENABLE_COZELOOP`, `ENABLE_TLS`, exporter-specific credentials/config; `OBSERVABILITY_OPENTELEMETRY_TRACE_CONTENT`. | Tracer attachment, not a tool. | Run one request and dump or inspect spans; disable content tracing for sensitive data when needed. | `components/observability/index.md` |
| Observability | Logging | Use Python logging for application logs and trace correlation. | Standard logging config plus VeADK logging docs. | Logging env/config and destination-specific setup. | Runtime/application behavior. | Run a local request and confirm log level/format. | `components/observability/logging.md` |
| Extension | Feishu channel | Bridge Feishu bot messages into Runner. | Feishu Channel extension. | Feishu app credentials, event/callback config. | Inbound channel integration, not an Agent tool by itself. | Verify HTTP invoke still works, then verify channel callback separately. | `components/extensions/feishu-channel.md` |
| Frontend | VeADK Web / A2UI / Studio | Inspect or operate agents through development or UI surfaces. | VeADK Web, A2UI, Studio docs. | UI/runtime-specific setup. | User interface layer. | Start the UI target and run a simple prompt. | `components/frontend/index.md` |

## Composition Surfaces To Keep Shallow

These are useful VeADK-adjacent surfaces, but they should not dominate this
component matrix. Expand them in delivery or AgentKit CLI guidance when the task
is about deployment, protocols, or cloud resources.

| Surface | VeADK-side note | Do not expand here |
| --- | --- | --- |
| App wrapper | A VeADK Agent can be wrapped by AgentKit application classes for HTTP or protocol serving. | Full AgentKit app lifecycle, routes, release, auth, and runtime config. |
| Harness | VeADK has harness-related runtime/config paths and skill loading behavior. | CLI-generated Harness specs, deployment registry, cloud invoke, and release flow. |
| MCP service exposure | Current component tree covers consuming MCP servers through tools; exposing an Agent as an MCP service is a delivery surface. | Gateway/MCP service creation, endpoint auth, and external client contracts. |
| A2A exposure | VeADK has A2A-related modules and frontend docs, but service exposure is protocol delivery. | AgentCard publication, hub registration, cloud endpoint auth, and runtime release. |
| Multi-agent topology | VeADK source/examples include sub-agents, routing, flows, and A2A modules. | Project-specific orchestration architecture unless the user asks for multi-agent design. |

## Exposure Rules

- Do not add remote, paid, write-capable, sandbox, MCP, or media-generation tools
  to `Agent.tools` just because they import successfully.
- Auto-mounted system tools are special: `KnowledgeBase` adds
  `load_knowledgebase`, and `LongTermMemory` adds `load_memory`.
- Short-term memory is session infrastructure for `Runner`, not a normal Agent
  tool.
- Content safety is attached through callbacks; tracing is attached through
  `Agent.tracers` or exporter env vars.
- Secrets must come from environment variables, `config.yaml`, hosted
  credentials, or runtime injection. Never hardcode real keys in examples.

## Retrieval Rules

- For current page names, fetch the Mintlify index at
  `https://agentkit-f14c9eb5.mintlify.site/llms.txt`.
- For exact symbols, read `veadk-python-index.md`, then inspect the installed
  package that the user's project actually runs.
- Treat CLI and cloud Runtime behavior as delivery concerns unless the user is
  explicitly packaging or deploying an Agent.
