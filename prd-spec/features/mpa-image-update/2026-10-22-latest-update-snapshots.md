# Resolve latest for independent MPA image updates

[中文](2026-10-22-latest-update-snapshots.zh.md)

Change ID: mpa-latest-image-update. Created/revised: 2026-10-22. Status: implemented.
Predecessor: [manual/public source choice](2026-10-22-manual-image-source.md).
Component: [MPA image management](../../../specs/mpa-image-update/README.md), CON-IMAGE-LATEST.
Upstream owner: [read-only latest resolution](../../bugfixes/studio-latest-image-refresh/2026-10-21-readonly-tag-resolution.md).

## Background and evidence

AgentWorkspace gates imagesAvailable with agentCategory=mpa; _authorize_mpa_image rejects general agents before entering the management scope. The catalog already selects separate Volcengine and BytePlus repositories for Runtime and Worker. ImageManager.update currently verifies the literal tag and submits repository:latest, so it does not use upstream snapshot_image from managed/image_snapshot.py. That resolver anonymously matches latest manifest bytes and SHA-256 to an existing non-latest same-repository tag, or verifies a saved selection without rereading latest. Its deployment wrapper pin_studio_images updates creation image_snapshots and both resources; that wrapper must not be called by independent image updates.

## Goals, non-goals and scenarios

FR-1: Preserve MPA-only UI and backend authorization. General-agent create/update paths, navigation, payloads and dependencies remain unchanged. Test API rejection as well as hidden navigation.
FR-2: Cover Volcengine and BytePlus, independently for Runtime and Worker, using their corresponding fixed public repositories. Do not switch provider or infer another cloud identity.
FR-3: Public tag latest uses the upstream snapshot_image resolver. Before confirmation, resolve to an existing same-repository version and digest and show the actual target. Submission revalidates that selected tag/digest without following a subsequently moved latest. No new registry writes, tag publication or copied images.
FR-4: Missing matching versions, changed/deleted selected content, invalid registry data, timeout and permission failures prevent cloud mutation and show safe actionable errors. Read-only preview retry is allowed; no write is automatically retried. Closing or switching cancels browser reads and ignores late preview results.
FR-5: Retain separate Runtime/Worker confirmation, payload and durable intent. Store requested latest, selected image and digest under the selected component's update intent; never replace creation image_snapshots or the other component's intent. Existing ownership, revision, unknown-outcome and sandbox-session semantics remain.
FR-6: Fixed public tags and manual image inputs preserve their current behavior. Manual addresses, including a manually entered latest reference, do not cause arbitrary registry requests from Studio. Preserve the existing {tag, revision} update API; legacy latest calls resolve server-side if no preview selection is supplied.

Given latest for one public component, the dialog displays its selected version/digest, the user confirms, and exactly that component is updated using the verified version. A moved latest after preview does not change the target. An overwritten/deleted selected version produces zero writes. A general agent cannot access detail, versions, latest preview or update routes. All four provider/component cases use their correct repository.

## Design and contract impact

Add a read-only GET /web/mpa-images/{runtime_id}/{component}/latest-preview?revision=... endpoint. It requires the same management/owner/MPA authorization and fresh resource revision/ownership checks. Resolve outside the account/region deployment lock, then reacquire and revalidate the resource before returning {component, revision, requestedImage, image, digest}. No preview selection is persisted. Existing read-only metadata reconciliation may still finish an already observed operation.

Reuse snapshot_image through asyncio.to_thread with a provider-only object, without cloud credentials. Keep its HTTP validation, anonymous authentication, pagination, digest checking and bounds unchanged. Do not call pin_studio_images: it owns creation state and both components. GET preview uses a bounded 180-second client/server wait; a cancelled thread may finish its bounded registry reads but cannot mutate cloud or registry intent.

Extend the public update request with optional selection={image,digest} only when tag=latest. Validate the exact source union; reject selection for manual or fixed-tag requests. Revalidate supplied selections through snapshot_image(selection=...) under the existing update lock. A legacy latest request without selection resolves and verifies before dispatch. Both sources retain fresh revision checks. Reject an unchanged resolved target; allow opening the latest preview even if the current literal reference is repository:latest. Persist selected target and digest before dispatch, with requestedImage retained for diagnosis. An unknown cloud result keeps the saved intent and blocks duplicate writes.

