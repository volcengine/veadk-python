# A2A member actions, space deletion and explicit registration errors

[中文版](2026-10-22-member-actions.zh.md)

Date: 2026-10-22. ID: mpa-a2a-member-actions. Status: implemented. User approved Studio detail dialogs and deregistration, added space deletion, and reported RuntimeId already exists after registering the same Runtime in Default. Related: [component contract](../../../specs/mpa-collaborating-agents/README.md), [space management](2026-10-22-space-management.md).

## Evidence and requirements

FR-1: Each member has View and Deregister actions. View opens the existing ModalButton/ModalLayout dialog and calls GetA2aAgent with Id and SpaceId. Display only bounded name/status/source/default-version/project and Runtime ID/network/import type fields. Never return original Cards, URLs with credentials, provider Reason or raw response bodies. Validate returned agent and space IDs before display or deletion.

FR-2: Deregister requires a named confirmation explaining removal from this shared space and its effect on discovery/calls while preserving the source Runtime. Authorize Studio management and target Runtime, verify GetA2aAgent identity, then call DeleteA2aAgent with Id. Success refreshes members; it never deletes Runtime or changes binding. No automatic retry on ambiguous outcomes.

FR-3: Add Delete space beside space selection. Confirmation identifies the selected space and irreversible effect. Before DeleteA2aSpace, authorize the target, read its current Runtime binding and reject the bound space (409 space_bound), verify GetA2aSpace identity, and query ListA2aAgents page 1 size 1. Reject nonempty spaces (409 space_not_empty). Never cascade deregistration or auto-unbind. Cloud API owns races and other callers; users must confirm other callers no longer depend on the space. Success refreshes spaces without retaining a deleted local option. Current-MPA binding check does not prove no other MPA uses this shared space.

FR-4: Distinguish explicit cloud refusal from uncertain writes. The current create handler collapses all exceptions into 502. The reported RuntimeId already exists message is an explicit rejection, not timeout evidence. Add an opt-in structured-error mode to the existing signed helper, used only by A2A Center. Map known provider status/code/message signatures to safe reason enums (runtime_already_registered, forbidden, invalid_parameter, not_found, conflict, rate_limited). Never return raw provider messages. Network/5xx/malformed success stay uncertain and require refresh. No automatic retry or workaround registration. Public docs do not establish a universal cross-account/region uniqueness rule; diagnostics apply to this actual Runtime-source rejection.

## Interfaces, concurrency and boundaries

GET/DELETE /web/a2a-agents/{agentId}?targetRuntimeId=...&spaceId=...&region=... provide sanitized detail or {deleted:true}. DELETE /web/a2a-spaces/{spaceId}?targetRuntimeId=...&region=... returns {deleted:true}. Existing admin, region, ID and target authorization apply before cloud effects. Read preflight failures perform no deletion. Result IDs must match the requested target; malformed responses fail closed. Details have explicit loading/error/retry; mutation confirmation shows known rejection or unconfirmed outcome. Closing during submission aborts the browser request, does not claim cloud rollback and locks further mutations until refresh. Runtime/space changes unmount dialogs and abort stale responses. Shared busy state prevents simultaneous create/bind/deregister/delete; independent views remain read-only. Success followed by failed refresh stays a successful mutation with a list error. Reuse existing component tokens/spacing, no dependency or icon additions.

Non-goals: source Runtime deletion, live registration/deletion during verification, automatic moving between spaces, raw Card editing, credential display, provider-wide policy changes, Runtime/Harness changes. Existing callers of the signed helper retain their prior errors because structured mode defaults off. Default Runtime list pagination is not changed.

## Tasks, tests and acceptance

T-1 / AC-1 (FR-1): add failing detail identity/redaction/auth tests and UI modal/loading/retry tests, then implement bounded projections.
T-2 / AC-2 (FR-2): test one explicit unregister write, wrong-space refusal, cancellation, permission denial and post-success refresh; implement confirmation and client.
T-3 / AC-3 (FR-3): test bound/nonempty/malformed checks, zero writes on refusal, exact DeleteA2aSpace payload and stale dialog cleanup; implement deletion.
T-4 / AC-4 (FR-4): test reported duplicate signature and 400/403 vs network/malformed outcomes, preservation of non-A2A helper behavior, and no auto-retry; implement sanitized errors.
T-5 / AC-5: reconcile both document languages, frontend README and assets; run targeted Python API/proxy tests, npm test/build/check:i18n/test:webui-assets, changed-file Ruff/Pyright and tsc, browser mocked normal/error/cancel/narrow cases, scoped secret scan and diff checks. Record actual outcomes below. Do not claim live cloud writes from mocks.

