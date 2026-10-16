# Runtime DeepSeek Harness Component

[中文版](README.zh.md)

## Metadata and Scope

- **Component ID:** `runtime-deepseek-harness`
- **Status:** active
- **Revision date:** 2026-10-15
- **Owned code:** `veadk/runtime/deepseek_harness/`, `veadk/runtime/__init__.py`, `veadk/agent.py` runtime fields, runtime support matrix entries.
- **Primary tests:** `tests/runtime/deepseek_harness/`
- **Related PRD:** [DSH Runtime](../../prd-spec/features/deepseek-harness-runtime/2026-10-15-deepseek-harness-runtime.md)
- **Dependent components:** Agent execution, runtime compatibility, optional dependency metadata, user runtime documentation.

## Responsibility and Non-goals

This component owns the Python SDK bridge between `Agent(runtime="dsh")` and the local DeepSeek Harness SDK runtime. It resolves runtime configuration, manages the long-lived SDK object and explicit `DSH_HOME`, maps VeADK session identity to DSH session identity, bridges ADK/MCP tools through DSH native tool plugins, bridges skills through DSH's native filesystem skill provider, and emits ADK-compatible partial, tool, and final response events.

It does not own DSH profile behavior, provider authentication semantics inside DSH, the bundled binary build pipeline, Studio's separate DeepSeek Harness sandbox flow, ADK skill checklist enforcement inside DSH's native skill loader, or descendant-session UI projection.

## Entry Points and Dependencies

- Public runtime value: `Agent(runtime="dsh")`.
- Public config import: `from veadk.runtime.deepseek_harness import DeepSeekHarnessRuntimeConfig`.
- Optional dependency: `veadk-python[dsh]`, which installs `deepseek-harness-sdk==0.1.5rc1` and the matching transitive `deepseek-harness-runtime-bin`.
- External SDK import: `deepseek_harness`.
- Runtime dispatch: `veadk.runtime.get_runtime("dsh")`.

## Contract

- **CON-1 — Runtime value.** `dsh` is the stable public runtime identifier. Unknown spellings are rejected by `Agent` or `get_runtime`.
- **CON-2 — Optional dependency.** Importing VeADK without the DSH extra succeeds. Resolving the DSH runtime without the SDK raises `ImportError` with `pip install "veadk-python[dsh]"`.
- **CON-3 — Config source.** `deepseek_harness_runtime_config` accepts a `DeepSeekHarnessRuntimeConfig` instance or dict. Environment variables with the `VEADK_DEEPSEEK_HARNESS_*` prefix override matching fields.
- **CON-4 — Model resolution.** If config `model` is unset, the runtime uses the first `Agent.model_name` entry. ADK before-model callbacks may mutate `llm_request.model`; the mutated model is used when selecting the DSH manager and SDK config.
- **CON-4a — Provider aliases.** Config `provider` is the user-facing provider name and defaults to `deepseek-official`; blank values normalize to that default. The aliases `openai`, `volcengine`, `volcengine-ark`, `ark`, `openai-compatible`, and `third-party` are mapped to the current DSH `deepseek-official` adapter before SDK construction. Unknown provider names are passed through unchanged for future DSH-native adapters.
- **CON-5 — Lazy sidecar.** No DSH subprocess starts during module import, runtime lookup, or agent construction. The SDK object starts from the first actual turn.
- **CON-6 — Explicit home.** When `dsh_home` is unset, the runtime creates and passes a non-empty generated DSH home. It never relies on implicit `~/.dsh`.
- **CON-7 — Session mapping and short-term context.** DSH `session_id` is stable for the tuple `(app_name, user_id, session_id, agent name)`. The prompt also serializes the visible ADK session history into a structured `<conversation_history>` block, keeping VeADK/ADK session state as the short-term memory source of truth rather than relying only on DSH's internal session state.
- **CON-8 — Tool bridge.** ADK function tools and ADK/MCP toolsets are expanded before the DSH run, registered as DSH native tools through a generated `defineTool` plugin patch, executed in Python through an authenticated loopback bridge, and emitted as ADK tool call/response events.
- **CON-9 — Sub-agent transfer.** Transfer-capable `sub_agents` are exposed through the injected `transfer_to_agent` tool. A transfer response runs the target agent and suppresses the DSH final text for that turn.
- **CON-10 — Skill bridge.** ADK `SkillToolset` and legacy VeADK skills are materialized into an isolated skill root. The runtime registers `@deepseek-ai/dsh-skill`, `@deepseek-ai/dsh-skill-filesystem` with `includeDefaultRoots=false`, and `@deepseek-ai/dsh-tool-skill` through a DSH patch. The materialized skill content digest participates in the manager key.
- **CON-11 — Event mapping.** Root-session DSH assistant stream chunks are emitted as ADK partial model events. DSH native `tool/call` and `tool/result` events are emitted as ADK function call/response events, excluding VeADK-bridged Python tool names to avoid duplicates.
- **CON-12 — Event output.** Each completed non-transfer DSH run emits one ADK model event containing `RunResult.final_response` after ADK after-model callbacks. Empty DSH final responses are represented as an empty final model response.
- **CON-13 — Unsupported surfaces.** ADK flow-only features remain covered by `veadk.runtime.compat`. ADK skill checklist enforcement and full descendant-session projection are not part of this component's active contract.

