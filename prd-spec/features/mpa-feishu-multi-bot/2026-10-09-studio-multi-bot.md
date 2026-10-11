# Studio multi-bot Feishu management

[中文版](2026-10-09-studio-multi-bot.zh.md)

- Change ID: mpa-feishu-multi-bot
- Created/revised: 2026-10-09
- Status: implemented; verification limits recorded
- Scope: Studio only; agentkit-mpa-agent owns Bot persistence, Gateway registration, session routing and migration.
- Contracts: [MPA channels](../../../specs/mpa-channels/README.md), [MPA tasks](../../../specs/studio-mpa-cron-tasks/README.md).

## Background and evidence

The local agentkit-mpa-agent feat/feishu-bots implementation advertises multiBotChannels=[feishu] and accountScopedPermissions=true. GET channels can contain multiple Feishu accounts identified by appId and enabled. Diagnostics without appId returns 409 when ambiguous. Studio currently queries unscoped diagnostics/permissions and treats every 409 as uncertain registration. Its task editor drops delivery.appId when changing a target. Runtime proxy already supports PATCH and administrator-only channel management.

## Goals and non-goals

Expose independent Feishu accounts, additive QR/manual binding, enable/disable/unbind, account-scoped diagnostics and group permissions, and explicit task delivery accounts. Preserve legacy single-bot Runtime and WeCom/DingTalk behavior. Do not change MPA persistence, Runtime creation/images, chat rendering, gateway authentication or deploy services. Live cloud writes and real message delivery are outside this local verification.

## Scenarios and requirements

- FR-1: Enable multi-bot UI only when capabilities.multiBotChannels contains feishu. Missing capability retains legacy behavior; failed requests are errors rather than empty lists.
- FR-2: Fetch GET channels and show account name, appId and enabled state. One account may be selected automatically; multiple accounts require an explicit selection. Adding a bot uses existing QR/manual endpoints and selects the returned appId after refreshing.
- FR-3: PATCH feishu/accounts/{appId} with enabled and DELETE root with channel/appId affect only the target. Unbind requires confirmation. Failed writes preserve inputs and existing accounts; no secrets in persistence or errors.
- FR-4: Diagnostics and permission GET/POST/DELETE always carry the selected appId on multi-bot Runtime. Composite identity prevents same-chat collisions. Distinguish ambiguous account selection from REGISTRATION_UNCERTAIN; only registration conflicts block binding.
- FR-5: MPA Feishu task creation/edit/copy selects a Bot and retains delivery.appId with target and unchanged thread metadata. Multiple bots never silently choose the first. Web delivery omits appId. Disabled/missing accounts block new Feishu writes. Existing tasks missing appId require selection when ambiguous. Preserve legacy task behavior if multi-bot capability is absent.
- FR-6: Account/Runtime/provider changes abort reads and polling; late responses cannot replace selection. Single-flight mutations lock account switching; cancellation does not claim to undo server writes. Cover loading, empty, error, retry, keyboard/IME and narrow screens.

## Design and boundaries

Reuse existing provider panel for binding and scoped account details, existing Select/Button and task dialog layouts. Add an account container gated by capabilities; fetch list before scoped details. Multi-bot management never probes unscoped diagnostics. Account controls are separate from additive binding. Only nonsecret account summaries are retained in React memory. The existing trusted Runtime proxy injects channel credentials. User-scoped cron requests retain current ownership and use delivery.appId inside the unchanged delivery object. Task account choices use existing authorized channel requests; lack of permission is shown and blocks multi-bot Feishu submission, without all-user or credential fallback.

No new dependency, database migration, cloud resource or general-agent behavior. Older runtimes do not receive new fields/endpoints. Public API changes are additive and capability-gated. UI inherits existing tokens and uses no new product icons.

## Tasks and affected files

| Task | Requirements | Files / verification |
| --- | --- | --- |
| T-1 | FR-1..6 | This bilingual PRD and both component contracts; manual design review |
| T-2 | FR-1..4,6 | adk/client.ts, ui/RuntimeChannels.tsx, new Feishu account container, locale pairs; failing frontend regression tests first |
| T-3 | FR-5..6 | cronjobs/MpaTaskEditor.tsx, MpaCronTasks.tsx, locale pairs; task regression tests first |
| T-4 | FR-1..6 | channel and task tests, frontend test/build, proxy Python tests, browser fixtures, frontend README bilingual section, generated veadk/webui |

## Acceptance and verification

