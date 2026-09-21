# MPA editor type diagnostics

[中文版](2026-09-21-mpa-test-types.zh.md)

- ID: mpa-test-types; created/revised: 2026-09-21; status: approved.
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).

## Background and scope

The user requested fixing editor errors. Pyright over managed MPA implementation, Studio route and tests reports 20 errors in test doubles and inferred numeric timeout types. Frontend `tsc --noEmit -p tsconfig.json` passes. Tests use narrower inferred literals, add undeclared attributes, pass an untyped namespace as Profile, fake SDK clients as tuples, and pass fake engines to an AsyncEngine contract. No runtime creation failure is implicated.

## Requirements and design

- FR-1: Eliminate the 20 reproducible Pyright errors without ignore comments, disabling checks, casts that hide incorrect fixtures, or relaxing production object contracts.
- FR-2: Use real Profile/Managed models in service tests, explicitly declare fake capabilities and method signatures, and use spec-constrained mocks for SDK/engine boundaries. Preserve assertions, fault injection and external-service isolation.
- FR-3: Annotate runtime/network timeout seconds as float to describe already-supported fractional durations; retain defaults and runtime logic. No dependency, config, HTTP/UI, persistence or resource change.

Component impact: no maintained contract change; annotations document existing numeric behavior and tests conform to existing interfaces. No component-spec edits required. Affected files: `runtime.py`, `network.py`, test_agent_deployment, test_deployment_database_unit, test_deployment_network_cloud, test_gateway, test_runtime_deployment_edges, test_service under managed MPA. No unrelated lint cleanup.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1/2 | T-1: reproduce and correct typed fixtures | AC-1: complete managed MPA implementation/route/test Pyright has zero errors; existing assertions retained |
| FR-3 | T-2: annotate durations | AC-2: defaults and timeout/cancellation tests unchanged |
| All | T-3: verification and paired documentation | AC-3: MPA/CLI regression, changed-file Ruff/format, TypeScript check and whitespace pass |

The failing Pyright run is the regression baseline (20 errors). Existing behavioral tests validate the fixture corrections; no redundant new behavior test is needed for type-only changes. Run `uv run --extra dev --with pyright pyright veadk/integrations/mpa/managed frontend/server/mpa_creation.py tests/integrations/mpa_managed`, `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q`, and pinned Ruff checks.

## Review and approval

The user explicitly requested “有爆红啊，修一下” and clarified “代码编辑器报红”. The stated plan fixes reproducible type mismatches without suppressions. Direct review (review-spec unavailable) found no contract/security/bilingual blocker. Risk: editor interpreter-specific errors outside this command may still need the exact file/message; do not claim unobserved editor state. No commit/push/cloud operations or service restart needed.

## Verification

2026-09-21 working diff: baseline Pyright fail (20 errors); TypeScript pass. Final checks not_run (pending). Browser/build not_applicable (no frontend changes); live cloud not_run (not relevant); pre-commit not_applicable (no commit requested).
