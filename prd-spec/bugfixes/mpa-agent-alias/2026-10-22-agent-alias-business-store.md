# Registered Agent aliases in the MPA business database

[中文版](2026-10-22-agent-alias-business-store.zh.md)

- Change ID: agent-alias-business-store
- Date: 2026-10-22
- Status: implemented
- Approval: user explicitly approved business-database aliases, removal of the alias dependency on AGENTKIT_ACCOUNT_ID, and synchronized changes in VeADK and agentkit-mpa-agent.
- Supersedes the account-shared storage decision in the 2026-10-22 space-aliases design.

## Background and evidence

The current Runtime alias provider opens SHARED_APIG_DATABASE_URL and requires AGENTKIT_ACCOUNT_ID, although the alias belongs to a registered Agent under a space in the current MPA. Studio consequently disables editing when account identity is absent. Its proxy also rejects alias PUT requests before forwarding them. Space bindings already use the durable MPA business engine; reuse that engine.

## Goals and non-goals

Persist registered Agent aliases in the business database; use the same data for management, discovery and exact @name resolution. Correct Studio labels and allow the existing alias update route through its authenticated proxy. Ordinary Agent behavior, center registration names, Agent Cards, cloud configuration and dispatch/Harness authority are outside this change. No new dependency, cloud write, deployment, automatic shared-data import or destructive schema change.

## Scenarios and requirements

- FR-1: With no account ID or shared database configured, saving and clearing an Agent alias succeeds using the durable business engine. A restart retains its value and revision.
- FR-2: Scope is (mpa_id, region, space_id, agent_id). Normalized alias uniqueness is within (mpa_id, region, space_id). Different MPAs/spaces/regions do not share aliases, even on one engine.
- FR-3: List, discovery and @name resolution use that same scope. Existing NFKC normalization, 80-character limit, casefold uniqueness, revision CAS, tombstones and live membership/dispatch checks remain. Storage errors fail closed without fallback to the account database.
- FR-4: Studio says Agent alias and explains the current MPA/space scope. Legacy Runtime capability absence remains disabled with an upgrade message. PUT is allowed only for the existing binding route and the exact alias route with a valid a-* ID; existing ownership/admin authentication remains enforced.

## Design and contract impact

Runtime A2AAliasStore reuses A2ASpaceStore.engine, never creates or disposes a separate engine. Add business table mpa_a2a_registration_aliases with mpa_id VARCHAR(256), region VARCHAR(64), space_id/agent_id VARCHAR(128) as primary key; alias VARCHAR(80), alias_key VARCHAR(240), revision INTEGER NOT NULL; unique (mpa_id, region, space_id, alias_key). Add migration 0016; preserve published migrations. Lazy initialization uses the existing advisory lock on PostgreSQL. Never alter or read the old mpa_a2a_agent_aliases table; users must re-enter previously shared aliases to avoid copying data into the wrong MPA. Rollback retains additive tables and restores the old binary; no deletion is needed.

The service owns one alias store over its business engine. Management list/save receive the current MPA identity from the server dependency, never from the request body. Region is derived from Runtime settings. External API paths, bodies and response fields remain compatible. A failed business-store operation remains an explicit error; no empty success or fallback. Management may edit accessible spaces while dispatch still requires the selected binding. Existing cancellation, finite resolution timeout, binding recheck and live registry verification remain intact.

VeADK only updates localized guidance, documents, proxy allowlist and matching built assets. No ordinary Agent deployment/configuration change. Reuse the existing alias editor and primitive controls without visual redesign. Update the maintained collaborating-Agent contracts in both repositories and both VeADK languages.

## Tasks and affected files

- T-1 / FR-1–3: failing Runtime store/service/route regressions, isolation/restart/conflict/error and PostgreSQL migration tests.
- T-2 / FR-1–3: app/stores/a2a_alias.py, app/services/a2a_space.py, app/api/v1/collaborating_agents.py and additive app/migrations/0016_a2a_registration_aliases.sql.
- T-3 / FR-4: proxy regression, veadk/cli/cli_frontend.py, frontend locale guidance, existing editor tests and generated web assets.
- T-4: reconcile contracts, user documentation and verification evidence; review security, compatibility, resource ownership and bilingual equivalence.

