# DSH Runtime

[中文版](2026-10-15-deepseek-harness-runtime.zh.md)

## Metadata

- **Change ID:** `deepseek-harness-runtime`
- **Created / revised:** 2026-10-15 / 2026-10-15
- **Lifecycle status:** implemented
- **Related component spec:** [Runtime DeepSeek Harness](../../../specs/runtime-deepseek-harness/README.md)
- **Owner areas:** `veadk.agent`, `veadk.runtime`, optional dependencies, runtime documentation, runtime tests.

## Background and Evidence

VeADK currently exposes three `Agent.runtime` values: `adk`, `codex`, and `piagent`. `codex` is installed through the `codex` extra: the Python SDK package pins a matching binary wheel. `piagent` resolves or downloads its binary on first runtime use.

DeepSeek Harness already ships a Python SDK package named `deepseek-harness-sdk==0.1.5rc1`. Its import package is `deepseek_harness`; the SDK depends on `deepseek-harness-runtime-bin==0.1.5rc1`, which contains the bundled `dsh` executable for supported platforms. The SDK requires an explicit `dsh_home` or non-empty `DSH_HOME`; it never falls back to `~/.dsh`. `DeepSeekHarness` starts its subprocess lazily and reuses it across `run()` calls.

Live SDK inspection on 2026-10-15 showed that the packaged DSH profile can start with the native provider name `deepseek-official`, while `volcengine`, `ark`, `volcengine-ark`, `openai`, `openai-compatible`, `third-party`, `doubao`, and `deepseek` are not registered DSH adapter names in the current wheel. VeADK therefore owns user-facing provider aliases for Volcengine and third-party OpenAI-compatible endpoints and maps them to the DSH adapter that currently accepts explicit `base_url` and `api_key`.

Assumptions that remain intentionally bounded:

- DSH native tool plugins are registered through the documented Cordis `ctx.tools.register(defineTool(...))` extension path.
- DSH skills are registered through the documented native `@deepseek-ai/dsh-skill`, `@deepseek-ai/dsh-skill-filesystem`, and `@deepseek-ai/dsh-tool-skill` plugins.
- DSH notifications are mapped for root-session assistant stream chunks and native tool call/result events; descendant session notifications are retained for future expansion but do not replace the root final response.

## Goals

- Add `runtime="dsh"` as a public Python SDK runtime value.
- Install DSH through a VeADK optional extra that depends on the Python SDK and its transitive runtime binary package.
- Start DSH lazily on first turn, not at import or `Agent(...)` construction time.
- Reuse a long-lived DSH SDK object per effective runtime configuration, with stable DSH session IDs derived from VeADK app/user/session/agent identity.
- Bridge ADK function tools and ADK/MCP toolsets into DSH as native tools through a generated DSH plugin and a local authenticated Python callback server.
- Bridge ADK sub-agent transfer through the same injected `transfer_to_agent` tool used by other external runtimes.
- Bridge ADK `SkillToolset` and legacy VeADK skills through DSH's native filesystem skill provider and `skill` loader tool.
- Stream DSH assistant deltas and native tool call/result events back as ADK events while preserving after-model callback semantics for the final response.
- Keep VeADK/ADK session history as the short-term memory source of truth by serializing visible session history into DSH prompts, matching the Codex runtime contract.
- Honor model changes made by before-model callbacks when selecting the DSH SDK config and cached manager.
- Use an explicit isolated `DSH_HOME` by default, with a configuration override for persistent deployments.
- Support omitted provider values and user-facing `openai`, `volcengine`, `volcengine-ark`, `ark`, `openai-compatible`, and `third-party` provider aliases without requiring callers to know the current DSH adapter name.
- Provide clear errors when the optional extra is missing.
- Document the lifecycle differences from Codex and PiAgent.

## Non-goals

- Do not build a custom VeADK first-run downloader for the `dsh` binary.
- Do not claim ADK `enable_skills_checklist` enforcement inside DSH's native skill loader.
- Do not implement a complete UI projection for descendant DSH subagent session notifications in this change.
- Do not add frontend Studio DeepSeek Harness behavior; Studio already has a separate DeepSeek Harness sandbox path.
- Do not run live provider calls as part of ordinary unit tests.

## Scenarios and Requirements

