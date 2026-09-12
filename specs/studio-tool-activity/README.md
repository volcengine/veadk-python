# Studio Tool Activity Component Contract

- **Component ID:** `studio-tool-activity`
- **Status:** active
- **Revision date:** 2026-09-12
- **Chinese counterpart:** [README.zh.md](README.zh.md)
- **Related PRD:** [Studio Tool Activity Visualization Design](../../prd-spec/features/studio-tool-activity-visualization/2026-09-12-studio-tool-activity-visualization-design.md)
- **Owned implementation:** `frontend/src/blocks.ts`, `frontend/src/ui/Blocks.tsx`, and `frontend/src/ui/tool-activity/`
- **Primary tests:** `frontend/tests/toolActivityModel.test.mjs`, `frontend/tests/toolBlockDefaultOpen.test.mjs`, and `frontend/tests/codexSandboxProgress.test.mjs`

## 1. Responsibility

The component turns ADK function calls, function responses, and Codex sandbox progress into bounded, accessible activity units in the Studio transcript. It owns presentation normalization, lifecycle correlation, safe read-only grouping, adaptive disclosure, output previews, and redacted raw-data inspection.

It does not own event transport, Runtime execution, session persistence, backend redaction, authorization flows, or final-answer generation. Existing specialized tool renderers remain authoritative for their own domain content.

## 2. Entry Points and Dependencies

- `applyEvent()` and `eventsToTurns()` in `frontend/src/blocks.ts` own live and history event projection.
- `flattenCodexActivityBlocks()` derives a display-only flat view from nested Codex activity without mutating source blocks.
- `presentToolActivity()` converts a tool block into `ToolPresentation`.
- `ToolActivityCard` renders one ordinary activity.
- `ToolExplorationGroup` renders an eligible sequence of successful read-only activities.
- `Blocks` dispatches ordinary tools through this component and retains existing specialized renderers.

The component depends on the existing ADK event types, i18n `conversation` namespace, Studio semantic CSS variables, and repository-owned SVG icons. It introduces no runtime dependency and no server contract.

## 3. Contracts

### `CON-1` — Source-preserving presentation

Presentation is derived from source `Block` values. Grouping and sandbox flattening must not mutate source block order or data. Raw `args` and `response` remain available only through bounded, redacted secondary disclosure.

### `CON-2` — Stable lifecycle correlation

Events with the same non-empty `callId` represent one logical activity, including known command aliases such as `exec_command` and `commandExecution`. A partial function response updates output and keeps the activity running; a terminal response completes or fails it. Same-name concurrent calls must never merge without matching IDs.

Duplicate event IDs are ignored within one projector instance. Tracking is bounded to 2,048 IDs. A result that arrives before its call remains visible and merges with a later matching call.

### `CON-3` — Status and disclosure state

Valid activity states are `queued`, `running`, `completed`, and `failed`. Running items default open, completed items default closed, and failed items default open. Once a user toggles an item, later lifecycle updates must not override that choice. Disclosure state is local UI state and is never persisted.

### `CON-4` — Typed presentation with generic fallback

The maintained categories are `command`, `read`, `search`, `file-change`, `mcp`, `authorization`, and `generic`. Unknown or malformed tools must remain visible through `generic`; a presenter failure must not break the transcript. Existing registered detail renderers keep their specialized content while ordinary built-ins keep their localized action titles.

### `CON-5` — Sandbox flattening

When `delegate_to_codex_sandbox` has structured child activity, its child blocks render at the current transcript level under one lightweight `Codex Sandbox` source marker. The outer tool card is retained while no child activity exists. The final assistant answer remains outside the tool activity sequence.

### `CON-6` — Safe exploration grouping

Only adjacent, completed, successful `read` and `search` activities with the same source may form an exploration group. Commands, file changes, MCP, authorization, failures, running activity, source changes, non-tool blocks, and final text terminate the group. Children remain ordered and individually inspectable.

### `CON-7` — Bounded output

