# Studio Tool Activity Visualization Design

- **Status:** Implemented and verified
- **Date:** 2026-09-12
- **Change type:** Feature
- **Chinese version:** [2026-09-12-studio-tool-activity-visualization-design.zh.md](2026-09-12-studio-tool-activity-visualization-design.zh.md)
- **Target branch:** `feat/mpa-agent-oneclick-provision`

## 1. Overview

### 1.1 Problem

AgentKit Studio already receives structured ADK tool calls and mpa-agent sandbox progress, but generic tool calls fall back to formatted JSON. One logical sandbox command may also appear as an outer delegation card plus inner `exec_command` and `commandExecution` rows. Users can inspect the protocol, but cannot quickly answer the operational questions that matter: what is running, what command or resource is involved, what output has arrived, whether it succeeded, and how long it took.

The current implementation already contains useful foundations: `Block.kind === "tool"`, stable `callId` matching, `CodexSandboxActivity`, built-in tool registration, and a shared `eventsToTurns()` history projection. This feature must extend those foundations instead of adding a second transcript model.

### 1.2 Goals

- Replace default JSON-first tool rendering with compact Codex-style activity units.
- Use one visual shell for all tools and type-specific detail presenters for commands, reads, searches, file changes, MCP calls, and generic tools.
- Merge tool start, output, result, and error events by stable identity into one updating unit.
- Flatten sandbox-internal activity into the conversation timeline while retaining a lightweight `Codex Sandbox` source label.
- Keep running activity visible, successful activity compact, and failures immediately diagnosable.
- Guarantee that live projection and persisted history reconstruction produce equivalent tool content and ordering.
- Preserve existing specialized cards, session history, search, feedback, attachments, artifacts, A2UI, parallel agents, and final answers.

### 1.3 Non-goals

- Changing the mpa-agent/A2A/ADK event protocol or database schema.
- Persisting disclosure state or other presentation-only state to a session.
- Replacing existing specialized renderers such as `create_agents` and `branch_compare`.
- Implementing an unrestricted JSON inspector or exposing values removed by backend redaction.
- Synthesizing fake streaming chunks when the upstream model emits only a final response.
- Redesigning the conversation page, navigation, or global Studio visual language.

## 2. User Scenarios

### Scenario 1: Follow a running command

**Given** a tool starts a sandbox command and streams output,
**When** Studio receives start and output events,
**Then** one expanded activity unit updates in place with the command, elapsed time, and recent output instead of adding JSON rows.

### Scenario 2: Review a completed conversation

**Given** a session contains persisted function calls, responses, or a Codex activity snapshot,
**When** the user refreshes Studio or switches back to the session,
**Then** the same ordered, structured activity units are reconstructed without duplicate calls or missing final text.

### Scenario 3: Diagnose a failure

**Given** a command or tool fails,
**When** its terminal event arrives or history is restored,
**Then** the activity remains expanded and shows a concise error, status or exit code, retained output, and a secondary raw-data disclosure.

### Scenario 4: Read a tool-heavy conversation

**Given** an agent performs multiple adjacent successful read-only operations,
**When** those operations complete,
**Then** Studio may collapse them into one “Explored N items” group while preserving each child operation and its raw data.

## 3. Functional Requirements

### FR-1 — Unified activity shell

Every ordinary tool activity uses the same header geometry: icon, explicit status marker, localized action title, one-line summary, compact metrics, and disclosure affordance. Color supplements but never replaces text or icon semantics.

### FR-2 — Presentation model

Tool rendering is derived through a pure presentation layer. The source `Block` retains raw `args` and `response`; React rendering does not contain ad hoc JSON-shape inference. The presentation model includes category, title, summary, status, source, duration, exit code, typed details, and raw values.

### FR-3 — Lifecycle correlation

Start, output, result, and error updates with the same stable `callId` update one activity unit. Replayed `eventId` values are ignored. Out-of-order results are buffered when safely correlatable; otherwise they remain visible as an unmatched generic activity instead of being discarded.

### FR-4 — Adaptive disclosure

- Queued/running activities default open.
- Successful activities default closed after completion.
- Failed activities default open.
- Once the user manually toggles an activity, later updates must not override that choice.
- Restored history initializes from final status and does not persist transient disclosure state.

