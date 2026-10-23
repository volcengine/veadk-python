# A2A space deletion Runtime authentication

[中文版](2026-10-22-runtime-auth.zh.md)

Change ID: mpa-a2a-space-deletion-runtime-auth. Created/revised: 2026-10-22. Status: implemented.
Related: [component](../../../specs/mpa-collaborating-agents/README.md), [preceding feature](../../features/mpa-collaborating-agents/2026-10-22-member-actions.md).

## Evidence, scope and requirements

The new space DELETE reads the target binding through `_runtime_json_request`, which omits `X-MPA-Studio-Key`. The existing dedicated collaborator proxy supplies this server-owned credential; the MPA binding endpoint requires it. An isolated reproduction returned 401 before any cloud call. A read through the existing proxy succeeded. This establishes an implementation defect; the original failed deletion's raw response was not captured.

FR-1: Apply existing `collaborator_management_headers` policy to Runtime JSON requests for collaborator paths. Use the authorized server Runtime key, strip browser-supplied credentials, enforce administrator access and reject missing keys before upstream I/O. Unrelated JSON paths remain unchanged.
FR-2: A 401/403 from the binding preflight returns a bounded `runtime_auth_failed` reason with the same status. The UI states Runtime authentication failed and deletion was not performed. Cloud refusals retain the existing permission message. No raw upstream error is returned for this preflight auth failure, no automatic retry and no cloud operation after any failed preflight.
FR-3: Retain bound/nonempty/identity checks, timeout/uncertainty and cancellation behavior. Do not delete a real space, change cloud IAM, deploy a Runtime, commit or push as part of verification.

## Design and affected files

Reuse `veadk/integrations/mpa/collaborator_proxy.py` from `_runtime_json_request` in `veadk/cli/cli_frontend.py`. No new key parameter, user-supplied header trust, dependency, database state or API route. Scope the new reason to binding reads in `frontend/server/a2a_center.py`. Add the reason to `frontend/src/adk/a2aSpace.ts`, map it in `A2AResourceActions.tsx` and provide equivalent en-US/zh-CN messages. Preserve ModalButton, alert/focus/retry controls and current layout. Update the component spec, frontend README and generated assets. SDK public contracts, generated projects, Runtime/Harness code and dispatch are unaffected.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1: failing real Studio route/MockTransport regression then header fix | AC-1: binding receives server key instead of browser forgery and an empty unbound fixture can reach simulated cloud deletion | tests/cli/test_frontend_runtime_proxy.py |
| FR-2 | T-2: preflight error and UI regressions then reason mapping | AC-2: binding auth refusal makes zero cloud calls; UI shows Runtime failure, remains retryable; cloud 403 retains its message | tests/cli/test_a2a_center_actions.py; frontend/tests/collaboratingAgents.test.tsx |
| FR-3 | T-3: regression, security and delivery review | AC-3: existing checks, authorization, redaction, cancellation and unrelated helper callers remain intact | targeted Python; npm test/build; i18n/assets/tsc; changed Python Ruff/Pyright; browser with mocked APIs; secret scan; git diff --check |

## Risks, review and approval

Shared helper changes must be route-scoped by the existing policy. Broadly adding credentials to unrelated paths is prohibited. A separate cloud IAM refusal may remain after authentication is fixed; it must be reported as such. Unit/mock checks do not prove a live cloud DELETE succeeds. Backend activation requires restarting the current local Studio; this must not interrupt active user work without checking.

The available skill catalog has no review-spec skill. Direct review covered contract ownership, error boundaries, server-owned credentials, compatibility, feasibility, negative cases and bilingual equivalence; no blockers remain. User approved the proposed authentication/error distinction fix with “能修复吗” before production/test edits. Additional endpoint/skill requirements are a separate scope confirmation and are not silently approved by this record.

## Verification record

Tested scope: current uncommitted A2A Center diff on branch feat/from-upstream-main-20261020; baseline HEAD 9ab0ef2d. Date: 2026-10-22. Final checks are recorded in the delivery evidence. No live cloud writes.


## Delivery evidence (2026-10-22)

Implemented the approved scope against the existing uncommitted A2A changes above 9ab0ef2d. Regression-first evidence: 22 selected Python and 8 UI cases failed before implementation. Review resolved stale endpoint selection, safe optional Card projection, browser credential override, and separate read-auth versus cloud-permission failures. No unresolved in-scope findings.

| Check | Result | Evidence / limits |
| --- | --- | --- |
| `uv run --extra dev pytest tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py tests/cli/test_frontend_runtime_proxy.py tests/test_mpa_collaborator_proxy_policy.py -q` | pass | 227 passed (6 warnings); MockTransport exercises actual Studio mounting and the shared helper, including successful simulated deletion and zero cloud calls on binding-auth refusal. |
| `npm --prefix frontend test` | pass | 1389 Node tests and 183 Vitest tests across 11 files, including 36 collaborating-Agent cases. |
| `npm --prefix frontend run build` | pass | Current packaged WebUI rebuilt; existing large-chunk advisory remains. |
| `npm --prefix frontend run check:i18n`; `npm --prefix frontend run test:webui-assets` | pass | 2 locales / 22 namespaces; 114 packaged files / 351 internal references. |
| `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json` | pass | No diagnostics. |
| `uv run --extra dev pre-commit run ruff-check --files ...`; `ruff-format` with the same files | pass | a2a_center.py, test_a2a_center_actions.py, test_frontend_runtime_proxy.py, cli_frontend.py. Formatter changes were reconciled before final tests. |
| Pyright using existing adjacent-repository executable, `--pythonpath .venv/bin/python frontend/server/a2a_center.py tests/cli/test_a2a_center_actions.py` | pass | 0 errors/warnings; no dependency installation or global configuration changes. |
| Whole-file CLI/proxy-test Pyright | fail (baseline) | 37 CLI and 20 existing proxy-test diagnostics. Re-running with only this change's helper block and proxy tests removed produced identical diagnostic-message multisets (57 each), establishing no added diagnostics. Temporary comparison files removed. |
| Browser | pass | Real browser with isolated mocked fetch: endpoint descriptions and full selected URL, mouse and keyboard switching, cancel/focus return, details/skills, 390px iframe and internal scrolling, and actionable preflight-auth alert. Fixtures and Vite process removed. |
| Live local read integration | pass | Current localhost Studio exposes the new endpoint route, serves the matching built app, and returns HTTP 200 for both real source Runtime endpoint reads and both registry detail reads. Observed one Runtime with public/private and another with public only; effective addresses and skills matched the console records. No cloud write performed. |
| Scoped gitleaks with repository config; document links/pairs/IDs; `git diff --check` | pass | No leaked secrets found; existing scanner exclusions retained, no bypass. |
| Full Python regression, commit-time all-files pre-commit, live cloud writes | not_run | Changes are scoped to A2A routes and a path-filtered existing auth policy; affected proxy/API consumers tested. No commit/push authorized, so branch synchronization and commit gates were not invoked. Real cloud deletion/registration is not proven by mocks or read-only checks. |

T-1/T-2/T-3 and AC-1/AC-2/AC-3 completed. Current Studio was restarted externally during the task; this agent did not interrupt it. New backend and built app are active; refreshing the browser loads the new UI. No commit, push or Runtime deployment. Retained all unrelated user changes. Subsequent name investigation used read-only live values and did not alter AgentCard or registration names.
