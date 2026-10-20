# Studio Codex final-answer ownership

[Chinese](2026-09-22-studio-codex-commentary-dedup.zh.md)

- ID: `studio-codex-commentary-dedup`
- Created/revised: 2026-09-22
- Status: superseded
- Component: [Studio tool activity](../../../specs/studio-tool-activity/README.md)

## Background and evidence

**Evidence correction (2026-09-22):** The following diagnosis assumed the delegate-tool path without the user's raw events. Native MPA uses its own session SSE endpoint; this attempt does not establish a fix for the reported MPA session. See the [native MPA follow-up](2026-09-22-mpa-wrapper-preview.md). Earlier synthetic checks remain valid only for their tested event format.

The legacy `arkclaw-team -> mpa-agent` path gives the delegated Codex result one final-answer owner. `mpa-agent` marks the completed sandbox invocation, stops later top-level model text, and filters duplicate model text from SSE/history. The current `Studio -> agentkit-mpa-agent` path uses the dynamically injected `delegate_to_codex_sandbox` tool instead. VeADK already sets `skip_summarization` for a successful tool result, but Studio preserves a visible Codex commentary item and separately appends the function response `message` as the final answer.

A reproduced turn contains the same complete answer before tool activities and after them. The first copy is a commentary activity and the second is the authoritative direct answer. Existing final-event filtering removes nested `assistant_final` events but intentionally preserves commentary, so it does not cover this case.

The first exact-match fix was insufficient against the live sequence. Codex may also emit completed reasoning that contains the full final answer, and the outer model may emit more reasoning and answer text after the successful function response. The legacy path treated the delegated response as the turn's final-answer owner; Studio needs the same ownership boundary rather than only comparing one commentary block.

## Goals and non-goals

### Goals

- Show one authoritative final answer after a successful Codex delegation, including when activity reasoning contains that answer or the outer model emits later text.
- Apply the same rule to live progress and persisted `codex_activity` replay.
- Preserve commands, searches, file changes, failures, distinct activity that does not repeat the final answer, and the final answer.

### Non-goals

- Changing Codex generation, app-server event schemas, Studio Channel transport, or `agentkit-mpa-agent`.
- Fuzzy, semantic, or cross-turn deduplication.
- Hiding command output that independently contains the same words.
- Changing ordinary chat turns or calls to tools other than `delegate_to_codex_sandbox`.

## Scenarios

1. A commentary item contains `Result`, tool activities follow, and the successful response message is `Result`: Studio removes the commentary item and renders one final `Result`.
2. Completed Codex reasoning contains the full `Result`: Studio omits that redundant reasoning item while keeping adjacent commands and searches.
3. The outer model emits reasoning and answer text after the successful Codex function response: Studio retains the delegated response and ignores those later model text parts in the same turn.
4. Commentary says `Checking the skill` and the final response says `Result`: both remain visible.
5. A general agent uses ordinary chat or another tool: its reasoning and answer projection remain unchanged. A general agent that explicitly invokes `delegate_to_codex_sandbox` receives the same tool-scoped final-owner behavior.
6. A failed or busy Codex response contains a message: existing behavior remains and no direct answer is synthesized.

## Requirements and design

- **FR-1 — Delegated final-answer ownership.** A successful `delegate_to_codex_sandbox` response with a non-empty `message` owns the final answer for that assistant turn. Once projected, later outer-model text and thought parts in the same turn are ignored.
- **FR-2 — Call-scoped activity reconciliation.** After hydrating the matched tool's activity snapshot, omit commentary or reasoning blocks whose boundary-trimmed text contains the complete boundary-trimmed final answer verbatim. Do not use fuzzy or semantic matching.
- **FR-3 — Preserve structured and unrelated activity.** Keep commands, searches, file changes, plans, authorization, failures, and activity text that does not contain the complete final answer. Never inspect command output for this rule and never alter another tool block.
- **FR-4 — Tool scope.** Apply final ownership only when a successful `delegate_to_codex_sandbox` result is present. Ordinary model chat and every other tool keep their existing projection behavior, regardless of agent category.
- **FR-5 — Live/history parity and idempotence.** Apply the same reconciliation to live progress plus response hydration and persisted history. Replaying the response or receiving a later wrapper-model answer must still produce one final answer.

Implementation uses a pure activity transformation in `frontend/src/ui/builtin-tools/codexSandboxProgress.ts` and invokes it from the matched Codex function-response branch in `frontend/src/blocks.ts` before the authoritative answer is appended. The turn projector derives final ownership only from a completed successful Codex tool response and suppresses subsequent unstructured model text/thought parts while continuing to process structured events. The transformation returns the original activity object when no item changes.

This changes the maintained `studio-tool-activity` transcript contract and therefore updates both component-spec languages. It does not change transport, backend, persistence, authorization, or public API contracts.

## Affected files and tasks

- `frontend/src/ui/builtin-tools/codexSandboxProgress.ts`: add the pure call-local deduplication helper.
- `frontend/src/blocks.ts`: apply it after response hydration and before final-answer projection.
- `frontend/tests/codexSandboxProgress.test.mjs`: add regression coverage for equal and distinct commentary.
- `specs/studio-tool-activity/README.md` and `README.zh.md`: record the final-answer ownership rule.
- `veadk/webui`: regenerate the packaged frontend. `.gitattributes` applies the existing generated-JavaScript whitespace exception to `website-integration.js` too, preserving semantic whitespace inside bundled template literals.

