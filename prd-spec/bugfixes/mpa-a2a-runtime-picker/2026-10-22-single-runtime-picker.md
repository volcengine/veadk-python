# One required Runtime picker for A2A registration

[中文版](2026-10-22-single-runtime-picker.zh.md)

ID: mpa-a2a-single-runtime-picker. Date/revision: 2026-10-22. Status: approved.
Related: [component](../../../specs/mpa-collaborating-agents/README.md), [endpoint design](../../features/mpa-collaborating-agents/2026-10-22-endpoints-and-skills.md).

## Evidence, goals and scope

A2ARegistration renders both a Runtime Select and a required Runtime ID input bound to the same form.runtimeId. The user identified the duplicate field and approved: “按此调整”. The manual field originally bypassed list pagination/read failures; the form already supports pagination and retry. Remove duplicate input while preserving selection, endpoint loading and registration payload.

FR-1: Always show one required existing-Runtime Select, using authorized paginated Runtime list values. Do not render a separate Runtime ID textbox. Keep IDs internally and in existing option labels/detail views. Source Runtime registration is blocked until an option still present in the current list and its matching endpoint are available. Switching selections cancels/discards stale endpoint reads. A selection removed by a list replacement must not remain submittable.
FR-2: Distinguish initial loading, successful empty list, and read failure. Empty/error states offer list retry; pagination appends/deduplicates choices and preserves selection. Remove manual-ID instructions in both locales. Keep keyboard navigation, Escape/cancel/focus return and Standard JSON/URL input/IME behavior.
FR-3: Preserve POST body RuntimeId/NetworkType, backend authorization, public API compatibility and uncertainty handling. No backend, Runtime, IAM, dependency or database change; no real cloud writes, commit or push.

## Design, tasks and acceptance

Reuse Select/FormLabel/Button/TextShimmer and existing form layout. Move required semantics to the Runtime picker; focus the first visible source control on form mount. Derive sourceRuntimeId only from a listed selection, so list replacement invalidates old endpoints and submit state. Keep source-specific API union unchanged. CON-RUNTIME-PICKER is a UI contract refinement; endpoint and backend contracts are unchanged.

| Requirement | Task | Acceptance | Tests |
| --- | --- | --- | --- |
| FR-1 | T-1: failing regression then remove input and gate listed selection | AC-1: no ID textbox; picker required; selected ID sent automatically; stale/missing selection cannot submit | frontend/tests/collaboratingAgents.test.tsx |
| FR-2 | T-2: loading/empty/error/pagination and keyboard regression; locales | AC-2: states distinct and retryable, pagination preserves choice, no manual-ID hint, Standard IME preserved | UI tests; real browser with mocked API, including narrow layout |
| FR-3 | T-3: docs, types, build/assets and review | AC-3: frontend tests/build/i18n/assets/tsc and scoped secret/doc checks pass; no backend diff added | repository frontend gates; git diff --check |

## Review, approval and risks

No review-spec skill is available. Direct review covers feasibility, component ownership, state/cancellation, errors, security, compatibility, testability and English/Chinese equivalence; no blockers. User approved the stated single-picker plan before code/test edits. Existing frontend-design/ui-ux-pro-max guidance applies to feedback and component reuse; no visual redesign. Removing manual entry means unavailable Runtime lists must be retried rather than bypassed. This is intentional approved scope. Provider eligibility and last-moment authorization still apply server-side. Whole Python regression and Ruff/Pyright are not applicable to this frontend-only delta; existing unrelated dirty changes are preserved.

## Verification

Date: 2026-10-22. Scope: incremental frontend-only change on existing uncommitted A2A Center work above 9ab0ef2d. All checks not_run until executed. Live registration/deletion not_run because verification must be read-only or isolated mocks. Results will be recorded below.


## Implementation and verification record (2026-10-22)

Production/UI implementation is complete. T-1/T-2/T-3 code and verification changes are present locally, with no backend/API changes in this incremental scope. Four new regression cases failed before implementation; all 40 collaborating-Agent tests now pass. Standard import IME coverage was moved to its actual text input after removing the Runtime text field. Review verified required semantics, selection-to-ID mapping, empty/error/loading states, append pagination, stale endpoint invalidation, focus and cancellation. No in-scope code findings remain.

| Check | Result | Evidence |
| --- | --- | --- |
| `npm --prefix frontend test` | pass | 1389 Node tests; 187 Vitest cases in 11 files, including 40 collaborating-Agent cases. |
| `npm --prefix frontend run build` | pass | Matching packaged assets generated; existing large-chunk advisory remains. |
| `npm --prefix frontend run check:i18n` | pass | 2 locales / 22 namespaces. |
| `npm --prefix frontend run test:webui-assets` | pass | 114 packaged files / 351 references. |
| `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json` | pass | No diagnostics. |
| Browser with isolated mock fetch | pass | One required picker, no manual ID input; automatic endpoint loading; retry after list failure; confirmed empty state; keyboard selection and cancel/focus return. At 390px the form clientWidth and scrollWidth both measured 342px. Fixture files, Vite and tab removed. |
| Scoped gitleaks using repository config; paired-document links/IDs; `git diff --check` | pass | No secrets found. Preserve configured scanner exclusions. |
| Python tests/Ruff/Pyright | not_applicable | This incremental fix changes no Python implementation or tests. Prior auth/endpoint verification remains in its own design. |
| Commit gates and live cloud writes | not_run | No commit, push or cloud registration/deletion authorized. |
| Local startup / current built entry | pass | Studio serves the current index and JavaScript asset, HTTP 200. |
| Cloud-account environment after local restart | blocked | The agent gracefully restarted Studio to clear its cached old index, but the replacement process did not inherit the original cloud AK/SK environment. Local .env has no matching credentials. Read-only space lookup now returns 409. This is an agent-caused operational regression, not a cloud IAM refusal. No credentials were printed, persisted or replaced, and no alternate CLI profile was selected. User has been asked for the original startup/configuration path or to restore the original terminal environment; recovery is pending. |

Lifecycle remains approved until the startup environment regression is recovered and verified. Do not claim full task completion. The UI implementation and tests are reviewable, but cloud access is currently unavailable. All prior unrelated changes are retained. No commit/push/Runtime deployment was performed.
