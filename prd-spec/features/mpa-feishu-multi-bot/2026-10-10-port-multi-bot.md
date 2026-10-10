# Port Studio multi-bot support to the upstream-based branch

[中文](2026-10-10-port-multi-bot.zh.md)

- Change ID: mpa-multi-bot-port; created/revised: 2026-10-10; status: implemented.
- Source: `49dd4696` on `feat/from-main-20261009`; target baseline: `f7576c40` on `feat/mpa-account-fixes-upstream-clean-20261010`.
- Design: [original feature](2026-10-09-studio-multi-bot.md). Contracts: [channels](../../../specs/mpa-channels/README.md), [tasks](../../../specs/studio-mpa-cron-tasks/README.md).

## Background, goals and scope

The source implements capability-gated Feishu account management and scheduled-task delivery. Target lacks the new containers and capability fields. Dry application accepts source/tests/spec changes; frontend README requires contextual reconciliation. User requests transferring this feature. Preserve current account-key work and unrelated package-lock edits. Do not merge unrelated branch history, change Runtime images/backend storage/authentication, or operate real bots. Historical source verification is not current-branch evidence.

## Requirements and design

- FR-1: Transfer the original FR-1–FR-6 semantics and regression cases: capability-gated multi-bot accounts, selected appId in diagnostics/permissions, additive binding, independent enable/disable/unbind, explicit task delivery, cancellation and stale-response handling.
- FR-2: Preserve older single-bot Runtime, WeCom/DingTalk and general-agent chat. Missing multiBotChannels keeps legacy UI; unsupported task capabilities (404) retain legacy task behavior. Authorization/network failures remain errors; never infer compatibility from an empty/error response.
- FR-3: Apply only feature source/tests/contracts/docs. Rebuild packaged assets from target sources rather than copying old bundles. Preserve all pre-existing local changes byte-for-byte. No dependency/lockfile changes needed; no new public Python or server API contract beyond the original capability-gated additions.

Reused components: existing RuntimeChannels layout, provider tabs, Select, Radio, Button, task DialogShell and text-shimmer. No new product icon or component design. Ports use public component properties; direct foundation/S1–S8 and UI review substitutes for missing frontend-design/ui-ux-pro-max skill files. Contract responsibility remains with MPA for bot storage/routing and Studio for account selection/proxy requests.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1 | T-1 | AC-1: apply tests first and record failure; port source and verify channel/task cases |
| FR-2 | T-2 | AC-2: run legacy regressions and browser fixtures for normal/loading/empty/error/retry/cancellation/keyboard/narrow flows |
| FR-3 | T-3 | AC-3: regenerate assets, verify references/localization/types/security, reconcile bilingual README/spec/design and compare pre-existing file hashes |

Commands: targeted Vitest (jsdom); npm --prefix frontend test; npm --prefix frontend run test:mpa-cron-coverage; npm --prefix frontend run build; npm --prefix frontend run check:i18n; npm --prefix frontend run test:webui-assets; local tsc --noEmit; uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/frontend/server/test_mpa_cron.py. No Python production changes require new Ruff/Pyright gates for this port; previous key-feature gates remain separate.

## Risks and review

Multi-bot requires a compatible Runtime deployed separately. Non-admin users may be unable to list delivery bots; surface permission failures. Mock browser fixtures cannot establish real Feishu/Gateway delivery. Native confirmation/IME limitations must be recorded. No resource cleanup/migration is performed.

Direct review (review-spec unavailable): checked source/target boundaries, preservation, capabilities, auth/errors, cancellation, tests and bilingual equivalence; no blocker. User approval: “把那个修改挪过来吧” after the scoped transfer plan. No commit/push/deployment authorized. Design/spec guidelines and frontend foundation/SPEC read; referenced UI skills unavailable in repository and installed skill roots, so established component behavior is retained.

## Verification record

Scope: source/test/document and regenerated WebUI diff against `f7576c4080da6230e263eac20ab5d32644405ed5`; execution date: 2026-10-10. T-1–T-3 and AC-1–AC-3 completed with the live-verification limits below.

