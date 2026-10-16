# MPA Creation Local Task Recovery

[中文版](2026-10-15-local-task-recovery.zh.md)

## Metadata

- Change ID: `mpa-creation-local-state`
- Created: 2026-10-15
- Revised: 2026-10-15
- Status: approved
- Related component spec: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and Evidence

Studio MPA creation already persists per-owner task state in a local SQLite database. However, the frontend mainly restores progress from browser `sessionStorage`. After refresh or storage loss, the dialog cannot discover the latest local task by owner and region. Local MPA operation recovery may also be unavailable when Studio TOS storage is not configured.

The `wlc-ap-test` BytePlus run also showed an intent mismatch after the operator changed TOS configuration between retries. The server removed `tosBucket` from the stored task payload but passed it to the child process, while Worker hashing included the resulting TOS mount configuration. That allowed the task layer to treat the request as unchanged even though the Worker intent changed, causing a late `configuration_changed` failure.

After the AIDAP retry fix, the same task reached the Worker stage repeatedly and BytePlus rejected `create_worker` with `InvalidParameter.TosEndpoint`. Retries with the legacy `https://tos-ap-southeast-1.bytepluses.com`, host-only `tos-ap-southeast-1.bytepluses.com`, omitted endpoint, and AgentKit-style `http://tos-ap-southeast-1.bytepluses.com` shapes failed, including request IDs `2026101511483686035D67AE3B4A1C41A8`, `20261015115339C02052F0ED43FE23806D`, `2026101512015520E30384A95D0B0B510C`, and `202610151214245AE8256781CAFD0F5F45`. This shows BytePlus Tool creation currently does not accept the Tool-level TOS mount configuration. Agent creation must therefore degrade by creating the Worker without a Tool TOS mount while preserving the rest of the MPA resources.

## Goals and Non-Goals

Goals:

- Add an owner-scoped local task listing endpoint for refresh recovery.
- Let the frontend recover the latest submitted task from the server when `sessionStorage` is absent or stale.
- Persist nonsecret `tosBucket` as part of task identity so changed TOS configuration is rejected early.
- Include the latest safe diagnostic summary in recovered task payloads.
- Retry transient AIDAP read/query failures with bounded backoff while preserving create idempotency safety.
- Try the AgentKit Tool mount endpoint shape `http://tos-ap-southeast-1.bytepluses.com` for BytePlus IAM role mounts, but automatically degrade to Worker creation without Tool-level TOS mount when BytePlus rejects `TosEndpoint`.
- Keep degraded retries idempotent and clear Runtime TOS mount environment flags so the Runtime does not assume a mount that was not created.

Non-goals:

- Change domestic Volcengine Worker TOS mount serialization.
- Persist TOS access keys or secrets.
- Replace the durable production MPA operation service.
- Add a full recovery console in this change.
- Retry `CreateWorkspace`, which lacks an idempotency token.

## Requirements

- `FR-1`: Given a submitted task exists in the local SQLite database, when the dialog opens after refresh without browser recovery state, then it can recover and poll the latest task for the current owner and region.
- `FR-2`: Given the same `requestId` is submitted with a different `tosBucket`, then the server rejects it at task admission instead of reaching Worker hash validation.
- `FR-3`: Given a task has diagnostics, then the latest diagnostic is returned as safe structured metadata and contains no raw provider text or credentials.
- `FR-4`: Given the task is passed to the child process, then nonsecret `tosBucket` still reaches the TOS configuration path and no TOS secret is persisted.
- `FR-5`: Given a read-only AIDAP call such as branch, compute, endpoint, account, database, connection, list or detail fails with a transient provider error, then the create flow retries with bounded backoff and records the exact safe AIDAP operation.
- `FR-6`: Given `CreateWorkspace` fails, then it is not automatically retried because the cloud API lacks a client idempotency token.
- `FR-7`: Given BytePlus Worker creation uses an IAM role TOS mount, then the first create payload uses `MountPoints[].Endpoint=http://tos-ap-southeast-1.bytepluses.com`, and unfinished legacy intents hashed with omitted endpoint, `tos-ap-southeast-1.bytepluses.com`, or `https://tos-ap-southeast-1.bytepluses.com` are upgraded instead of being rejected as changed inputs.
- `FR-8`: Given BytePlus rejects Worker creation with `InvalidParameter.TosEndpoint`, then the same creation flow records a safe diagnostic and retries Worker creation without `TosMountConfig`, with a new client token and a persisted degradation marker.
- `FR-9`: Given Worker TOS mount is degraded, then Runtime deployment does not set `MPA_CODEX_WORKER_TOS_MOUNT_ENABLED` or `MPA_CODEX_WORKER_TOS_BUCKET`.

## Design and Contract Impact

`CreationTasks` will expose an owner-scoped `list()` method returning recent tasks. `GET /web/mpa-creation/tasks?region=...` will call it and return `{tasks:[...]}`. Each task keeps the existing task shape and may add `latestDiagnostic`.

The task payload will keep `tosBucket` when present. The child input will still receive a separate `tos` object, and `_run()` will not forward `tosBucket` through unrelated resource fields. This makes the existing duplicate request comparison catch TOS changes before child startup.

Frontend `MpaCreateDialog` will call the list endpoint when no submitted task is already restored from session storage, then attach to the most recent submitted task for the region. Browser storage remains an optimization, not the only source of truth.

