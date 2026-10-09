# MPA A2A final-answer ownership

[中文](2026-09-22-mpa-a2a-final.zh.md)

- Date: 2026-09-22
- ID: `mpa-a2a-final`
- Status: implemented; local server activation pending
- Components: [Runtime diagnostics CON-8](../../../specs/studio-runtime-diagnostics/README.md), [Studio tool activity](../../../specs/studio-tool-activity/README.md)

## Evidence and background

Read-only inspection of the user's completed v7 A2A task found a sandbox artifact with 57 thought deltas, 14 answer deltas, one usage update, and one `invocation.completed` whose payload contains `finalMessage`. Concatenated answer deltas and finalMessage have identical hashes. A separate artifact holds the outer function response. The restored session exposes one final answer. No credentials, original task identifiers, or private event bodies are retained in fixtures.

`runtime_a2a_stream._sandbox_event` ignores `finalMessage`; sandbox deltas carry invocationId while the outer result does not. The frontend therefore places these answer copies in different accumulators. Previous fixes for delegate-tool activity and native MPA session wrappers do not cover this A2A bridge.

## Goals, non-goals, and requirements

- **FR-1:** Project a nonempty sandbox `invocation.completed.payload.finalMessage` as the authoritative consolidated, completed answer, retaining the sandbox invocation identity.
- **FR-2:** Once that successful answer is projected, suppress later outer text/thought/result mirrors for the same known A2A task. Preserve sandbox tool events, errors and usage accounting. Do not compare arbitrary answer text or affect ordinary ADK/native session paths.
- **FR-3:** Project each identified sandbox source event at most once per task across streaming updates and task snapshots. Other tasks and legacy non-MPA A2A streams retain existing behavior.
- **FR-4:** A failed/cancelled invocation or an empty final must not claim answer ownership. A stream without a sandbox final keeps its existing fallback behavior. Finalizing an already consolidated sandbox answer must not synthesize another answer.

Non-goals: authentication/deployment changes, fixing the separate transient discovery error, changing worker generation, hiding arbitrary reasoning, or modifying stored task data.

## Design and affected files

In `veadk/cli/runtime_a2a_stream.py`, add successful sandbox-final projection and decoder-local ownership keyed by A2A task ID. Track projected sandbox event IDs by task to handle replay without treating mutable outer artifact IDs as immutable events. Filter only outer projected text after ownership; metadata-only usage/status continues. State lives only for the request's decoder, so cancellation or disconnect discards it normally. The existing stream boundary and network timeouts do not change.

Tests in `tests/cli/test_runtime_a2a_stream.py` model the observed sandbox delta/final plus outer result shape. A sanitized Python-to-TypeScript projection replay checks the actual frontend accumulators. Update the paired component spec; frontend release artifacts are required only if frontend production code changes.

## Tasks, tests, and acceptance

- **T-1 / AC-1:** Failing test proves sandbox final was missing and duplicate outer result survives; final result must have one authoritative answer.
- **T-2 / AC-2:** Cover late outer reasoning, same/different text mirrors, replayed sandbox final/task snapshot, task isolation, tool/usage preservation, empty finals, failure/cancellation, and legacy A2A fallback.
- **T-3 / AC-3:** Run targeted Python bridge/proxy tests, Ruff/Pyright on changed Python files, cross-layer/browser replay, and relevant frontend regression. Record actual gates and remaining live limitations.

## Review and authorization

The user explicitly asked to continue fixing the original duplicate after discovery recovered. This implements that existing scope using verified task evidence. Direct design review (review-spec unavailable) confirms no public request schema or cloud state change; the intended change is the A2A projection contract. Successful nonempty finals alone own the answer. Risk: an outer model's later reformulation is omitted intentionally after delegated completion. A task must emit its sandbox final before the outer mirror, as the inspected executor does. Missing IDs cannot safely establish cross-event ownership.

## Verification

- **pass:** Read-only task structure inspection; no new agent execution.
- **pass:** Before implementation, three new regression cases failed (32 existing/negative cases passed).
- **pass:** `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q`: 121 passed, five existing SDK deprecation warnings.
- **pass:** Ruff 0.11.12 check and format check plus Pyright on both changed Python files (zero errors/warnings). The repository environment lacks standalone Ruff/Pyright executables; `uv run --with ruff==0.11.12 ...` and `uv run --with pyright ...` supplied temporary tools without modifying project dependencies or global configuration.
- **pass:** Python-to-TypeScript replay using the observed protocol shape and placeholder text: HEAD bridge produces two answer blocks in two turns; fixed bridge produces one answer block in one turn. Real browser replay with production `eventsToTurns` and `Blocks` confirms that difference; no browser console errors. This reconstructed fixture is not a complete captured SSE trace.
- **pass:** Related frontend projector/activity regressions: 70 tests. `git diff --check`; paired documents and links reviewed. Temporary browser fixture and Vite server removed.
- **pass:** Repository pre-commit `gitleaks` hook for this follow-up's changed code/document files; no hardcoded secrets detected.
- **blocked:** A further full raw-task replay query returned intermittent HTTP 429/500. Earlier successful read-only task structure/hash evidence is recorded above; no live generation was triggered.
- **not_run:** Activation on the user's local Studio process requires restart. A2A task/session mappings are currently process-local; restart clears that local history index without deleting remote tasks. Await user agreement before this disruptive step. No cloud deployment, commit or push.
- **not_applicable:** Frontend build/IME/layout/network lifecycle changes: this follow-up changes the Python projection only; previous frontend assets remain intact. Broader unrelated Python suites are omitted because the affected bridge and Runtime proxy suites cover this change.

Implementation review on 2026-09-22 confirms task-scoped successful-final ownership, replay identity isolation, legacy payload fallback and preservation of usage/tools. T-1–T-3 and AC-1–AC-3 pass for the recorded regression and replay scope; production activation remains pending.

> The broad suppression rules are superseded by [preserving follow-up content](2026-09-22-preserve-followup-content.md). Historical verification below describes the earlier behavior.