Only the latest confirmation path acquires preview state. Display loading, safe error and a read-only retry control inside the existing ModalButton; disable confirmation until the selected target is validated. A selection matching the current configured image is shown as unchanged and cannot be submitted. Closing, changing source, refreshing or switching Agent invalidates the preview, so a late result cannot override the current target. Fixed-tag/manual UI retains its current controls and payloads. API client and parser types live in src/adk, with a longer deadline only for MPA image operations needing resolution. No Python public SDK signature or dependency metadata changes.

## Tasks and affected files

T-1 / FR-1,2: Extend existing navigation/route integration regressions for general rejection and the four provider/component combinations.
T-2 / FR-3..6: Add the resolver adapter, read-only preview, source-union extension, selected-tag validation and update-intent evidence in frontend/server/mpa_images.py; reuse managed/image_snapshot.py without changing its creation wrapper or contracts.
T-3 / FR-3,4,6: Extend frontend/src/adk/mpaImages.ts and requestMpaImage in client.ts; integrate preview loading/error/retry/cancellation and actual target display in MpaImageUpdates.tsx with bilingual text.
T-4: Test-first regressions for latest literal dispatch, digest changes, moved latest, failed resolution, unknown outcomes and preservation of creation state/other component; update bilingual component/user docs, build assets and record checks.

## Verification and acceptance

AC-1: General agents have no image-update entry and all image routes reject them without resolving or writing.
AC-2: Domestic/BP Runtime/Worker latest targets match their corresponding public repository and reuse the existing resolver.
AC-3: Confirmation shows the selected existing version; moved latest is ignored during selected-content validation; failed/changed/deleted content or stale metadata causes zero writes.
AC-4: No creation image_snapshots or other-component mutation; fixed-tag/manual behavior and old tag request shape stay compatible. Unknown writes remain blocked until reconciliation.
AC-5: Record affected Python tests including tests/cli/test_mpa_images.py, tests/cli/test_frontend_runtime_proxy.py and tests/integrations/mpa_managed/test_image_snapshot.py, changed-file Ruff/Pyright, npm --prefix frontend test, npm --prefix frontend run build -- --emptyOutDir false, i18n/asset checks, mock browser loading/error/retry/cancel/keyboard/narrow flows, paired language/link/whitespace and scoped secret checks. No real cloud write is authorized.

## Risks and review

Resolver reads can take time; preview must not hold a provisioning lock during discovery. Existing resolver bounds remain authoritative and in-flight reads can finish after cancellation, with no write side effect. Publisher tag retention/non-overwrite rules still apply; digest verification detects changes but cannot make a mutable tag immutable. Longer waits are scoped to MPA image operations. Existing cloud launch-environment/activation issues remain outside this change; do not restart Studio or choose another account automatically.

2026-10-22: User requested MPA-only scope, both providers and reuse of latest creation optimization. Direct design review (review-spec unavailable) checked ownership boundaries, anonymous reads, no arbitrary manual-host fetch, legacy API compatibility, exact target confirmation, cancellation, saved intent and bilingual equivalence. User explicitly approved preview-before-confirmation, both providers, MPA-only scope and independent updates. Review blockers are resolved. Implemented against this approval; no commit, push or cloud write authorized.


## Delivery review and verification evidence

2026-10-22, HEAD 33671a15 plus the local MPA image diff after rebase onto upstream/main cb9975df. T-1–T-4 and AC-1–AC-5 are satisfied by local implementation and simulated verification. Direct implementation review checked source validation, provider/component repository isolation, pre/post-discovery ownership and revisions, no preview lock during discovery, no creation-state writes, saved-selection verification, cancelled/late reads and unknown-write blocking. No review blockers remain. Manual input and fixed tags preserve their paths. The upstream resolver and ordinary-agent production code were not modified for this extension.