Component spec impact: this is an additive HTTP endpoint and a stricter request identity check. Existing task query endpoints remain unchanged.

AIDAP read calls use up to eight total attempts with bounded exponential backoff. Retryable categories are `connection`, `timeout`, `throttled`, and `unavailable`. Permission, authentication, invalid parameter, ownership/configuration, missing resource and protocol-shape failures fail closed. `create_workspace` remains single-attempt to avoid duplicate resources.

BytePlus Worker TOS mount serialization rewrites `MountPoints[].Endpoint` from the domestic AgentKit default to `http://tos-ap-southeast-1.bytepluses.com` before hashing and cloud submission. The Worker retry path recognizes unfinished legacy hashes that omitted the endpoint, included the original HTTPS BytePlus endpoint, or included the later host-only endpoint, then upgrades the stored hash to the HTTP endpoint request.

If the provider still returns `InvalidParameter.TosEndpoint`, the Worker provisioner records `worker_tos_mount_disabled=true` with a safe reason, switches to a request without `TosMountConfig`, rotates the client token to avoid idempotency conflicts across changed payloads, and retries `create_worker`. `provision()` rereads the registry record after Worker creation and reapplies Runtime TOS env from the actual Worker state so degraded workers do not advertise an unavailable mount.

## Tasks

- `T-1`: Add `CreationTasks.list()` with latest diagnostic summary.
- `T-2`: Add `GET /web/mpa-creation/tasks`.
- `T-3`: Keep `tosBucket` in task payload while still passing `tos` to the child.
- `T-4`: Add frontend client and dialog recovery logic.
- `T-5`: Add backend and focused frontend tests.
- `T-6`: Add AIDAP read retry diagnostics and tests while keeping Workspace creation single-attempt.
- `T-7`: Adjust BytePlus Worker TOS mount serialization and legacy hash recovery.
- `T-8`: Add BytePlus Worker TOS mount degradation and Runtime env reconciliation.

## Verification and Acceptance

| Requirement | Task | Acceptance criterion | Test or verification command | Result/evidence |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-2`, `T-4`, `T-5` | Refresh recovery can discover a submitted task without session storage | `uv run --extra dev pytest tests/integrations/mpa_managed/test_tasks.py tests/integrations/mpa_managed/test_routes.py -q`; `npm --prefix frontend test -- mpaCreation.test.tsx --runInBand` | `pass`, backend 34 passed and frontend 1389 Node tests plus 117 Vitest tests passed on 2026-10-15 |
| `FR-2` | `T-3`, `T-5` | Changed `tosBucket` for the same request is rejected at admission | Same backend pytest command | `pass`, backend 34 passed on 2026-10-15 |
| `FR-3` | `T-1`, `T-5` | Latest diagnostic is safe and structured | Same backend pytest command | `pass`, backend 34 passed on 2026-10-15 |
| `FR-4` | `T-3`, `T-5` | Child receives TOS selection and secrets stay out of persistence | Same backend pytest command | `pass`, backend 34 passed on 2026-10-15 |
| `FR-5` | `T-6` | Transient AIDAP read failures retry and report the concrete AIDAP operation | `uv run --extra dev pytest tests/integrations/mpa_managed/test_auto_pg.py tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_tasks.py tests/integrations/mpa_managed/test_routes.py -q`; `uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_auto_pg.py::test_sdk_read_calls_tolerate_repeated_cross_region_failures -q` | `pass`, 129 passed plus focused repeated-failure coverage on 2026-10-15 |
| `FR-6` | `T-6` | `CreateWorkspace` failures do not retry automatically | Same AIDAP/PG pytest command | `pass`, 129 passed on 2026-10-15 |
| `FR-7` | `T-7` | BytePlus Worker create uses the HTTP TOS Endpoint and legacy endpoint hashes resume | `uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_byteplus.py::test_byteplus_worker_mount_and_environment_are_overseas tests/integrations/mpa_managed/test_byteplus.py::test_byteplus_worker_recovers_legacy_tos_endpoint -q` | `pass`, covered by focused 6-test run on 2026-10-15 |
| `FR-8` | `T-8` | BytePlus `InvalidParameter.TosEndpoint` falls back to Worker creation without Tool TOS mount | `uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_byteplus.py::test_byteplus_worker_tos_endpoint_failure_falls_back_without_mount -q` | `pass`, covered by focused 6-test run on 2026-10-15 |
| `FR-9` | `T-8` | Runtime TOS env is cleared when Worker mount is degraded | `uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_service.py::test_tos_runtime_env_is_owned_and_contains_no_credentials -q` | `pass`, covered by focused 6-test run on 2026-10-15 |

## Risks

- Local SQLite remains instance-local; it is suitable for local Studio and single-instance deployments, not cross-instance production recovery.
- Listing recent tasks must stay owner-scoped to avoid exposing another user's drafts or cloud resource names.

## Review and Delivery Record

Design review conclusion: the change is a narrow reliability fix over existing local task storage. It avoids new cloud side effects and makes TOS changes fail earlier.

Implementation completed on 2026-10-15. Targeted backend tests, focused frontend tests, AIDAP/PG retry tests, BytePlus Worker TOS endpoint/degradation regression tests, Ruff, i18n check, frontend build and `git diff --check` passed. The frontend build emitted existing chunk-size and mixed dynamic/static import warnings.
