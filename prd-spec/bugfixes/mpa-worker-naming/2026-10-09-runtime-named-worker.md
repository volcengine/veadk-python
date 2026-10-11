# Use the entered Runtime name for new MPA sandbox templates

[中文版](2026-10-09-runtime-named-worker.zh.md)

- Change ID: `runtime-named-worker`; created/revised: 2026-10-09; status: implemented.
- Contract: [Studio MPA creation CON-3](../../../specs/studio-mpa-creation/README.md).
- Predecessor: [agent-derived worker names](2026-09-28-agent-derived-worker-name.md).

## Background, goals and non-goals

Named Studio creation keeps an automatically generated agent ID separate from the entered Runtime name. `service.provision` forwards the name to Runtime deployment but not to `ensure_worker`, so sandbox templates still display the generated ID with hyphens replaced by underscores. The user withdrew the proposed internal-ID change and requested only matching new template names to the entered name.

Keep internal ID generation, ownership, database/Skill Space/channel bindings, Runtime names, image defaults, directory search and the three-step form unchanged. No cloud renames, task/database edits, credential changes, deployment, commit or push are authorized. Generic agents and existing CLI callers without a name remain unchanged.

## Requirements and scenarios

- FR-1 / AC-1: A fresh named request creates/discovers a Worker with exactly the validated, trimmed Runtime name, including case, hyphens and underscores. The existing 4–64 ASCII-name contract applies; invalid names fail before Worker cloud calls. The [official CreateTool contract](https://docs.volcengine.com/docs/agentkit/CreateTool_-_Creates_tool?lang=zh) supports the same characters and length.
- FR-2 / AC-2: The service passes the name to Worker preparation; `MPA_AGENT_ID`, scoped ownership tags, registry keys and Runtime `ToolId` retain their original identifiers. Legacy calls without a name still use the normalized agent ID.
- FR-3 / AC-3: Existing bound/configured Worker IDs are authoritative and are not renamed. A pending pre-upgrade Worker intent can replay the normalized-ID name or older hashed name only if the entire candidate payload matches its persisted hash, retaining the original ClientToken. All other payload changes fail before discovery/creation.
- FR-4 / AC-4: New pending intents store their selected `worker_name` in the existing deployment JSON. A later different name must not be treated as a legacy fallback. A matching name owned by another agent is still an error; no silent adoption or success.

Given a named fresh request, the template name matches the Runtime name and internal bindings remain stable. Given a lost create response or upgrade, the exact pending payload/token is retried. Given a registered Worker, no discovery/create/rename occurs. Given an unrelated duplicate name or changed image, fail without weakening ownership checks.

## Design, contracts and affected files

Add an optional keyword-only `runtime_name` to `ensure_worker` and forward it from `service.provision`. Validate it with the existing Runtime-name validator and use it directly as new CreateTool `Name`. Existing IDs bypass naming reconciliation. Persist nonsecret `worker_name` with newly saved intents. For old records without that field, compare the complete current payload against the two historical Name variants before permitting fallback; retain the field's absence across retries so repeated lost responses still replay the original name. Names alone never authorize reuse. Existing account locking, retry bounds, timeout/cancellation and metadata verification remain unchanged.

Production files: `managed/worker.py`, `managed/service.py`. Tests: `test_worker.py`, `test_service.py`. Maintain bilingual creation specs and managed README naming sections. No SQL migration, external API/request-body change, new dependency, permission or frontend/build artifact is needed. Public optional-keyword addition preserves existing callers. Search already uses Runtime `name`, so its behavior is unchanged. Human names can collide; existing collision refusal remains required rather than adding unrequested suffixes.

## Tasks, acceptance and verification

1. T-1 / FR-1–FR-4: Add failing regressions for exact names, boundaries, service forwarding, pending replay, changed-name/image refusal, collision refusal and existing-ID reuse.
2. T-2 / FR-1–FR-4: Implement the optional name and full-hash legacy compatibility.
3. T-3: Reconcile both documentation languages; run targeted Worker/service tests, managed/CLI regression, changed-file Ruff/Pyright, pre-commit and whitespace/link checks.

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_service.py -n 2 -q`; `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`; Ruff/Pyright on changed Python files; `uv run --extra dev pre-commit run --all-files`; `git diff --check`. Real cloud creation is not authorized and is reported separately. Frontend/browser/sidecar gates are not applicable because this change touches only managed provisioning, with no UI or sidecar changes.

## Review, approval and risks

The user's final instruction “保持原样吧，但是把沙箱模板的名称也换成手填的就行” approves this bounded scope and supersedes the internal-ID proposal, which made no code changes. `review-spec` is unavailable; direct review checked ownership, hash/token recovery, existing IDs, exact-name constraints, cancellation/timeouts, bilingual equivalence and testability. No design blockers. An existing same-name Tool can reject a new request. Existing tools will still have their previous names; correcting them requires a separately authorized operation. A pending new-name intent requires this code to replay it after rollback.

## Delivery evidence

T-1–T-3 and AC-1–AC-4 are complete. Direct implementation review found and fixed the repeated legacy-retry case before delivery. Existing uncommitted image-discovery rollback is preserved separately; its tests/assets are not attributed to this naming fix. Tested scope: the four changed Python files and affected managed/CLI suites on the uncommitted diff based on `df797f94`, 2026-10-09.

- `pass`: Regression-first new-name tests initially failed in 16 cases; a subsequent repeated legacy-retry regression failed in two cases before its fix.
- `pass`: Targeted Worker/recovery/service checks: 175 tests. Final managed/CLI regression with two workers: 678 tests, including continuous legacy retry and existing-ID reuse.
- `pass`: Ruff 0.11.12 check/format on the four changed Python files; Pyright: zero errors/warnings.
- `pass`: `uv run --extra dev pre-commit run --all-files`, including both secret checks; `git diff --check`; paired-language and local-link checks.
- `not_run`: Full repository Python regression; the affected managed/CLI integration coverage was selected for this bounded provisioning change.
- `not_run`: Real cloud creation/rename; not authorized. Restart the running Studio service to load the change before creating a fresh named request.
- `not_applicable`: Frontend/browser/build, sidecar and runtime-process smoke gates; no UI, generated assets, sidecar or runtime-process change in this fix.

No commit, push, deployment or existing-resource rename was performed.
