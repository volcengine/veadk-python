# Preserve MPA direct-answer reasoning
[中文版](2026-09-22-mpa-direct-answer-reasoning.zh.md)

ID: `mpa-direct-answer-reasoning`; date: 2026-09-22; status: implemented.

## Evidence and requirements
Following [snapshot normalization](2026-09-22-mpa-reasoning-snapshots.md), a replay with outer thought deltas and an answer-only final loses the thinking block. Normalization suppresses the complete thought mirror; `applyEvent` only preserves sandbox thinking when clearing the preview. The user approved the proposed correction with “改下”.

FR-1: Explicit MPA A2A mode preserves both outer and sandbox thinking before consolidated events without authoritative thought content. A direct answer retains completed, expandable reasoning and exactly one final answer.
FR-2: Authoritative thought snapshots still replace their previews. Invocation isolation, distinct phases, tools, final deduplication, usage, errors and interrupted output remain intact. General ADK/A2A and native MPA default modes remain unchanged.
FR-3: No authentication, cloud, persistence, layout or dependency changes. Backend correction scope is specified in FR-4. No recovery of events absent from server history.

## Design, tasks and acceptance
T-1/AC-1: Add failing live/full-event replay tests for outer thought → answer delta → corrected final, and preservation across a tool boundary. Test default-mode compatibility, authoritative snapshot replacement and interrupted output.
T-2/AC-2: Remove only the sandbox-source restriction from MPA preview-thinking retention in `frontend/src/blocks.ts`. Keep the explicit `mpaA2a` gate and authoritative-thought guard. Update runtime diagnostics CON-10 in both languages. No new state; existing finalization closes thinking.
T-3/AC-3: Run targeted tests, full frontend test/build/assets checks, actual Blocks browser replay, scoped secret scan, bilingual review and diff whitespace checks. Ship matching generated web assets.

## Review and risks
Direct review substitutes for unavailable review-spec. Scope, compatibility, event ownership, failure/cancellation and bilingual equivalence checked; no blockers. The risk is duplicated thinking when an authoritative thought snapshot exists; the existing guard and regression test retain replacement behavior. New controls/IME/narrow-layout and Python/sidecar verification are not applicable. User approval covers implementation, not commit/push or server restart.

## Verification
2026-09-22; working diff based on `962ac8e0`. Verification results below.

### Results
Executed 2026-09-22 on the working diff based on `962ac8e0`. T-1 through T-3 complete.
- `pass`: two new regression cases failed before the fix; 51 targeted projection/grouping tests pass after it.
- `pass`: `npm --prefix frontend test` — 1,305 Node tests and 25 Vitest tests.
- `pass`: `npm --prefix frontend run build` and `npm --prefix frontend run test:webui-assets` — TypeScript, app/widget builds; 104 packaged files, 248 references. Existing chunk-size warnings remain.
- `pass`: isolated browser using actual Python bridge fixture output, live projector and Blocks: reasoning survives completion and can expand above the single answer. Temporary fixture/server removed. No new cloud generation.
- `pass`: local `/index.html` serves `index-ek6fATgL.js`, byte-identical to the current build. Root `/` still caches `index-Y2wjLniI.js`; use `/index.html` to verify without restarting.
- `pass`: scoped source/test/doc/generated-asset secret scanning, bilingual review and `git diff --check`.
- `not_applicable`: Python, sidecar, new layout/input/keyboard/IME/loading/retry gates; none changed. Interruption covered by partial-output regression.
- `not_run`: live cloud generation; verification uses synthetic event replay. No commit, push or backend restart performed.

## Correction after real multipart artifact regression
2026-09-22: The user reported word-sized reasoning blocks after the direct-answer fix. Read-only inspection confirmed 35 thought parts and one answer part in the final artifact. The original fixture incorrectly represented the artifact thought as a single part. Previous browser/test passes did not validate this shape; acceptance is reopened.

FR-4: In explicit MPA mode, coalesce adjacent thought text parts in artifact-update and task artifacts before normalization, just as for status messages. Preserve exact whitespace, non-thought parts and boundaries. Completed/replacement artifacts are snapshots; append chunks are deltas. Do not reinterpret generic A2A or merge across tools/answers. Full snapshots match the complete streamed text, not individual words.
T-4/AC-4: Failing regressions must include tokenized final artifact-update and task snapshots, with/without prior deltas, extended snapshots, whitespace, append chunks and generic compatibility. Verify the real task read-only replay and a sanitized end-to-end Python bridge → frontend Blocks browser replay. Backend change is limited to `runtime_a2a_stream.py`; its tests, Ruff/Pyright and proxy regressions are required. Activation requires backend restart and must be reported explicitly.

Direct design review: additive correction to user-approved direct-answer preservation; requirements, boundary ownership, no cross-source deletion, privacy and bilingual equivalence reviewed. No authentication, cloud deployment, persisted state or general-agent behavior changes. Approval is the user's ongoing regression correction request.

### Multipart correction verification
2026-09-22, same working diff based on `962ac8e0`. T-4 complete; initial verification above is retained as evidence of the coverage gap.
- `pass`: seven new backend scenarios failed before correction and pass afterward; 54 decoder tests pass.
- `pass`: read-only real task history + tokenized final artifact replay; projected thought exactly equals the 128-character authoritative thought, zero extra thought events from the final artifact. Actual frontend projection/grouping yields one completed thinking block and one answer block. Private temporary payloads removed.
- `pass`: browser replay of synthetic 35-part artifact through actual Python bridge/projector/Blocks; one expandable complete reasoning block and one answer. No real cloud generation.
- `pass`: `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q` — 137 tests, five existing deprecation warnings. Ruff 0.11.12 check/format and Pyright on decoder/tests — zero errors/warnings.
- `pass`: previous 1,305 Node/25 Vitest tests and app/widget build remain applicable because frontend production code did not change during this correction; scoped gitleaks and diff whitespace checks pass.
- `not_run`: backend activation; existing running service must restart to load the parser correction. No commit/push or restart performed.
