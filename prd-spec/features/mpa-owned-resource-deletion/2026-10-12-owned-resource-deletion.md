# MPA owned-resource deletion

[中文版](2026-10-12-owned-resource-deletion.zh.md)

Change ID: `mpa-owned-resource-deletion`. Date: 2026-10-12. Status: implemented.
Contracts: [Studio MPA](../../../specs/studio-mpa-control-plane/README.md), [provisioning](../../../specs/mpa-runtime-provisioning/README.md).

## Evidence and scope
MPA delete preview queries Profile before sessions. A Profile authentication failure prevents confirmation; the detail page hides the sidebar containing the error. The current delete handler cleans sessions and Runtime only. Managed deployment records already persist worker/Skill Space IDs and ownership flags, with matching cloud ownership tags.

## Goals, scenarios, and requirements
- FR-1: General Runtime deletion remains unchanged. MPA deletion must not query Profile. Active lifecycle operations and active sessions still block deletion; failed operations are terminal and do not block by themselves. Session-query failures remain errors, never zero-session success.
- FR-2: Delete only managed, exclusively owned worker templates and Skill Spaces. Verify the deployment Runtime binding, managed flags, account/region/project, ownership tags, and absence of other deployment/Runtime references. Preserve shared, imported, or unproven resources and explain preservation in preview. Discovery/ownership conflicts fail safely.
- FR-3: Cleanup order is idle sessions, worker template, Skill Space, Runtime. Persist resource cleanup intent/completion under the existing account/region advisory lock. Missing resources during cleanup support retry; other errors preserve Runtime for retry. Keep database, Workspace, network, APIG, identity, storage and all unrelated data.
- FR-4: Open confirmation immediately with a loading state. Surface preview/execution errors inside the dialog and allow preview retry. Cancel/unmount aborts preview; late responses cannot reopen or overwrite dialogs. Confirmation revalidates server-side authorization, sessions and resource ownership.

## Design and affected files
Use the authorized Runtime's server-side registry URL and current provider credentials; do not resolve creation configuration or provision new prerequisites. Add a managed deletion service and resource-plan callback to the existing preview route. Runtime/Tool/Skills SDK calls respect provider and region. Missing registry URL/record preserves associated resources. A registered deployment mismatch blocks cleanup. Record deletion state so provisioning cannot recreate resources while cleanup is pending or complete. Extend preview additively with retained resources and resource IDs; `profile` stays null for compatibility. The existing confirmation component is the UI baseline.
Affected: managed deletion/database/cloud helpers; Studio BFF and cli_frontend; AgentWorkspace/client/i18n; focused Python and React tests; release assets; bilingual component contracts and frontend README.

## Tasks and acceptance
| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1 remove Profile dependence | AC-1 no Profile calls; general unchanged; active work protected | BFF and Studio RBAC regressions |
| FR-2/FR-3 | T-2 owned cleanup | AC-2 exclusive resources removed; shared/unproven resources preserved; partial retry safe | Offline managed deletion tests |
| FR-4 | T-3 visible states | AC-3 loading/error/retry/cancel/late events work | React tests and browser fixture |
| All | T-4 reconcile and verify | AC-4 localized release build and required checks | frontend test/build, targeted pytest, Ruff, Pyright, i18n/assets |

## Risks and boundaries
External actors can change references outside the advisory lock; perform fresh cloud reads immediately before cleanup. Cloud APIs may reject deletion while references exist; propagate this failure and retain Runtime rather than report success. Session visibility remains limited to the authenticated Runtime API; no global-session claim. Removing Profile lookup does not bypass session authentication. Live deletion of user resources is not part of verification; use isolated mocks/browser fixtures. Existing independent provisioning/operation stores do not provide a cross-system transaction.

## Review and approval
Direct design review performed because review-spec skill is unavailable: checked ownership, provider isolation, partial failure, concurrency, secrets, compatibility, bilingual equivalence and tests. User explicitly approved this approach on 2026-10-12. No unresolved design blockers. Commit/push/deployment are not authorized by design approval.

## Verification record
Scope: local changes on d6065d6e, 2026-10-12; no commit or push.