### FR-5 — Typed presenters

The initial presenter set is:

| Category | Header summary | Expanded content |
| --- | --- | --- |
| Command | normalized command | command, working directory, stdout/stderr, exit code, duration |
| Read/list | file or resource count | paths, ranges, omission marker |
| Search | query and result count | matched paths/items and snippets |
| File change | file count and diff totals | path, add/update/delete action, diff summary |
| MCP | `server/tool` and result count/status | selected inputs and structured result |
| Authorization | requested resource/tool | explanation and primary authorization action |
| Generic | tool name and best-effort summary | readable key-value fields |

Authorization keeps its existing dedicated interaction instead of becoming a passive collapsible row. Existing specialized tool renderers remain authoritative.

### FR-6 — Codex Sandbox flattening

Nested `CodexSandboxActivity.items` are projected as first-class activity units in the current assistant turn. The outer `delegate_to_codex_sandbox` container is not rendered as a second card when structured child activity exists. A lightweight source label identifies the contiguous activity as `Codex Sandbox`. The final assistant answer stays outside the activity group.

### FR-7 — Safe read-only aggregation

Adjacent completed successful read, list, search, or resource-query activities from the same invocation and source may be grouped as “Explored N items”. Grouping occurs only after completion. Commands, writes, deletions, MCP calls, authorization, failures, cancellations, source changes, invocation changes, and final-answer boundaries end the group. Grouping changes presentation only and preserves the original ordered children.

### FR-8 — Raw data disclosure

Each activity provides a secondary “View raw data” disclosure inside its expanded details. Input and result are separate, formatted lazily, bounded for rendering, and individually copyable together with the call ID. It is closed by default and cannot reveal data removed by upstream allowlists or redaction.

### FR-9 — Output handling

Live command output updates in place. Completed output uses an authoritative aggregate when available. The default preview shows a bounded head and tail with an explicit omitted-line count. Full output uses an independently scrolling region with a height limit. ANSI/control sequences are sanitized or safely rendered; they are never injected as HTML.

### FR-10 — History compatibility

`eventsToTurns()` remains the sole history reconstruction entry point. Live and persisted events use the same normalization and presentation functions. Both camelCase and snake_case payloads remain supported. Missing status, duration, source, or call ID uses safe fallbacks. Unknown legacy tools retain a generic visible activity.

### FR-11 — Responsive and accessible behavior

At narrow widths, secondary summaries hide before titles or status metadata, details become full width, and no horizontal page scroll is introduced. Interactive headers and secondary disclosures are keyboard reachable, expose `aria-expanded`, retain visible focus, and provide at least a 44px effective hit area. Motion is limited to 120–180ms opacity/transform transitions and disabled under `prefers-reduced-motion`.

### FR-12 — Localization

All action, status, omission, copy, and empty/error labels are provided in the existing `conversation` namespace for Chinese and English. Raw tool names remain available only where they carry useful technical meaning or in raw details.

## 4. Design

### 4.1 Data flow

```text
ADK / A2A event
  -> existing applyEvent/eventsToTurns projection
  -> tool lifecycle correlation by callId
  -> pure ToolPresentation derivation
  -> optional read-only presentation grouping
  -> ToolActivityCard + category detail presenter
```

No transport or persistence contract changes. The same source blocks remain available for debugging and backward compatibility.

### 4.2 Proposed modules

- `frontend/src/ui/tool-activity/model.ts`: presentation types, safe accessors, normalization, summaries, output truncation, and grouping predicates.
- `frontend/src/ui/tool-activity/ToolActivityCard.tsx`: common header, adaptive disclosure, copy actions, raw-data disclosure, and accessibility semantics.
- `frontend/src/ui/tool-activity/ToolActivityDetails.tsx`: typed command/read/search/file/MCP/generic presenters.
- `frontend/src/ui/tool-activity/tool-activity.css`: component-local layout and state styles using existing semantic tokens.
- `frontend/src/blocks.ts`: minimal lifecycle correlation and sandbox flattening integration; no JSX.
- `frontend/src/ui/Blocks.tsx`: dispatch tool blocks through the new presenter while retaining registered specialized renderers.
- `frontend/src/i18n/resources/{zh-CN,en-US}/conversation.json`: localized activity labels.