Visible text is stripped of ANSI CSI/OSC sequences, unsafe control characters, and credential-like values. Multiline output previews retain five leading and five trailing lines with an omission count. A single oversized line retains at most 8,000 leading and 8,000 trailing characters with an omitted-character count. Detail regions scroll independently and do not create body-level horizontal overflow.

### `CON-8` — Raw-data safety

Raw data is closed by default and formatted only after disclosure. Sensitive keys and credential patterns embedded in strings are masked before display or clipboard copy. Traversal is bounded to depth 8, 50 items per collection, 500 total nodes, and 4,000 characters per string. Circular references produce `[circular]`; exceeded bounds produce `[truncated]`. Clipboard failure is visible and does not throw into the transcript.

### `CON-9` — History compatibility

`eventsToTurns()` remains the history reconstruction authority. Live and replayed events use the same `applyEvent()` lifecycle logic. Persisted `functionCall` plus `functionResponse` must be sufficient to reconstruct activity, including camelCase and snake_case payloads. Missing progress degrades to a generic activity.

An A2A virtual session that persists only final text cannot reconstruct transient tool activity; Studio must preserve the final answer and must not fabricate missing history. This is a transport persistence limitation, not permission to submit the task again.

### `CON-10` — Accessibility and responsive behavior

Interactive disclosure uses native buttons, `aria-expanded`, visible focus, textual status, and at least a 44px effective target. Collapsed content is `aria-hidden` and inert. Secondary summaries hide before titles or state at narrow widths. Motion uses bounded transitions and is disabled under `prefers-reduced-motion`.

## 4. State and Concurrency

```text
queued -> running -> completed
                  -> failed
```

Output deltas may repeat while running. A terminal event owns final status and authoritative output. Concurrent activities are isolated by `callId`; projector state is isolated per active assistant turn and session. Session switching reconstructs or selects that session's own turns and must not share component-local disclosure state.

## 5. Security and Isolation

Tool payloads are untrusted display data. The component does not use raw HTML injection. It preserves backend allowlists and applies an additional value-aware mask before rendering or copying. It must not expose Authorization values, cookies, passwords, access keys, secret keys, tokens, signed query credentials, or unrestricted environment payloads.

## 6. Compatibility and Evolution

- Both camelCase and snake_case event fields remain supported by the owning ADK types and projection.
- New tool categories must keep generic fallback and must add bilingual labels and presenter tests.
- A new merge alias must be proven unambiguous through a lifecycle test.
- Changing persistence or adding resumable tool history requires a separate transport/session contract change; it is outside this component.

## 7. Failures and Diagnostics

- Malformed values fall back to readable generic content and bounded raw data.
- Unmatched responses remain visible rather than being discarded.
- Clipboard failures render localized feedback.
- The component emits no independent network request, retry, metric, or log. Existing Studio stream and browser diagnostics remain the observability surfaces.

## 8. Verification

| Contract | Verification | Evidence |
| --- | --- | --- |
| `CON-1`–`CON-9` | `npm --prefix frontend test` | Model, lifecycle, Codex, history, and existing transcript regression suites |
| `CON-10` | Component DOM tests plus real browser checks at normal and narrow widths | Activity disclosure/status DOM and screenshots |
| Build assets | `npm --prefix frontend run build` and `npm --prefix frontend run test:webui-assets` | Generated `veadk/webui` references are complete |
| Bilingual labels | `npm --prefix frontend run check:i18n` | Locale namespaces are equivalent |

## 9. Change Record

- **2026-09-12:** Contract introduced by the approved Studio Tool Activity Visualization PRD. Initial implementation covers unified tool cards, command lifecycle correlation, sandbox flattening, read-only grouping, bounded output, raw-data redaction, and history-safe fallbacks.
- **2026-09-12:** Non-final A2A `submitted` and message-less `working` updates are forwarded as metadata-only heartbeats. They clear the first-event deadline without creating transcript blocks, completing turns, or resubmitting requests.
- **2026-09-12:** A2A text parts marked `adk_thought` are projected as Studio thinking events. Reasoning and answer cumulative-delta state is isolated so one stream cannot suppress or corrupt the other.
