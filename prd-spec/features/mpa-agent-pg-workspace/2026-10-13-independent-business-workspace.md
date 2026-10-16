# Independent business PostgreSQL Workspace per new MPA

[中文版](2026-10-13-independent-business-workspace.zh.md)

- Change ID: `mpa-agent-pg-workspace`
- Created/revised: 2026-10-13
- Status: implemented
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-19
- Predecessor: [shared PG preparation](../mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.md)

## Background and evidence

`managed/pg_bootstrap.py` scopes both Workspaces by verified account, region and project. `service.py` pins their IDs and the business endpoint in each deployment record. Thus independent databases currently share compute and maintenance credentials. `deletion.py` reads the registry connection from the Runtime; it does not require a shared business Workspace. The MPA image consumes its injected PG connection independently of the provisioning layout.

## Goals and non-goals

New Studio MPA requests use one business Workspace per agent while retaining `mpa_admin_workspace/mpa_admin_db` and account/region network/APIG reuse. Existing agents and submitted tasks keep their database bindings. No migration, business-schema initialization, PG deletion, credential redesign, general-agent changes, image change, or cloud mutation belongs to this implementation.

## Scenarios and requirements

- FR-1: Two new agents share management resources but have distinct business Workspaces, endpoints and `mpa_agent_<hash>` databases. Both providers use their existing AIDAP adapter.
- FR-2: Retry, cancellation, uncertain creation and restart reuse the agent-scoped bootstrap identity. Do not blindly repeat uncertain purchases; retain current terminal-failure recovery.
- FR-3: Missing `businessWorkspaceMode` means the old shared request contract. New Studio requests explicitly persist `per-agent`. A submitted draft is never upgraded automatically.
- FR-4: Before a per-agent purchase, inspect existing deployment bindings in the prepared management DB. Registered shared agents retain their shared Workspace; recorded per-agent agents reuse theirs. Conflicts fail closed. Do not migrate, overwrite or delete business data.
- FR-5: Inject only that agent's business credentials into its PG settings; keep shared registry injection unchanged. Retain Workspace IDs and layout in the deployment record without secrets.
- FR-6: Keep the three-step wizard, update the database explanation, preserve manual/shared profiles and all generic-agent flows. Deletion continues retaining business PG resources.

## Design and contract impact

Add `managed.postgres.business-workspace-mode: shared|per-agent`, default `shared`, allowed only with automatic provisioning for public input; reject an explicitly configured business Workspace ID for per-agent mode. Add optional request/config `businessWorkspaceMode`. The built-in Studio configuration advertises `per-agent` as a capability without changing execution defaults for old requests; new forms explicitly submit it. Existing explicit CLI/YAML configuration may opt in.

Pass stable internal `agent_id` to PG preparation. Keep management scope unchanged. Per-agent business scope hashes account/region/project plus agent ID; name is `mpa_agent_<agent_suffix>`, respecting AIDAP name limits. Reuse the bootstrap store, ownership validation, locks and readiness timeout. Prepare management DB first for per-agent mode and read registered binding under the existing registry lock; an old record without a layout marker is shared. Registered identities must match bootstrap state, scope and endpoints. Never infer ownership merely from name or accept conflicting tags. Registry/connection errors stop before purchasing a business Workspace. Management and business preparation remain under the existing bounded account bootstrap lock; no new cross-host lock guarantee is claimed.

The existing business database provisioner receives the new maintenance URL, so database naming, markers and schema ownership remain unchanged. `bind_postgres_workspaces` pins the resolved layout as well as IDs. Runtime/session/skill/Feishu code and sibling `agentkit-mpa-agent` need no changes. Missing `openviking_users` is a separate image/schema issue.

Security: use refreshed provider credentials; never persist PG passwords or model/OV keys in bootstrap, registry, request or docs. Existing Runtime registry credentials are unchanged, not redesigned. PG resources remain billable after cancellation/deletion until separately released by an operator.

## Tasks and affected files

- T-1 / FR-1,2,4: failing fake-cloud tests, `config.py`, `pg_bootstrap.py`, `service.py`, existing PG tests.
- T-2 / FR-3,5: request validation, task forwarding, config capability and frontend types/form tests; retain request fingerprints.
- T-3 / FR-6: locale copy, paired component spec/module docs, generated assets; inspect deletion without changing its scope.
- T-4: targeted/broader Python, Ruff/Pyright, frontend tests/build/i18n/assets, isolated browser checks and bilingual review.