The exact split may be reduced if a module remains trivial, but parsing, state reduction, and React presentation must stay independently testable.

### 4.3 Visual specification

- The activity row aligns with the existing 32px tool header and the transcript's horizontal anchor.
- Effective interactive height is at least 44px without forcing the visible row to become visually heavy.
- Status states use neutral/amber/green/destructive semantic treatments plus explicit labels.
- Commands and output use the existing monospace stack; titles, metrics, IDs, and normal summaries use the system UI font.
- Successful collapsed rows remain border-light or borderless. Expanded detail uses one subtle left rail, not nested card borders.
- Running updates reserve metric space to avoid layout shift.
- Long labels truncate with an accessible full-value affordance; output wraps or scrolls inside its own boundary.

### 4.4 State ownership

Tool lifecycle data belongs to the transcript projection. Disclosure state belongs to the individual rendered activity instance. Read-only grouping is a pure render-time view over adjacent blocks. No view state is written into ADK session state or server storage.

## 5. History Safety Contract

History behavior is a P0 release gate. The implementation must satisfy all of the following:

1. Refreshing a completed session preserves tool order, status, details, and final answer.
2. Switching between sessions does not share disclosure or activity state.
3. Persisted `functionCall` plus `functionResponse` is sufficient to rebuild a complete activity without live progress.
4. Persisted Codex snapshots and live progress do not create duplicate child activities.
5. Missing or legacy fields degrade to a generic activity instead of throwing or hiding the event.
6. Presentation aggregation never mutates source blocks and never crosses an invocation or final-answer boundary.
7. Existing history listing, search, feedback, attachment, artifact, A2UI, and parallel-agent behavior remains unchanged.

If live and replayed output cannot be made equivalent for an event type, the release must retain the existing generic renderer for that type rather than shipping an incomplete specialized view.

## 6. Edge Cases

| Case | Required behavior |
| --- | --- |
| Duplicate start/output/result | Deduplicate by stable event identity and update one unit. |
| Result arrives before start | Buffer by call ID; fall back to a visible unmatched result. |
| Missing call ID | Generate a deterministic projection-local identity where possible; do not merge ambiguous calls. |
| Same tool runs concurrently | Correlate by call ID, never by tool name alone. |
| Long or binary-looking output | Bound preview, preserve omission metadata, offer safe full view when text-renderable. |
| Malformed response | Show a generic “Unrecognized tool result” state plus raw-data access. |
| Running stream disconnects | Preserve the visible received state; history refresh later rebuilds the terminal state without resubmission. |
| User manually collapses running item | Preserve the user's choice during subsequent updates. |
| Specialized renderer throws | Isolate the error to that activity and use the generic presenter; do not break the transcript. |
| Secret-bearing field | Respect server redaction and apply existing client-side sensitive-key masking before raw display/copy. |

## 7. Testing and Acceptance

### 7.1 Unit tests

- Presenter mapping for command, read/list, search, file change, MCP, authorization, and generic tools.
- Lifecycle merge for start/output/result/error, duplicate event IDs, out-of-order events, and concurrent same-name calls.
- Head/tail output truncation, omitted-line count, malformed values, and sensitive-key masking.
- Safe aggregation boundaries and preservation of child order.
- Adaptive disclosure transitions and manual-choice lock.

### 7.2 History regression tests

- Assert live event projection and `eventsToTurns()` replay produce equivalent normalized activity content.
- Refresh sessions containing old camelCase/snake_case tools, missing fields, Codex snapshots, attachments, artifacts, A2UI, and final text.
- Switch repeatedly between two sessions and assert no state leakage or mutation.
- Run all existing history, search, feedback, parallel-agent, and Codex sandbox tests unchanged.

### 7.3 Component and accessibility tests

- Running, completed, failed, empty, malformed, and long-output snapshots.
- Keyboard activation, visible focus, `aria-expanded`, accessible status text, and copy feedback.
- Widths 375px, 768px, 1024px, and 1440px; light and dark themes; reduced-motion mode.
- No body-level horizontal scroll or layout shift during streaming updates.

### 7.4 Real E2E

