# Disable application APM in the BytePlus Studio profile

[中文版](2026-10-14-disable-application-apm.zh.md)

Change ID: mpa-byteplus-application-apm. Date: 2026-10-14. Status: superseded.
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-17.
Successor: [Restore application APM](2026-10-14-restore-application-apm.md).

## Background, goals and scope

A BytePlus Runtime failed during Agent initialization after APM GetAppKey returned InternalServiceTimeout. The built-in overseas profile inherits ENABLE_APMPLUS=true and FORCE_APMPLUS_EXPORTER_REGISTRATION=true from the domestic profile. The user explicitly approved setting these two BytePlus defaults to false to test application startup. No production log, credential or signed URL is retained here.

Goal: stop requesting application APM initialization by default for BytePlus managed Studio creation. Live verification showed that `ApmplusEnable=true` rewrites the Runtime `ENABLE_APMPLUS` value to `true`, so the BytePlus control-plane setting must also be false. Non-goals: changing domestic defaults, general agents, Worker telemetry, agentkit-mpa-agent code, retry/network recovery, or existing cloud resources.

## Requirements and scenarios

- FR-1: Given the built-in BytePlus profile, both ENABLE_APMPLUS and FORCE_APMPLUS_EXPORTER_REGISTRATION are string false in the resolved Runtime environment and deployment payload.
- FR-2: Given the built-in Volcengine profile, both application flags and ApmplusEnable remain true. Given BytePlus, both application flags and ApmplusEnable are false. Provider calls return fresh profiles and cannot contaminate each other.
- FR-3: Retain trusted explicit configuration overrides, existing request hashing, cancellation and partial-failure handling. No API, credential, schema or task-state changes. Do not automatically update an existing Runtime or bypass a conflicting pending deployment.

## Design, impact and tasks

T-1: Add a failing provider-parametrized regression to tests/integrations/mpa_managed/test_byteplus.py, checking raw defaults, resolved profile and apply_runtime_settings output without cloud calls (FR-1/FR-2).
T-2: Override the two application keys and `apmplus-enable` in the existing BytePlus branch of studio_profile_values (FR-1/FR-3). The maintained CON-17 and bilingual managed README document the provider distinction.
T-3: Run targeted tests, managed/startup regression with two workers, changed-file Ruff/Pyright, scoped secret scan and bilingual/link/whitespace checks. No frontend assets change; browser/build checks are not applicable because no frontend or HTTP interface changes.

## Review, risks and acceptance

User approval: explicit requests on 2026-10-14 to disable the two BytePlus flags and, after live evidence showed the platform override, to disable BytePlus `ApmplusEnable`. Direct design review (review-spec unavailable): scope, configuration precedence, provider isolation, security, compatibility, tests and bilingual equivalence reviewed; no blockers. No new dependencies or sensitive values. BytePlus application and platform APM initialization are disabled; Volcengine remains unchanged. This does not prove startup, OV or chat succeeds, and does not resolve separately diagnosed failures. Changed Runtime settings may conflict with an already pending deployment hash; use a new request for the trial.

- AC-1: BytePlus resolved environment and payload contain both false values.
- AC-2: Domestic environment and platform ApmplusEnable remain unchanged; BytePlus ApmplusEnable is false; repeated provider loads remain isolated.
- AC-3: Local checks pass; live verification is reported separately, without cloud writes.

## Verification and delivery

2026-10-14, local diff based on 2ffe6e14: not_run, implementation checks pending. not_run, live creation/restart/commit/push and all-files pre-commit, none requested. not_applicable, frontend/browser/build and harness smoke, no changes to these boundaries. Preserve unrelated local changes.

2026-10-14 results, scoped local change on 2ffe6e14:
- pass: pre-fix regression reproduced one BytePlus failure while the domestic case passed.
- pass: `uv run --extra dev pytest -q tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_config.py`, 105 tests.
- pass: `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`, 1,093 tests, four dependency deprecation warnings; two workers chosen for the local environment.
- pass: Ruff 0.11.12 check/format and Pyright `--pythonpath .venv/bin/python` on studio_profile.py and test_byteplus.py, zero errors/warnings.
- pass: repository-configured Gitleaks hook on an isolated snapshot of scoped source/tests/docs; paired requirement/task/acceptance identifiers, relative links and diff whitespace.
- not_run: live cloud startup and chat; user will restart Studio and submit a new request. No cloud resource, task record or service was changed. No commit/push requested, so synchronization and all-files pre-commit remain not_run.
Final review: only two BytePlus application flags changed in production code. Domestic and platform APM flags retain their values; no retry bypass, frontend artifact, dependency or general-agent changes. AC-1/AC-2/AC-3 satisfied by local evidence; live deployment remains unverified.
