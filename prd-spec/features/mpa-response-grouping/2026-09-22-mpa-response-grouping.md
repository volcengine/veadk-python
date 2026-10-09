# MPA A2A response grouping

[中文版](2026-09-22-mpa-response-grouping.zh.md)

## Scope and evidence
ID: `mpa-response-grouping`; date: 2026-09-22; status: implemented.
Contract: [runtime diagnostics CON-11](../../../specs/studio-runtime-diagnostics/README.md).
The transcript renders each projected assistant turn with its own footer. Outer reasoning and sandbox final turns therefore have separate actions. TraceDrawer already retrieves session spans through an end timestamp. The user approved one response area with a unified footer, preserving general-agent behavior.

## Requirements and scenarios
- FR-1: Only explicitly identified MPA A2A apps group adjacent assistant fragments between user/system boundaries. Keep raw events/turns unchanged. General ADK/A2A, native MPA and parallel-agent layout retain their defaults.
- FR-2: Preserve ordered reasoning, tools, text, attachments, errors and auth cards within one response; a stable first-fragment key avoids remounting during streaming. Hide the single footer until request presentation completes or authorization resolves. Cancellation/failure preserve partial content and existing error handling. A subsequent user request is independent.
- FR-3: Copy/share cover the grouped answer/region; feedback and annotation retain the last answer-bearing event identity. Unified trace uses the latest available fragment timestamp, preserving session spans from all phases; this is not a new per-request trace API.
- FR-4: Record reported A2A usage deltas once per source/event identity, merge request ledgers instead of summing duplicated fragment snapshots. Include metadata-only and trailing usage. Missing event identity uses source/request/invocation and usage value as a conservative replay key. For older turns without ledgers, retain max reported tokens per invocation (or one unidentifiable source), never invent missing worker usage. No billing accuracy or reconstructed missing history claim.

## Design and boundaries
A pure presentation helper in `transcriptRows.ts` derives grouped turns. App renders and annotates this view, while persistence/stream updates operate on source turns. The MPA-only projector records a usage ledger in optional TurnMeta fields; late usage updates the most recent projected turn without changing completion. Existing Blocks, actions, trace drawer and styles are reused; no new dependency, API/auth/backend/cloud change. Frontend design skills referenced by SPEC were not found at repository/global locations; follow existing components and SPEC directly without redesign.

## Tasks and acceptance
T-1 / AC-1 (FR-1,2): failing tests for grouping, stable identity, user/system boundaries, default identity, running/completed/cancelled content.
T-2 / AC-2 (FR-3,4): failing tests for live/history usage including replay, trailing/early metadata, copy/feedback target, latest trace timestamp; wire presentation and annotations to the same derived view.
T-3 / AC-3: full frontend tests, build/assets, isolated real-browser normal/running/empty/error/narrow/keyboard checks, bilingual docs and secret scan. No real cloud creation needed; live cloud generation reported separately.

## Review and authorization
User's “改改看” approves the previously proposed MPA-only grouping. Direct review (review-spec unavailable): no source-turn mutation, no cross-request grouping, existing trace API retained, source-keyed usage, explicit default opt-out, no secret persistence; bilingual consistency checked. No blockers. Risks: missing usage identities cannot distinguish identical unlabelled calls; missing history stays missing. No commit/push/restart is authorized by this design.

## Verification
Verified 2026-09-22 against the working diff based on `3bbd260a`, including prior uncommitted changes. T-1 through T-3 / AC-1 through AC-3 completed. Direct implementation review: presentation and annotation use the same grouped view; writes still target raw turns and original feedback event IDs; general mode returns the original array; source usage snapshots do not multiply across fragments. No blocking findings.

- `pass`: test-first baseline failed before implementation; nine new `frontend/tests/mpaResponseGrouping.test.mjs` tests cover boundaries, stable keys, partial/error/auth content, general defaults, usage replay and continuation, live/history and App wiring.
- `pass`: `npm --prefix frontend test` — 1,296 Node tests and 25 Vitest tests. Existing source-wiring assertions were updated for `transcriptTurns` after the first run exposed stale variable-name expectations.
- `pass`: `npm --prefix frontend run build` — TypeScript and both app/widget builds; existing chunk-size warnings remain.
- `pass`: `npm --prefix frontend run test:webui-assets` — 104 files and 248 references.
- `pass`: isolated browser fixture with actual grouping and Blocks, simulated footer actions: one MPA region/footer and 300 reported tokens (100 outer + 200 worker), running footer hidden, general control stays split, empty and stopped/error cases retain content. Keyboard activates the sample trace action; width 390 has no horizontal overflow; no console errors. This does not prove live trace contents or image export. Temporary files/server removed and viewport reset.
- `pass`: actual Studio `/index.html` loads `index-c5Xo62sv.js`, connects the selected MPA through A2A, and displays a usable composer. Backend not restarted.
- `pass`: scoped gitleaks over changed source/tests/docs and app/widget assets; `git diff --check`; paired documents and relative links reviewed.
- `not_run`: new cloud model generation, real trace retrieval, clipboard/image export end-to-end. Their underlying handlers remain unchanged; new derived targets are covered by tests. No claim of newly captured cloud output.
- `not_applicable`: Python and harness/sidecar gates (no backend/protocol/sidecar changes), input IME changes (composer untouched). No commit/push performed.