| Task | Requirement | Acceptance |
| --- | --- | --- |
| T-1: add failing projection tests | FR-1–FR-5 | The reported commentary/reasoning/late-answer sequence reproduces repeated output; unrelated-tool fixtures retain normal text |
| T-2: implement tool-scoped final ownership | FR-1–FR-5 | The regression passes without changing structured activity or ordinary chat |
| T-3: verify and reconcile bilingual documents | All | Targeted test, full frontend tests, TypeScript/build, assets, i18n, and diff checks are recorded |

## Tests

- Targeted: `node --test frontend/tests/codexSandboxProgress.test.mjs`.
- Frontend regression: `npm --prefix frontend test`.
- Build and generated assets: `npm --prefix frontend run build` and `npm --prefix frontend run test:webui-assets`.
- Localization: `npm --prefix frontend run check:i18n`.
- Real browser: reproduce a Codex turn containing equal commentary/final text; verify one answer, preserved tool activities, replay after reload, and distinct-commentary behavior.

## Risks

- A short final answer may occur inside a longer reasoning item. Omitting that completed reasoning is acceptable because the same successful delegation has already supplied the user-visible answer; structured execution evidence remains visible.
- Boundary trimming plus verbatim containment covers the reported self-talk without semantic comparison or Markdown normalization.
- Suppressing all later model text could affect unrelated turns if scoped broadly. Ownership is therefore derived only from a successful Codex tool response in the current accumulator and does not cross turns, sessions, or other tools.

## Acceptance criteria

- AC-1: The reproduced `commentary -> reasoning containing answer -> tools -> successful response -> outer reasoning/final` turn displays the answer once.
- AC-2: Structured activity and distinct commentary/reasoning remain ordered and visible.
- AC-3: Ordinary chat, non-Codex tools, and failed/busy Codex calls retain their existing projection behavior.
- AC-4: Live and persisted response paths produce the same blocks, including response replay.
- AC-5: Required automated checks pass; any unavailable browser check is reported as blocked or not run.

## Review and approval

The user approved the original exact-match implementation and then approved the expanded tool-scoped final-ownership plan on 2026-09-22 after the live counterexample and general-agent boundary were explained. Direct design review was used because no `review-spec` skill is available. The review found the solution deterministic, backward compatible at the transport boundary, isolated to successful Codex delegation, free of credential/data changes, and testable in the existing projector suite. No blocker remains.

## Verification

Execution date: 2026-09-22. Scope: the working-tree fix based on `3bbd260a` on `codex/from-main-20260921`.

- **pass** — Test-first regression: the expanded duplicate-activity test and late-event/history test failed before implementation and passed afterward.
- **pass** — From `frontend`, `node --test tests/codexSandboxProgress.test.mjs tests/parallelStreamAggregation.test.mjs`: 39/39 tests. Coverage includes live activity, persisted snapshots, repeated responses, late model text/thought, ordinary tools, separate authors/invocations, next user turn, unfinished success, failed/busy/cancelled/timeout responses, and existing parallel-turn behavior.
- **pass** — `npm --prefix frontend test`: 1,258 Node tests and 25 Vitest tests. The later cancellation/timeout fixture extension passed in the targeted rerun above.
- **pass** — From `frontend`, `npx tsc --noEmit -p tsconfig.json`; `npm run check:i18n` (2 locales, 21 namespaces).
- **pass** — `npm --prefix frontend run build` and `npm --prefix frontend run test:webui-assets`: 104 files and 248 references validated. Build warnings concern existing mixed imports and large bundles.
- **pass** — Isolated real-browser rendering with the production `eventsToTurns` and `Blocks` modules and synthetic events: running-to-completed transition, late duplicate output, history replay, distinct commentary and command preservation, ordinary chat, failed response, keyboard selection, and a 360-pixel content column. The completed result contained one final answer; browser error logs were empty. The temporary fixture and development server were removed afterward.
- **pass** — Local Studio on port 8000 serves the rebuilt `index-WJxKEjkM.js` entry. This confirms the served version, not an already-open tab's cached version.
- **pass** — `git diff --check`; bilingual requirements/identifiers and relative links reviewed.
- **not_run** — Live cloud MPA reproduction: the actual failing session's raw event envelope was not available. The browser and unit checks model the reported sequence and do not establish that the online session uses this delegate tool.
- **not_applicable** — Python, IME/input, and request cancellation UI gates: no backend, input, or request lifecycle code changed. Cancellation result projection is tested. Commit-time pre-commit gates have not run because no commit is requested.

Direct implementation review found final ownership confined to the current assistant author/invocation state until transport finish or a new user round. Structured tool activity and separate authors/invocations remain intact. T-1–T-3 and AC-1–AC-5 are satisfied by the recorded checks, with live-cloud verification explicitly outstanding.

> The broad suppression rules are superseded by [preserving follow-up content](2026-09-22-preserve-followup-content.md). Historical verification below describes the earlier behavior.
