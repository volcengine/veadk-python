# Align package dependency metadata for Google ADK and OpenTelemetry

[中文版](2026-10-12-google-adk-opentelemetry-baseline.zh.md)

- Change ID: `runtime-dependency-compatibility`
- Created/revised: 2026-10-13
- Status: implemented
- Related component spec: [Runtime dependency compatibility](../../../specs/runtime-dependency-compatibility/README.md)
- Scope: main package dependency metadata, the main development lock, metadata regression tests, and minimal ADK 2.7 build-graph/Studio compatibility coverage. Studio, sandbox, generated project, managed sidecar, and Docker dependency declarations are intentionally out of scope.

## Background and evidence

Two upstream Google ADK commits fix session event timestamp determinism and UTC storage/filtering:

- `4ca975eb9acd30a64b2c8615a93d31dada63052c`: `fix(sessions): make event reads deterministic and timezone-correct`
- `1b8ed3d9c0b125852df1902dd32b65bcab63ce1d`: `fix(sessions): store and filter event timestamps in UTC`

Those fixes are available in Google ADK `2.7.0` and later. The local VeADK lock previously selected Google ADK `2.2.0`.

The confirmed resolver blockers were:

- AgentKit SDK's old OpenTelemetry upper bounds. They were fixed by publishing `agentkit-sdk-python==0.8.9`.
- VeADK's direct `opentelemetry-exporter-otlp==1.37.0` exact pin.

Fresh resolver evidence on 2026-10-13 showed that an unconstrained `google-adk>=2.7.0` selects `google-adk==2.11.0`. The targeted compatibility suite failed on that line because ADK 2.11 removed or changed internals VeADK still patches, including `google.adk.flows.llm_flows.functions.__call_tool_async`, and piagent tool execution then saw a missing `run_config` on the test invocation context. This PR therefore supports the current 2.7 compatibility window as `google-adk>=2.7.0,<2.8.0`.

## Goals

- Raise VeADK's Google ADK requirement to `google-adk>=2.7.0,<2.8.0` so the UTC session timestamp fixes are available while avoiding known ADK 2.8+ compatibility risk.
- Keep VeADK's AgentKit requirement flexible at `agentkit-sdk-python>=0.8.5` so new installs can resolve to `0.8.9` without forcing an exact pin.
- Keep VeADK's direct OpenTelemetry exporter flexible at `opentelemetry-exporter-otlp>=1.37.0`.
- Update the main development `uv.lock` to the current compatible resolution.
- Preserve ADK 2.7 build-graph and Studio lazy GenAI behavior covered by regression tests.

## Non-goals

- Do not change Studio, sandbox, generated project, managed sidecar, or Docker dependency declarations in this change.
- Do not pin VeADK to `agentkit-sdk-python==0.8.9`.
- Do not support ADK `2.8.0` or later in this PR; that requires a separate compatibility pass for changed ADK internals.
- Do not publish packages, Docker images, sandbox images, or Studio assets.

## Requirements

- `FR-1`: Package metadata must use `google-adk>=2.7.0,<2.8.0` for the base dependency and `google-adk[eval]>=2.7.0,<2.8.0` for the eval extra.
- `FR-2`: Package metadata must keep `agentkit-sdk-python>=0.8.5`.
- `FR-3`: Package metadata must use `opentelemetry-exporter-otlp>=1.37.0`, not an exact pin.
- `FR-4`: The main `uv.lock` metadata must reflect the updated package metadata and resolve Google ADK to a compatible 2.7.x release.
- `FR-5`: Regression tests must cover package metadata and lock metadata.
- `FR-6`: ADK build-graph serialization must continue to expose VeADK nested `sub_agents` under ADK 2.7.x.
- `FR-7`: Studio startup tests must continue to verify lazy GenAI model loading under ADK 2.7.x telemetry APIs.

## Design and contract impact

Update the published package dependency metadata and the main development lock:

- `google-adk>=2.7.0,<2.8.0`
- `agentkit-sdk-python>=0.8.5`
- `opentelemetry-exporter-otlp>=1.37.0`

`google-adk[eval]` uses the same `>=2.7.0,<2.8.0` window. The `harness-sidecar` optional dependency keeps the same AgentKit lower bound.

The `google-adk<2.8.0` upper bound is deliberate. It prevents fresh installs from selecting currently unverified ADK 2.8+ releases after the targeted suite reproduced ADK 2.11 incompatibility.

ADK 2.7's graph serializer skips Pydantic fields marked `exclude=True`; VeADK's `Agent.sub_agents` uses that flag. The build-graph compatibility patch therefore adds `sub_agents` from the live VeADK agent only when ADK's serialized result omits them.

