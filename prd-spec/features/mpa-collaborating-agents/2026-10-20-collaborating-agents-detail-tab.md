# MPA collaborating Agents detail tab

## Background, scope and approval
The existing change exposes management from the chat information rail. On 2026-10-20 the user explicitly requested moving it to Agents → MPA → selected agent, in a tab below Basic, affecting MPAs only. This request approves the relocation; existing administrator authorization is retained.

## Requirements and scenarios
1. MPA administrators with a Runtime see Basic followed by Collaborating Agents. The manager renders inline only when selected.
2. General agents, drafts, and non-administrators gain no tab or management requests. Unsupported external focus returns to Basic.
3. Switching tabs, Runtime, region, or permission unmounts the manager, aborts pending requests and clears transient forms/results. Late responses cannot update another target.
4. Remove the chat-rail entry. Keep CRUD, errors, revision checks, unknown-outcome recovery and server authorization unchanged.

## Design and affected files
Reuse CollaboratorManager in AgentWorkspace, keyed by region and Runtime ID. App passes an explicit admin/super_admin permission; AgentTopology loses the unused entry slot. Reuse ResourceDetailLayout navigation and existing localized title. Update frontend README, the bilingual component contract, tests and packaged web assets.

## Non-goals and risks
No API, persistence, cloud resources, general-agent navigation, chat protocol or authorization changes. Primary risks are stale target state and accidentally exposing the tab to general agents; test both. Existing unrelated lock-file changes are preserved.

## Design review
Direct review (review-spec skill unavailable): boundaries, permissions, cancellation, failure semantics and bilingual equivalence reviewed. No blockers. The [component contract](../../../specs/mpa-collaborating-agents/README.md) updates UI location/lifecycle only; server contracts remain unchanged. This supersedes the location in the [original design](2026-10-20-collaborating-agents.md).

## Tasks, tests and acceptance
- Add failing navigation, permission, general-agent and target-switch regressions; implement relocation.
- Run targeted tests, full frontend tests, build, i18n and packaged-asset checks.
- Browser-check normal, loading, empty, error/retry, cancellation, keyboard/IME and narrow layouts using synthetic data; no live cloud writes.
- Synchronize bilingual docs and verification. Accept when the tab is below Basic only for authorized MPAs, old entry is removed and requests remain target-scoped.

## Verification
Implementation complete. Direct code review found no blocking issue in permission/category gating, lazy mounting, target keys or cleanup. Existing server authorization is unchanged.

- pass: regression-first run produced 3 expected failures; targeted Vitest checks then passed (30 tests).
- pass: `npm --prefix frontend test` (1,389 Node tests and 127 Vitest tests).
- pass: `npm --prefix frontend run build` (TypeScript and both production bundles); existing bundle-size warnings remain.
- pass: `npm --prefix frontend run check:i18n` (2 locales, 22 namespaces).
- pass: `npm --prefix frontend run test:webui-assets` (114 files, 351 references).
- pass: real browser with an isolated synthetic-fetch fixture: tab below Basic, inline loading/empty/unsupported states, refresh recovery, add/cancel form, Chinese text input, Tab focus, general-agent navigation and 390px layout. Fixture and temporary server removed after verification.
- pass: automated tests verify abort on leaving, Runtime/region switch and permission loss, plus absence for general agents and non-admins.
- not_run: physical IME composition; Chinese text and keyboard focus were checked, composition behavior was not changed.
- not_applicable: Python/Ruff/Pyright and cloud integration for this UI-only relocation; no Python or cloud mutation in this task. Existing collaboration backend changes predate this task.
- pass: paired documents, referenced paths and diff whitespace reviewed.

Tested scope: working-tree relocation on feat/from-upstream-main-20261020, 2026-10-20. No commit or push authorized.

## Follow-up: input focus appearance (2026-10-20)

The user requested removing the extra dark outline inside the name and credential fields. Browser inspection reproduced an inner `2px` workspace outline and the existing outer wrapper outline. A scoped CSS override removes only the inner focus-visible outline of collaborator input components. The outer keyboard focus indicator remains. No API, state or component contract change; this is a visual-only correction under the formatting exception. No new behavior-mirroring test was added. Real browser checks cover name/password input and Tab navigation; an unrelated input retains its original outline. Verification results follow below.

Verification: pass — `npm --prefix frontend test` (1,389 Node + 129 Vitest), `npm --prefix frontend run build`, `npm --prefix frontend run test:webui-assets` (114 files/351 references), browser focus checks and `git diff --check`. Existing bundle-size warnings remain. No cloud operations, commit or push.