## State and Concurrency

Effective runtime configurations are keyed after resolving model, provider, DSH profile, homes, paths, timeouts, explicit environment overrides, the bridged DSH tool schema digest, and the materialized skill content digest. Each key owns one `DeepSeekHarness` instance, one generated `dsh_home` when applicable, one long-lived tool bridge/plugin patch when tools are present, and one native DSH skill patch/root when skills are present. Managers are closed at process exit.

Turns sharing a manager are serialized with an async lock. This avoids undocumented concurrent access to one SDK stdio client. Multiple different manager keys may run independently.

Cancellation from the surrounding task cannot reliably cancel one in-flight DSH `run()` call through the current synchronous SDK. The component closes the manager on cancellation where possible and does not claim graceful per-turn cancellation.

Tool bridge calls are accepted only while the manager lock owns an active turn. The bridge rejects calls without the per-manager bearer token or without an active ADK tool bundle.

## Data and Configuration

Configuration fields:

- `provider`, `model`, `reasoning_effort`, `max_tokens`
- `cwd`, `runtime_cwd`, `dsh_bin`, `profile`, `patches`, `dsh_home`
- `env`, `initialize_timeout_seconds`, `request_timeout_seconds`, `shutdown_timeout_seconds`
- `base_url`, `api_key`

Environment overrides:

- `VEADK_DEEPSEEK_HARNESS_PROVIDER`
- `VEADK_DEEPSEEK_HARNESS_MODEL`
- `VEADK_DEEPSEEK_HARNESS_REASONING_EFFORT`
- `VEADK_DEEPSEEK_HARNESS_MAX_TOKENS`
- `VEADK_DEEPSEEK_HARNESS_CWD`
- `VEADK_DEEPSEEK_HARNESS_RUNTIME_CWD`
- `VEADK_DEEPSEEK_HARNESS_DSH_BIN`
- `VEADK_DEEPSEEK_HARNESS_PROFILE`
- `VEADK_DEEPSEEK_HARNESS_DSH_HOME`
- `VEADK_DEEPSEEK_HARNESS_INITIALIZE_TIMEOUT_SECONDS`
- `VEADK_DEEPSEEK_HARNESS_REQUEST_TIMEOUT_SECONDS`
- `VEADK_DEEPSEEK_HARNESS_SHUTDOWN_TIMEOUT_SECONDS`
- `VEADK_DEEPSEEK_HARNESS_BASE_URL`
- `VEADK_DEEPSEEK_HARNESS_API_KEY`

The default `profile` is `sdk-minimal`, so VeADK can inject the exact DSH tool and skill plugins it owns. Callers may opt into DSH's fuller `sdk` profile; in that mode VeADK patches the existing skill filesystem plugin configuration rather than inserting a duplicate plugin set.

## Security and Isolation

Generated `DSH_HOME` paths are process-owned temporary directories. Configured `dsh_home`, `cwd`, and `runtime_cwd` are expanded and resolved before use. The runtime passes `api_key` and `base_url` only through SDK config; redaction of DSH internals belongs to DSH.

User prompts and session IDs are untrusted input. Session IDs are hashed rather than embedded raw into DSH identifiers.

## Compatibility and Evolution

The component is additive. Existing runtime values and configs remain unchanged. Future versions may add checklist enforcement, descendant-session projection, and finer cancellation only after the PRD/spec contract is updated and covered by tests.

## Observability and Failures

The runtime logs selected model/provider and session identity at a non-secret level. SDK import errors, initialization errors, and run errors propagate unless an ADK on-model-error callback returns a fallback `LlmResponse`.

## Verification

| Contract | Guarantee | Test or validation | Evidence |
| --- | --- | --- | --- |
| `CON-1` to `CON-4a` | Runtime dispatch and config resolution. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD verification record |
| `CON-5` to `CON-7` | Lazy manager, explicit home, stable session IDs. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD verification record |
| `CON-8` | ADK tools bridge through a generated DSH plugin and loopback callback. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD verification record |
| `CON-9` | Sub-agent transfer uses the injected transfer tool path. | Source review plus bridge-path tests | PRD verification record |
| `CON-10` | Skills bridge through DSH native skill plugins and an isolated materialized root. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD verification record |
| `CON-11` | DSH partial and native tool events become ADK events. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD verification record |
| `CON-12` | Final response becomes an ADK event after callbacks. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD verification record |
| `CON-13` | Unsupported surfaces are documented and gated. | Source/doc review plus runtime compatibility tests | PRD verification record |

## Change Record

- 2026-10-15: Initial active contract for `runtime="dsh"` introduced by `deepseek-harness-runtime`.
- 2026-10-15: Added VeADK provider aliases for omitted, OpenAI, Volcengine, and third-party OpenAI-compatible endpoints, mapped to the current DSH adapter.
