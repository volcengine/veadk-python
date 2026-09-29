# Registry-owned MPA network bootstrap

[中文版](2026-09-28-registry-owned-network.zh.md)

- Change ID: `mpa-shared-network-bootstrap`
- Created/revised: 2026-09-28
- Status: implemented
- Contract: [Studio creation CON-1/2/8/13](../../../specs/studio-mpa-creation/README.md)

## Background and scope

`studio_profile.py` pins an existing VPC, subnet and APIG. Although
`AccountNetworkProvisioner` and `SharedAPIGService` already persist shared
resources, Studio adopts these fixed resources even when the management registry
is empty. The user requests that creation reuse registered resources or create
and persist missing resources in `mpa_admin_workspace/mpa_admin_db`.

Goals: make the built-in Studio entry point use that existing bootstrap path.
Non-goals: network migration, deleting/resetting existing records or resources,
quota increases, changing sharing scope, Runtime retry recovery, database
permissions redesign, or changes to generic-agent chat/UI.

## Requirements and design

- FR-1: Remove the built-in VPC/subnet/APIG IDs. Keep the existing account,
  region, images, model and credential requirements. Explicit CLI adoption is
  unchanged.
- FR-2: After automatic PG preparation, use its resolved management URL for
  `mpa_account_network`, `mpa_account_apig`, and deployment records. Share by
  verified account and region. Empty registry: create VPC/subnet, then APIG and
  IM Gateway, persist identities, then create the agent's dependent resources.
- FR-3: Existing registry: validate and reuse the registered network and gateway.
  A partial preparation resumes using durable intent and known resource IDs.
  Permission errors, unavailable resources, quota failures and uncertain creates
  are not treated as missing records or successful creation.
- FR-4: Retain account locks and pre-dispatch persistence. Concurrent callers
  must not duplicate resources; cancellation/timeout retains recorded resources.
  No cloud resource deletion or registry rewrite occurs during this change.

Use the existing provisioners, schemas and locks rather than adding another
resource registry or new selector. No HTTP/schema/frontend asset change is
required. Existing records (including an exhausted VPC) continue to be reused;
changing them requires a separately scoped migration. Automatic APIG creation
retains the existing Serverless request; APIG quotas and private database
connectivity remain deployment prerequisites.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1 remove fixed resource defaults | AC-1 built-in profile has no adopted IDs | configuration regression fails before fix |
| FR-2/3 | T-2 exercise Studio profile through service with simulated PG/cloud | AC-2 shared records use admin DB; first call creates, next reuses | service regression |
| FR-3/4 | T-3 run recovery/concurrency tests | AC-3 uncertain creates and failures do not cause duplicate resources | network/gateway/PG suites |
| FR-1–4 | T-4 reconcile docs and review | AC-4 bilingual contract and operator guidance match | links, whitespace, Ruff/Pyright, managed regression |

Affected files: `studio_profile.py`, managed config/service tests, Studio creation
spec pair, managed README pair, and `frontend/README.md` operator notes.

## Review and approval

The user's 2026-09-28 instruction explicitly approves registry-first reuse and
creation of missing shared VPC/APIG resources. It supersedes the earlier proposal
to move all new agents to a separate network. No additional approval is inferred
for editing live records or deleting resources. `review-spec` is unavailable;
direct design review checked scope, source-of-truth, compatibility, errors,
concurrency, security, testability and bilingual equivalence. No design blocker:
existing provisioners implement FR-2–4; the defect is the built-in selection.

## Verification record

Scope: working diff based on `79acf209`, 2026-09-28.

- `pass`: test-first reproduction: the new configuration assertion and four
  service scenarios failed with the old pinned resource IDs before the fix.
- `pass`: `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py -q --tb=short`
  — 414 passed, five dependency deprecation warnings.
- `pass`: after test lint cleanup,
  `uv run --extra dev pytest tests/integrations/mpa_managed/test_studio_shared_resources.py -q`
  — four passed.
