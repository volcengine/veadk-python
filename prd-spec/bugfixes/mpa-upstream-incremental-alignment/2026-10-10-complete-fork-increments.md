# Complete fork MPA increments on official main

- Change ID: `mpa-upstream-incremental-alignment`; date: 2026-10-10; status: implemented.
- [Chinese](2026-10-10-complete-fork-increments.zh.md).
- Contract: [Studio MPA control plane](../../../specs/studio-mpa-control-plane/README.md).

## Background and evidence
The prior official contribution branch `feat/mpa-studio-upstream-alignment-20261009` ends at `033b2711`; official PR #1156 landed as `171d8d86`. Fork main `035387d1` has a different history. Official PR #1160 starts directly from `171d8d86` and already includes fork PR #23, but omits PR #22's Basic-only MPA details. Copying the entire fork tree would remove newer official Codex and other changes.

The incremental audit uses the fork alignment merge `ef0ad519` through `035387d1`, compared with official base and contribution HEAD `80fd1e19`. This establishes feature coverage, rather than treating every historical commit as an unapplied change.

| Fork change | Contribution treatment |
| --- | --- |
| PR #21: entered Runtime name, description, three-step creation, image defaults, name validation, TOS guidance | Already in official PR #1156; retain unchanged. |
| PR #22: Basic-only MPA details, synchronous focus normalization, no hidden Profile requests | Port production code, regression tests, documentation, and rebuild release assets. |
| PR #23: STS account resolution, IAM preparation and Python 3.10 timeout, network discovery/description/subnet order, standard APIG, independent worker creation/defaults/naming, skill-space description, deployment diagnostics | Already in #1160; retain unchanged and run affected regressions. |
| Lockfile restoration | Effective lockfile content already present on official main; retain. |
| Official secret-scan exclusions and cancellation PID race fix | Retain official implementation; fork lacks these contribution fixes. |
| Official BytePlus sidecar behavior and SDK features | Retain; differences from fork are not new fork increments. |

## Goals, scenarios and requirements
FR-1 / AC-1: all effective fork increments since the previous contribution remain available in the official contribution; no blanket fork/main merge or reversed official changes.
FR-2 / AC-2: selecting an MPA, restoring any hidden section, or switching from a General agent renders Basic only before effects run, with no Agent View/Profile/session configuration requests or Profile operations. General navigation and update behavior remain.
FR-3 / AC-3: package tests, bilingual contracts and historical designs accompany source changes; generated web assets match the combined official source.
FR-4 / AC-4: preserve official secret scanning and cancellation fixes, and run the current repository gates with honest results.
Non-goals: backend API redesign, chat changes, cloud resource creation, deployment, merging the official PR, rewriting fork main, or closing another PR.

## Design and affected files
Port the reviewed PR #22 patch to `frontend/src/ui/AgentWorkspace.tsx`; derive the effective section synchronously from category and requested section. Keep hidden control-plane implementations and their cleanup, gated by their owning sections. No new dependencies, data migration, authentication or concurrency contract changes. Update `frontend/tests/mpaBasicDetails.test.tsx`, source-contract tests and the package test command; append the Basic-only contract to both component spec languages and README while retaining official documentation. Import the historical Basic-only PRD pair; its dated cloud evidence is historical, not evidence of this integration. Rebuild `veadk/webui` from the combined tree.

## Tasks and verification
T-1 (FR-1): audit all paths changed by `ef0ad519..035387d1`, excluding generated hashes and formatting-only historical document differences; account for each remaining difference.
T-2 (FR-2): run the imported component regression before porting production code, then port the patch and source-contract expectations.
T-3 (FR-3): frontend tests, build, i18n, asset references, component coverage and loopback browser checks using the actual component with mocked network boundaries.
T-4 (FR-4): targeted managed-creation/CLI tests, default two-worker Python regression, fetch/rebase official base, all-files pre-commit, and diff/document review before authorized commit/push.
Browser cases: MPA and General navigation, hidden focus, switching, normal/loading/empty/error Runtime information, read-only and narrow viewport, keyboard focus. New input/IME, mutation cancellation and retry are not applicable because this patch introduces no inputs or mutations; existing creation/sidecar regressions remain required. Live cloud writes are not run.

## Risks and review
Risk: replacing whole files from fork could overwrite official enhancements. Resolution: only port the audited PR #22 behavior and use content comparisons for retained creation paths. Asset churn is required hashed build output, not additional hand-written functionality.
Direct design review performed because `review-spec` is unavailable: boundaries, effect ordering, cleanup, compatibility, security, tests and bilingual equivalence have no blockers. Referenced frontend design skills are absent locally; existing SPEC/Foundation rules and direct review apply. No visual redesign or new components are proposed.
Approval: the user's explicit 2026-10-10 request to compare the previous contribution and include all new main functionality approves this bounded integration; prior authorization to prepare/push the official PR remains applicable.