| Requirements / acceptance | Command or procedure | Result |
| --- | --- | --- |
| FR-1..6 / AC-1..4 | Test-first targeted tests/cli/test_mpa_images.py and frontend/tests/mpaImages.test.tsx | pass: expected red baseline was 9 Python failures/64 passes and 5 UI failures/30 passes; both passed after implementation. |
| FR-1..6 / AC-1..4 | uv run --extra dev pytest -n 2 tests/integrations/mpa_managed tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py tests/test_mpa_collaborator_proxy_policy.py tests/skills/test_skill_telemetry.py tests/test_harness_sidecar_release_gate.py tests/test_studio_release_workflow.py -q | pass: 1613 tests, two workers selected to bound local resource use. Initial expanded run had one timeout because the new provider fixture had not mocked TAGApi; isolated that read and reran successfully. No real cloud write occurred. |
| FR-3,4,6 / AC-3..5 | npm --prefix frontend test | pass: 1389 Node tests and 234 Vitest tests, including manual IME/Enter, stale responses, independent writes and latest preview states. |
| FR-3,4 / AC-5 | npm --prefix frontend run build -- --emptyOutDir false; npm --prefix frontend run check:i18n; npm --prefix frontend run test:webui-assets | pass: TypeScript, app and widget builds; 2 locales/23 namespaces; 239 files/1031 references. Existing chunk-size advice remains. Retained old assets for the running server's cached references. |
| AC-5 | uv run --extra dev pre-commit run ruff-check --files frontend/server/mpa_images.py tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py; ruff-format on mpa_images.py and test_mpa_images.py via the same hook command | pass. |
| AC-5 | Pyright with repository .venv/bin/python on frontend/server/mpa_images.py and tests/cli/test_mpa_images.py | pass: 0 errors. |
| AC-5 | Pyright on tests/cli/test_frontend_runtime_proxy.py, compared to the preserved pre-change file | fail: the same 20 pre-existing diagnostics in both copies; 0 added diagnostics and none in the changed image-route test. No unrelated typing cleanup. |
| FR-3,4 / AC-3,5 | Real IAB browser against temporary Vite fixture with mocked image API only | pass: domestic Runtime loading/actual version/digest, BP Worker failure/read-only retry/independent selected-tag payload, cancel during a slow read, reopening, Tab/Escape/focus return, and 390px wrapped addresses/scrollable dialog/fixed action footer. Simulated writes only. Temporary page, tab and Vite process removed. Screenshot /tmp/veadk-mpa-latest-confirmation.png; narrow screenshot /tmp/veadk-mpa-latest-narrow.png. |
| AC-5 | Bilingual contract/identifier/relative-link review, git diff --check and scoped gitleaks detect --no-git with .gitleaks.toml | pass. Secret scan uses repository exclusions; no real credentials or raw production logs added. |
| AC-5 | Real cloud update, deployment and live account smoke | not_run: outside authorization. Studio restart/activation not_run: preserve the original launch environment; existing server remains running. Full pre-commit --all-files and whole-repository regression not_run: no commit requested; affected regression and scoped gates used. Codex process smoke and sidecar coverage not_applicable: their contracts were not changed. |

Activation: restart Studio using its original cloud credentials/environment and refresh the browser to load the new backend and bundled UI. No commit, push, publication or resource update was performed by this implementation task. Mutable selected tags still require publisher retention; submission verifies the chosen content immediately before dispatch but does not make the tag immutable.


## Authorized Git delivery checks

2026-10-22: The user subsequently authorized committing and pushing the local changes. This section supersedes the earlier not_run Git-gate entries; it covers the staged MPA collaboration and image-update changes on feat/from-upstream-main-20261020, based on HEAD 33671a15. Fetched origin/upstream and ran git rebase upstream/main: already current at cb9975df. Backed up and restored all 193 original changed paths before staging. Restored 27 accidentally omitted optional-platform lockfile entries to their existing HEAD contents; dependency versions are unchanged. Ruff formatted two already changed test files.

- pass: uv run --extra dev pre-commit run --all-files (Ruff check/format, hardcoded secret scanning, dependency policy and YAML secret scanning).
- fail (pre-existing): uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke": 7855 passed, 53 skipped, 4 xfailed, 1 failed in 457.53 seconds. The failure is tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes: this environment resolves .md as application/octet-stream instead of text/markdown. The unchanged writer file alone reproduces it (48 passed, 1 failed). A pristine git archive of HEAD, using the same Python environment, reproduces the identical failing assertion (1 failed). This is not an MPA regression and is recorded without modifying unrelated artifact behavior or weakening the assertion.
- pass: npm --prefix frontend test: 1389 Node and 234 Vitest tests; npm --prefix frontend run build -- --emptyOutDir false; npm --prefix frontend run check:i18n (2 locales, 23 namespaces); npm --prefix frontend run test:webui-assets (114 files, 351 internal references). Built output matches staged assets. The packaged asset count differs from the earlier retained-cache verification because the current tree contains only the current packaged set.
- pass: paired-language completeness/relative links for all 26 staged PRD/spec files and git diff --cached --check.

The known baseline test failure remains disclosed; no test was skipped to conceal it, no security hook was bypassed, and no real cloud update or Studio restart is part of this Git delivery. Push targets superops-team/veadk-python, feat/from-upstream-main-20261020; the prior authorized rebase requires force-with-lease against the fetched remote head rather than an unrestricted force push.
