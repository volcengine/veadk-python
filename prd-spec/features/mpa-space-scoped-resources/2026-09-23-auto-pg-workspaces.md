# Automatic management and business PG Workspaces

[中文版](2026-09-23-auto-pg-workspaces.zh.md)

Date: 2026-09-23. Status: approved for implementation by the user's request to implement the preceding automatic-PG flow. Owner: [Studio creation contract](../../../specs/studio-mpa-creation/README.md). Supersedes manual preparation as the recommended path in the [two-Workspace design](2026-09-23-two-pg-workspaces.md); retain manual profiles and explicit migration compatibility.

## Intent and evidence

Use refreshed VeADK deployment credentials, verified with STS, to prepare one `mpa_admin_workspace/mpa_admin_db` plus one business Workspace (default `mpa_business_workspace`) per account/region/project. Each MPA still owns an independently named business database. The installed `volcenginesdkaidap.AIDAPApi` exposes CreateWorkspace, DescribeWorkspaces/WorkspaceDetail/Branches/Computes/WorkspaceEndpoint/DBAccounts/Databases/DBAccountConnection, matching ArkClaw's inspected source. SDK request fields have no ClientToken; never assume creation retries are idempotent.

## Requirements and design

1. `managed.postgres.mode: auto` needs no PG URL/user/password; optional Workspace IDs allow explicit adoption. Legacy/manual profiles keep working. Engine version defaults to PostgreSQL_17; project defaults to default. Business Workspace name can be configured. Config API reports auto mode without cloud calls or credentials; the PG wizard step becomes explanatory, with no editable host/port. OpenViking remains step three. Supplied PG fields are rejected in auto mode; unsubmitted browser drafts clear them, submitted tasks preserve their original payload and fail safely if configuration changes.
2. AIDAP adapter uses SDK signing with current deployment credentials on every request, checks account consistency, and sanitizes provider failures. List all pages with bounded/repeated-page validation. Wait for explicit ready states with cancellation and stage deadlines; reject terminal/unknown statuses, ambiguous branches/compute/accounts/endpoints and incomplete credentials. SQL connections stay server-side/in memory and are injected into the requested Runtime only.
3. Before any PG registry exists, persist nonsecret creation intent, scope/config digest and Workspace IDs in private SQLite (`.adk/mpa-pg-bootstrap.sqlite3`, configurable path). Serialize per account/region/project using an OS file lock, including separate Studio/CLI processes sharing that path. Persist intent before create and ID before readiness waits. Lost create responses reconcile exact names and scope/purpose tags; no second create after an uncertain result, missing previously recorded resource, or ownership/config conflict. Independent deployment hosts must share a coordinator/state location; this release does not claim distributed-lock support.
4. Find/reuse the unique matching Workspace in the verified account/region/project; validate name, engine and scope, and reject conflicting purpose tags. Explicit IDs are validated independently. New resources get stable ownership tags. Prepare management first, then business, derive management DB URL and initialize `mpa_admin_db` using the existing safe SQL initializer. Keep business DB names and account/region APIG sharing unchanged. Do not create one Workspace per MPA. Adopting existing business data requires an explicit business Workspace ID; check the legacy business endpoint before switching.
5. Existing registry endpoints must not silently switch to an empty management DB. Automatic provisioning rejects any configured legacy shared URL by default. An explicit `managed.postgres.legacy-urls: ignore` selection makes new creations start from fresh admin and business Workspaces without reading either old PG URL; existing agents and databases remain untouched and are not imported. The alternative `init-admin-db --source-url-env ...` path copies existing registry records using the stopped-writer migration contract. No automatic live migration, deletion, public-access changes, password resets or paid-cloud test executions in this coding task.
6. New safe stages report management Workspace, business Workspace and management DB initialization. Maintenance credentials never reach the browser/task database/log output. Runtime settings inherited from a reference are overridden with the resolved business connection. Shared Workspace IDs remain bound in agent deployment records.

## Tasks and acceptance

- T1: configuration, API contract and wizard; test auto/manual modes, no PG secrets required, optional adoption, draft/submission compatibility and localization.
- T2: SDK adapter and connection resolution; test request/account refresh, pagination, readiness, selection and redaction.
- T3: durable bootstrap and SQL integration; test reuse for two agents, concurrency, cancellation, uncertain create, missing IDs, mismatched scope, legacy migration guard and unchanged business identity.
- T4: service/CLI integration, bilingual docs, generated assets; run managed Python/CLI tests, Ruff/Pyright, frontend tests/build/i18n/assets and browser checks. Full regression may reuse earlier baseline evidence if only known dependency failures recur. Live cloud/SQL verification remains explicitly not_run without an isolated authorized target.

## Review and risks

Direct review (review-spec unavailable): user-approved topology is preserved; auto mode is explicit to avoid unexpectedly allocating resources for old configs. SDK credentials replace hand-filled PG credentials, not database authentication. Missing service access/CREATEDB/network connectivity remains a failure. File locks protect one shared state directory, not multiple independent hosts. Pending work survives process termination through persisted intent. Cloud calls run with request deadlines; late responses cannot cause a blind retry. No unresolved design blocker for offline implementation; actual provider readiness values, account privileges and endpoint reachability require live verification. No commit/push/deployment authorized.

