# MPA name preflight and readable business Workspace names

[中文版](2026-10-13-runtime-name-and-workspace-labels.zh.md)

- Change ID: `mpa-name-preflight`
- Created/revised: 2026-10-13
- Status: implemented
- Owner contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-20
- Predecessor: [independent business Workspace](../mpa-agent-pg-workspace/2026-10-13-independent-business-workspace.md)

## Background and evidence

The form validates Runtime name characters/length but does not query cloud availability. Service preparation reaches PG/network before `ensure_worker` discovers foreign same-name templates. `RuntimeCloud.list_runtimes` expands every Runtime detail for deletion; reusing it for typing preflight would be unnecessarily expensive. A lightweight paginated name lookup is needed. New per-agent PG names currently use a hash, making console lookup difficult.

[AIDAP CreateWorkspace](https://docs.volcengine.com/docs/87275/2105881) documents names of 2–128 characters, beginning with a letter or Chinese character. Runtime names allow 4–64 ASCII letters, digits, underscores and hyphens. Proposed `mpa_agent_<Runtime name>` is at most 74 characters and safely starts with a letter. New dedicated business databases use `aidb`; existing database names remain pinned.

## Goals, scenarios and requirements

- FR-1: Check the selected deployment provider/account/region before starting a fresh MPA task. A foreign same-name Runtime, worker template or target business Workspace blocks creation with an explicit localized name-conflict message. Do not return cloud credentials or foreign resource details.
- FR-2: The first wizard Next action checks name availability; final POST and provisioning enforce checks independently of the frontend. Query errors fail closed with a retryable check error, not an available/empty result. Pagination, timeout, cancellation, IME and stale-response behavior must be covered.
- FR-3: Same-request retry may reuse its own resources when identity/binding is proven; foreign or ambiguous ownership fails closed. Existing pending/registered resources retain their bindings and names. Current owner authentication and provider selection remain server-owned.
- FR-4: New independent business Workspaces use `mpa_agent_<hand-entered Runtime name>`. The business database is `aidb` for new dedicated requests; existing requests retain their recorded name. Persist/preserve selected Workspace name with bootstrap/registry identity; never rename an existing Workspace or switch a business endpoint during retry. Explicit/manual/shared profiles remain compatible.
- FR-5: Generic-agent creation, shared admin PG/network/APIG, Runtime business schemas, OV provisioning and resource deletion behavior are unchanged.

## Design and contract assessment

Add a Studio-authorized read-only name check and lightweight Runtime pagination that retrieves details only for matching candidates when ownership requires verification. Reuse `WorkerCloud.find` and AIDAP `find`; never use PostgreSQL connection preparation as a read-only preflight because it may change endpoint settings. Check current in-flight local creation requests as well as cloud names and recheck before purchase. Retain platform uniqueness as the final concurrent-creation boundary; a read-then-create check alone cannot provide atomic exclusion across independent Studio hosts. Any additional shared reservation protocol needs a reviewed contract before implementation.

MPA inputs retain existing validation, while prefixed Workspace naming accommodates digit-leading Runtime names. Same-name foreign retained PG resources block automatic reuse after Runtime deletion; explain the conflict rather than silently sharing them. Registered Workspace IDs, ownership tags, endpoint checks and stable internal identity remain authoritative. Existing hashed per-agent Workspaces use the stored bootstrap name or a verified registered name, not a newly derived name. Private secrets remain server-only.

Affected files: managed Runtime/worker lookup consumers, name-check helper, PG bootstrap/config/service and runner error mapping; BFF creation endpoints/tasks, frontend API types/dialog/locales, targeted Python/React tests, bilingual maintained specs/docs and generated WebUI assets. The sibling MPA repository needs no change.

## Tasks and acceptance

- T-1 / FR-1,2,3 / AC-1: write failing tests for foreign collisions, valid ownership retry, pagination, unavailable checks and stale/cancelled UI responses; implement the read-only endpoint and early server enforcement.
- T-2 / FR-4 / AC-2: naming tests for digits/case/64-character names, existing hashed bootstrap/registry bindings, restart and uncertain purchase; use `aidb` only in verified dedicated Workspaces and avoid existing resource rebinding.
- T-3 / FR-5 / AC-3: generic-agent/deletion regression, paired docs/assets and review. No cloud resources created by tests.

Run targeted tests via `uv run --extra dev pytest`, then the existing managed/deployment regression with two workers, Ruff/Pyright for changed Python, `npm --prefix frontend test`, build/i18n/asset checks, and an isolated real browser. No live purchase, commit, push or deployment is authorized. Results are recorded below after implementation.

## Risks and review record

Cloud listing is eventually consistent; preflight cannot guarantee cross-host atomicity. Fail clearly on a late platform name collision. Additional discovery requires the deployment credentials' existing Runtime/tool/AIDAP read permissions. Retained old Workspace names and failed-task resources must not be silently renamed/adopted. `review-spec` is unavailable; direct review has confirmed ownership boundaries and proposed compatibility requirements. User approval is recorded in the amendment below; final implementation review is recorded at delivery. The user requested pre-creation duplicate detection and asked to replace the Workspace hash with the MPA name on 2026-10-13; a concrete scope/naming question has been presented as required by AGENTS.md. Implementation follows the approved amendment below.

## Approved aidb and request compatibility amendment

User approved all three changes with “改成aidb吧 … 这个也一起改了？” on 2026-10-13. Direct design review replaces the unavailable review-spec skill; no design blockers remain. New config/forms explicitly carry `businessDatabaseName: aidb`, requiring `businessWorkspaceMode: per-agent`. Omission preserves the preceding hashed database/Workspace contract and saved request fingerprints. CLI/YAML opt in with `managed.postgres.business-database-name: aidb`. Named Workspaces persist layout in bootstrap intent and name/database choices in registry metadata. Existing two-element bootstrap configurations and old registered hashed names retain their original layout even on a new-form retry.

AIDAP precreates `aidb`. Before marking it as this agent's database, verify dedicated Workspace identity, DB owner, empty non-system/non-extension relations, no prior Runtime/ready binding, and a transaction advisory lock. A mismatched marker, nonempty initial database or missing registered database fails closed. Persist initialization intent before marking; matching markers make retry idempotent. Runtime validation, PGDATABASE, token/meta seeding and readiness all use the same selected database. Shared admin DB remains mpa_admin_db.

The BFF checks names before creating a task and uses a private task name-scope snapshot (verified provider/account/region) to reject same-host concurrent same-name requests in the SQLite transaction; legacy scope-less active requests are conservatively checked within their provider/region. No failed-task reservation blocks later tasks. The runner verifies the snapshotted deployment account before new-layout side effects and checks names again. Read-only checks are bounded and return only availability/error codes. General-agent APIs remain unchanged. Cross-host read/create races still use cloud enforcement and ownership validation; no distributed reservation guarantee is claimed.

Implementation follows this approved scope; actual verification is recorded below. No cloud purchase, commit, push or deployment is authorized.

## Implementation review and verification (2026-10-13)

T-1–T-3 and AC-1–AC-3 are implemented. Direct review confirmed fail-closed ownership checks, database marker/empty-data guards, retry compatibility and provider/account boundaries. New-layout web requests must use the server-derived owner/request identity; a supplied different agent ID is rejected before task acceptance. This prevents claiming another request's partial Workspace by copying its internal ID. Legacy requests retain their existing explicit-ID contract.

Tested scope: the working diff on `71175c68636dc5b951e9804eb292d85402511e68`, including earlier independent PG and automatic OV work already in this workspace. Regression-first checks initially failed (12 Python and 2 React cases); subsequent implementation passes the affected checks. No unrelated user changes were reverted.

| Check | Result | Evidence / limits |
| --- | --- | --- |
| Managed/deployment Python regression | pass | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_skill_space.py tests/integrations/test_ve_faas_deploy_image_key_auth.py -q --no-cov`: 978 passed; two workers selected for local resources. |
| Changed Python static checks | pass | Ruff 0.11.12 and Pyright against `.venv/bin/python`, all changed Python files. Repository-local tools were unavailable; temporary `uvx` tools were used without global installation. |
| Frontend tests | pass | `npm --prefix frontend test`: Node and React suites, including duplicate Next/POST, pending-check cancellation and late-result suppression, existing generic-agent/deletion tests. |
| Frontend build | pass | `npm --prefix frontend run build`; generated WebUI assets synchronized. |
| Localized strings and asset references | pass | `npm --prefix frontend run check:i18n` and `npm --prefix frontend run test:webui-assets`: 2 locales / 21 namespaces and 113 assets / 350 references. |
| Browser flow | pass | Actual React dialog with isolated fake HTTP responses: occupied/free name, unavailable query, late POST conflict with editable name, old shared request recovery, BytePlus manual OV and 390×844 layout. No cloud operation dispatched; temporary fixture/server removed. |
| Secret scanning / diff whitespace | pass | Repository-configured Gitleaks over changed files, redacted output; `git diff --check`. |
| Live cloud creation and real PostgreSQL integration | not_run | Not authorized for this task. Provider purchase, DB claim SQL and readiness still require an isolated live acceptance run. |
| Harness/process smoke gates | not_applicable | No harness/sidecar or process contract changed. |
| Commit / pre-commit gate | not_run | No commit authorized; pre-commit and branch synchronization remain required before a later commit. |

No remaining local review blockers. Cross-host listing/purchase races remain bounded by cloud enforcement and ownership validation; no distributed lock guarantee is claimed. Existing data is not migrated. Restart Studio and start a fresh request to use the new layout.
