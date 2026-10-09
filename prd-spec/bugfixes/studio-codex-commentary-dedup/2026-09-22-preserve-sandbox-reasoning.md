# Preserve sandbox reasoning when the final answer arrives

[中文版](2026-09-22-preserve-sandbox-reasoning.zh.md)

## Scope and evidence
ID: `mpa-preserve-sandbox-reasoning`; date: 2026-09-22; status: implemented.
Continuation of [content preservation](2026-09-22-preserve-followup-content.md), authorized by the user's request to fix missing messages and subsequent screenshot correction. Source inspection shows `applyEvent` truncates the shared live-preview region on consolidated events, removing sandbox thought deltas when the final contains only answer text. The screenshot shows distinct outer and sandbox reasoning; the actual failing sequence will be verified before implementation.

## Requirements and scenarios
- FR-1: In explicit MPA A2A mode, sandbox reasoning streamed before an answer must survive answer completion and non-reasoning consolidated tool/control events. Given outer reasoning, sandbox thought deltas, answer deltas and a final answer, retain both reasoning stages and one answer.
- FR-2: A consolidated event containing authoritative thought text still replaces its thought preview. Preserve invocation isolation, replay deduplication, tool/error content and cancellation behavior. Live and full-event history projection agree; missing server history is outside scope.
- FR-3: Default/general-agent and native MPA projection remain unchanged. No API, backend, authentication, cloud resources, session persistence or input/UI layout changes.

## Design and contract impact
Keep thinking blocks from the live-preview region before an MPA sandbox consolidated event replaces answer preview, unless that event supplies its own thought text. Preserve their order; existing completion logic closes them. Do not guess whether thoughts are duplicates by text or merge distinct invocation identities. This uses existing blocks and adds no state, timers or dependencies. Update runtime diagnostics CON-10 in both languages. Permissions/security and cloud side effects: not applicable; pure local projection.

## Tasks and acceptance
- T-1 / AC-1 / FR-1: Add a failing full-sequence regression with two reasoning stages and one answer, for live projection and full-event replay/grouping.
- T-2 / AC-2 / FR-2: Implement the scoped preservation; test consolidated tool events, authoritative thought snapshots, repeated event IDs, interrupted previews and separate invocations.
- T-3 / AC-3 / FR-3: Test unchanged default mode; run frontend tests/build/assets and an isolated real-browser replay with actual Blocks rendering. Check paired documentation and whitespace.

## Review, risks and verification
Direct design review (review-spec unavailable): scope, event ownership, concurrency, failure/cancellation, compatibility and bilingual equivalence checked; no design blockers. Prior “修正吧” approval and continued report authorize this correction. The risk is retaining a preview when an authoritative thought snapshot exists; explicit thought detection and regression coverage address it. Existing server history may contain only the final answer and cannot recover absent thought events.

Verification date: 2026-09-22; scope: working diff based on `3bbd260a`. Tests/build/browser: pass; results below. No commit, push, restart or live cloud generation authorized by this change.

## Verification results
2026-09-22; working diff based on `3bbd260a`; T-1 through T-3 complete.
- `pass`: regression reproduced three failures before the fix (lost worker reasoning); all 48 targeted projection/grouping tests passed after it.
- `pass`: `npm --prefix frontend test` — 1,302 Node tests and 25 Vitest tests.
- `pass`: `npm --prefix frontend run build` (TypeScript, app and widget) and `npm --prefix frontend run test:webui-assets` (104 files, 248 references). Existing chunk-size warnings remain.
- `pass`: isolated browser replay using actual projector, grouping and Blocks; two completed reasoning headers remain, worker reasoning expands, one final answer. Fixture files and server removed.
- `pass`: scoped gitleaks with 20 MB target limit, bilingual contract/link review and `git diff --check`.
- `pass`: `/index.html` on port 8000 serves current entry `index-BpWPgu-v.js`, whose bytes match the new build. `/` still caches the earlier entry `index-D5nISdvG.js`; use `/index.html` without restarting the server.
- `not_run`: live cloud generation and incomplete server-history reconstruction. Browser check uses synthetic events.
- `not_applicable`: Python/sidecar gates (no new changes), input/IME/loading/retry/narrow-layout changes (no controls/layout changed); cancellation covered by retained partial output and stream-finish tests. No commit, push or restart performed.
