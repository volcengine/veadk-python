# Chat Model Dropdown Visibility Bugfix

- **Change ID:** `chat-model-dropdown`
- **Created:** 2026-09-14
- **Status:** implemented
- **Chinese:** [2026-09-14-chat-model-dropdown.zh.md](2026-09-14-chat-model-dropdown.zh.md)
- **Related specs:** [Studio MPA Control Plane](../../../specs/studio-mpa-control-plane/README.md)

## Background And Evidence

In an active Studio chat, the Turn model selector in the composer uses `NewChatCompactSelect`. The shared compact select menu opens below its trigger by default. The composer model selector overrides the menu to open upward with `bottom: calc(100% + 6px)`, but it did not reset the inherited `top` position. That left the menu over-constrained, so users could see the search field without a usable full option list.

The issue affects switching models during chat. It does not affect model list retrieval or the immutable Turn model snapshot contract.

## Goals

- Make the chat composer model dropdown show the search field and the option list together.
- Keep the option list scrollable within the viewport.
- Preserve the existing compact select behavior for Agent, Skill, and video controls.

## Non-Goals

- Do not change how models are loaded from Sandbox sessions.
- Do not change selected model persistence or Turn snapshot semantics.
- Do not redesign `NewChatCompactSelect`.

## Requirements

- `FR-1`: The composer model menu must open upward from the model trigger without conflicting `top` and `bottom` positioning.
- `FR-2`: The composer model option list must have a bounded height so long model catalogs remain scrollable.
- `FR-3`: Shared compact select menus outside the composer must keep their existing default downward placement.

## Design

Add composer-scoped CSS overrides for `.composer-model-select .new-chat-compact-select__menu` and `.composer-model-select .new-chat-compact-select__list`. The menu explicitly sets `top: auto` while preserving the existing right-aligned upward placement. The list gets a viewport-aware `max-height` so the full model catalog can be inspected by scrolling instead of being clipped.

No component contract changes are required. The fix is presentation-only and uses existing markup, keyboard behavior, search placeholder text, and listbox semantics.

## Tasks

- `T-1`: Update composer-scoped compact select CSS.
- `T-2`: Add source-level regression assertions for the upward menu placement and bounded list height.
- `T-3`: Run targeted frontend tests, build Studio assets, and verify packaged asset references.

## Verification And Acceptance

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-2` | Composer model menu resets inherited `top` and opens upward from the trigger. | `node --test frontend/tests/newChatComposerLayout.test.mjs frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs` | pass |
| `FR-2` | `T-1`, `T-2` | Composer model options are constrained by a viewport-aware max height and scroll inside the menu. | `node --test frontend/tests/newChatComposerLayout.test.mjs frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs` | pass |
| `FR-3` | `T-1` | The override is scoped to `.composer-model-select`; shared compact select defaults remain unchanged. | `node --test frontend/tests/newChatComposerLayout.test.mjs frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs` | pass |
| All | `T-3` | Built Studio assets include the UI fix and pass asset reference validation. | `npm --prefix frontend run build -- --mode development`; `npm --prefix frontend run test:webui-assets`; `git diff --check` | pass |

## Risks

Real browser validation is still needed to confirm the exact viewport in the user's active chat. The CSS change is scoped and reversible if the visual check finds an additional stacking or clipping parent.
