# Preserve distinct follow-up content during MPA deduplication

[中文版](2026-09-22-preserve-followup-content.zh.md)

## Metadata and evidence
ID: `mpa-preserve-followup`; date: 2026-09-22; status: implemented.
Supersedes the broad ownership/filtering rules in [Codex ownership](2026-09-22-studio-codex-commentary-dedup.md) and [A2A final ownership](2026-09-22-mpa-a2a-final.md); retains final projection, wrapper handling and MPA grouping.
Isolated review reproduced three defects: a general agent's distinct text after delegate completion disappears; commentary containing an answer plus a warning is removed in full; the A2A bridge drops all outer text after a sandbox final regardless of equality. The user explicitly authorized correcting these findings.

## Requirements and design
- FR-1: Restore general Codex delegate projection/activity to the remote-base behavior. Remove generic answer ownership and substring filtering, including associated obsolete tests; replace them with preservation regressions. Do not change ordinary ADK/native MPA protocols.
- FR-2: The A2A bridge records successful nonempty sandbox final strings per task and drops only boundary-trimmed exact duplicate complete answer text parts. Preserve reasoning, distinct/extended text, partial deltas, tools/errors and metadata; unknown/failed/empty finals cannot establish a reference. Keep sandbox event-ID replay deduplication. No buffering or new stream lifetime state beyond task-local reference strings.
- FR-3: Tag the final-owner turn only in explicitly enabled MPA A2A projection. The grouped presentation suppresses other fragments' answer text only when their complete concatenated answer equals a known sandbox final. Never mutate raw turns or remove reasoning/tools/attachments. If later deltas extend that fragment, the entire original answer becomes visible again. This prevents permanent prefix loss and hides exact stream mirrors without buffering. Feedback points to a visible answer, not a suppressed mirror. User/system boundaries isolate grouping.
- FR-4: Keep the single MPA footer and usage aggregation. Content-bearing usage/progress events must still reach the renderer; empty control events must not erase an existing preview. No auth, API routing, cloud deployment, persistence schema or general-agent grouping change.

## Tasks and acceptance
T-1/AC-1: first add failing general-follow-up and mixed-commentary tests, backend distinct/thought/exact/partial/task-isolation tests, and MPA view exact/extended/live-history/feedback tests.
T-2/AC-2: remove obsolete generic filtering, implement narrow backend equality and non-destructive MPA view filtering; update runtime diagnostics CON-8/CON-11 and tool activity contracts in both languages.
T-3/AC-3: affected frontend/Python tests, full frontend suite/build/assets, Ruff/Pyright, secret scan, browser replay with actual projector/grouping/Blocks; record live activation separately. No server restart without a concrete decision because it loses the local A2A session index.

## Review and risks
Direct review substitutes for unavailable review-spec; source and contracts inspected, bilingual parity reviewed, no blockers. User “修正吧” authorizes this correction. Streaming text equal to the final is hidden only in the derived view and reappears intact if extended. Missing runtime history cannot be reconstructed. General agents deliberately retain their original tool commentary behavior. Failure/cancellation does not erase distinct partial output. Existing supplementary trace/copy/share handlers remain unchanged.

## Verification
Verified 2026-09-22 on the working diff based on `3bbd260a`. T-1 through T-3 implemented and reviewed. Existing generic tool implementation and tests are restored to `origin/main`; the new preservation suite replaces the removed broad-suppression assertions. Exact view filtering is reversible and preserves non-text blocks and the visible feedback target.

- `pass`: red baseline reproduced seven backend failures; frontend counterexamples reproduced generic follow-up/commentary loss and absent scoped final metadata. A fixture assertion was corrected to inspect concatenated text rather than require a separate block.
- `pass`: `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q` — 126 tests, five existing SDK deprecation warnings.
- `pass`: `npm --prefix frontend test` — 1,298 Node and 25 Vitest tests, including six new preservation cases and unchanged general Codex regressions.
- `pass`: `npm --prefix frontend run build` and `npm --prefix frontend run test:webui-assets`; TypeScript and app/widget build, 104 files and 248 references. Existing chunk-size warnings remain.
- `pass`: Ruff 0.11.12 check/format and Pyright on `veadk/cli/runtime_a2a_stream.py` and `tests/cli/test_runtime_a2a_stream.py`, zero type errors/warnings. Temporary `uv run --with` tools used without changing dependencies/global settings.
- `pass`: isolated real-browser replay using fixture events projected by the actual Python bridge, actual TypeScript projection/grouping and Blocks. Exact final/prefix mirror shows one answer; extended text shows its entire prefix and unique warning. No browser errors; temporary fixture/server removed. This is simulated data, not a live cloud generation.
- `pass`: scoped gitleaks, paired-language/contract review and `git diff --check`.
- `not_run`: backend activation and live cloud generation; awaiting the user's restart decision because existing process-local A2A session indexes would be cleared. Code tests do not imply activation on port 8000.
- `not_applicable`: new layout/IME/keyboard behavior, broader SDK/sidecar changes; rendering structure and input controls unchanged. No commit or push performed.
