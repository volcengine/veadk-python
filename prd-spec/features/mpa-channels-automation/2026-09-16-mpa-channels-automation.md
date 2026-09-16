# MPA channels in Automations

[中文](2026-09-16-mpa-channels-automation.zh.md)

- Change ID: `mpa-channels-automation`
- Created/revised: 2026-09-16
- Status: implemented
- Component: [MPA channels](../../../specs/mpa-channels/README.md)
- Baseline: `1263a268`; branch: `feat/mpa-channels-automation`

## Background and scope

`AgentWorkspace.tsx` currently mounts `RuntimeChannels` inside MPA agent details. Automations already groups Feishu bot creation and website integration under Messaging channels. `getRuntimes` supports authorized scope, `agentCategory=mpa`, region and cursor pagination. `DeploymentSelect` already supports search, keyboard navigation and pagination.

Move the existing management flow into Automations so users can choose an existing MPA agent in one place. Retain the Feishu bot creation and website integration cards. Do not create/deploy runtimes, alter provider APIs, migrate bindings, change permissions or modify MPA backend behavior.

## Requirements and scenarios

- FR-1: Messaging channels includes an adjacent `MPA智能体消息渠道` card (`mpa-channels`). Opening it shows a back action, page title and searchable MPA Runtime selector. Remove the old agent-detail section.
- FR-2: Request `getRuntimes` with `agentCategory: mpa`, the authorized Runtime scope and all regions. Paginate explicitly without dropping later results. Reject explicitly non-MPA records; accept omitted category only because the request explicitly filters MPA. Identify options by region plus Runtime ID; display the name once, followed by description and creator/creation time; selected-target context retains region and ID. Require explicit selection before mounting channels.
- FR-3: Reuse `RuntimeChannels` for Feishu, WeCom and DingTalk with unchanged quick/manual flows. Key the panel by region and Runtime ID; selecting another Runtime unmounts the old panel, aborts polling/SDK work, clears transient credentials and ignores late results. Existing durable bindings remain intact. Cancelling frontend work does not revoke a server-side registration already accepted.
- FR-4: Only Studio admin/super_admin can enter management; other roles see a permission explanation and issue no list/channel requests. The existing backend authorization remains authoritative. Failed requests, empty results, loading, no search matches and unsupported Runtime capabilities have distinct messages; errors allow retry. Pagination errors retain prior options and the current binding panel.
- FR-5: Follow current Automations layout, semantic colors, self-authored SVG icons and existing search/select behavior. Cover keyboard/IME, long names and narrow windows. Both locales must be complete.

## Design and contract impact

Add a dedicated automation definition and page under `frontend/src/automations/`; wire its discriminated union, registry, catalog icon and App routing. Pass role and Runtime scope from App. Reuse `DeploymentSelect`; its existing global styles are already loaded by Studio. Keep list loading within the page, guarded by AbortController and request identity. Load subsequent pages on demand with an explicit load-more/retry action, including while a search has no matches. Search filters loaded names, IDs and regions and explains that more pages may exist. No automatic selection or authorization.

The page owns navigation/list/selection; `RuntimeChannels` retains provider state and adds an optional header flag to avoid duplicate page headings. The selection never enters browser persistence. Switching role/scope resets page state through a keyed child. No secrets are requested by the selector. No Python API, deployment payload, database or event contract changes. Update MPA navigation and CON-14 in both component languages. The old detail selection is component-local, with no public deep-link contract.

## Tasks and acceptance

| Task | Requirement | Acceptance / verification |
| --- | --- | --- |
| T-1 | FR-1, FR-5 | AC-1: bilingual card, correct routing/back navigation, old detail entry removed; catalog/navigation tests |
| T-2 | FR-2, FR-4 | AC-2: scoped MPA paging/search, explicit selection, loading/empty/error/retry/permission tests |
| T-3 | FR-3 | AC-3: actual channel panel remounts; old pending responses cannot affect selected Runtime; existing provider regression tests |
| T-4 | FR-5 | AC-4: browser verifies normal flow, cancellation, keyboard/IME and 390px layout; i18n and build/assets gates |
| T-5 | All | AC-5: bilingual specs and frontend README reconciled; diff review and secret scan |

Affected files: automation types/registry/new definition/page/styles/icon; `Applications.tsx`, `App.tsx`, `AgentWorkspace.tsx`, `RuntimeChannels.tsx`; both automation locale files; targeted tests; `frontend/README.md`; MPA specs; generated `veadk/webui` assets.

Commands: targeted Vitest tests (`mpaChannelsAutomation.test.tsx`, `runtimeChannels.test.tsx`), `npm --prefix frontend test`, `npm --prefix frontend run check:i18n`, `npm --prefix frontend run build`, `npm --prefix frontend run test:webui-assets`, `git diff --check`, repository pre-commit secret scan. Browser checks use isolated fake Runtime/channel APIs, never real provider credentials.

## Risks and review

Search covers loaded pages; an explicit load-more action avoids silently hiding later agents. Runtime reachability/capability is checked after selection by the existing component. Changing agents aborts frontend work but does not roll back an accepted backend operation. Live provider connectivity is outside this navigation change and is not implied by mocked checks.

2026-09-16: User approved the described move, requested an isolated branch, then explicitly requested pushing it and starting development. Branch pushed before edits; original branch preserved. Direct design review checked scope, bilingual equivalence, compatibility, authorization, pagination, stale responses, secrets and testability; no blockers. Referenced frontend-design/ui-ux-pro-max and review-spec skills were not found in repository/user skill locations; review uses `frontend/SPEC.md` and repository review criteria directly. No new design system or dependencies.