## Delivery record
Checks below cover the integration diff above `80fd1e19`, with matching evidence in the Chinese counterpart. No current cloud verification is claimed.

Verification record on 2026-10-10, integration diff over `80fd1e19`:
- **pass**: path audit: 83 non-generated paths in `ef0ad519..035387d1`; all effective new source/tests/contracts/designs match fork main. Exceptions: README preserves official documentation and adds bilingual guidance; `test_tasks.py` preserves the official PID race fix; four historical PRDs differ only in trailing whitespace. Official secret-scan exclusions, BytePlus behavior and Codex SDK files are retained.
- **pass**: regression first: `npm --prefix frontend exec -- vitest run --root frontend tests/mpaBasicDetails.test.tsx` failed all 10 cases before production port; after port, all 10 pass.
- **pass**: `npm --prefix frontend test`: 1,377 Node and 65 Vitest tests.
- **pass**: `npm --prefix frontend run build` (TypeScript plus app/widget builds); `npm --prefix frontend run check:i18n`; `npm --prefix frontend run test:webui-assets` (113 files, 350 references).
- **pass**: `npm --prefix frontend run test:harness-sidecar-coverage`: statements 98.55%, branches 94.44%, functions/lines 100%, above the existing thresholds.
- **pass**: `npm --prefix frontend exec -- vitest run --root frontend tests/mpaBasicDetails.test.tsx --coverage --coverage.include=src/ui/AgentWorkspace.tsx --coverage.reporter=json`: changed executable statement-start lines 7/7 covered (100%); not whole-component coverage.
- **pass**: loopback in-app browser, actual `AgentWorkspace` with mocked fetch: MPA Basic-only including restored Profile/session focus, chat callback, General navigation/Integration, switching back, Runtime normal/loading/failure, empty envs and read-only, keyboard Tab focus, 390px viewport (body width 390px), no hidden control-plane requests. Integration discovery failure was simulated, not a live provider result. Temporary fixture, tab, viewport override and server removed.
- **pass**: `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py -q`: 678 passed. An initial invocation referenced a nonexistent extra test path and ran no tests; corrected above.
- **not_applicable**: focused Ruff/Pyright for new Python code (no Python files changed in this integration); all-files pre-commit still required. Real cloud creation/deployment and new IME/mutation flows were not run as explained above.
- **fail** (unchanged baseline): `uv run --extra dev --extra codex --extra extensions --extra sandbox pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 6,869 passed, 53 skipped, 4 xfailed, 1 failed in 480.71s. Two workers were used per the repository default. Optional dependencies were prepared through declared extras in the repository-local environment; no dependency file changed. The only failure is `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`: local Python 3.10/macOS `mimetypes.guess_type("reports/summary.md")` returns no type, producing `application/octet-stream` instead of `text/markdown`. The test and complete `frontend/server/runtime_artifacts/` implementation are identical to official main. This unrelated baseline remains a limitation, not a passing test.
- **pass**: refreshed `origin/main` and `upstream/main` remain `035387d1` and `171d8d86`; `git -c rebase.autoStash=true rebase upstream/main` reported up to date and restored all integration changes.
- **pass**: bilingual links/requirement IDs/quoted identifiers and scoped diff whitespace review. Direct final review found no lost increments, new dependencies, backend/chat changes, or overwritten official fixes.
- **pass**: after synchronization, `uv run --no-sync --extra dev pre-commit run --all-files`, `uv run --no-sync --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py -q` (678 passed), and `npm --prefix frontend test` (1,377 Node / 65 Vitest) passed again. `--no-sync` preserves the prepared repository-local optional extras. Commit/push metadata belongs to Git and the official PR.

| Requirement | Task | Acceptance | Evidence |
| --- | --- | --- | --- |
| FR-1 | T-1 | AC-1: all effective increments retained | 83-path audit and documented official exceptions: pass. |
| FR-2 | T-2 | AC-2: Basic-only MPA, unchanged General | 10 regression cases plus loopback browser: pass. |
| FR-3 | T-3 | AC-3: tests, documents and matching assets | Frontend/build/i18n/assets/coverage and bilingual review: pass. |
| FR-4 | T-4 | AC-4: preserve official fixes and execute gates honestly | Rebase, pre-commit, targeted tests: pass; full regression: one unchanged MIME baseline failure recorded. |