- **FR-1 — Runtime selection.** Given an agent constructed with `runtime="dsh"`, when it runs, VeADK dispatches to the DSH runtime instead of the ADK LLM flow.
- **FR-2 — Optional dependency boundary.** Given a default VeADK installation without DSH, when code resolves the runtime, the error names the missing extra and installation command.
- **FR-3 — Binary acquisition.** Given `veadk-python[dsh]` is installed, the matching `dsh` binary is acquired through `deepseek-harness-runtime-bin`; VeADK performs no runtime download.
- **FR-4 — Lazy startup.** Given a process imports VeADK or constructs an agent, DSH is not started until a turn reaches `DeepSeekHarnessRuntime.run_async`.
- **FR-5 — Session identity.** Given repeated turns for the same `app_name`, `user_id`, `session_id`, and agent name, VeADK passes the same DSH `session_id`.
- **FR-6 — Isolated home.** Given no `dsh_home` is configured, VeADK creates an explicit process-owned `DSH_HOME` under a temporary root and passes it to the SDK.
- **FR-7 — Callback compatibility.** Given model callbacks are configured, before/after/error model callbacks fire at the same coarse per-turn boundary used by other external runtimes.
- **FR-8 — Tool bridge.** Given ADK function tools or ADK/MCP toolsets are configured, VeADK exposes them as DSH native tools through `defineTool`, executes them in Python, and emits the corresponding ADK tool events.
- **FR-9 — Sub-agent transfer.** Given transfer-capable `sub_agents` are configured, VeADK exposes `transfer_to_agent`; when DSH calls it, VeADK runs the target agent and suppresses the DSH final text for that turn.
- **FR-10 — Skill bridge.** Given ADK `SkillToolset` or legacy VeADK skills are configured, VeADK materializes them to an isolated skill root, registers DSH's native skill plugins with `includeDefaultRoots=false`, and includes the skill content digest in the manager key.
- **FR-11 — Event mapping.** Given DSH emits root-session assistant stream chunks or native tool call/result events, VeADK maps them to ADK partial model events and function call/response events without duplicating VeADK-bridged Python tool events.
- **FR-12 — Codex-aligned short-term context and model callbacks.** Given ADK session history exists, DSH receives it as structured conversation data in the prompt. Given a before-model callback mutates `llm_request.model`, DSH uses the mutated model for manager selection and SDK config.
- **FR-13 — Honest limitations.** Given unsupported ADK flow features, VeADK warns or errors through the existing runtime support matrix and documentation rather than silently claiming equivalence.
- **FR-14 — Provider aliases.** Given config `provider` is omitted, blank, `openai`, `volcengine`, `volcengine-ark`, `ark`, `openai-compatible`, or `third-party`, VeADK resolves a valid user-facing configuration and passes DSH the currently registered OpenAI-compatible adapter provider.

## Design and Contract Impact

The selected design matches Codex's dependency-acquisition model: add a `dsh` optional extra that pins `deepseek-harness-sdk==0.1.5rc1`, letting that package bring the matching runtime binary wheel. This is preferred over the PiAgent-style first-run downloader because DSH already publishes an SDK/runtime-bin pair, so VeADK should not duplicate platform selection, cache management, and version coupling logic.

The runtime package is `veadk.runtime.deepseek_harness`. Its public config class is `DeepSeekHarnessRuntimeConfig`. `Agent` gains `deepseek_harness_runtime_config`, accepting either that config or a dict.

Effective DSH configuration resolves as:

1. Agent `deepseek_harness_runtime_config`.
2. Narrow environment overrides with the `VEADK_DEEPSEEK_HARNESS_*` prefix.
3. Agent model fields for model name, API base, and API key when no DSH-specific override is set.
4. Conservative defaults (`provider="deepseek-official"`, `profile="sdk-minimal"`). `sdk-minimal` lets VeADK inject the DSH tool and skill plugins it owns, while a caller may still opt into DSH's fuller `sdk` profile.

Provider handling is intentionally two-layered. `DeepSeekHarnessRuntimeConfig.provider` remains the user-facing provider name. Blank provider values normalize to `deepseek-official`. The runtime maps the aliases `openai`, `volcengine`, `volcengine-ark`, `ark`, `openai-compatible`, and `third-party` to DSH's current `deepseek-official` adapter before constructing `DeepSeekHarnessConfig`. Unknown provider names are passed through so future DSH-native providers can work without a VeADK release.

State and lifecycle:

