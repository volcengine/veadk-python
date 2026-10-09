# MPA A2A reasoning snapshots and empty-response notices

[中文版](2026-09-22-mpa-a2a-reasoning.zh.md)

## Metadata and evidence
- ID: `mpa-a2a-reasoning`; date: 2026-09-22; status: implemented.
- Contract: [Studio runtime diagnostics](../../../specs/studio-runtime-diagnostics/README.md), CON-10.

The user reports one final answer, repeated outer reasoning and an empty-response notice preceding sandbox tools. Read-only task inspection confirms successful completion and a nonempty sandbox final. App.tsx displays the empty notice for each finalized reasoning-only turn independently. The A2A bridge marks consolidated outer reasoning with `projectionSource=a2a-artifact`; repeating such snapshots after the preview boundary is committed appends the same full thought again. Exact live SSE chronology is not captured; tests use the observed event contract, not raw production text.

## Goals, scope and requirements
- FR-1: Enable the change only for a registered Runtime app `a2a-default` with MPA category/instance metadata. General ADK, general A2A, local agents and native MPA use existing behavior.
- FR-2: In the opted-in projector, a nonpartial, reasoning-only `a2a-artifact` snapshot matching or extending the adjacent prior reasoning block replaces that block. Preserve distinct thoughts, token deltas, sandbox reasoning, tools, attachments and errors. Never deduplicate arbitrary model text.
- FR-3: Only for MPA A2A, decide empty response across assistant fragments between two user messages. No notice while that request runs/presents, or when any fragment has visible content. A genuinely empty completed request retains one notice at its last nonempty fragment. Previous requests remain independent. General agents retain the old per-turn rule.
- FR-4: Live streams, history replay and auth continuation use the same explicit projector option, with state scoped to one request. No auth, API routing, cloud deployment or backend modification.

## Design, tasks and acceptance
T-1 / AC-1: add failing projector tests for repeated/extended snapshots, live/history, two requests, tools and default/general behavior. T-2 / AC-2: add empty-notice tests for running, success, empty, cancelled, multiple user messages and general behavior. T-3 / AC-3: wire `frontend/src/adk/client.ts`, `blocks.ts`, `App.tsx` and a small pure transcript helper, run targeted/full frontend tests, build, assets and browser checks; update README and paired contract. Existing cancellation/errors remain unchanged and are not converted to successful empty output.

## Review, authorization and risks
The user explicitly approved fixing these symptoms while preserving general-agent behavior. Direct review substitutes for unavailable review-spec: opt-in protocol/category gates, no default projection changes, no cross-request state, no credential changes, bilingual parity reviewed. No blockers. Risk: incomplete captured chronology; bounded snapshot reconciliation must not remove distinct reasoning or partial deltas. Existing persisted task restoration may contain final text only; missing history is not reconstructed. No visual design changes.

## Verification
Verified on 2026-09-22 against the working diff based on `3bbd260a`, including existing uncommitted changes. T-1 through T-3 are complete. Direct implementation review confirmed opt-in gating at all five projection entry points, independent user-request boundaries, and preserved default behavior; bilingual requirements and contract are aligned.

- `pass`: test-first baseline reproduced the duplicate snapshot (six failures before implementation, five from the missing empty-notice helper); focused regressions now pass as part of the full suite.
- `pass`: `npm --prefix frontend test` — 1,287 Node tests and 25 Vitest tests.
- `pass`: `npm --prefix frontend run build` — TypeScript and app/widget builds. Initial incorrect argument placement and ES2020-incompatible array access were corrected before the successful run; existing chunk-size warnings remain.
- `pass`: `npm --prefix frontend run test:webui-assets` — 104 packaged files and 248 references.
- `pass`: isolated browser fixture using the actual projector, notice helper and Blocks renderer — one MPA reasoning snapshot/final, no intermediate or running empty notice, one genuine empty notice, unchanged general-agent control; no console errors. Temporary fixture/server removed.
- `pass`: browser at `http://127.0.0.1:8000/index.html` loaded the rebuilt `index-BoFYrKMR.js`; no backend restart. The running process caches `/` HTML, so use `/index.html` to load new assets.
- `pass`: scoped `uv run --with pre-commit pre-commit run gitleaks --files ...` and `git diff --check`.
- `not_run`: new live cloud model generation/full captured SSE replay; browser cases use contract-derived simulated events. Verify the user's next real message separately.
- `not_applicable`: Python gates, keyboard/IME and responsive-layout changes; this increment changes neither backend code nor controls/layout. Cancellation/request-boundary behavior is covered by regression tests. No commit/push requested or performed.
