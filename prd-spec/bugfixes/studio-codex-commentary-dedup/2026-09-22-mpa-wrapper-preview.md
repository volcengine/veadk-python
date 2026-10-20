# Preserve MPA preview replacement after wrapper completion

[中文](2026-09-22-mpa-wrapper-preview.zh.md)

- ID: `mpa-wrapper-preview`
- Date: 2026-09-22
- Status: implemented; original-session verification pending
- Component: [Studio tool activity](../../../specs/studio-tool-activity/README.md)
- Earlier attempt: [Codex tool final ownership](2026-09-22-studio-codex-commentary-dedup.md)

## Evidence and scope

The user reports an unchanged duplicate answer separated by a reasoning block. The earlier attempt assumed `delegate_to_codex_sandbox`; inspection of `client.ts` confirms native MPA endpoints use `/api/v1/sessions/{id}/run` and `/sse`. The local agentkit-mpa-agent implementation projects `message.delta`, `thought.completed`, and `invocation.completed` with sandbox metadata. The user's raw session is still unavailable; this is a contract-derived reproduction, not a captured production trace.

Studio reproduces two answers with this sequence: `sandbox_task` call, sandbox answer delta, wrapper `finalAlreadyEmitted: true`, completed thought, sandbox final. The wrapper advances `liveStart` to the block count, incorrectly committing the preview. The later authoritative answer is appended to the committed preview.

## Requirements and design

- **FR-1:** A wrapper completion closes the parent tool and thinking but preserves the existing preview boundary. It must not commit or discard streamed answer text.
- **FR-2:** A later consolidated event replaces the preview using existing ADK projection rules. The authoritative answer may differ from the preview; no text-equality heuristic is needed.
- **FR-3:** If the transport ends without a durable final, the preview remains visible and completed. Tool failures/results, history without partials, other invocations, and ordinary agents keep their existing behavior.

Change only the `isFinalAlreadyEmittedSandboxResponse` branch in `frontend/src/blocks.ts`. Add regressions to `frontend/tests/parallelStreamAggregation.test.mjs`; update paired component contracts and regenerate `veadk/webui`. No backend, transport, persisted data, permissions, inputs, styles, or deployment changes. Do not redesign the separate delegate-tool implementation in this follow-up.

## Tasks and acceptance

1. **T-1 / AC-1:** Add a failing regression for wrapper-before-final ordering, including an intervening completed thought and changed final text. Exactly one authoritative answer remains.
2. **T-2 / AC-2:** Preserve the preview boundary; verify wrapper-only finish retains the answer and completes the tool. Verify history parity and ordinary chat regressions.
3. **T-3 / AC-3:** Run targeted and full frontend tests, typecheck, build/assets checks, and browser replay. Record outcomes and limitations in both languages.

## Review, authorization, and risks

The user has repeatedly authorized fixing this same duplicate-display issue. Direct design review (review-spec unavailable) finds the change local to the MPA wrapper marker and consistent with existing preview semantics. No new scope or external operation needs approval. Risk: later events can replace live preview text; this is intentional consolidation behavior, and transport-only finish must retain it. The production screenshot alone cannot establish that this particular ordering caused it; raw-session verification remains outstanding.

## Verification

- **pass:** Before editing, a standalone replay of the contract-derived sequence produced text, thinking, duplicate text in one turn.
- **pass:** Test-first regression: all 4 new cases failed before the one-line boundary fix, then passed. `node --test frontend/tests/parallelStreamAggregation.test.mjs frontend/tests/toolActivityModel.test.mjs frontend/tests/codexSandboxProgress.test.mjs`: 70 passed.
- **pass:** `npm --prefix frontend test`: 1,261 Node tests and 25 Vitest tests; no skipped Node tests. Typecheck: `npx tsc --noEmit -p tsconfig.json` from frontend.
- **pass:** `npm --prefix frontend run build`, `npm --prefix frontend run test:webui-assets` (104 files, 248 references), and `git diff --check`. Existing build chunk-size/import warnings remain.
- **pass:** Browser replay using actual `eventsToTurns` and `Blocks` with the contract-derived fixture: running preview, wrapper-only finish, completed answer, durable history, ordinary-agent answer, and 360px content width. One answer is visible and console errors are empty. Temporary fixture and Vite server removed.
- **pass:** Local Studio was found serving a cached old entry because `_index_html` is read at process startup. Restarted using the original `uv run veadk studio` command (omitting automatic browser opening); rebuilt entry is `index-i19v0vDQ.js`.
- **not_applicable:** Backend, input/IME, network retries/cancellation UI, and cloud execution gates: this follow-up only changes preview consolidation. No commit/push requested; commit-time gates not run. Existing related and unrelated working-tree changes were preserved.
- **blocked:** Raw-session verification pending the session URL/identity requested from the user.

Review on 2026-09-22: no text matching, cross-agent state, or stored data changes were introduced. T-1–T-3 and AC-1–AC-3 pass for the reproduced native-event sequence; the original session remains explicitly unverified.