AC-1: Two accounts can be displayed, independently selected/toggled/deleted, and adding B leaves A intact (FR-1..3, T-2).
AC-2: Same chat under A/B stays scoped in diagnostics and permission CRUD; ambiguous reads do not disable registration (FR-4, T-2).
AC-3: Task create/edit/copy keeps the intended appId; switching Web removes it; unavailable Bot and stale responses fail safely (FR-5..6, T-3).
AC-4: Legacy Feishu/WeCom/DingTalk regressions pass; normal, loading/error/retry, IME/keyboard and narrow browser fixture checks pass (FR-1,6, T-4).
AC-5: npm --prefix frontend test; npm --prefix frontend run build; targeted Vitest channel/task tests; uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/frontend/server/test_mpa_cron.py. Record actual outcomes. Existing task coverage gate applies when affected; no harness-sidecar change.

## Risks and rollout

The MPA changes are local/unpublished; offline fixtures do not prove live double-bot delivery. Deploy compatible Runtime before enabling multiple accounts. Group management uses administrator-only channel APIs; non-admin task users may not list bots and must see a permission error rather than an invented default. UI refresh cannot revoke in-flight Gateway operations. No automatic rollback/deletion/migration.

## Review and delivery record

User approved the complete proposed scope with “改改看” on 2026-10-09. review-spec is unavailable; reviewed requirements, compatibility, identity, permission boundaries, errors, cancellation, tests and bilingual equivalence directly. No design blocker identified. frontend/SPEC.md and foundation Specification read; referenced frontend-design/ui-ux-pro-max skill files absent in repository and installed skill locations; use established components and direct UI review without adding a competing design system.

Initial baseline: Baseline feat/from-main-20261009 at f8c96211; clean working tree before this design; git pull --ff-only origin main reports already up to date. No commits, cloud writes or deployment authorized by this design.

## Implementation review and verification (2026-10-09)

Tested scope: working-tree changes on `feat/from-main-20261009`, based on `f8c96211`. T-1 through T-4 are implemented. `frontend/README.md` retains its existing mixed-language convention; both languages were updated there rather than introducing a second README. Component contracts and locale pairs were updated together. No Python production code changed. Manual implementation review checked account identity, additive binding, permission boundaries, stale reads, cancellation, single-flight writes and task metadata. A QR completion selection race found by regression testing was fixed before delivery.

| Check | Outcome | Evidence / limits |
| --- | --- | --- |
| Failing regression before implementation | pass | New channel/task tests failed on the original implementation: 8 failed, 50 passed. |
| Targeted frontend regression | pass | `cd frontend && npx vitest run --environment jsdom tests/runtimeChannels.test.tsx tests/feishuAccounts.test.ts tests/mpaTaskBots.test.tsx tests/mpaManagement.test.tsx tests/mpaCronTasks.test.tsx src/adk/channels.test.ts`: 162 passed. |
| Default frontend suite | pass | `npm --prefix frontend test`: 1,376 Node tests and 47 Vitest tests passed. |
| MPA task coverage | pass | `npm --prefix frontend run test:mpa-cron-coverage`: 87 passed; statements 99.31%, branches 97.44%, functions 99.18%, lines 99.74%; existing thresholds unchanged. |
| TypeScript | pass | `cd frontend && npx tsc --noEmit`. |
| Localization | pass | `npm --prefix frontend run check:i18n`. |
| Build / packaged assets | pass | `npm --prefix frontend run build`; `npm --prefix frontend run test:webui-assets`: 113 files / 350 internal references verified. Build retains the existing large-chunk warning. |
| Backend proxy / task regression | pass | `uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/frontend/server/test_mpa_cron.py`: 18 passed, with a Starlette deprecation warning. Existing proxy forwards appId and PATCH without a new backend contract. |
| Browser fixture flows | pass | Actual components with local simulated APIs: explicit account selection, independent enable/disable, additive manual binding and returned-account selection, scoped group save, task bot selection/payload, loading/provider navigation, empty/error/retry, legacy UI and keyboard navigation. At 390 px, document width equals viewport width and diagnostics use one column. Narrow nested cards were corrected during QA. Temporary fixture removed after checking. |
| Native browser confirmation / IME | blocked | In-app browser could not complete the native unbind confirmation; no real account was touched. Automated tests cover confirmation and selected-account deletion, IME composition guards and cancellation. Chinese input was checked in the browser; native OS IME was not exercised by this tool. |
| Live double-bot delivery | not_run | Requires a separately deployed compatible MPA image and explicit live-operation authorization. Simulated API checks do not establish Gateway delivery. |
| Ruff / Pyright / harness-sidecar coverage | not_applicable | No Python or harness-sidecar implementation changed. |
| Commit-time synchronization / pre-commit | not_run | No commit requested. Fetch/rebase and all-files pre-commit remain required before a future commit. |

Initial invocation without jsdom failed on browser globals and was corrected; it is not a runtime failure. AC-1 through AC-3 are covered by regression tests and applicable fixture flows; AC-4 browser coverage has the native-tool limits above; AC-5 gates passed. The implementation does not change general-agent chat rendering, cloud resources or deployment images. Production rollout still requires compatible Runtime deployment and a live smoke test. No commit, push or deployment was performed.