## Verification and acceptance

AC-1 (FR-1/T-1–2): no shared configuration required; business-store persistence survives a new service/connection. AC-2 (FR-2/T-1–2): MPA/region/space isolation, uniqueness, CAS and clearing work on SQLite and disposable PostgreSQL. AC-3 (FR-3/T-1–2): management save/list, discovery and exact mention lookup agree; inaccessible membership and database errors cannot dispatch. AC-4 (FR-4/T-3): actual Studio proxy forwards alias PUT with server credentials, preserves upstream conflicts and rejects unrelated PUT/unauthorized writes; UI no longer requests shared-account setup.

Commands and actual results are recorded below after execution. Runtime: targeted pytest, make lint, full make test, governance/project-skills/project-tooling checks, isolated PostgreSQL migration/store contracts. VeADK: targeted uv run --extra dev pytest, Ruff/Pyright on changed Python, npm --prefix frontend test, npm --prefix frontend run build, i18n/assets checks and real browser fixture normal/error/keyboard/IME/cancel/narrow states. No real cloud calls; local fixtures are not deployment evidence.

## Risks and review

Aliases formerly saved in the shared database are deliberately not imported. Upgrade both Studio and Runtime to activate the complete route/storage change. Business-store failure blocks alias-dependent operations. Existing database engine lifecycle belongs to the channel store and must not be disposed by alias code. No external side-effect authority changes. Direct design review performed because review-spec is unavailable: ownership, scope, failure semantics, API compatibility, additive rollback, tests and paired-language consistency reviewed; no design blockers. User approval above covers this correction.

## Delivery record

2026-10-22, uncommitted implementation over Runtime 0d3dd35 and VeADK 46f60e12:

- pass: RED before implementation reproduced 3 Runtime failures, 6 alias proxy rejections and 2 locale failures; corresponding regressions are now green.
- pass: final isolated PostgreSQL/Runtime targeted command covering tests/test_a2a_aliases.py, tests/test_a2a_business_aliases.py, tests/test_a2a_business_alias_migration.py, tests/test_a2a_rebase_migration.py, tests/test_a2a_registry_collaborators.py, tests/test_a2a_management_routes.py and tests/test_schema_migration_contracts.py — 54 passed, no skips. Disposable PostgreSQL 16 verified fresh/v15 and all v14 migration lineages, repeated initialization, cross-connection conflicts and preservation of the old shared table. Container removed afterwards.
- pass: PATH=/tmp/a2a-codex-0155/node_modules/.bin:$PATH make test — 10823 passed, 386 skipped in 634.22 seconds. Before/after source fingerprint 5a56a035892b8a93396e4d82a69df257965e39da64f9d02ec8c13c5748db7694 matched. Skips are not proof of live integrations. An earlier interrupted run was invalidated by source drift and is excluded.
- pass: make lint; Ruff on changed Runtime files; Pyright on the three changed Runtime implementation files — 0 errors. A previously implicit pagination total is initialized explicitly without changing lookup behavior.
- pass: make governance-check BASE_SHA=HEAD HEAD_SHA=HEAD (current worktree correction; contract check plus 14 tests), make project-skills-check. Default origin/master comparison includes multiple historical change IDs and cannot select one; no gate code or validation was bypassed.
- fail: make project-tooling-check — pre-existing missing OpenViking CLI/skills. User declined separate environment documentation; global configuration was not changed. Full release qualification is not claimed.
- pass: uv run --extra dev pytest -q tests/cli/test_frontend_runtime_proxy.py — 142 passed. Broader uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/cli — 1844 passed, 6 skipped (2 workers).
- pass: npm --prefix frontend test — 1389 Node tests and 236 Vitest tests; npm --prefix frontend run build; npm --prefix frontend run check:i18n (2 locales/23 namespaces); npm --prefix frontend run test:webui-assets (114 files/351 references). Build regenerated matching hashed assets and removed obsolete hashes.
- pass: real browser fixture using the actual alias editor, Studio tokens/CSS and actual Runtime HTTP routes with a fake cloud registry and disposable SQLite business database: Chinese save, page reload/read-back, clear, CAS conflict and refresh, Escape cancel, unsupported Runtime message, and a 360-pixel container. Synthetic IME, request cancellation/unmount and duplicate-submit tests passed; a native IME and resized browser window were not separately exercised. Temporary fixture files, servers and database were removed.
- pass: VeADK Ruff hooks, pre-commit --all-files (including secret scan); Pyright compared current files against HEAD with the same interpreter: 57 existing diagnostics, 0 added. Raw Pyright is therefore fail on the baseline; no unrelated type fixes were included. Repo dependencies do not install a standalone Ruff command, so the pinned repository pre-commit hooks supplied it.
- pass: paired-language requirement/identifier/relative-link and diff-whitespace checks. Final edits after the full Runtime run change documentation and its ignore exception only; implementation/tests remain as tested.
- not_run: real cloud/model smoke, deployment, image publication, commit and push — outside this authorized correction. No Tool/MCP declaration/adapter changes, so the path-triggered MCP tool gate is not applicable. Full coverage/release gates were not run for this local code delivery.

