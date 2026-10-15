# BytePlus Studio MPA OTLP endpoint

[中文版](2026-10-15-otlp-endpoint.zh.md)

## Metadata and evidence
Change ID: mpa-byteplus-otlp-endpoint. Date: 2026-10-15. Status: implemented.
The SDK default uses the domestic volces.com suffix even for overseas regions. The operator supplied the BytePlus Singapore collector address. AppKey retrieval alone does not select this collector.

## Scope and requirements
FR-1: New BytePlus Studio profiles inject `OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT=http://apmplus-ap-southeast-1.bytepluses.com:4317` into Runtime Envs.
FR-2: Volcengine profiles, generic agents, global SDK defaults, AppKey retrieval and APM enablement remain unchanged. Existing Runtime resources and submitted task snapshots are not migrated.
FR-3: Existing trusted Runtime environment override precedence remains unchanged.
Given a new BytePlus request, its generated Runtime payload carries the endpoint. Given a domestic request, no overseas endpoint is added.

## Design and tasks
T-1: Extend provider isolation regression to fail on the missing endpoint, checking raw defaults, loaded profiles and Runtime payloads, including explicit override behavior.
T-2: Add the constant value only to the BytePlus branch of `veadk/integrations/mpa/managed/studio_profile.py`.
T-3: Reconcile Studio creation CON-17 and managed README in both languages; run targeted tests, Ruff, Pyright and whitespace/link checks.
Related contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-17. Affected test: `tests/integrations/mpa_managed/test_byteplus.py`.
No new API, schema, credentials, network calls, timeout, cancellation or concurrency behavior. Existing environment-to-payload handling is reused. Only the default collector configuration changes.

## Review and acceptance
User approval: explicit request on 2026-10-15 to inject the supplied endpoint for BytePlus creation without changing domestic behavior. Direct design review performed because review-spec is unavailable: provider boundary, override precedence, retry snapshots, security, compatibility and bilingual equivalence checked; no blockers.
AC-1: BytePlus default and resulting payload contain the endpoint. AC-2: Domestic default/payload omit it and explicit overrides survive. AC-3: scoped checks pass with live verification separately stated.
Risk: actual collector reachability and accepted traces require cloud validation. Existing deployments need a separately authorized update; restart Studio for new requests. This change does not itself prove successful APM export.

## Verification
2026-10-15, local change on 4997196d, only Studio profile, provider regression and paired documentation:
- pass: regression before implementation reproduced BytePlus KeyError while domestic passed.
- pass: `uv run --extra dev pytest -q tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_apm_key.py tests/integrations/mpa_managed/test_service.py` — 219 tests, two dependency deprecation warnings.
- pass: `uv tool run --from ruff==0.11.12 ruff check` and `ruff format --check` on the two changed Python files; `uv tool run pyright --pythonpath .venv/bin/python` on those files — zero errors/warnings. Temporary tools used because local Ruff/Pyright executables are absent, following the existing user preference to record verification only.
- pass: `git diff --check`. Paired requirement IDs and relative links checked.
- not_applicable: frontend build/browser and harness smoke; no UI, API or harness code changed.
- not_run: live cloud deployment/export verification and all-files pre-commit; no deployment or commit requested. Scoped hooks checked separately below.
Review: the domestic branch returns before the new environment entry; no shared SDK change or secret added. Existing unrelated frontend lockfile changes preserved. AC-1/AC-2 covered by generated-payload tests; live Trace delivery remains unverified.


- pass: `uv run --extra dev pre-commit run --files <eight changed files>` — Ruff check/format and hardcoded-secret scan passed; dependency/YAML hooks skipped because their file types are unaffected.
