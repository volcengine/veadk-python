# Studio Bot binding types

[中文](2026-10-16-bot-binding-types.zh.md)

Date: 2026-10-16. Base: origin/main edae5b58. Status: implemented.

## Scope and approval

The user requested a branch from main and a PR for the existing private/shared binding selector. This explicitly authorizes implementation, testing, commit, push and PR creation. A subsequent instruction fixes the private description to “私聊可召回同 Bot 的历史，包括群聊。” No cloud deployment or changes to Runtime recall/authentication rules are included.

## Background and design

Runtime already advertises botBindingTypes and accepts bindingType, but Studio's ProviderChannel sends only credentials/domain. Reuse Radio and the configuration-method fieldset styling. Render a separate “Bot type” group before Quick/Manual setup, only for Feishu (including the Lark brand) and only for known advertised shared/private values. Prefer shared by default; a Runtime advertising private only selects private. Missing, empty or unknown-only capabilities retain the exact legacy payload. Both binding modes and QR retry forward the selection. Preserve domain=lark.

Selection stays in component memory, is locked during requests and after a durable QR binding exists (including failure/retry), and resets when switching Runtime/provider or cancelling/reopening Add bot. Switching setup methods cancels the old QR UI and allows a new choice; it does not mutate the existing server binding. Management of an existing account exposes no editable type. All existing cancellation, late-result guards, administrator authorization and error presentation remain in place. No owner identity is invented or sent by the browser.

Private copy: “Private chats can recall this Bot’s history, including group chats.” Shared copy: “Sessions are isolated from each other.” These are short UI descriptions, not a replacement for Runtime authorization policy.

## Requirements and acceptance

| Requirement/task | Acceptance | Verification |
| --- | --- | --- |
| FR-1 / T-1 | Advertised shared/private options, shared default, requested concise descriptions, no control for unsupported providers/versions | RuntimeChannels component cases and browser fixture |
| FR-2 / T-2 | QR/manual/retry payloads carry selected type; Lark keeps domain; old payload unchanged | Component request assertions |
| FR-3 / T-3 | Busy/pending/retry locks; reset on target/add lifecycle; errors and cancellation cannot leak selection | Component cases and keyboard/narrow browser checks |
| FR-4 / T-4 | Bilingual contract/user docs, rebuilt release assets, >95% changed executable line coverage | Build, i18n, asset checks, coverage diff and pre-commit |

Affected files: frontend/src/ui/RuntimeChannels.tsx, frontend/src/adk/client.ts, both ui.json locales, frontend/tests/runtimeChannels.test.tsx, frontend/README.md, specs/mpa-channels/README.md and README.zh.md, veadk/webui generated assets. No Python, storage, dependencies or permission policy changes.

## Review and risks

Design reviewed directly because review-spec is unavailable: additive capability/field, legacy and Lark compatibility, request ownership, retry type stability, no secret storage, bilingual equivalence, testability and S1–S8 reuse checked; no blocker. frontend-design read; ui-ux-pro-max unavailable in repository/installed skill catalog; use frontend/SPEC.md and foundation instead. Existing Radio controls supply focus/keyboard semantics; no new styles/icons. The user's current request supplies scope approval; no additional approval is needed.

A compatible Runtime remains required; the server owns immutable type validation and recall rules. Component/browser fixtures do not prove real Feishu binding. Verification below.

## Verification and delivery (2026-10-16)

Scope: origin/main edae5b58 plus this change. Implementation review: no blockers; checked capability absence/unknown values, private-only support, immutable retry selection, Lark domain, target lifecycle, no owner spoofing and no type editing on managed accounts. No Python contract or permission implementation changes.

- pass — TDD: added 15 component cases. Before implementation, 9 new assertions failed and 78 tests passed; after implementation all 87 passed. The initial feature gap is resolved; no additional defect reported.
- pass — `vitest run --environment jsdom tests/runtimeChannels.test.tsx tests/feishuAccounts.test.ts tests/mpaChannelsAutomation.test.tsx src/adk/channels.test.ts --coverage`: 116 passed. An initial invocation omitted jsdom and failed the existing client test with `window is not defined`; rerun with the required browser environment passed. Fixed an incomplete new retry fixture to return a terminal binding rather than an object without polling metadata.
- pass — `npm --prefix frontend test`: 1,389 Node tests and 118 Vitest tests.
- pass — `npm --prefix frontend run build`: TypeScript and both production bundles; generated WebUI assets included. Existing large-chunk/dependency warnings remain.
- pass — `npm --prefix frontend run check:i18n`: 2 locales / 21 namespaces consistent. `npm --prefix frontend run test:webui-assets`: 113 files / 350 internal references.
- pass — changed executable lines: 6/6 (100%) against edae5b58; client.ts changes are type-only. RuntimeChannels overall line coverage is 94.71%, distinct from incremental coverage. Coverage source: V8/Istanbul JSON + Cobertura line hits intersected with git diff; utree's parser returned zero targets for this TSX file and is not used as passing evidence. Raw logs and reproducible diff counts: `/tmp/studio-bot-binding-types/`.
- pass — `uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py -q`: 6 passed.
- pass — real in-app browser with isolated mocked Runtime: empty list, shared default, keyboard ArrowRight selects private, exact private description, QR and retry private payloads, locked radio state, manual payload, legacy absence, capability error/retry and loading state. Existing Radio/fieldset styling reused; S1–S8 inspected. At the actual 708px width no horizontal overflow; 390px override did not take effect, so 390px is not verified. Temporary fixture files/browser removed; no real credentials or cloud writes.
- not_run — real Feishu registration, cloud deployment, actual IME input and full Python regression (no Python production change). Existing component IME/duplicate-submit regression remains covered. This PR does not assert live authorization or recall behavior.
- pass — fetched origin/main and rebased with autostash (base remained edae5b58), restored all changes; `uv run --extra dev pre-commit run --all-files` passed Ruff, hardcoded-secret, dependency-policy and YAML-secret checks; final focused rerun: 116 passed. `git diff --check` passed.