| Check | Result | Evidence |
| --- | --- | --- |
| Test-first targeted Vitest | fail, expected | Before source migration: 27 new tests failed and account helper import was missing; 123 existing tests passed |
| Targeted Vitest (jsdom) | pass | 6 files, 162 tests: channels, account response validation, task bots, management, cron and channel API |
| `npm --prefix frontend test` | pass | 1,377 Node tests and 65 Agent info/creation/details Vitest tests |
| `npm --prefix frontend run test:mpa-cron-coverage` | pass | 87 tests; statements 99.31%, branches 97.44%, functions 99.18%, lines 99.74%; configured gates met |
| `frontend/node_modules/.bin/tsc --noEmit` (frontend cwd) | pass | Current TypeScript source compiles |
| `npm --prefix frontend run check:i18n` | pass | Two locales, 21 namespaces consistent |
| `npm --prefix frontend run build` | pass | Studio and website integration regenerated from target sources; existing bundle-size warnings remain |
| `npm --prefix frontend run test:webui-assets` | pass | 113 packaged files, 350 internal references |
| Targeted Python command listed above | pass | 18 proxy-policy/cron tests |
| Isolated real-browser checks | pass | Mock API with real components: account selection, independently toggling B, scoped diagnostic/group requests, additive manual binding C preserving A/B, task B delivery/thread preservation, Web clearing appId, single-bot legacy view, unchanged DingTalk view, empty/error/retry/loading, abort on remount, cancel addition and keyboard selection; 390px viewport has no horizontal overflow, including task editor |
| Native unbind confirmation / real IME | blocked | In-app browser confirmation blocks CDP input; closed the affected test tab. Unbind/cancellation/stale requests and composition safeguards covered by component regressions; no actual IME session asserted |
| Gitleaks scoped directory scan (`--redact=100`) | pass | 24 migration source/test/document files, no finding |
| Preservation and document review | pass | All 20 pre-existing dirty files retain identical SHA-256, including account-key changes and package-lock; paired docs, relative links and whitespace checked |
| Ruff/Pyright and harness-sidecar coverage | not_applicable | No Python production or sidecar contract changes |
| Live Runtime/Feishu/Gateway writes | not_run | Compatible Runtime deployment and real delivery are outside this Studio migration |
| Commit-time fetch/rebase and full pre-commit | not_run | No commit requested |

Implementation review: capability-gated ownership and backward compatibility match the contracts; bot diagnostics/groups/deletion and task delivery remain scoped; failed reads never become successful empty lists or arbitrary bot choices; abort/single-flight handling is preserved. No production changes to general chat, MPA provisioning, image defaults, IAM or model-key discovery. Temporary fixture/server and browser viewport overrides were removed. Historical source design evidence is retained separately.

Documentation check note: the full frontend README link check reports an existing unavailable local-only `.agents` example link, already present at HEAD. All migrated links pass; that unrelated link was left unchanged.

## Commit preparation (2026-10-10)

User authorization: “把当前的修改都提交吧”. Commit only; no push or deployment. Fetched origin/upstream, then ran `git rebase --autostash upstream/main`: the upstream-based branch was already current and the autostash restored successfully. All 172 changed/deleted/untracked file states matched their pre-sync hashes; no production or test files changed during hooks. The user-authorized existing package-lock changes are included; `npm ci --prefix frontend --dry-run --ignore-scripts --offline` passes without changing the lockfile.

- pass — `uv run --extra dev pre-commit run --all-files`: Ruff check/format, hardcoded-secret detection and YAML-secret scan.
- pass — changed Python production/test files checked with `uv tool run --from pyright pyright --pythonpath .venv/bin/python`: zero errors/warnings.
- pass — frontend full suite rerun after synchronization: 1,377 Node tests and 65 Vitest tests; multi-bot/channel/task regression rerun: 162 passed. Previous build, localization, coverage, asset and isolated browser evidence remains valid because synchronization/hooks changed no source or artifacts.
- fail, pre-existing baseline issue — `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 6,933 passed, 53 skipped, four xfailed, one failed, 55 warnings, 412.63 seconds. The sole failure is `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`: expected `text/markdown`, received `application/octet-stream`. The writer and test match HEAD byte-for-byte. An isolated `git archive HEAD` baseline using the repository Python environment reproduces the same failure; this host's `mimetypes.guess_type("summary.md")` returns `(None, None)`. Independent current writer suite reproduces it with 48 other tests passing. No unrelated MIME implementation/test change was added to this commit; the full suite is not represented as passing. This does not identify a regression in the submitted feature scope.
- pass — staged whitespace check and secret hooks; local `.env` remains ignored and excluded. Live Ark/Feishu/cloud verification and native browser confirmation/IME limits remain as recorded above; skipped tests do not establish live behavior.
