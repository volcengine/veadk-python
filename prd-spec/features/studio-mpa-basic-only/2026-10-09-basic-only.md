# MPA details: basic information only

- Date: 2026-10-09; status: implemented and locally verified; not deployed.
- Approval: the user explicitly requested hiding all other tabs and stopping Profile requests on the MPA details page.
- [Chinese](2026-10-09-basic-only.zh.md); contract: [Studio MPA control plane](../../../specs/studio-mpa-control-plane/README.md).

## Scope and evidence
`AgentWorkspace.tsx` loads `getMpaAgentView` on MPA selection, indirectly invoking Runtime `/profile-status`. Hiding navigation alone does not stop this request. The basic-page footer also links to Profile configuration.

## Requirements and design
- FR-1: MPA details expose only Basic information, using the existing layout and styles. General agents retain their sections.
- FR-2: Every requested MPA section, including restored/external focus, resolves synchronously to `basic`, before effects run.
- FR-3: Basic information must not fetch MPA Agent View, Profile status, or issue Profile mutations. Gate the existing control-plane loader to its owning Profile/session sections and hide the footer Profile entry.
- FR-4: Preserve Runtime details, execution flow, chat/delete actions and their authorization. Backend APIs, native chat session creation and Profile storage are outside this change.

## Review and verification plan
Direct review: the change is presentation/request scheduling only; no data migration or authentication changes. Existing hidden implementations remain available for a later explicit re-enable. `ui-ux-pro-max` is unavailable locally; existing component standards and direct review apply. Validate bilingual equivalence and existing styling.

Regression: render the real workspace with mocked network boundaries; cover all hidden focus sections, MPA switching, general navigation, visible basic content, and zero Profile/control-plane calls. Run frontend tests/build/assets and pre-commit, check changed executable-line coverage above 95%, and verify a browser fixture when available. No cloud deployment is implied by local checks.

## Delivery
Implemented FR-1 through FR-4 in `frontend/src/ui/AgentWorkspace.tsx`; updated existing source contracts, added `frontend/tests/mpaBasicDetails.test.tsx`, and rebuilt `veadk/webui`. No backend or API contract changes.

Verification on the diff against `42b50624` (2026-10-09):
- **pass**: `npm --prefix frontend test`: 1,377 Node tests and 64 Vitest tests, including 10 new component cases.
- **pass**: `vitest run --root frontend tests/mpaBasicDetails.test.tsx --coverage --coverage.include=src/ui/AgentWorkspace.tsx --coverage.reporter=json`: changed executable statement-start lines 7/7 (100%). This is changed-line coverage, not whole-component coverage.
- **pass**: `npm --prefix frontend run build`; `npm --prefix frontend run test:webui-assets`: 113 packaged files and 350 references verified.
- **pass**: real Chrome with a temporary loopback fixture using the actual component and mocked fetch: MPA basic-only, General navigation and Integration interaction, General-to-MPA transition, zero Profile requests, narrow viewport layout. Temporary fixture removed before commit.
- **pass**: `uv run --extra dev pre-commit run --all-files`; `git diff --check`; latest `origin/main` fetched and already included.
- **not_applicable**: new input/IME, mutation cancellation/retry flows, and backend tests; these paths were not changed. Hidden section focus is covered by component tests.
- **not_run**: cloud deployment and live cloud E2E; browser fixtures and local checks do not prove publication. Native chat session creation retains its existing Profile behavior.

Direct final review: category gating leaves General navigation and update behavior unchanged, synchronous section resolution prevents stale focus from starting hidden-page requests, and existing effects retain cleanup. English/Chinese requirements and component documentation were reconciled.