## Verification record

Execution date: 2026-09-16. Tested scope: the local diff from `1263a268` on `feat/mpa-channels-automation`, including new files and rebuilt WebUI assets. T-1 through T-5 and AC-1 through AC-5 are complete.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Test-first selector suite | fail (expected) | New component import did not exist before implementation. |
| `./frontend/node_modules/.bin/vitest run --root frontend tests/mpaChannelsAutomation.test.tsx tests/runtimeChannels.test.tsx --maxWorkers 1` | pass | 62 tests; includes real channel component remount, role/scope changes, polling and late SDK credentials. |
| `npm --prefix frontend test` | pass | 1207 tests; replaced two obsolete detail-channel tests with one migration assertion. An additional old section-union assertion failed initially and was updated to the approved navigation. |
| `node --test frontend/tests/agentWorkspace.test.mjs frontend/tests/applications.test.mjs` | pass | 38 tests after final formatting/cleanup. |
| `npm --prefix frontend run check:i18n` | pass | 2 locales, 21 namespaces. |
| `npm --prefix frontend run build` | pass | TypeScript and both app/widget builds; existing large-chunk advisory remains. |
| `npm --prefix frontend run test:webui-assets` | pass | 104 packaged files, 248 references. |
| Browser with isolated fake APIs | pass | Catalog card, explicit selection, Chinese search and keyboard selection, back-to-channels category, QR panel cleared on target switch, manual binding success, paging, unsupported image, loading/empty/error/retry/permission states. At 390×844, body width 390 and content client/scroll width 347/347. Production styles loaded without component-preview theme tokens. |
| IME composition | pass | Unit event test verifies Enter during composition cannot choose a Runtime; browser exercised Chinese text entry. |
| `uv run --extra dev pre-commit run --all-files` | pass | Ruff check/format and repository Gitleaks. Explicit `--files` scan also passed for new source, tests and PRDs (Python hooks correctly skipped for those files). |
| Additional default Gitleaks scan including changed build assets/tests | fail (reviewed false positive) | 83 changed/new files scanned with redaction; one generic-api-key finding in bundled MarkdownPromptEditor is the Lexical selection anchor/focus key expression. Exact flagged expression is present in baseline. No rule weakened; no credential found on review. |
| `git diff --check -- ':!veadk/webui'` | pass | Source/docs/tests whitespace clean. Full diff check reports whitespace inside generated vendor template strings; baseline and current widget each contain 36 such lines with identical trailing contexts. Generated semantics retained. |
| Bilingual identifiers and relative links | pass | FR/T/AC identifiers match; all paired PRD/spec links resolve. |
| Python/runtime/cloud/provider suites | not_applicable / not_run | No Python or backend contract changes. Browser API simulations do not prove live provider delivery; no live cloud/provider operations performed. |

Final review found no blocking defects in target identity, category filtering, access enforcement, pagination, cancellation, credential lifetime or navigation. Existing provider binding behavior remains owned by RuntimeChannels. The shared DeploymentSelect uses its existing ProjectPreview stylesheet through an explicit import. Temporary browser fixtures, preview server and tab were cleaned up. Branch baseline was pushed as requested; development changes are left uncommitted for review.


### Option details refinement (2026-09-16)

User requested replacing the repeated option name with description, creator and creation time. Approved within FR-2/FR-5: keep the title once, use a second line for description and a third line for creator/time. Missing/invalid values have localized placeholders; format valid timestamps in the current locale. Selected target still shows region/ID. Add an optional `metadata` string to DeploymentSelectOption without changing existing callers; its tooltip includes all option text. No API, binding, permission or storage changes. Direct review found no contract/security blockers. Add option-content and missing-value regressions, then rerun frontend tests, i18n, build/assets and isolated browser layout checks. Refinement checks: not_run before editing.

Refinement verification (2026-09-16): test-first 2 failed / 13 passed, then 64 channel/automation tests passed; full frontend suite 1207 passed; i18n, app/widget build and 104-file/248-reference asset validation passed. Browser verified three-line metadata, localized dates, missing-value placeholders and long description/creator wrapping. At 390×844, body width is 390 and option client/scroll widths are both 292; full details remain available in the tooltip. Existing options without metadata retain their previous layout. No live Runtime/provider operations. Temporary fixture/server/tab removed.

### Compact creator and Runtime context (2026-09-16)

User refined the option footer to creator name (fallback “Unknown creator”) | relative creation time, with no field-name prefixes, and requested region and Runtime ID inside each option again. Keep the name and description rows; show the compact creator/time row followed by region/Runtime ID. Reuse `formatRelativeTimeLabel`; invalid/missing times show an em dash. This supersedes the preceding absolute-time footer decision. Extend the existing metadata string with a line break and let the shared metadata style preserve that break; callers without metadata remain unchanged. FR-2/FR-5 and CON-14 are updated accordingly. User request authorizes this display refinement; review found no API, permission, state or credential impact. Verification pending.

Compact-footer verification (2026-09-16): regression-first 2 failed / 13 passed; final channel/automation suite 64 passed, full frontend suite 1207 passed, i18n/build/assets passed. Browser confirmed “未知创建者 | 14 小时前” and region/Runtime ID on separate footer lines. At 390×844, body width 390; both option client/scroll widths 292. Missing time uses an em dash; relative time uses the existing shared helper. Temporary preview files, server and tab removed. Changes remain uncommitted.
