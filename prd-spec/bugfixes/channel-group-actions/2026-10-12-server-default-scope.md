# Server-owned defaults for new Feishu group permissions

[中文](2026-10-12-server-default-scope.zh.md)

Change: studio-channel-server-default-scope. Date: 2026-10-12. Status: implemented.
Contract: [mpa-channels](../../../specs/mpa-channels/README.md), CON-17.

## Evidence and scope
RuntimeChannels initializes group_sender and sends it with every group-permission POST. This overrides Runtime defaults even when the administrator only intends to allow a group. The user explicitly approved removing the isolation selector and omitting this field, while preserving existing groups. Only the Studio consumer changes; Runtime API types, optional scope support and backend precedence remain intact.

## Requirements and design
FR-1: A new group form contains no isolation selector or hidden scope state. FR-2: Its POST contains channel, trimmed chatId and appId when an account is selected, but never groupSessionScope, including null or an empty string. FR-3: Existing groups retain their returned scope display; rendering, refreshing or adding another group must not issue automatic updates to them. FR-4: Existing loading, disabled, IME, cancellation, failure/retry and multi-bot targeting behavior remains.

Delete only the selector, its local state/options/imports, and the POST property. Do not force group, clear stored scopes, change data structures, migrate data, add dependencies or touch execution/streaming. API-level callers may still use the optional field. The Runtime owns resulting defaults; Studio does not claim every deployment defaults to group. Adding an already existing ID follows the unchanged Runtime upsert behavior; no migration guarantee is invented.

## Tasks and acceptance
| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1/FR-2 | T-1: regression first, then minimal RuntimeChannels change | AC-1: selector absent and exact POST body omits scope in single/multi-bot modes | runtimeChannels.test.tsx |
| FR-3 | T-2: retain returned scope rendering | AC-2: existing group_sender/topic modes display without writes | runtimeChannels.test.tsx |
| FR-4 | T-3: run existing interaction tests and local browser checks | AC-3: normal/failure/retry/keyboard/narrow flow and account identity preserved | npm test, targeted Vitest, npm run build, browser |

## Review and authorization
Direct design review: feasible existing optional API, no backend or migration change; selected-account auth and abort handling unchanged. The existing-list fallback stays unchanged. No blockers. Authorization is the user's explicit request in this chat. No additional approval needed for the specified minimal change. The referenced frontend-design/ui-ux-pro-max files were absent after searching the repo and local skill roots; this deletion uses frontend/SPEC.md and the component foundation without a new visual design. A global/local VeADK review-spec skill is absent; this review records the equivalent checks directly, without applying another repository's report workflow.

## Verification and delivery
Verified on 2026-10-12 against HEAD 812faadf plus this worktree diff. Production change removes 31 lines from RuntimeChannels; English/Chinese group description now only describes admission. Existing Button/input/form styles and returned scope labels are reused unchanged; no new styles or dependencies. frontend/README.md and CON-17 are reconciled in both languages.

- pass: before-fix targeted regression 2 failed / 3 passed / 61 skipped, reproducing the selector and unintended multi-bot scope property.
- pass: targeted `./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx tests/feishuAccounts.test.tsx` from frontend: runtimeChannels.test.tsx 66 passed. No separate feishuAccounts test file matched; multi-bot tests run in RuntimeChannels.
- pass: `npm --prefix frontend test`: Node 1377 passed, Vitest 67 passed. Existing i18next/localStorage warnings remain; no failed tests.
- pass: `npm --prefix frontend run check:i18n`: 2 locales / 21 namespaces consistent.
- pass: final `npm --prefix frontend run build`: TypeScript and both Vite builds succeeded; generated veadk/webui assets updated. Asset grouping changes are generated output, not edits to unrelated source.
- pass: `npm --prefix frontend run test:webui-assets`: 113 files / 350 internal references verified.
- pass: real browser mounted the actual component with isolated HTTP fixtures: disabled empty submit, no isolation control, busy controls disabled, failed save preserves chat ID, keyboard Enter retries, success clears input, original group_sender label stays visible; 390px viewport flow usable. Recorded three actual POST bodies contain only channel/chatId; no write to the existing group. Multi-bot appId omission regression is covered by Vitest, not this single-bot browser fixture. Temporary viewport reset and fixture files/processes removed after verification.
- pass: gitleaks via repository pre-commit hook on changed source/test/docs files; `git diff --check`.
- not_applicable: Python tests/Ruff/Pyright, because no Python changes.
- not_run: real cloud/Feishu E2E, deployment, remote CI, full pre-commit/all-files; no such publication authorized and preserve unrelated worktree edits.

Local logs and browser evidence are `/tmp/mpa-studio-default-scope-*`, including the form screenshot. No credentials or real production data used. Existing package-lock.json change (512 removed lines) was preserved without modification. No commit/push/deploy performed. Remaining risk: Runtime bot-level inheritance may differ by deployment; omission deliberately delegates that choice. Re-adding an existing ID uses existing Runtime upsert semantics rather than a new preservation guarantee.
