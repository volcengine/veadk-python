# Restore application APM in the BytePlus Studio profile

[中文版](2026-10-14-restore-application-apm.zh.md)

Change ID: mpa-byteplus-application-apm-restore. Date: 2026-10-14. Status: implemented.
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-17.
Predecessor: [Disable application APM](2026-10-14-disable-application-apm.md).

## Background, goals and scope

BytePlus application APM was temporarily disabled to bypass an overseas
`GetAppKey` timeout. Live creation then reached Runtime readiness, but the
platform removed `ENABLE_APMPLUS=false` from the effective environment and the
creation verifier waited for an exact configuration match. The user has now
requested restoration of all APM bypass settings.

Goal: restore the inherited Runtime defaults for BytePlus:
`ApmplusEnable=true`, `ENABLE_APMPLUS=true`, and
`FORCE_APMPLUS_EXPORTER_REGISTRATION=true`. Non-goals: fixing the upstream
APMPlus timeout, changing readiness reconciliation, mutating existing Runtime
resources, or changing Volcengine defaults.

## Requirements and scenarios

- FR-1: New BytePlus profiles inherit all three enabled APM defaults.
- FR-2: Volcengine defaults remain enabled and provider profile calls remain
  isolated.
- FR-3: Existing Runtime resources and submitted task snapshots are unchanged;
  a restarted Studio and a new request are required to consume the restored
  defaults.

## Design, impact and tasks

- T-1: Change the provider regression to require enabled APM defaults for both
  providers and confirm it fails before implementation (FR-1/FR-2).
- T-2: Remove only the BytePlus APM overrides from
  `studio_profile_values`; preserve image, model, OV and provider settings
  (FR-1/FR-3).
- T-3: Reconcile this PRD, its predecessor and the bilingual component contract;
  run targeted tests, Ruff, Pyright, bilingual/link and whitespace checks.

No API, schema, credential, frontend or generated-asset contract changes.
The known BytePlus APMPlus service timeout can again make Runtime startup fail;
this rollback is intentional and does not claim that upstream APMPlus works.

## Review, risks and acceptance

User approval: on 2026-10-14 the user explicitly requested restoring
`ENABLE_APMPLUS` and the related APM bypass settings. Direct design review:
scope, provider isolation, compatibility, security and testability were checked;
no blocker remains. The primary risk is recurrence of the already observed
`GetAppKey InternalServiceTimeout`.

- AC-1: Both providers resolve and deploy all three APM settings as enabled.
- AC-2: Targeted tests and static checks pass.
- AC-3: Documentation is bilingual and records that no existing Runtime is
  mutated.

## Verification and delivery

2026-10-14, local diff based on the current worktree:

- pass: the changed regression failed for BytePlus before implementation and
  passed after removing the three overrides.
- pass: `uv run --extra dev pytest -q
  tests/integrations/mpa_managed/test_byteplus.py
  tests/integrations/mpa_managed/test_config.py`, 105 tests.
- pass: `uv run --extra dev pytest -n 2 -q
  tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`,
  1,093 tests with four dependency deprecation warnings.
- pass: Ruff 0.11.12 check/format and Pyright on the changed Python files.
- pass: paired-document presence, relative links and scoped diff whitespace.
- not_run: live cloud creation, commit, push and all-files pre-commit were not
  requested.
- not_applicable: frontend build/browser checks; no frontend behavior changes.