## Acceptance and verification

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| FR-1,2,4,5 | T-1 | AC-1: distinct new business Workspaces; same-agent retry stable; old binding retained; uncertainty never duplicates | `uv run --extra dev pytest tests/integrations/mpa_managed/test_auto_pg.py tests/integrations/mpa_managed/test_service.py` | pass |
| FR-3 | T-2 | AC-2: request mode persists through BFF/task/runner; legacy omission stays shared; resumed form does not upgrade | targeted config/routes/tasks and frontend tests | pass |
| FR-6 | T-3,4 | AC-3: compatible three-step UI, general-agent/deletion regression, synchronized docs/assets | broader managed Python, `npm --prefix frontend test`, build, i18n/assets and browser | pass |

Tested scope: current working diff on `71175c68`, including pre-existing uncommitted OV work; date 2026-10-13. Live allocation: not_run (no isolated cloud creation authorized). Codex process smoke and harness coverage: not_applicable (contracts unchanged). Commit/push/pre-commit synchronization: not_run (not requested).

## Risks and recovery

Additional Workspaces increase cloud resource count and potential minimum compute cost. No migration is performed. Shared admin PG remains a control-plane failure domain. Bootstrap files/locks are local; unknown cross-host creates retain existing fail-closed recovery limitations. Independent Workspaces do not replace MPA business schema initialization. API limits and permissions remain those of the existing PG adapter.

## Review and approval

`review-spec` is unavailable; direct review covered boundaries, retry/cancellation, registered bindings, ownership, secrets, compatibility, testability and paired-language equivalence. No design blockers. User approved one Workspace per new MPA with “那帮我改吧” on 2026-10-13, then requested confirmation of other repository impacts. That approval covers creation/request/binding/UI adaptations; no migration or PG deletion is included. No commit, push or deployment is authorized.

## Final implementation review and verification (2026-10-13)

All T-1 through T-4 and AC-1 through AC-3 are complete for the isolated implementation scope. Reviewed the request-to-runner mapping, registered legacy binding preservation, agent-scoped naming/ownership, metadata uncertainty, timeouts, registry closure and retained PG deletion behavior. No blocking code/contract findings remain.

- Regression-first: 11 new Python cases and the new frontend layout case failed before their respective implementation; final new PG suite has 15 passing tests.
- pass: `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_skill_space.py tests/integrations/test_ve_faas_deploy_image_key_auth.py -q --no-cov` — 951 passed, two workers. The full unrelated SDK suite is not_run; changes are isolated to managed MPA creation.
- pass: `npm --prefix frontend test` — 1,379 Node tests and 81 React tests; `npm --prefix frontend run build`, `npm --prefix frontend run check:i18n`, `npm --prefix frontend run test:webui-assets` (113 files, 350 references).
- pass: pinned Ruff 0.11.12 and Pyright over all 14 changed/new Python files, including preceding OV work. The local environment lacks Ruff/Pyright executables; used `uvx --from ruff==0.11.12 ruff check <files>` and `uvx pyright --pythonpath .venv/bin/python <files>`, no machine-global configuration changes.
- pass: real browser with the actual React dialog and isolated simulated API, new request/legacy request mode, failure and retry, cancellation confirmation, loading/error/empty input states, keyboard Next, 390×844 window and screenshot inspection. Fixture/server/tab removed; no cloud resource created. Existing automated IME/general-agent tests remain passing; no input handlers changed.
- pass: paired-language and relative-link review, `git diff --check`, configured repository Gitleaks over the 94 changed/new files. A separate default-rule scan of generated bundles flagged a minified editor expression (`p.anchor.key`), reviewed as a vendor-code false positive; repository policy already excludes generated vendor bundles. No scan policy or hook was weakened.
- not_run: live AIDAP allocation/Runtime deployment, data migration, commit/push and pre-commit synchronization — not authorized/requested. Generated Runtime PG payloads and both cloud-provider branches were verified offline. Shared control PG and retained Workspace billing are the stated operational limitations.
