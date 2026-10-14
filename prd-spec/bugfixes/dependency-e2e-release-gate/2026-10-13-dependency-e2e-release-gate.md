# Dependency E2E Release Gate

[中文版](2026-10-13-dependency-e2e-release-gate.zh.md)

| Field | Value |
| --- | --- |
| Change ID | `dependency-e2e-release-gate` |
| Created | 2026-10-13 |
| Status | approved |
| Component specs | No component contract impact; this change only adds release-time validation for package metadata and dependency resolution. |

## Background

The dependency incident showed that local `uv.lock` success is not enough for PyPI users. VeADK can publish metadata that lets pip resolve an unsupported upstream version, or pin a shared base dependency so tightly that a compatible upstream stack cannot be installed.

## Goals and non-goals

| Type | Scope |
| --- | --- |
| Goal | Block PyPI publication when the built wheel cannot be installed in a clean environment. |
| Goal | Expose high-risk direct dependency upgrades that conflict with current runtime pins or other package metadata. |
| Goal | Reject high-risk unbounded runtime dependencies and exact pins for shared OpenTelemetry packages. |
| Non-goal | Exhaustively test every optional extra, Studio/docker/sandbox runtime, or real cloud service. |

## Requirements

| ID | Requirement |
| --- | --- |
| FR-1 | The tag publish workflow must install the built wheel in a clean venv, run `pip check`, and run a minimal import smoke before uploading to PyPI. |
| FR-2 | The tag publish workflow must test selected high-risk base runtime direct dependencies at their highest currently available versions inside VeADK's declared ranges, together with the built wheel's current runtime pins. |
| FR-3 | The policy check must fail for unbounded `google-adk` and exact `opentelemetry-*` runtime pins. |
| FR-4 | The checks must run on the release artifact, not the developer `uv.lock` environment. |

## Design

| Part | Decision |
| --- | --- |
| Script | Add `scripts/check_dependency_e2e.py` with `policy`, `clean-install`, and `declared-range` commands. |
| Workflow | Expose a standalone `dependency-policy-gate` on PRs and pushes; run clean install and declared-range checks only for tag publication or manual workflow dispatch. |
| Dependency scope | Check selected high-risk base dependencies: `google-adk`, `agentkit-sdk-python`, OpenTelemetry packages, `litellm`, `mcp`, `fastmcp`, `tos`, and `jsonschema`; each candidate upgrade is resolved against the full wheel metadata, including exact runtime pins. Optional extras are deferred. |
| Developer guidance | Add repository-level dependency metadata guidelines so developers and coding agents avoid unbounded high-risk dependencies, unjustified shared base pins, and `uv.lock`-only validation before the heavier release E2E runs. |
| Runtime smoke | Import `veadk`, `google.adk`, and `opentelemetry` only; no credentials or external service calls. |

## Tasks

| ID | Work | Requirement |
| --- | --- | --- |
| T-1 | Add the dependency E2E script. | FR-1, FR-2, FR-3, FR-4 |
| T-2 | Add unit tests for dependency policy and highest-version selection. | FR-2, FR-3 |
| T-3 | Wire the script into the tag publish workflow and PR-visible dependency policy gate. | FR-1, FR-2, FR-4 |
| T-5 | Run the policy check from pre-commit for dependency metadata edits. | FR-3 |
| T-6 | Document repository-level dependency metadata guidelines for developers and coding agents. | FR-2, FR-3 |
| T-4 | Adjust runtime dependency metadata if the new checks expose an existing conflict. | FR-2, FR-3 |

## Acceptance

| Requirement | Task | Criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| FR-1 | T-1, T-3 | Clean wheel install gate exists before PyPI upload. | `uv run --extra dev pytest tests/test_dependency_e2e.py` | pass |
| FR-2 | T-1, T-2, T-3 | Selected high-risk direct dependency highest-version checks are implemented and unit-tested against current runtime pins. | `uv run --extra dev pytest tests/test_dependency_e2e.py`; `uv run python scripts/check_dependency_e2e.py --dist-dir <tmp-dist> declared-range` | pass |
| FR-3 | T-1, T-2, T-4 | `google-adk` requires an upper bound and `opentelemetry-*` exact pins are rejected. | `uv run python scripts/check_dependency_e2e.py policy` | pass |
| FR-4 | T-3 | Workflow checks `dist/*.whl` instead of `uv.lock`. | workflow diff review | pass |
| FR-3 | T-5 | Local pre-commit runs the same runtime dependency policy check when `pyproject.toml` changes. | `uv run --extra dev pre-commit run --all-files` | pass |
| FR-2, FR-3 | T-6 | `AGENTS.md` documents dependency metadata rules for high-risk upper bounds, shared base pins, direct dependency declarations, and heavyweight E2E deferral. | guideline diff review | pass |

## Risks

| Risk | Mitigation |
| --- | --- |
| PyPI state can change after release. | Keep the gate on tag publish and optionally run it manually before tagging. |
| Highest-version installs may be slower than normal unit tests. | Check only selected high-risk dependencies and run the heavy checks only on tag publication or manual workflow dispatch. |

## Review record

User approved implementation after reviewing the E2E plan in chat. Direct review found no component-spec change because public SDK behavior and runtime contracts are unchanged.

## Verification record

| Date | Command | Result | Notes |
| --- | --- | --- | --- |
| 2026-10-13 | `uv lock` | pass | Refreshed lock metadata after dependency bound updates. |
| 2026-10-13 | `uv run --extra dev pytest tests/test_dependency_e2e.py` | pass | 11 tests passed. |
| 2026-10-13 | `uv run python scripts/check_dependency_e2e.py policy` | pass | Runtime dependency policy passed. |
| 2026-10-13 | `uv run python scripts/check_dependency_e2e.py --dist-dir <tmp-dist> declared-range` | pass | Validated selected high-risk dependency pins including `google-adk==2.7.1`, `opentelemetry-exporter-otlp==1.42.1`, `opentelemetry-instrumentation-logging==0.63b1`, `fastmcp==3.4.8`, `tos==2.8.7`, and `jsonschema==4.23.0`. |
| 2026-10-13 | `uv run python scripts/check_dependency_e2e.py --dist-dir <tmp-dist> clean-install` | blocked | Local PyPI download for `google-adk` was too slow and was interrupted; the workflow gate remains wired to run this in GitHub Actions before upload. |

## Dependency metadata adjustments found by the E2E check

| Dependency | Before | After | Reason |
| --- | --- | --- | --- |
| `opentelemetry-exporter-otlp` | `>=1.37.0` | `>=1.37.0,<1.43` | `google-adk 2.7.x` caps OpenTelemetry SDK/API at the 1.42 line. |
| `opentelemetry-instrumentation-logging` | `>=0.56b0` | `>=0.56b0,<0.64` | The 0.64+ instrumentation line resolves with newer OpenTelemetry packages than `google-adk 2.7.x` allows. |
| `fastmcp` | `>=2.12.3` | `>=2.12.3,<4` | `fastmcp 4.x` requires `mcp>=2`, while VeADK currently declares `mcp==1.26.0`. |
| `tos` | `>=2.8.4` | `>=2.8.4,<2.9` | `tos 2.9.x` pins `wrapt==1.16.0`, conflicting with VeADK's `wrapt==1.17.2`. |
| `jsonschema` | `>=4.23,<5` | `>=4.23,<4.24` | `litellm 1.83.x` pins `jsonschema==4.23.0`; the previous range overstated installable versions. |
