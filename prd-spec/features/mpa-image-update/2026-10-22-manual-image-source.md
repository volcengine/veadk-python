# Manual image address or public version

[中文](2026-10-22-manual-image-source.zh.md)

Change ID: mpa-image-source-choice. Created/revised: 2026-10-22. Status: implemented.
Predecessor: [independent images](2026-10-22-independent-images.md).
Component: [MPA image management](../../../specs/mpa-image-update/README.md), proposed CON-IMAGE-SOURCE extension.

## Background and evidence

MpaImageUpdates currently renders a search input above its public-version selector. ImageManager accepts tag plus revision and always constructs the address from a fixed repository. Replacing the label alone would not enable manual addresses. The user requested replacing the search field with a manual image address, mutually exclusive with the public-version choice. Runtime and Worker must remain independent.

## Goals, non-goals and scenarios

FR-1: Replace loaded-version search with a manual full image-address input. Keep the public-version selector visible below it, labeled as the alternative. Typing an address clears the selected public tag; selecting a public tag clears the manual address. Clearing one source does not silently select the other. Confirmation displays exactly the final target.
FR-2: Other registries are allowed as explicit manual input. Accept a bounded host/namespace/repo:tag reference, optional numeric registry port, and no scheme, credentials, query, fragment, whitespace, or digest. Format errors appear beside the input. No registry credentials are collected. Image compatibility and pull authorization remain AgentKit responsibilities.
FR-3: Public-version selection retains fixed domestic/overseas repositories, pagination, manifest checking and refresh. Public catalog loading/failure/empty state cannot block a valid manual address, and refreshing public versions must not erase it. Remove search-specific text and behavior.
FR-4: POST accepts exactly one of tag or image with revision, preserving existing tag callers. Reject both/neither and invalid addresses before any write. Manual input never causes Studio to request an arbitrary registry host. Runtime manual custom images use ArtifactType=image; its corresponding fixed public repository keeps public_image. Worker sends only ImageUrl. Existing ownership, revision, intent, unknown-outcome and independent-update protections remain in force.
FR-5: Preserve cancellation, late-response isolation, duplicate-submit protection, keyboard/IME behavior, and narrow layout. Selecting a source never submits an update; explicit confirmation is still required.

Given a manual address and a failed public catalog, the authorized user can confirm only the chosen component update. Given a selected public version, typing an address clears it; choosing a public version again clears the manual text. Invalid/both-source requests cause zero cloud writes. Updating one component leaves the other's form and resource unchanged.

## Design and contract impact

Reuse InputWithTailIcon, Select, FormLabel and the current confirmation dialog; no new mode navigation or duplicate form. Source precedence follows the latest explicit input action, with inactive source cleared rather than a hidden priority rule. Validation and final-target derivation are shared in the frontend domain API module and independently enforced in Python. Manual-address requests bypass catalog reads, including manifest verification; AgentKit validates its own image pull. No Studio-side arbitrary URL fetch, authentication changes, new dependency or generated source change.

Extend the existing POST union with {image, revision}; keep {tag, revision} compatible. Target validation precedes persistence and dispatch. Both sources use the same deployment lock, optimistic recheck and durable per-component intent. No change to rollout/session semantics or permission policy. Manual images do not inherit an assumption of compatibility with MPA Runtime or Worker; the user explicitly chooses the component and confirms the complete address.

## Tasks and affected files

T-1 / FR-1,3,5: Update MpaImageUpdates.tsx, its CSS and bilingual mpaImages.json; remove loaded-version filtering and support mutually exclusive source input without coupling cards.
T-2 / FR-2,4: Add typed target validation in frontend/src/adk/mpaImages.ts and extend frontend/server/mpa_images.py request parsing and image dispatch. Existing client transport remains unchanged.
T-3 / FR-1..5: Write failing frontend/backend regressions first. Cover mutual exclusion in both directions, manual updates for both components, catalog independence, malformed/ambiguous input, custom/public ArtifactType, stale/unknown/cancel/IME boundaries and unchanged legacy tag behavior.
T-4: Update both component-spec languages and frontend/README.md; rebuild packaged assets preserving the running Studio's cached references; record checks and browser evidence.