- `pass`: changed-Python-file Ruff and Pyright. Bare `uv run ruff`/`uv run pyright`
  were unavailable; `uv run --with ruff --with pyright <tool> <changed-python-files>`
  used an isolated tool environment. Pyright: zero errors/warnings. Initial
  uv-cache sandbox access required an approved escalation. No global settings or
  project dependencies were changed; the user requested recording this here only.
- `pass`: `uv run --with pre-commit pre-commit run --files <changed-files>`:
  repository-pinned Ruff check/format passed. The gitleaks staged hook passed but
  does not cover unstaged files; a separate redacted directory scan covers all
  changed/new files. YAML hook: `not_applicable`, no YAML changes.
- `pass`: `git diff --check`, new relative links and paired requirement/task/acceptance
  IDs. Direct final review found no blocking code or bilingual inconsistency.
- `not_run`: live cloud smoke and real PostgreSQL integration. All new scenarios
  simulate cloud/PG boundaries; they do not prove live permissions, quotas or
  connectivity. No live registry/resource was changed.
- `not_applicable`: browser/frontend build, no UI or HTTP shape changes. Full
  repository regression omitted in favor of the affected 414-test suite: the
  production change only removes built-in resource selection defaults.

T-1–4 and AC-1–4 are complete for the local code change. Existing registry entries
remain authoritative; restart local Studio or redeploy cloud Studio to load the
new defaults. No commit, push or deployment was performed.

## PR #17 rebase reconciliation — 2026-10-07

User authorized conflict resolution against `origin/main` (`e0448a4d`). Direct review preserves main's Workload Identity initialization, Worker metadata waiting, MPA-first A2A discovery and `DISABLE_JWT_AUTH=true`, alongside this branch's registry selection, Worker naming and typed-event deduplication. No new production contract is introduced. Documentation retains both contributions; Worker test imports retain `_missing_worker_metadata`. The unrelated 512-line lockfile deletion is removed to preserve main's dependency records.

The first offline combined regression produced 686 passes and four failures: the shared-resource fake cloud returns no credentials, while main now invokes `ensure_workload_identity`. Adapt this test boundary using an `AsyncMock` that returns distinct agent-derived workload identities, and assert initialization plus Runtime environment propagation. Keep production Identity initialization intact and retain all network/PG assertions. This is test-fixture compatibility within the approved rebase scope; real cloud operations remain excluded. Verification results follow after rerun.

### Reconciliation results

Scope: the rebased PR #17 diff on `e0448a4d`, 2026-10-07.
- `pass`: `uv run --extra dev pytest -n 2 tests/integrations/mpa_managed tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py tests/cli/test_cli_mpa.py tests/cli/test_cli_mpa_control.py tests/cli/test_mpa_a2a_url.py tests/integrations/test_mpa_provision_env.py -q` — 690 tests, 14 dependency deprecation warnings; two workers used. The four previously failing fixture cases pass after adapting the Identity boundary.
- `pass`: `node --test frontend/tests/mpaResponseGrouping.test.mjs frontend/tests/mpaContentPreservation.test.mjs frontend/tests/mpaSessionProtocol.test.mjs frontend/tests/runSseAbort.test.mjs` — 71 tests.
- `pass`: `uv run --extra dev pre-commit run --all-files`; changed Python files pass Pyright with zero errors/warnings; the adjusted fixture additionally passes Ruff/Pyright.
- `pass`: all Worker test functions from both sides are retained (13 combined); the three original production patches are unchanged relative to their respective bases; main's discovery/authentication and lockfile match exactly. Paired documents/relative links and diff whitespace checked.
- `not_run`: full-repository regression, real cloud/browser smoke and deployment. This is conflict reconciliation with a test-only dependency adapter; targeted provisioning/proxy/protocol suites establish the affected compatibility. No frontend source/generated assets or cloud resources changed.
