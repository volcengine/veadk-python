# Attach the worker Tool during initial Runtime creation

[中文版](2026-09-29-runtime-initial-tool-attachment.zh.md)

- **Change ID:** `mpa-runtime-initial-tool`
- **Date:** 2026-09-29
- **Status:** implemented
- **Contract:** [MPA Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md)

## Background and evidence

Managed MPA deployment currently removes `ToolId` from the first `CreateRuntime`
request and attaches it in a later `UpdateRuntime`. A live comparison showed that
the control plane can move such a Runtime directly to version 0 `Error` before
network and worker resources are prepared, while a creation request containing
the ready worker Tool reaches `Ready`. The delayed attachment was introduced to
work around an `InvalidParameter.ToolId` observed while replacing the Tool on an
already failed Runtime; it does not establish that initial creation rejects the
Tool.

## Goals and non-goals

- Restore `ToolId` in the initial Runtime create payload when the desired
  configuration contains it.
- Preserve the existing final update that publishes authoritative endpoint/key
  environment values and converges all desired fields.
- Preserve pending-request hashing, client-token retry, worker creation, TOS
  configuration, and existing Runtime update behavior.
- Do not change Tool provisioning, TOS credentials, session mounts, Runtime
  images, or migrate existing failed Runtimes.

## Scenarios and requirements

- **FR-1:** Given a newly provisioned worker Tool, when a new managed Runtime is
  created, `CreateRuntime` MUST include that Tool's `ToolId`.
- **FR-2:** Given the Runtime becomes platform-ready, finalization MUST continue
  to publish endpoint/key environment values and converge the desired Tool.
- **FR-3:** Lost-response retries MUST retain the same desired payload and
  `ClientToken` behavior.

## Design and contract impact

Remove the special copy-and-pop operation before `cloud.create`; pass the
already normalized `desired` payload directly. Keep `ToolId` in the convergent
update field set so existing Runtimes and finalization remain idempotent. This
changes the managed Runtime lifecycle contract, so the bilingual provisioning
spec is updated. Public Python signatures, persistence schemas, permissions,
credential handling, and compatibility inputs are unchanged.

## Tasks, verification, and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| `FR-1` | `T-1` update regression assertions, then Runtime create payload | `AC-1` first create contains the worker `ToolId` | `uv run --extra dev pytest tests/integrations/mpa_managed/test_agent_deployment.py tests/integrations/mpa_managed/test_service.py` |
| `FR-2` | `T-2` preserve convergent update | `AC-2` final Runtime retains the same `ToolId` and finalized environment | same command |
| `FR-3` | `T-3` run managed deployment regressions | `AC-3` retry/idempotency tests remain green | `uv run --extra dev pytest tests/integrations/mpa_managed` |

## Risks, recovery, and review

The remaining risk is a control-plane variant that rejects a newly created Tool
at Runtime creation. The observed live path and the successful reference Runtime
support initial attachment; a failure remains visible rather than being reported
as partial success. Recovery is to revert this focused change. No secrets or
external mutations are part of automated verification.

`review-spec` is unavailable. Direct review covered scope, lifecycle ordering,
retry/idempotency, security, compatibility, testability, and bilingual
equivalence; no blockers remain. The user's instruction to fix the diagnosed
regression approves this design.

## Delivery record

Implemented on 2026-09-29. `T-1` through `T-3` and `AC-1` through `AC-3` are
complete for the affected path.

- `pass`: the two affected test files pass, 58 tests total. The regression
  failed before the implementation with missing `ToolId` and passes after it.
- `pass`: a standard-library line trace over the regression test executed both
  changed production lines, giving 100% incremental executable-line coverage.
- `pass`: changed-file pre-commit checks passed Ruff check/format and hardcoded
  secret scanning; `git diff --check` passed.
- `fail` (unrelated environment issue): the whole `mpa_managed` suite under
  coverage reports AgentKit SDK/Pydantic `AliasChoices` class-identity errors.
  The same coverage instrumentation also fails the isolated regression before
  reaching the changed path; ordinary targeted pytest passes.
- `fail` (unrelated existing formatting): all-files pre-commit reformats
  `veadk/integrations/mpa/managed/tasks.py`, which is outside this change. That
  generated edit was reverted and the affected-file hooks were rerun cleanly.
- `not_run`: live cloud creation; automated tests use isolated fake control
  planes and perform no external mutations.