## Verification and acceptance

AC-1: Both cards show manual address and public-version alternatives; no search control remains. Switching sources clears only the other field on the same card.
AC-2: Final confirmation and API target match the chosen source; manual input works during catalog loading/failure and does not contact arbitrary registries from Studio.
AC-3: The backend rejects invalid/both/neither-source payloads and preserves all prior ownership/concurrency protections. Only the selected cloud component is updated.
AC-4: `uv run --extra dev pytest tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py`, changed Python Ruff/Pyright, `npm --prefix frontend test`, `npm --prefix frontend run build -- --emptyOutDir false`, i18n and asset checks, mocked browser keyboard/IME/cancel/error/390px flows, bilingual links/identifiers, whitespace and scoped secret scanning are recorded. Real cloud writes are not authorized.

## Risks and open decisions

Confirmed: manual addresses may use other registries, without Studio-side fetching. The public-version catalog remains restricted to the existing fixed public repositories. Private image pull depends on AgentKit's existing permissions, not new credentials entered in Studio. Tags are mutable; digest syntax remains unsupported. Existing sandbox sessions may keep their old image. The current port-8000 credential/startup issue remains unresolved; do not restart the service or choose another identity during this change.

## Review and approval

2026-10-22: Inspected current UI, parser, cloud payloads and existing tests. review-spec skill unavailable; direct review covers bilingual equivalence, API compatibility, arbitrary-host avoidance, source precedence, catalog independence, ownership and unknown outcomes. The user explicitly approved the complete proposed plan, including other registries, mutually exclusive inputs and independent Runtime/Worker updates. Design review is clear; T-1 through T-4 and AC-1 through AC-4 are complete for local implementation, with verification below. No commit, push or real cloud write is authorized.

## Verification and delivery — 2026-10-22

Tested scope: this manual-source working-tree delta on feat/from-upstream-main-20261020, preserving the earlier independent-image feature and unrelated local changes.

- pass: test-first regressions reproduced unsupported manual updates (9 backend failures) and missing manual/mutual-exclusion controls (7 UI failures) before implementation.
- pass: `uv run --extra dev pytest tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed/test_deletion.py -q` — 215 passed. Both sources retain ownership/stale/unknown-state protections; manual writes contact no registry.
- pass: `npm --prefix frontend test` — 1389 Node tests and 223 Vitest cases. Includes matching frontend/backend format cases, source mutual exclusion, catalog-loading/failure independence, custom payloads, IME Enter and late-response/cancellation tests.
- pass: `npm --prefix frontend run build -- --emptyOutDir false`; both production bundles and TypeScript passed, with the existing chunk-size advisory.
- pass: `npm --prefix frontend run check:i18n`; `npm --prefix frontend run test:webui-assets` — 2 locales/23 namespaces; 177 files/695 references.
- pass: repository pre-commit Ruff check/format on frontend/server/mpa_images.py and tests/cli/test_mpa_images.py, plus Pyright on both — zero diagnostics. Unmodified CLI/proxy-test baseline diagnostics from the predecessor are outside this delta.
- pass: actual-browser mock flow verified both source-switch directions, keyboard public selection, catalog error with manual confirmation/submission, independent Worker selection/resource preservation, invalid manual format, cancellation/focus return and 390px long-address layout. Page/dialog widths equaled scroll widths (342px/310px). Preview: `/tmp/veadk-mpa-manual-image.png`. Fixtures and Vite were removed.
- pass: bilingual requirement/contract identifiers and relative links, diff whitespace and scoped repository-configured secret scanning.
- blocked: activation/account-connected Studio checks still require the original cloud credential launch environment. The port-8000 service was not restarted by this change.
- not_run: real cloud writes/private-registry pulls, image compatibility, rollout/application health and new-sandbox smoke, since no cloud-write test was authorized. Full all-files pre-commit/branch synchronization are deferred to an authorized commit; no commit or push performed.
