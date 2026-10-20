# Inject a deployment-account APM AppKey into BytePlus Studio Runtimes

[中文版](2026-10-14-server-app-key.zh.md)

Change ID: mpa-byteplus-server-app-key. Date: 2026-10-14. Status: implemented.
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-17.
Predecessor: [APM restoration](2026-10-14-restore-application-apm.md).

## Evidence, goals and non-goals

Runtime Agent initialization fails when its bundled VeADK GetAppKey call times out. A read-only probe of apmplus-server.ap-southeast-1.byteplusapi.com using the deployment account succeeded. Bundled VeADK 1.1.5 supports OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY and skips automatic lookup when present; this was verified against installed source in isolation. No real key or production log is recorded here.

Goal: Studio obtains the BytePlus AppKey before resource preparation and injects it into Runtime Envs. Restore the inherited enabled APM defaults as previously requested, replacing the temporary bypass. Non-goals: changing the image, global VeADK host selection, domestic/generic-agent/CLI behavior, OTLP endpoint selection, sandbox credential compatibility, existing cloud resources or network retry recovery.

## Requirements and scenarios

- FR-1: After verifying the deployment account and resolving the model key, Studio BytePlus creation calls GetAppKey with service apmplus_server, version 2024-07-30, signing region ap-southeast-1 and host apmplus-server.ap-southeast-1.byteplusapi.com. Refresh and verify credentials for each attempt; include STS token and X-Apmplus-Region. Resolve before IAM/PG/network/resource mutations. Domestic and non-Studio callers do not call this helper.
- FR-2: Accept only a usable data.app_key string; inject OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY into Runtime creation/update Envs. Do not mutate the caller profile or persist the raw key in task/bootstrap/deployment records, browser responses, diagnostics or reports. Valid trusted explicit Runtime keys are preserved; blank values use discovery; malformed/masked keys fail safely.
- FR-3: At most three transient read attempts with 10/30-second HTTP connect/read limits and a 45-second per-attempt async deadline; retry delays 0.2/0.5 seconds. Cancellation prevents later attempts or mutations. Permission, protocol and permanent provider failures stop without fallback. Diagnostics retain only allowlisted operation/category/attempt/outcome/errorCode/requestId, including HTTP error metadata. Fail before resource preparation with a safe exception.
- FR-4: Restore BytePlus ApmplusEnable=true, ENABLE_APMPLUS=true and FORCE_APMPLUS_EXPORTER_REGISTRATION=true; preserve domestic values, explicit configuration and provider isolation. No submitted snapshot upgrade or existing Runtime update. Reads on retries obtain the account key again; unchanged pending request hashes remain authoritative and changed keys/configurations fail rather than silently redeploying.

## Design and tasks

T-1: Add failing isolated helper and service regressions: signed request fields, Runtime environment delivery, trusted configuration reuse, exclusion of domestic and CLI paths, malformed responses, errors/retries/cancellation and pre-mutation failure. Update enabled-default regression (FR-1 through FR-4).
T-2: Add a small managed apm_key module, reuse signed transport and existing diagnostic metadata validators, allowlist get_apm_key and wire service.provision. Hold the fetched key only in a local variable until Runtime environment construction. Existing request/hash and secret storage rules remain unchanged.
T-3: Update bilingual CON-17, managed README and frontend README; record review and checks. Run targeted and managed/startup regression with two workers, changed-Python Ruff/Pyright, configured scoped Gitleaks, paired identifiers/links and whitespace checks.

## Review, security, risks and acceptance

User approval: explicit 2026-10-14 request to implement the described server-side key retrieval/injection; earlier request withdrew the APM bypass. Direct review (review-spec unavailable): provider scope, credential refresh, safe failure diagnostics, secret persistence, bounded cancellation, compatibility and bilingual equivalence reviewed; no blockers. Runtime environment access remains privileged. Deployment credentials additionally need apmplus_server:GetAppKey; no Runtime role policy expansion or long-lived deployment AK/SK injection. Platform rewriting of disabled APM flags motivated restoring the enabled defaults.

AC-1: Only Studio BytePlus looks up the key before mutations and the actual Runtime payload contains it. AC-2: Safe failure/cancellation and secret exclusions pass regression. AC-3: Domestic/generic/CLI paths and pending-input guards remain unchanged; checks and docs reconciled. Real APM export and Runtime startup/chat are separate live tests. The known BytePlus sandbox IAM defect is not fixed here. Old incomplete deployments may need a new request because their original payload lacks this environment variable.

## Verification

2026-10-14, local diff based on 2ffe6e14: not_run, implementation checks pending. not_run, live creation/update/restart/commit/push and all-files pre-commit, none authorized for this implementation. not_applicable, frontend/browser/build and harness smoke, no affected UI/API/event boundaries or artifacts. Preserve unrelated local changes.

2026-10-14 final verification (local diff on 2ffe6e14):
- pass: pre-implementation helper regression failed collection because the module was absent; the first implementation run also exposed the missing diagnostic operation/service wiring, which was completed before final tests.
- pass: `uv run --extra dev pytest -q tests/integrations/mpa_managed/test_apm_key.py tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_service.py`, 213 tests. Four additional isolation/invalid-explicit-key cases subsequently passed with the final 23-test helper suite.
- pass: `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`, 1,112 tests, two dependency deprecation warnings; two workers selected for local resources. Subsequent edits only added tests/docs, with targeted rerun.
- pass: Ruff 0.11.12 check/format and Pyright `--pythonpath .venv/bin/python` on apm_key.py, service.py, diagnostics.py, test_apm_key.py and test_service.py, zero errors/warnings. An initial test double's undeclared account_id assignment was corrected with monkeypatch; test_service formatting was corrected.
- pass: `uv build --wheel --out-dir /tmp/mpa-app-key-wheel`; archive contains the new helper and wired service, excludes .env. No new frontend build or dependency changes.
- blocked: live read-only new-helper smoke could not start because Studio no longer listened on port 8000 and its process credentials were unavailable. The earlier dedicated-host GetAppKey probe succeeded, but was not this new helper. No Runtime/resource update occurred. Live injection, startup, tracing and chat remain not_run.
- pass: final scoped repository-configured Gitleaks, bilingual IDs/links and diff whitespace (recorded after execution below).
Final review: Runtime handoff is verified in the existing full fake provisioner, and its result/registry contain no raw AppKey. Global SDK GetAppKey host selection and Runtime/sandbox IAM clients are unchanged. All in-scope tasks and local acceptance checks complete; existing cloud deployments remain unchanged. No commit/push/service restart.

Final documentation checks: pass, scoped relative links and paired identifiers. An unrelated pre-existing frontend README link to an optional local skill example is absent and was not changed. An initial Gitleaks scan flagged a documentation phrase; prose was reworded and the unchanged repository-configured scan passed. No exclusions were added.