- One `DeepSeekHarness` manager is cached per effective process configuration.
- The manager starts lazily and is closed at interpreter exit.
- A generated `DSH_HOME` lives under a process-owned temp root unless `dsh_home` is configured.
- The manager key includes the bridged DSH tool schema digest. Each manager owns a long-lived localhost tool bridge and a generated DSH plugin patch when tools are present.
- The manager key includes the materialized skill content digest. Each manager owns its DSH skill patch and skill root when skills are present.
- Turns on the same manager are serialized. During one active turn, the manager binds the current ADK tool bundle to its bridge and clears it after the SDK call returns.
- The DSH session id is a SHA-256 based stable ID over VeADK app/user/session/agent identity.
- The DSH prompt serializes the callback-visible `LlmRequest.contents` into structured prior conversation and current-message blocks. This keeps ADK session history, not DSH's private session state alone, as the portable short-term memory contract shared with Codex.

Security:

- The SDK subprocess inherits the process environment by default, matching DSH SDK behavior. Configured `env`, `base_url`, and `api_key` are explicit overrides.
- The runtime does not invent a sandbox policy. DSH profile behavior is owned by DSH.
- Tool bridge calls are accepted only on loopback and require a per-manager bearer token embedded in the generated DSH plugin.
- The generated `DSH_HOME` avoids implicit writes to `~/.dsh`.

Compatibility:

- Existing `adk`, `codex`, and `piagent` behavior is unchanged.
- The new runtime is opt-in by both runtime value and extra dependency.
- Missing extra failures are import-time-on-resolution, not package import failures.

Component contract impact: a new component spec is required because this changes public runtime values, optional dependency behavior, session state, sidecar lifecycle, and configuration semantics.

## Implementation Tasks

- **T-1:** Add bilingual PRD/spec entries for the runtime contract. Covers `FR-1` through `FR-8`.
- **T-2:** Add the optional dependency extra and lock metadata. Covers `FR-2`, `FR-3`.
- **T-3:** Extend `Agent.runtime`, add `deepseek_harness_runtime_config`, and dispatch from `veadk.runtime.get_runtime`. Covers `FR-1`, `FR-2`.
- **T-4:** Implement `veadk.runtime.deepseek_harness` config, manager, prompt translation, generated DSH tool plugin, local tool bridge, native skill patch, event translator, and runtime. Covers `FR-4` through `FR-12`.
- **T-5:** Extend runtime compatibility warnings/errors for the new runtime. Covers `FR-13`.
- **T-6:** Add unit tests using a fake `deepseek_harness` module, without requiring the real binary. Covers `FR-1` through `FR-12`.
- **T-7:** Update runtime documentation in Chinese and English. Covers `FR-2`, `FR-3`, `FR-8`, `FR-10` through `FR-14`.

## Verification and Acceptance