AC-1–4 and T-1–4 are satisfied for local behavior. Code/security/test/architecture review found no remaining blocker in this correction: business engine lifecycle stays with its original owner, scope is server-derived, store failures fail closed, migration is additive, and proxy authorization remains intact. Old shared aliases require re-entry. Upgrade Studio and Runtime together; no cloud account-ID patch is needed. Complete release qualification still has the tooling/baseline static limitations listed above. No commit, push, image publication or deployment performed.

Additional secret-scan evidence: default Gitleaks over all changed files (17.70 MB) flagged one minified vendor expression a minified member-access expression; manual source inspection confirmed an identifier expression, not a credential. VeADK scan using its existing .gitleaks.toml (1.02 MB of included source) and the Runtime default scan (456.14 KB) both found zero leaks. No scanner rule or allowlist was changed.

2026-10-22 follow-up authorization: user authorized committing/pushing VeADK only and tracking PR CI. Fetched official main and fork branch, then rebased official main (already current at cb9975df). The lockfile only lost 27 optional build-tool records; backed up and restored without changing dependencies. Staged scanning flagged the quoted minified vendor expression in these documents; removed that example without changing scanner rules. The Runtime repository is not committed in this follow-up.

CI preparation: static inspection found missing Apache headers in five existing PR files. Added license comments only to frontend/server/a2a_center.py, frontend/server/mpa_images.py, tests/cli/test_a2a_center_actions.py, tests/cli/test_a2a_center_registration.py and tests/cli/test_mpa_images.py. No runtime or contract change; this comment-only correction requires no recursive PRD.

Final pre-commit validation (2026-10-22): after synchronization with cb9975df, all pre-commit hooks passed; frontend 1389 Node + 236 Vitest tests, build, i18n and 114-file/351-reference checks passed; dependency policy and uv lock --check passed. Running the CI Sidecar script produced 143 passed/1 skipped (96% coverage, threshold 91%), 9 passed/50 deselected, 97 passed and 39 passed across its four backend groups; frontend Sidecar 22 passed, 100% line/94.44% branch coverage. Pyright on the five license-only files reported zero errors; all 30 PR Python files have required headers. Default Python regression (2 workers): 7861 passed, 53 skipped, 4 xfailed, 1 failed in 474.00 seconds. The sole failure remains tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes; an independent archive of unchanged HEAD 46f60e12 fails identically in this environment. Local Python 3.10 returns None for the .md MIME lookup; unrelated artifact behavior was not modified. Commit/push are authorized in this follow-up. GitHub CI must be assessed on the new remote revision; older runs are action_required and are not passes.
