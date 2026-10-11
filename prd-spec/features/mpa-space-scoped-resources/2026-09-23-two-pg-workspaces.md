# Separate management and business PostgreSQL Workspaces

[中文版](2026-09-23-two-pg-workspaces.zh.md)

- Change ID: `mpa-two-pg-workspaces`; date: 2026-09-23; status: implemented; live database cutover pending operator setup.
- User decision: shared records move to `mpa_admin_workspace/mpa_admin_db`; all agent business databases stay together in a different Workspace with database-level isolation. This supersedes the earlier [per-agent Workspace proposal](2026-09-23-space-scoped-manual-pg.md). Workspace creation remains an operator prerequisite, as requested previously.
- Owner: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).

## Evidence, goals and boundaries

`Profile.admin_url` already supplies business database administration while `Profile.shared_url` supplies network/APIG/deployment registries and Runtime bootstrap. Current profiles can accidentally point both at one Workspace. Moving only the connection to an empty registry would lose reuse/ownership records. Existing business databases and Runtime PG identity must remain stable.

The target contains one management Workspace named `mpa_admin_workspace`, one management database named `mpa_admin_db` with the existing three registry tables, and one separate business Workspace containing `mpa_agent_<hash>` databases. Account/region network and APIG scope is preserved. Generic agents, per-agent Workspace creation, Space catalog/selection, automatic cloud Workspace creation, business-data migration, credential removal from the existing Runtime bootstrap contract, and automatic live cutover/deletion are outside this change.

## Requirements and design

- FR-1: Optional `managed.postgres` opts into the two-Workspace layout. It requires distinct nonempty `admin-workspace-id` and `business-workspace-id`; `admin-workspace-name` is fixed to `mpa_admin_workspace`. `SHARED_APIG_DATABASE_URL` must address `mpa_admin_db` on a different host from the business administrator URL. IDs and host ownership are operator assertions verified in the AIDAP console, not a claim of cloud API validation. Different hostnames alone do not prove different Workspaces. Legacy profiles without the section retain compatibility.
- FR-2: `admin-database-url-env` in that section names a separate maintenance connection for preparing the management database. It must target the same host/port as the shared registry connection. Normal creation never creates an empty management database automatically. Explicit `veadk mpa init-admin-db --config ...` creates/reuses `mpa_admin_db`, checks the configured registry owner, and initializes the known registry tables. A pre-existing database must belong to that owner and contain only the known public tables. SQL identifiers are quoted; output contains no URL or password. The maintenance credential never enters Runtime or browser payloads.
- FR-3: The command optionally accepts `--source-url-env OLD_SHARED_APIG_DATABASE_URL` to copy the three existing registry tables while retaining the source. Operators stop creation and registry writers for the whole migration/cutover window. The source is read-only, table locks bound concurrent writes, the destination transaction copies all records or none, and a rerun accepts identical records but rejects conflicting or extra target rows. Copy preserves JSON records, owner hashes, agent IDs, network/APIG IDs and database identity. Lock/statement and overall timeouts are bounded; cancellation closes connections. Cloud changes and Runtime rollouts remain explicit operational steps.
- FR-4: New creation uses only the business connection for `mpa_agent_<hash>` and only the management connection for registry/bootstrap. Record the two configured Workspace IDs on new or verified legacy deployment records. Reject changing a recorded Workspace binding before cloud resource mutation; reject a changed business host on an existing record. Fresh creation and same-ID retry preserve current database naming, ownership and cleanup rules.
- FR-5: Studio config returns safe layout/name metadata. The PG step explains that it configures the shared business Workspace and creates an independent database for this MPA; the management Workspace is server-configured. Preserve old clients and draft/task recovery. Both languages and example YAML agree.

## Tasks, acceptance and verification

Review refinement: migration rejects source deployment records with `pending=true`. Their persisted Runtime request hash includes the old registry URL; operators must finish/reconcile them under the original configuration before copying. This preserves idempotent recovery rather than silently rewriting hashes.

| Task | Requirements | Acceptance |
| --- | --- | --- |
| T-1 | FR-1 | AC-1: reject same IDs/host, wrong management database and maintenance target; legacy configuration still loads. |
| T-2 | FR-2–3 | AC-2: offline tests cover initialization, missing/foreign tables, copy/retry/conflict/rollback/timeouts; source is never modified. |
| T-3 | FR-4 | AC-3: two agents retain distinct database names on the same business host and receive the same management connection; changed binding fails early. |
| T-4 | FR-5 | AC-4: localized dialog/API tests, browser check, frontend build and generated assets; paired operator instructions show migration and recovery. |