- pass: reproduced failures first (missing cleanup module, Profile dependency, invisible dialog errors), then implemented; offline and React cases for AC-1 through AC-3 pass.
- pass: `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/frontend/server/mpa/test_runtime_profile_client.py tests/cli/test_studio_rbac.py`: 1004 passed, using 2 workers.
- pass: subsequent ownership review, provider SDK requests and changed references: complete resource-cleanup file 17 passed; final focused deletion selection 21 passed. Covers ordering, shared retention, imported/legacy resources, ownership conflicts, discovery failure, partial retries, NotFound, cancellation intent, domestic/international requests, forged client IDs and resource preview plans.
- pass: `npm --prefix frontend test`: 1379 Node + 78 Vitest = 1457 passed; `npm --prefix frontend run build`, `check:i18n`, `test:webui-assets` (113 files, 350 references), and `git diff --check`.
- pass: real-browser isolated simulated verification: error, preview retry, cleanup failure, successful retry, loading, Escape cancellation/focus return, ignored late results, original general confirmation and 390×844 layout. No live cloud resources are changed by the fixture.
- pass: Ruff 0.11.12 matching `.pre-commit-config.yaml`, via `uvx --from ruff==0.11.12 ruff check --config pyproject.toml <changed-python-files>`; new/affected managed modules have 0 Pyright errors; `uvx pre-commit run gitleaks --files <changed-files>` passes.
- fail (existing baseline): `uvx pyright --pythonpath .venv/bin/python frontend/server/mpa/routes.py veadk/cli/cli_frontend.py` reports 49 pre-existing diagnostics; comparison with the two HEAD files shows no added diagnostic. Historical cleanup is outside scope.
- not_run: live cloud deletion (user resources are not verification fixtures); all repository Python tests (all managed MPA and affected Studio authorization/control-plane tests selected); full pre-commit (no commit requested).
- not_applicable: native IME (no text inputs changed). Ruff/Pyright were unavailable locally; temporary tools were used without global configuration changes. AC-4 release assets, documentation and targeted checks are complete, with the verified existing full-file Pyright limitation retained.

Remaining boundaries: removing Profile does not bypass session authentication; session API failure still blocks deletion and shows its cause. Live cloud cleanup is unverified. External reference edits do not honor registry locks; cloud deletion and registry writes cannot provide a cross-system transaction.

## Session identity correction (2026-10-12)

User verification found `x-user-id header is required` (HTTP 422) in preview. Session transport previously sent only Bearer authorization and omitted caller identity. Within approved FR-1/FR-4 scope, session listing/cleanup in preview and execution must forward Studio's server-authenticated `owner_id`, matching chat/scheduled-task identity; browser-supplied `x-user-id` is not trusted. Add optional `user_id` to Runtime client methods, preserving existing calls without it and general deletion. Review covers identity, compatibility and error propagation; add client header and BFF/execution anti-spoofing regressions. Verification: reproduced 2 failing regressions before fixing; 22 focused deletion cases pass; `uv run --extra dev pytest -n 2 -q tests/frontend/server/mpa tests/cli/test_studio_rbac.py` reports 242 passed. Ruff, Runtime client Pyright (0 errors), Gitleaks and diff whitespace pass. General deletion does not enter MPA session calls. Live cloud deletion: not_run; no frontend code changed in this correction, so the matching assets do not require rebuilding.

## Preview latency correction (2026-10-12)

User verification remained in checking state; the current Studio root returned HTTP 200 in 0.003 seconds, confirming responsiveness. Verified code bottlenecks are sequential Runtime detail reads and repeated STS verification on each SDK call; step logs have not yet established the slowest call in this specific request. Within approved FR-2/FR-4, preserve complete reference checks and batch detail reads with at most 4 concurrent requests. Only deletion contexts opt into request-local identity caching for unchanged credentials; credential rotation re-verifies identity and account changes remain rejected. Creation retains per-call verification by default. Limit the whole preview to 25 seconds (before the frontend 30-second deadline), returning structured `mpa_delete_preview_timeout` (HTTP 504) for retry; offload the preview’s synchronous authorization read to avoid blocking the event loop. Add timeout, concurrency, default compatibility, credential rotation/account-change regressions and directly review boundaries and bilingual equivalence. Live resource deletion remains outside verification. Verification (2026-10-12, local diff on d6065d6e): pass — `uv run --extra dev pytest -q tests/integrations/mpa_managed/test_deletion.py tests/frontend/server/mpa/test_runtime_profile_routes.py tests/integrations/mpa_managed/test_runtime_deployment_edges.py tests/integrations/mpa_managed/test_byteplus.py` (106 passed); `uv run --extra dev pytest -q tests/cli/test_studio_rbac.py -k 'delete'` (7 passed). Python 3.10 timeout cancellation is covered. Pass — pinned Ruff; `uvx pyright --pythonpath .venv/bin/python` on runtime/deletion (0 errors); Gitleaks; diff whitespace. Full routes/CLI Pyright: fail with the same 49 baseline errors, 0 added diagnostics. Not applicable — frontend rebuild/browser fixture rerun, since this correction changes no frontend source or payload shape. Not run — live cloud deletion, measured live preview timing after restart, all-repository tests and full pre-commit (no commit requested). Existing browser state/error/retry verification remains applicable. Cancellation cannot terminate an already-running synchronous SDK thread; such preview work is read-only and no deletion is performed by preview.
