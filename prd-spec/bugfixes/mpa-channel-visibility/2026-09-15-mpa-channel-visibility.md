# MPA-only message channel visibility

[中文](2026-09-15-mpa-channel-visibility.zh.md)

Date: 2026-09-15. Status: implemented. User approval: only the MPA agent category should expose Message channels after Runtime selection. Contract: [MPA channels](../../../specs/mpa-channels/README.md).

## Evidence and requirements
CloudRuntime carries agentCategory, but MyAgents runtime cards and App detail AgentEntry drop it; AgentWorkspace currently shows channels for every type. FR-1: preserve general/mpa category through Runtime list → card → detail entry. Prefer explicit Runtime category, falling back to the category of the filtered list for older responses. FR-2: expose/render channels only when selectedAgent has a Runtime ID and category mpa; general/unknown/local agents hide it. FR-3: if channels is selected when the category changes or an unsupported focus is requested, fall back to basic without mounting channel requests.

## Design and scope
Add optional category metadata to MyAgentCardData.runtime and AgentEntry, propagate it in MyAgents and App, filter sections and guard content in AgentWorkspace. Preserve usage permissions, other sections, provider behavior and QR lifecycle. Unknown category fails closed for visibility. No backend/API authorization changes and no live cloud operations.

## Review, tasks and acceptance
Direct review (review-spec unavailable): additive metadata, backward-compatible optional fields, filtered-list fallback tied to request category, explicit guard prevents stale panel mounting. No blockers; user request approves scope.
T-1/AC-1 (FR-1): source contract tests for metadata propagation, including cached list mapping.
T-2/AC-2 (FR-2/3): executable predicate cases for MPA/general/unknown/no Runtime; section filter/render/fallback tests. Implement four source files listed above.
T-3/AC-3: targeted/frontend regression, build/assets, real browser with mocked Runtime APIs for category switching and unsupported focused section. Update paired docs and generated assets.

## Verification and risks
Execution date: 2026-09-15; scope: the current uncommitted category propagation and visibility diff, its tests/docs, and rebuilt WebUI assets.
- pass: test-first regression failed before implementation; `node --test frontend/tests/agentWorkspace.test.mjs` then passed 34 tests.
- pass: `npm --prefix frontend test` passed 1208 tests after updating the existing Runtime mapping assertion for its category argument.
- pass: `npm --prefix frontend run build`; `npm --prefix frontend run test:webui-assets` verified 104 files and 248 internal references. Existing bundle-size warnings remain.
- pass: real browser running AgentWorkspace with mocked APIs showed MPA channels, hid them for general/unknown categories, returned to basic after switching, and restored the entry on returning to MPA. The MPA/general switch also passed at 480×850. Basic metadata error UI was expected from the isolated mock.
- pass: direct implementation review found no blockers; paired documents and scoped diff whitespace checked. T-1 through T-3 and AC-1 through AC-3 complete.
- not_applicable: Python checks, IME/input and channel binding/error/retry behavior are unchanged by this diff. No commit was requested, so pre-commit synchronization was not run.
- not_run: live cloud/provider verification and deployment; no live operations were requested.
Category-less non-list entry points intentionally hide the channel; no name/image heuristics.
