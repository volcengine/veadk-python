# Stabilize PR #1190 CI tests

[中文版](2026-10-28-stabilize-concurrent-tests.zh.md)

Change ID: `pr1190-ci`; created/revised: 2026-10-28; status: approved.
Comparison base: feature commit `7527a832`; upstream `23014771`.
Related design: [first-token timestamps](../../features/first-token-timestamps/2026-10-28-first-token-timestamps.md).

## Evidence and scope

Unit Tests run `40649026439`, Python 3.10 job `122684493009`, reports 1 failed, 7,937 passed, 46 skipped, 4 xfailed. The failing startup-prefetch test assumes `tool-codex` is inspected before `tool-codex-snapshot`. Production intentionally uses `asyncio.gather` and `asyncio.to_thread`, so either order is valid. Python 3.12 was cancelled by matrix fail-fast.

The earlier local full regression also exposed a baseline Sidecar test that inherits developer model upstream settings, activating a stable relay while asserting a fixed fake discovery URL. `run_with_harness_sidecar` already supports an explicit `env` mapping.

Goal: deterministic tests for the actual contracts. Non-goals: runtime changes, serializing production concurrency, weakening assertions, retries/skips, CI configuration changes, frontend changes, dependencies, additional cloud deployments.

## Requirements and design

- FR-1: Both configured Sandbox tools are inspected exactly once, regardless of scheduling order, and their final cached states appear in the system-info response.
- FR-2: Explicitly exercise both inspection orders using a bounded thread Event; compare exact call multiplicities without requiring a production order.
- FR-3: Poll the returned state within a bounded deadline instead of treating entry into the inspection stub as cache publication.
- FR-4: The fake Sidecar child receives exact discovery endpoints in an explicitly isolated environment, even if the parent has model/MCP upstream variables.

Change only `tests/cli/test_studio_rbac.py` and `tests/extensions/harness/sidecar_runtime/test_sidecar.py`, plus bilingual design/evidence. Preserve every existing response and endpoint assertion. No component spec changes: all public/runtime/permission/data/observability contracts are unchanged. Rollback reverts this test-only commit.

## Tasks and acceptance

| Requirement | Task | Acceptance | Evidence |
| --- | --- | --- | --- |
| FR-1/2 | T-1: force both thread orders, then correct the ordered assertion | AC-1: reverse scheduling fails before the correction; both schedules pass after it | Targeted pytest, original CI failure |
| FR-3 | T-2: wait for both published response states | AC-2: exact existing model-state assertions pass | Same parameterized TestClient test |
| FR-4 | T-3: give the Sidecar fake an explicit empty environment | AC-3: exact endpoint assertions pass with parent upstream variables present | Fake runtime and real child subprocess test |
| All | T-4: required gates, publish, inspect CI | AC-4: affected suites, full default regression, pre-commit and remote CI green; production diff coverage stays >=95% | Repository commands below |

Commands: `uv run --no-sync --extra dev pytest tests/cli/test_studio_rbac.py tests/extensions/harness/sidecar_runtime/test_sidecar.py -n 2 -q`; `uv run --no-sync --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q`; `uv run --no-sync --extra dev pre-commit run --all-files`. Reuse feature coverage and real cloud evidence because production code is unchanged; verify its source hashes.

## Review and authorization

2026-10-28: User authorized repairing CI on PR #1190 after completing the Feishu design document. Earlier commit/push authorization persists for this branch. Direct design review (`review-spec` unavailable) confirms test-only scope, exact multiplicity/state/URL oracles, bounded synchronization, unchanged production concurrency and isolation from real credentials. English/Chinese identifiers and acceptance criteria agree. No design blocker remains.

Risks: thread entry does not imply cache publication; response-state polling addresses this. Local Python 3.12 differs from CI's 3.10/3.12 matrix; remote results are required for delivery. Cloud revalidation is not applicable to a test-only repair; preserve the previously executed 6/6 real cloud conclusion.

## Verification record

2026-10-28, `7527a832` plus this test-only diff, Python 3.12.13:

- Original ordered assertion with controlled schedules: 1 passed, 1 failed; reverse order reproduces the exact CI failure.
- Parent-upstream injection before explicit `env={}`: 1 failed with fixed discovery URL versus relay URL. Original isolated single-case execution passed, confirming the environment-dependent mechanism.
- After corrections: 3 targeted cases passed (two schedules and child environment).
- Combined affected run: 185 passed, 4 failed. All 174 Studio cases passed; four unrelated loopback requests used the local machine proxy and received HTTP 403. Rerunning the complete 15-case Sidecar file with command-scoped `NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1` passed. Thus all 189 affected cases passed in the appropriate local environment; no network test assertion or proxy policy was changed.
- All-files pre-commit passed after formatting; bilingual identifiers, literal commands, relative links and whitespace checks passed.
- All nine production file hashes match the original real-cloud build. Production changed-line coverage remains 100% (208/208); real cloud E2E remains 6/6 pass. This repair adds no production executable lines.
- Full default regression with the same command-scoped loopback bypass and `--junitxml` outside Git: **7,942 passed, 0 failed, 42 skipped, 4 xfailed; 6 subtests passed; 472.66s**. The 7,988 selected cases comprise 7,946 executed cases (including four expected failures) and 42 skipped cases. Final remote 3.10/3.12 results are tracked on the published PR. The user subsequently limited additional test execution to failed cases; no additional broad test run is planned.


### Gate status

| Gate | Status | Evidence |
| --- | --- | --- |
| Change Basis | PASS | Complete test/design diff against `7527a832`; upstream `23014771` unchanged; no unrelated work. |
| Contract | PASS | Exact tool multiplicities, published states and child discovery endpoints; production contracts unchanged. |
| Impact | PASS | R-CI-1/2 cover the affected test oracles and environment boundary. |
| Portfolio | PASS | Two controlled thread schedules, TestClient state publication, real fake-runtime/child processes. |
| Baseline | PASS | Reverse-order assertion and parent-upstream injection both observed RED before correction. |
| Execution | PASS | Targeted 3 cases; all 189 affected cases; full default regression; all-files pre-commit. |
| Evaluation | PASS | Original state/URL assertions retained; duplicate calls still fail; source hashes and 208/208 production coverage unchanged. |
| Handoff | PASS | Bilingual design/evidence reconciled; final published CI evidence is linked from PR #1190. |

### Change Impact

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
| --- | --- | --- | --- | --- | --- |
| FR-1/2/3 | Test scheduling and completion oracle | Startup-prefetch test and system-info cache response | `asyncio.gather`, `asyncio.to_thread`, `test_system_info_prefetches_codex_model_env_state_on_startup` | False CI failure on valid scheduling, or checking states before publication | R-CI-1 Medium |
| FR-4 | Test subprocess environment | Fake Sidecar and child execution | `run_with_harness_sidecar(env=...)`, child-environment test | Parent upstream variables change expected discovery endpoints | R-CI-2 Medium |

Both risks cross owned integration boundaries; inherent impact/exposure/hazard/detection are Medium/Medium/Medium/Low. No material unknown remains in the changed test scope. Residual uncertainty is bounded to untested host loads; no load/performance claim is made.

### Test Portfolio

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-CI-1 | Threaded provider stub and real ASGI response | Controlled schedules and state transitions | Codex first; snapshot first; exact per-kind final state | Both tool IDs exactly once; controlled first entry; all original state/error assertions | RED: 1 failed/1 passed; GREEN: both cases and affected/full suites | VERIFIED |
| R-CI-2 | Real fake-runtime and child subprocesses | Parent-environment injection and isolation | Model/MCP parent upstreams; explicit empty child base environment | Exit 0 and exact original model/MCP URLs | RED: 1 failed; GREEN: targeted case and all 15 Sidecar tests | VERIFIED |

Production, frontend, dependencies, CI policies, credentials and cloud behavior are not changed. Existing source-hash evidence discriminates accidental production drift. No new tests of formatting or duplicated implementation were added. Opt-in Codex/Pi smoke checks are outside this test-only repair; remote CI still runs its existing Codex smoke job. Final remote results are authoritative at https://github.com/volcengine/veadk-python/pull/1190/checks.
