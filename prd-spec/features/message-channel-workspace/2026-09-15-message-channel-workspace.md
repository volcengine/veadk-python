# Message channel workspace

[中文](2026-09-15-message-channel-workspace.zh.md)

- Change ID: message-channel-workspace
- Date: 2026-09-15
- Status: implemented (UI scope)
- Contract: [MPA channels](../../../specs/mpa-channels/README.md)

## Background and scope
The current uncommitted RuntimeChannels panel is embedded at the top of AgentWorkspace integrations. Diagnostics are a flat definition list. The user requested a sibling Message channels tab and Feishu, WeCom and DingTalk channel categories, then authorized implementation (企业微信，帮我改).

## Requirements and scenarios
- FR-1: Opening Message channels from an existing Runtime shows a dedicated workspace, alongside Integrations and Versions. Integrations no longer renders channel management.
- FR-2: The workspace identifies Feishu, WeCom and DingTalk. Preserve working Feishu binding and permissions. Other channels must not imply successful setup or invoke Feishu endpoints; WeCom and DingTalk are explicitly unavailable in this UI scope.
- FR-3: Present binding, channel diagnostics and allowed groups as readable sections. Localize Gateway as 消息网关. Show gateway configuration, inbound route configuration and observed reply delivery independently; configuration is not proof of delivery.
- FR-4: Preserve polling cleanup, retry, form values on error and permission checks. Support keyboard navigation, IME, long names and narrow layouts.

## Design and contract impact
Add channels to AgentSection and the shared section list. Extract a channel selector around the existing Feishu manager. Reuse UI tokens, Button and Select; no dependencies or server changes. Unavailable providers show an explicit unavailable state with no setup actions. The existing MPA channel HTTP, identity, storage and registration contracts remain unchanged. Add the navigation and availability presentation obligation to both component-spec languages.

## Tasks and affected files
- T-1 / FR-1: AgentWorkspace.tsx, bilingual ui.json; standalone navigation.
- T-2 / FR-2–4: RuntimeChannels.tsx and CSS; channel selection and structured status/binding/groups.
- T-3: runtimeChannels.test.tsx and agentWorkspace.test.mjs; regressions, browser checks, build and generated assets.
- T-4: Reconcile bilingual design/spec and frontend README.

## Acceptance and verification
- AC-1: Channels is a sibling section, absent from Integrations.
- AC-2: Channel categories are localized; unsupported providers cannot trigger Feishu mutations.
- AC-3: Real status values remain distinguishable and readable at wide/narrow widths.
- AC-4: Existing binding and cleanup regressions pass; keyboard, loading, empty, errors and retry verified.
Commands: frontend/node_modules/.bin/vitest run tests/runtimeChannels.test.tsx (from frontend); npm --prefix frontend test; npm --prefix frontend run build; npm --prefix frontend run test:webui-assets; git diff --check for changed scope. Browser checks use isolated simulated responses; no cloud binding or deletion is authorized.

## Risks and review
Uncommitted work predates this task; preserve it. Built asset hashes change on rebuild. Do not change MPA services or global tooling. frontend-design and ui-ux-pro-max skills were unavailable at prescribed and searched locations; the user authorized proceeding after disclosure, so apply frontend/SPEC.md and existing patterns. review-spec is unavailable; direct review checked scope, interfaces, safety, cleanup, compatibility, tests and bilingual parity. No design blocker for navigation/Feishu changes. The optional clarification received no response; the UI-only assumption was announced before implementation. WeCom and DingTalk show unavailable states; implementing their server integration is outside this presentation change.

## Verification record
2026-09-15, baseline HEAD f1aa2d75 plus pre-existing worktree changes; scope: channel navigation, presentation, locale keys, tests, docs and rebuilt assets.

- pass: regression first run reproduced 3 new failures / 4 existing passes; final `cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1`: 8 passed, including IME/Safari keyCode 229, keyboard selection, cleanup, error recovery and unavailable providers.
- pass: `npm --prefix frontend test`: 1206 passed. Updated the existing exact section-union assertion for the new channels section.
- pass: `npm --prefix frontend run build`: TypeScript and both Vite builds. Existing large-chunk warnings remain.
- pass: `npm --prefix frontend run test:webui-assets`: 104 files / 248 references. An earlier check ran before build completion and failed against transient output; rerun after successful build passed.
- pass: browser inspection of the real RuntimeChannels component with isolated mock responses: bound/empty, loading, configuration error and retry, binding pending, keyboard provider switching and 480px layout. Temporary preview files removed. No real cloud actions were taken.
- pass: scoped `git diff --check`, bilingual channel-key parity, paired designs and relative links.
- not_run: live Feishu registration/delivery and end-to-end cloud Agent navigation; no cloud operations authorized. Component browser checks do not prove these integrations.
- not_applicable: Python tests/Ruff/Pyright and pre-commit/branch synchronization; no Python changes or commit in this task.

Review: no blocking UI findings remain. Existing backend changes and dependency-lock changes were preserved. Local preview initially hit sandbox EPERM; a narrowly scoped approved localhost launch succeeded. No machine-global configuration was changed.