| Requirement | Task | Acceptance criterion | Test or verification command | Result/evidence |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-3`, `T-6` | `runtime="dsh"` constructs and dispatches. | `uv run --extra dev pytest tests/runtime/deepseek_harness tests/runtime/differential/test_runtime_parity.py::test_model_fallbacks_warn_for_external_runtime` | pass, 2026-10-15 |
| `FR-2` | `T-2`, `T-3`, `T-6` | Missing SDK reports the extra installation command. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-3` | `T-2` | The extra declares `deepseek-harness-sdk==0.1.5rc1`; no downloader is added. | `uv lock --check`; source review | pass, 2026-10-15 |
| `FR-4` | `T-4`, `T-6` | Fake SDK is not instantiated until runtime execution. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-5` | `T-4`, `T-6` | Same VeADK session maps to the same DSH session id. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-6` | `T-4`, `T-6` | Runtime passes a non-empty explicit `dsh_home` by default. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-7` | `T-4`, `T-6` | Final DSH response becomes an ADK final event and callbacks can short-circuit. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-8` | `T-4`, `T-6` | Fake DSH loads the generated plugin patch and calls an ADK FunctionTool through the localhost bridge. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-9` | `T-4`, `T-6` | Sub-agent transfer uses the same injected transfer tool path as other external runtimes. | `uv run --extra dev --extra dsh pytest tests/runtime/deepseek_harness -q` | pass, 2026-10-16 |
| `FR-10` | `T-4`, `T-6` | Fake DSH config includes native DSH skill plugins and a materialized isolated skill root. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-11` | `T-4`, `T-6` | Fake DSH notifications/events map to ADK partial model events and native function call/response events. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-12` | `T-4`, `T-6`, `T-7` | Fake DSH receives structured ADK session history and uses the model selected by before-model callbacks. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |
| `FR-13` | `T-5`, `T-7` | Limitations are represented in support matrix and docs. | Source/doc review | pass, 2026-10-15 |
| `FR-14` | `T-4`, `T-6`, `T-7` | Provider aliases map to the current DSH adapter while preserving explicit model/base/key configuration. | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass, 2026-10-15 |

Required follow-up verification before release:

- Dependency install smoke on each published wheel platform supported by DSH.
- Optional live DSH smoke only with an isolated API key and explicit authorization.

Additional verification run on 2026-10-15:

- `uv run --extra dev ruff check veadk/runtime/deepseek_harness tests/runtime/deepseek_harness/test_deepseek_harness_runtime.py examples/deepseek_harness_runtime/main.py` — blocked in this checkout because the `ruff` executable is not installed in the active environment. The broader dev-dependency cleanup was not retained because it is outside this runtime change.
- `uv run --extra dev pytest tests/runtime/deepseek_harness -q` — pass, 15 passed, 1 warning.
- `uv run --extra dev --extra dsh pytest tests/runtime/deepseek_harness -q` — pass, 15 passed, 1 warning.
- `uv run --extra dev pytest tests/runtime/deepseek_harness tests/runtime/differential/test_runtime_parity.py::test_model_fallbacks_warn_for_external_runtime -q` — pass, 16 passed, 1 warning.
- `uv run --extra dev --extra dsh python examples/deepseek_harness_runtime/main.py --sqlite-path /tmp/veadk_dsh_runtime_acceptance_final_check.sqlite` — pass with the prepared environment. The live run uses separate skill and memory runners and proved all five example checks: `streaming` reported 2 partial chunks, `skill` returned `DSH-SKILL-OK`, `short_term_memory_sqlite` persisted 6 session events and recalled the session secret, `long_term_memory_auto_save` found 1 direct long-term-memory match after a session switch, and `observability` recorded 15 matched spans including 5 `call_llm` spans.
- `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` — pass, 7065 passed, 50 skipped, 4 xfailed, 82 warnings. The local metrics exporter reported transient `localhost:8000` unavailable messages after the pytest result, but pytest completed successfully.
- `npm --prefix docs run lint` — not retained as a release signal for this change. Temporary docs-toolchain and formatting fixes were reverted because they touched site-wide docs files outside the DSH runtime scope.
- `npm --prefix docs run types:check` — not retained as a release signal for this change for the same scope reason.

Additional review-fix verification run on 2026-10-16:

- `uv run --no-sync --extra dev --extra dsh pytest tests/runtime/deepseek_harness -q` — pass, 20 passed, 1 warning. This covers `additionalProperties` preservation, persistent `dsh_home` cleanup registration, process-private tool plugin paths, cancellation without closing the shared manager, and sub-agent transfer execution.
- `uv run --no-sync --extra dev --extra dsh pytest tests/runtime/piagent/test_piagent_runtime.py::test_build_executable_tools_custom_runtime_label_controls_logs -q` — pass, 1 passed, 1 warning.
- `uv run --extra dev pre-commit run --files veadk/runtime/deepseek_harness/tool_runtime.py veadk/runtime/deepseek_harness/runtime.py tests/runtime/deepseek_harness/test_deepseek_harness_runtime.py docs/content/docs/framework/agent/runtime.en.mdx docs/content/docs/framework/agent/runtime.mdx specs/runtime-deepseek-harness/README.md specs/runtime-deepseek-harness/README.zh.md` — pass.

## Risks and Open Questions

- DSH SDK is currently `0.1.5rc1`; the release-candidate pin should be revisited before a stable VeADK release.
- `enable_skills_checklist` is not enforced for DSH native skill loading because that checklist is an ADK before-tool callback.
- Descendant DSH subagent session notifications are not yet projected as first-class ADK child-session events.
- A persistent `dsh_home` may contain durable DSH session data; operators are responsible for retention and cleanup when they configure one.

## Review and Delivery Record

- User approved the extra-based SDK/runtime-bin direction and requested implementation on 2026-10-15.
- Direct design review was performed because no repository `review-spec` skill is available in this session. Findings:
  - Dependency acquisition must not duplicate DSH's runtime-bin wheel.
  - `DSH_HOME` must be explicit because the SDK requires it and avoids global state.
  - ADK/MCP tools must use the documented DSH tool plugin path; skills must use the documented DSH native skill plugins rather than ordinary tool expansion.
  - Runtime support-matrix warnings must include the new non-ADK runtime.
- Blocking findings: none after the limitations above were made explicit.