Using the existing mpa-agent test Runtime:

1. Run a command with delayed output and verify one activity updates in place.
2. Verify successful completion collapses and the final answer remains separate.
3. Run a failing command and verify the error remains expanded.
4. Refresh both sessions and compare content/order with the live views.
5. Run two sessions concurrently and verify no cross-session activity.
6. Verify legacy non-streaming Runtime history still renders.
7. Scan rendered raw data and copied content for configured secrets.

### 7.5 Acceptance criteria

- `AC-1`: No supported tool displays raw JSON as its primary UI.
- `AC-2`: One logical command produces one updating activity unit.
- `AC-3`: Running opens, success collapses, failure stays open, and manual disclosure choice is respected.
- `AC-4`: Command output, exit status, duration, and omission count remain readable and bounded.
- `AC-5`: Safe read-only operations aggregate only within the defined boundaries.
- `AC-6`: Raw input/result/call ID remain available through a secondary disclosure and copy actions.
- `AC-7`: Refresh produces equivalent structured content and preserves final assistant output.
- `AC-8`: Existing specialized cards and non-tool transcript content do not regress.
- `AC-9`: Keyboard, focus, screen-reader, narrow-screen, theme, and reduced-motion checks pass.
- `AC-10`: No credential or unrestricted environment payload becomes visible or copyable.

## 8. Delivery Sequence

1. Add failing presenter and lifecycle tests.
2. Introduce the pure presentation model and typed presenters.
3. Add the unified activity card and adaptive disclosure.
4. Flatten Codex sandbox child activities and add the source marker.
5. Add safe read-only grouping.
6. Add raw-data disclosure with masking, bounds, and copy feedback.
7. Run history equivalence and full frontend regression tests.
8. Run real Runtime/Studio E2E and visual/accessibility verification.

## 9. Risks and Mitigations

- **History regression:** gate release on live/replay equivalence and retain generic fallback.
- **Incorrect correlation:** use call ID first and never merge ambiguous concurrent calls by name.
- **Excessive rendering cost:** derive presentation with pure memoizable functions, bound output, and lazily format raw JSON.
- **Visual noise:** successful items collapse and safe read-only work aggregates; failures and active work stay visible.
- **Loss of debugging detail:** preserve original values on the source block and expose them through the secondary disclosure.
- **Sensitive data exposure:** preserve backend allowlists and add value-aware masking before display and clipboard operations.

## 10. Implementation and Verification Record

- **Component contract:** [Studio Tool Activity](../../../specs/studio-tool-activity/README.md)
- **Implemented:** pure tool presentation, bounded/redacted raw data, adaptive disclosure, command alias lifecycle correlation, out-of-order response retention, bounded event deduplication, Codex child flattening, source markers, and adjacent read-only grouping. Existing registered specialized renderers remain unchanged.
- **Targeted verification (2026-09-12):** the final targeted tool/model and component reruns passed, including signed-URL masking, explicit partial failure, disclosure, and localized grouping cases; `npx tsc --noEmit` passed; `npm run check:i18n` passed.
- **Full frontend regression (2026-09-12):** `npm --prefix frontend test` passed 1,078 tests; `npm --prefix frontend run build` passed; `npm --prefix frontend run test:webui-assets` verified 102 packaged files and 246 internal references; `uv run --extra dev pre-commit run --all-files` passed.
- **Repository regression:** `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` ran 4,030 tests successfully but ended with 6 failures and 2 collection errors because optional `llama_index` and `anthropic` packages are absent from the local environment. The failures are outside this frontend change.
- **Live Runtime evidence:** Runtime `r-yeuujrrcowb21078p9jh` produced one in-place running command activity. Replaying its 34 captured frames after the lifecycle fix produced one completed activity with exit code `0` and duration `1601 ms`.
- **Browser evidence:** the rebuilt Studio was served successfully and `/web/ui-config` returned the expected Studio configuration. A final headless Chrome capture attempt hung and was stopped; previously completed normal-width screenshots and live DOM checks remain the visual evidence.
- **Known transport limitation:** the tested A2A virtual session persisted only final text, so refresh preserved the final answer but had no tool activity to reconstruct. Studio does not fabricate or resubmit missing activity.