ADK 2.7 no longer exposes `_experimental_semconv.transformers` in the Studio test path. The test now falls back to `google.genai.models.t` while preserving the assertion that Studio defers the real GenAI models module until first use.

No persistent state, security boundary, or public Python API changes are introduced.

## Implementation tasks

| Task | Requirements | Affected files |
| --- | --- | --- |
| `T-1` | `FR-1`, `FR-2`, `FR-3` | `pyproject.toml` |
| `T-2` | `FR-4` | `uv.lock` |
| `T-3` | `FR-5` | `tests/test_runtime_dependency_compatibility.py` |
| `T-4` | `FR-6` | `veadk/utils/patches.py`, `tests/cli/test_frontend_trace.py` |
| `T-5` | `FR-7` | `tests/cli/test_studio_startup_imports.py` |
| `T-6` | all | PRD/spec reconciliation and verification record |

## Verification and acceptance

| Requirement | Acceptance criterion | Result/evidence |
| --- | --- | --- |
| `FR-1` | Package metadata uses `google-adk>=2.7.0,<2.8.0` and `google-adk[eval]>=2.7.0,<2.8.0` | pass |
| `FR-2` | `agentkit-sdk-python>=0.8.5` remains in package metadata | pass |
| `FR-3` | `opentelemetry-exporter-otlp>=1.37.0` remains flexible | pass |
| `FR-4` | `uv.lock` metadata reflects the updated package metadata and resolves ADK 2.7.x | pass: lock resolves `google-adk==2.7.1` |
| `FR-5` | targeted dependency metadata tests pass | pass |
| `FR-6` | nested VeADK agents appear in ADK build-graph JSON | pass |
| `FR-7` | Studio lazy GenAI startup tests pass under ADK 2.7.x | pass |

## Risks and open questions

- Users with existing lock files or constraints can still remain on older dependency selections until they update those files.
- ADK `2.8.0` and later are intentionally excluded until VeADK adapts to upstream internal API changes.
- Studio, sandbox, generated project, managed sidecar, and Docker paths still have their existing dependency declarations and should be handled separately if product owners decide to update those surfaces.

## Review and approval

- User approved upgrading ADK directly in this PR on 2026-10-13 and asked to add an upper bound if higher ADK versions are incompatible.
- Direct design review (`review-spec` unavailable): scope, dependency bounds, lock behavior, ADK 2.7 compatibility, ADK 2.11 failure evidence, and bilingual equivalence reviewed.

## Delivery record

### Verification (2026-10-13, working diff)

| Check | Result |
| --- | --- |
| PyPI version check for `google-adk` | pass: latest stable observed as `2.11.0`; unrestricted `>=2.7.0` would select a newer line |
| `uv lock --upgrade-package google-adk` with unrestricted `>=2.7.0` | fail for compatibility scope: resolved `google-adk==2.11.0`; targeted suite failed on ADK internal changes |
| `uv lock --upgrade-package google-adk` with `>=2.7.0,<2.8.0` | pass: resolved `google-adk==2.7.1` |
| `uv run --extra dev pytest -q tests/test_runtime_dependency_compatibility.py tests/extensions/harness/test_sidecar_wheel.py::test_wheel_metadata_keeps_sidecar_optional_and_sdk_constraints_aligned tests/cli/test_frontend_sandbox.py::test_snapshot_metadata_survives_older_sdk_and_scopes_cards tests/runtime/piagent/test_piagent_runtime.py::test_piagent_runtime_emits_canonical_bridge_tool_events tests/runtime/piagent/test_piagent_runtime.py::test_piagent_runtime_exposes_before_model_added_tools tests/test_adk_sync_tool_thread_pool_patch.py::test_run_code_uses_agent_thread_pool_when_configured tests/tools/builtin_tools/create_agent/test_create_agent_toolset.py::test_runner_transfers_from_create_agents_to_dynamic_sub_agent tests/cli/test_frontend_trace.py::test_build_graph_serializes_nested_veadk_agent_models tests/cli/test_studio_startup_imports.py::test_studio_fast_api_defers_genai_models_until_first_request tests/cli/test_studio_startup_imports.py::test_studio_deferred_genai_models_support_openapi_first_use` | pass: 11 passed |
| `uv run --extra dev pre-commit run --all-files` | pass |
| `git diff --check` | pass |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail: 6913 passed, 55 skipped, 4 xfailed, 16 failed. The failed run included stale assertions fixed by this change and Codex runtime tests missing the optional `openai_codex` package under `--extra dev`. The Codex failure subset passed with `--extra codex`. |
| `uv run --extra dev --extra codex pytest -q` for the 10 failed Codex runtime tests | pass: 10 passed |

This change is complete for the main package dependency and ADK 2.7 compatibility scope. Studio, sandbox, generated project, managed sidecar, and Docker dependency declarations are deferred.