Files: managed config/service and new admin database module; CLI registration/module; Studio dialog/types/locales; managed tests, paired component specs/operator guide/example YAML. Run targeted `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`, changed-file Ruff/Pyright, frontend tests/build/i18n/assets, then the two-worker non-smoke Python regression when feasible. No live resource or private-profile modification is part of these tests.

## Review, risks and delivery record

### Implementation review and verification, 2026-09-23

Scope: base `821f0f36`, branch `feat/from-main-20260922`, uncommitted working diff including the existing three-step creation work. No commit, push, private profile update, cloud Workspace creation, live data copy or Runtime rollout was performed. T-1–T-4 are implemented; AC-1–AC-3 have offline regression coverage, and AC-4 has frontend/browser/build coverage. Database transactions/locks are tested with isolated simulations, not a real PostgreSQL server.

| Check | Status | Evidence |
| --- | --- | --- |
| Targeted Python | pass | `UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q`; 317 passed. Includes separate hosts, copy conflict rollback, cancellation/error cleanup, CLI redaction, two agents sharing business host with distinct databases, and safe config API. |
| Frontend | pass | `npm --prefix frontend test`: 1305 Node tests and 33 Vitest tests; separate `npm --prefix frontend exec -- vitest run frontend/tests/mpaCreation.test.tsx`: 16 passed. |
| Build/localization/assets | pass | `npm --prefix frontend run build`, `check:i18n`, `test:webui-assets`; 2 locales/21 namespaces and 104 packaged files/248 internal references checked. |
| Browser | pass | Actual dialog with mock config API: Chinese and English management/business explanation, AIDAP link, normal navigation and 390 px iframe viewport checked. No cloud submission. Loading/error/cancel/retry coverage comes from automated tests, not a new live resource run. Temporary preview files/server removed. |
| Ruff | pass | Changed Python files checked and formatted using the cached pre-commit Ruff executable; the project dev extra does not install a standalone `ruff` command. |
| Pyright, feature code/tests | pass | Cached Pyright with `--pythonpath .venv/bin/python` over config/service/new database and CLI modules and changed managed tests: no errors. |
| Pyright, CLI registration file | fail (pre-existing) | `cli_mpa.py` has a 3-or-5 tuple return/unpack mismatch in legacy VeFaaS deployment. Reproduced against `git show HEAD:veadk/cli/cli_mpa.py`; the new registration adds no error. |
| Full two-worker Python regression | fail (environment) | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 4980 passed, 76 failed, 11 skipped, 2 xfailed, 5 errors. Failed-node retry with local-port permission: 73 passed, 6 failed, 2 collection errors. Remaining Harness/self-host failures require missing `llama_index`/`anthropic`; those files are unchanged. These results are not a full-green regression claim. |
| Live SQL/cloud cutover | not_run | New management Workspace/credentials and a stopped-writer migration window are not configured. No claim of live lock, ownership, connectivity or existing Runtime verification. |
| Pre-commit full repository | not_run | No commit requested. Required before any later commit after branch synchronization. |

Direct review confirmed unchanged table keys and business database derivation, management maintenance credential exclusion from Runtime, no overwrite/delete migration, all-table destination rollback, fixed timeout limits, cancellation propagation, and no URL/password in normal output. The caller must coordinate a single registry endpoint for all consumers. Existing database grants are retained; Workspace separation alone does not provide stronger isolation between the business databases.

Direct design review replaces unavailable `review-spec`: user approved the two-Workspace topology; previous unanswered per-agent Workspace and Space-selector questions are superseded. Preserve wire/table compatibility with the existing MPA image, retain source registry for rollback, and require maintenance credentials only for the explicit initialization command. Existing Runtime instances retain their previous shared URL until an authorized rollout; therefore operators must coordinate their migration before restoring registry writers. No automatic rollback to the old registry after new writes: reconcile records first. Unknown cloud account/Workspace ownership is not inferred from endpoint labels. Status of implementation/tests/live checks: `not_run` at design creation; results will be appended.
