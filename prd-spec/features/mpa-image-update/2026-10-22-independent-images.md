# Independent MPA image updates

[中文](2026-10-22-independent-images.zh.md)

Change ID: mpa-image-update. Created/revised: 2026-10-22. Status: implemented.
Component: [MPA image management](../../../specs/mpa-image-update/README.md).

## Background and evidence

Studio currently hides the general update flow for MPA in AgentWorkspace.tsx. Managed creation already defines domestic/overseas public mpa_agent and mpa_codex_worker repositories in studio_profile.py. Anonymous OCI tag reads were verified for all four repositories; tag listing supplies names, not publication times. UpdateRuntime supports ArtifactUrl/ArtifactType and ReleaseEnable; UpdateTool supports ImageUrl. See [UpdateRuntime](https://docs.volcengine.com/docs/86681/1923461) and [UpdateTool](https://docs.volcengine.com/docs/86681/1913799).

## Goals, non-goals and scenarios

FR-1: MPA navigation is Basic, Image updates, Collaborating Agents, subject to existing management permissions. General Agent navigation stays unchanged.
FR-2: Runtime and Worker have separate current metadata, catalog loading, selection, confirmation, submission, errors and reconciliation. Updating either must issue exactly one corresponding cloud update and leave the other unchanged.
FR-3: Select tags only from fixed provider repositories. Show the full selected address. Paginate registry order without claiming newest-first; search explicitly filters loaded versions and offers load-more. Refresh resets catalog selection.
FR-4: Verify fresh authorized Runtime identity, MPA category, deployment lock/state, Worker binding/ownership/exclusive references, optimistic revision and tag existence before mutation. Reject ambiguity and arbitrary hosts, paths, tags or payload fields.
FR-5: Submission is not application health. Runtime requests immediate release; Worker updates its template, and existing sandbox sessions may retain the old image. Show configured image and cloud status separately. A lost write response blocks duplicate submission until read reconciliation; never silently retry writes.
FR-6: Loading, empty, forbidden, errors, retry, stale selection, cancellation/navigation, late responses, keyboard/IME and narrow layouts have explicit behavior.

Given an authorized MPA, selecting a Runtime version and confirming updates only Runtime. Selecting Worker updates only its exclusively owned template. A stale preview, shared Worker, pending deployment or failed registry read causes zero writes. Leaving the page aborts browser reads; an already submitted cloud write is not rolled back by closing the dialog.

## Design and impact

Use a domain React component and typed API client plus a separate Studio backend module. Reuse Select, Button, FormLabel, InputWithTailIcon, TextShimmer and ModalButton. Existing Agent detail navigation anchors the layout. Component contract owns endpoints, validation, persistence, failure/concurrency semantics and bounds. No generated agent source, Python SDK signature, dependencies, session protocol, Worker binding or cloud credentials are changed.

Use the existing account/region deployment advisory lock and registry record for mutation ownership and durable image-update intent. Keep Runtime and Worker intents separate. Persist intent before cloud submission and reconcile only when the target image is observed with a usable resource status. Ambiguous outcomes retain the intent and block conflicting management operations; cloud rejections clear it. Do not rewrite creation request hashes. Managed deployment and deletion must refuse unresolved image intents. Read failures cannot become empty catalogs or permission success.

Tag names remain mutable. Revalidate tag existence immediately before update; submit the documented tag syntax. Digest pinning is not implemented because AgentKit digest reference support was not verified; the UI does not claim immutable image identity. Platform state and catalog are refreshed explicitly; no automatic real cloud updates or writes are used for tests.

## Tasks and affected files

T-1 / FR-4,5: Backend catalog, ownership, revision, intent reconciliation and route wiring in frontend/server/mpa_images.py and cli_frontend.py; guards in managed deployment/deletion.
T-2 / FR-1,2,3,6: Typed client, MpaImageUpdates component/style, AgentWorkspace navigation, bilingual i18n.
T-3 / FR-1..6: Failing backend and UI regression tests, independent mutation assertions, adversarial registry and ownership tests; mock browser flows.
T-4: Synchronize docs, generated web assets and verification record.

## Verification and acceptance

AC-1: Second MPA tab; general navigation unchanged; no unauthorized image page.
AC-2: Both provider catalogs map each component correctly, pagination/search/refresh and empty/error/retry work.
AC-3: Runtime-only and Worker-only mutations preserve all unrelated configuration, and stale/shared/unowned/busy resources produce zero writes.
AC-4: Unknown outcome never becomes success or automatic retry; old sandbox behavior is explained; late reads cannot replace new Agent state.
AC-5: Targeted Python tests, Ruff, Pyright, npm --prefix frontend test, npm --prefix frontend run build, check:i18n, TypeScript and built asset checks, mocked browser keyboard/narrow/error/cancel checks, bilingual/link checks, diff whitespace and scoped secret scan are recorded honestly. No live cloud write is authorized.

## Risks and recovery

Cloud state may take time to converge; a target tag is not immutable, and application health cannot be inferred from Update success. Unresolved intent requires read reconciliation or operator investigation rather than unsafe blind retries. Studio on port 8000 currently lacks the prior process cloud credentials after an earlier restart; this is recorded as an existing agent-caused operational regression. Do not restart again or select another CLI identity; account-connected verification remains blocked pending original launch environment restoration.

## Review and approval

2026-10-22: User approved this feature and explicitly required independent updates. review-spec skill unavailable; direct review covered bilingual equivalence, feasibility, fixed-host security, authorization, ownership, locks, unknown outcomes, compatibility and testability. No design blocker remains. Implementation and local verification completed; no commit/push or cloud update authorized.

## Delivery verification — 2026-10-22

Tested scope: working-tree image-management changes on feat/from-upstream-main-20261020 (base HEAD 9ab0ef2d), preserving prior local edits. T-1 through T-4 and AC-1 through AC-5 are complete for local implementation.

- pass: initial regression collection failed before the backend/UI existed; navigation regression failed before adding the second tab.
- pass: `uv run --extra dev pytest tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed -q` — 1345 passed. Subsequent security/deadline refinements: affected route/deletion run 189 passed; final image contract file 35 passed.
- pass: `npm --prefix frontend test` — 1389 Node tests and 202 Vitest cases.
- pass: `npm --prefix frontend run build -- --emptyOutDir false` — TypeScript and both production builds. Old hashed assets retained to preserve the running server's cached HTML; existing chunk-size advisory remains.
- pass: `npm --prefix frontend run check:i18n`; `npm --prefix frontend run test:webui-assets` — 2 locales/23 namespaces, 177 packaged files/695 references.
- pass: changed Python Ruff check/format via repository pre-commit environment; Pyright on the new module/tests and changed managed files has zero diagnostics. Existing CLI/proxy-test files retain 57 pre-existing diagnostics; none point to the new blocks.
- pass: mocked real-browser keyboard selection, cancel/focus return, Runtime-only submission with Worker unchanged, pagination/search, error/retry, empty catalog, unknown outcome disabling repeat submit, and 390px page/dialog checks (342px/310px content widths equal scroll widths). Preview: `/tmp/veadk-mpa-image-updates.png`. Temporary fixtures and Vite server removed.
- pass: anonymous live read-only pages and latest manifests for all four fixed public repositories. No cloud credentials used for catalog reads.
- pass: paired-language contract/identifier and relative-link checks, diff whitespace, scoped Gitleaks scan (1.79 MB; no leaks).
- blocked: account-connected Studio verification/activation because the prior restart lost its credential environment. This change did not restart Studio. Restore the original launch environment before activating.
- not_run: real Runtime/Worker writes, rollout/application health and new sandbox smoke — no authorization for cloud mutation. Full repository parallel regression is not required for this scoped Studio/managed-image change; affected managed integration coverage ran instead. Full all-files pre-commit is reserved for a separately authorized commit. No commit or push performed.