## Review and approval

Direct design review substitutes for unavailable review-spec. User approval: “可以，按这个给我实现” and “增加删除空间的功能”. Official docs read on 2026-10-22: [GetA2aAgent](https://docs.volcengine.com/docs/86681/2249666), [DeleteA2aAgent](https://docs.volcengine.com/docs/86681/2249664), [DeleteA2aSpace](https://docs.volcengine.com/docs/86681/2249661), [delete space prerequisite](https://docs.volcengine.com/docs/86681/2248661). DeleteA2aAgent's example mistakenly uses an as- prefix; implementation uses the actual selected a- member identity and verifies it with GetA2aAgent. No production edits before this design review. Scope, identity, permissions, bounds, bilingual equivalence, state recovery and testability reviewed with no blockers.

Risks: shared-space deletion/deregistration affects other callers; require confirmation, no live writes in this task. Cloud preflight cannot lock registry membership, so provider rejection remains authoritative. Ambiguous writes never silently succeed or auto-retry. Binary rollback does not restore removed cloud registrations/spaces; recovery is explicit recreation by an operator, not an automatic code path. Initial verification: not_run; implementation and actual evidence follow. No commit/push/deployment requested.

## Implementation, review and verification (2026-10-22)

Status: implemented locally, no cloud mutation performed. T-1 through T-5 and AC-1 through AC-5 completed for the incremental diff over the existing uncommitted Center changes. Test-first evidence: 19 Python cases and 4 frontend cases failed before the implementation. Final review fixed repeat submission during dialog exit, distinguished failed read preflight (no write executed) from unknown post-write outcomes, and preserved explicit Runtime duplicate errors even when a provider uses an inappropriate 5xx status. Only the known duplicate signature is recognized; unrelated 5xx/network errors stay uncertain. API projections do not expose raw Cards, original configuration URLs or provider error bodies.

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| uv run --extra dev pytest tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py tests/test_mpa_collaborator_proxy_policy.py -q | pass | 70 passed; local mocked cloud, identity/auth/redaction/empty-space/error classification |
| uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py -q | pass | 129 passed; signed-helper default compatibility and existing proxy regressions |
| npm --prefix frontend test | pass | 1389 Node tests; 175 Vitest cases in 11 files, including 28 collaborator cases |
| npm --prefix frontend run build | pass | updated packaged assets; existing large-chunk warning |
| npm --prefix frontend run check:i18n | pass | 2 locales / 22 namespaces |
| npm --prefix frontend run test:webui-assets | pass | 114 packaged files / 351 references |
| frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json | pass | no diagnostics |
| pre-commit ruff-check / ruff-format for changed Python | pass | frontend/server/a2a_center.py, tests/cli/test_a2a_center_actions.py, veadk/cli/cli_frontend.py |
| Pyright, new server module and tests, .venv/bin/python | pass | 0 errors/warnings; existing Pyright executable with repository interpreter |
| CLI whole-file Pyright | fail (baseline) | 37 diagnostics; exact severity/message/rule multiset equals a comparison restoring the previous signed helper/mount; no new diagnostics |
| Browser | pass | real browser, simulated API: detail dialog, 390px view, Escape/focus restoration, explicit unregister and refresh, empty-space delete and removal of stale selection; preflight failure/uncertainty/late responses also covered in React tests |
| Source secret scan / diff whitespace | pass | gitleaks with repository configuration; existing exclusions remain. No policy bypass |
| Full Python regression / live cloud mutations | not_run | shared helper defaults preserved and affected proxy/API suites pass; no permission to mutate live registrations/spaces during verification |

The provider's reported duplicate Runtime error explains this incident; list reads alone do not establish global uniqueness or eventual mutation outcome. No automatic relocation, deregistration, deletion, retry, commit, push or cloud deployment occurred. Local service activation and asset checks are recorded separately below. Temporary fixtures and diagnostic comparison files are removed after verification.

Review refinement: public documentation does not establish a separate local ban on deleting a default-marked space. The UI/server therefore enforce the documented empty-space prerequisite and the current-MPA unbind requirement, then let AgentKit enforce its actual deletion policy. No deletion was attempted against a live default space.

Local activation verified: restarted the same `veadk studio` command, checked the current built entry and JS assets (HTTP 200), confirmed GET/DELETE member routes and DELETE space route in live OpenAPI, and received HTTP 422 for an invalid target without a cloud request. Temporary browser fixtures, the comparison Python file and the verification Vite process are removed. The latest build, targeted tests, i18n, type checks, secret scan and asset validation were reconciled after the default-space policy refinement. No commit or cloud mutation was performed.