## Verification and delivery record — 2026-09-23

Scope: branch `feat/from-main-20260922`, working diff over `821f0f36`, including the already uncommitted three-step wizard and manual two-Workspace work. T1–T4 are implemented. The local private profile was backed up and switched to auto mode; the local Studio process was restarted. Deployment credentials were used for read-only STS/AIDAP checks only. No cloud Workspace creation, live SQL migration, Runtime rollout, commit or push occurred.

| Check | Status | Evidence |
| --- | --- | --- |
| Managed Python and provisioning integration | pass | `UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py -q`: 344 passed. Covers SDK request shape, refreshed credentials, discovery, tags/ownership, idempotent retries, cancellation, timeout, explicit legacy-URL ignore, default migration guard, service and CLI integration. |
| CLI regression | pass | `UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/cli/test_cli_mpa.py tests/cli/test_cli_mpa_control.py -q`: 41 passed with local mock-server binding allowed. |
| Static and type checks | blocked | Python compilation and `git diff --check` pass. Ruff and Pyright were clean before the latest config field/test change; rerun is blocked because those executables are absent locally and Ruff is unavailable from the offline cache. |
| Frontend tests and release assets | pass | `npm --prefix frontend test`: 1305 Node + 36 Vitest passed. `npm --prefix frontend run build`, `check:i18n`, `test:webui-assets`: pass; 104 packaged files and 248 internal references validated. |
| Browser | pass | Isolated localhost mock: automatic PG explanation and link, three-step navigation/keyboard, progress stage, cancellation/retry, configuration error, loading and narrow 390px layout observed. No provider calls. |
| Local profile and Studio endpoint | pass | The private YAML is in auto mode with explicit `legacy-urls: ignore`. After restarting Studio, `/web/mpa-creation/config` reports `postgresMode=auto`, empty PG host, `configured=true`, and no migration flag. Existing registry records are left untouched. |
| Live AIDAP/PG and migration | not_run | Read-only STS/AIDAP discovery succeeded; the configured admin and business Workspace names do not yet exist in the deployment account. Workspace allocation and registry/Runtime cutover require a separate coordinated procedure and were not run. |
| Full Python non-smoke regression | not_run | Earlier related uncommitted scope had baseline failures from absent optional dependencies and local-port sandboxing; all affected managed and CLI suites above pass. No new shared SDK dependency or core runtime contract was changed. |

Remaining operator work: verify AIDAP IAM, endpoint reachability and Workspace creation with a controlled new-agent run. The local profile deliberately starts fresh, so old registry records and old business databases are not visible to new creation tasks; existing agents retain their original connections. Keep the bootstrap state file durable on one coordinator host. Manual mode and explicit migration remain available for installations choosing preservation.

## Main-history alignment and pre-PR verification — 2026-09-23

The user approved preserving the current feature changes on a clean branch from rewritten `origin/main`. Created `feat/mpa-pg-workspaces` at `c7b23a9b` and explicitly ran `git pull --ff-only origin main`; the old `feat/from-main-20260922` remains at `821f0f36`. No old commits were merged into the rewritten history. This operation does not change a component contract.

Before switching, a private local archive recorded all 125 existing files and 62 deletions, including ignored local configuration. All entries matched byte-for-byte after switching. After rebuilding, source and local configuration still matched the archive; the only additional edits are this bilingual verification record and correction of the two readiness-design contract links. Ignored configuration and the backup are not part of the PR. No cloud resource or running service was changed by the branch operation.

Verification scope: the preserved feature diff on `c7b23a9b`, after alignment.

| Check | Status | Evidence |
| --- | --- | --- |
| Targeted Python | pass | `uv run --offline --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/cli/test_mpa_a2a_url.py tests/cli/test_frontend_runtime_proxy.py tests/scripts/test_scan_yaml_secrets.py -q`: 470 passed, 5 warnings. |
| Frontend | pass | `npm --prefix frontend test`: 1305 Node tests and 36 Vitest tests passed. Production build, `check:i18n`, and `test:webui-assets` passed; 104 packaged files and 248 references verified. |
| Commit hooks | pass | `uv run --offline --extra dev pre-commit run --all-files` and `pre-commit run --files <all existing changed paths>` passed Ruff, formatting, Gitleaks and YAML secret scanning. The latter includes untracked new files. Hooks did not alter Python sources. |
| Types | partial | Pyright passed on 23 focused changed Python files. Full-file checks of the other three existing CLI/proxy files report 57 previously recorded diagnostics; this alignment preserves those files exactly and does not claim all-file type success. |
| Preservation | pass | File hashes/deletions verified against the private archive; `git diff --check` passed. The rewritten main history is the branch base. |
| Browser/cloud rerun | not_run | Branch alignment changes no UI or runtime behavior; previously recorded browser/cloud evidence remains historical. No new live deployment or chat was performed during this verification. |
| Full non-smoke Python regression | fail (environment) | `uv run --offline --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 5137 passed, 6 failed, 11 skipped, 2 xfailed and 2 collection errors. All six failures require missing `llama_index`; the two collection errors require missing `anthropic`. These match the earlier dependency limitations; no full-green claim. |
