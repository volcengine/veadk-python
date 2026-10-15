# Restore PR 1167 CI without changing product behavior

[中文版](2026-10-15-lock-and-tos-tests.zh.md)

Date: 2026-10-15. Base: `8ae26a6d`. Status: approved for implementation.

## Background and scope

PR 1167 frontend CI and release verification fail at npm ci because the lockfile lacks esbuild 0.28.2 and its platform packages for the nested Vite dependency. Python 3.12 reports three failures in test_creation_images.py: old assertions forbid persisting tosBucket, conflicting with the approved [local task recovery design](../mpa-creation-local-state/2026-10-15-local-task-recovery.md). Bucket names are nonsecret request identity; TOS credentials must remain excluded.

## Requirements and design

- R1: Repair only missing lockfile resolution entries. Keep package.json, all existing package versions and product source unchanged. Generate in a clean directory using CI-compatible Node/npm; verify a clean npm ci.
- R2: Update the three stale test cases to require the selected bucket in the task response/persistent payload and retain secret-exclusion checks. Read the stored JSON structurally, rather than searching raw SQLite bytes. Preserve existing request-change rejection and child TOS forwarding tests.
- R3: Run targeted failures first, then managed Python regression, npm test, build, sidecar coverage, and changed-file lint/secret checks. Do not weaken CI gates or remove tests.

Affected files: frontend/package-lock.json; tests/integrations/mpa_managed/test_creation_images.py; this bilingual design. Component contract impact: none; this restores verification of the existing task recovery contract and completes development dependency metadata. No production runtime, public API, cloud resources or security policy changes. No deployment, publication, commit or push in scope.

## Tasks and acceptance

1. Reproduce existing test failures and lockfile installation failure in isolation.
2. Repair lock metadata and align assertions; preserve bucket-change conflict and secret rejection behavior.
3. Verify that existing locked packages retain versions, clean install succeeds, all affected tests and build pass, then inspect the final diff.

Risks: npm can rewrite unrelated metadata, so compare all existing lock entries; builds may generate assets, so run in an isolated workspace and avoid unrelated asset churn. Linux CI must still rerun after publication; macOS validation is not Linux execution. UI/browser checks are not applicable to this metadata/test-only change.

## Review and approval

User approved the previously proposed scope with “帮我修一下，不要影响功能”. Direct design review (review-spec unavailable) checked contract alignment, security, minimal scope, dependency compatibility, tests and bilingual equivalence; no blockers. Existing failure evidence is the regression-first baseline; production behavior remains unchanged.

## Verification

Completed; detailed evidence follows.


## Verification record

2026-10-15, base `8ae26a6d`, lockfile/test/documentation diff only:

- pass: reproduced the exact npm ci missing-esbuild error under Node 22.17.0/npm 10.9.2 in a clean temporary directory and the three pytest failures (15 other cases passed).
- pass: `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` in that directory adds exactly 27 lock entries. Structural comparison confirms no existing entries or versions changed. package.json and all production sources remain unchanged.
- pass: clean `npm ci --ignore-scripts --no-audit --no-fund` with Node 22.17.0/npm 10.9.2 on macOS installs 697 packages.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed -n 2 -q --tb=short` — 1151 passed on Python 3.10; two workers bound local resource use.
- pass: isolated Python 3.12 environment, `uv run --python 3.12 --extra dev pytest tests/integrations/mpa_managed/test_creation_images.py tests/integrations/mpa_managed/test_routes.py tests/integrations/mpa_managed/test_tasks.py -n 2 -q --tb=short` — 55 passed, including bucket-change rejection and persistence coverage. The repository environment was not replaced.
- pass: `npm test` in the isolated frontend workspace — 1389 Node tests and 118 Vitest tests passed. The first isolated attempt lacked supporting repository files and failed four test modules with ENOENT; copying the required tracked support files resolved the harness setup error without code changes.
- pass: `npm run test:harness-sidecar-coverage` — 22 tests; statements 98.55%, branches 94.44%, functions/lines 100%.
- pass: `npm run build` in the isolated workspace — TypeScript and both Vite builds succeeded; existing size/deprecation warnings remain. No generated repository assets are included in this change.
- pass: changed-file pre-commit Ruff check/format and secret scan; dependency/YAML hooks not_applicable; `git diff --check` and bilingual identifier/link review.
- fail (pre-existing): changed-file Pyright reports two diagnostics. The same command against the HEAD file reports identical rules/messages; no newly introduced diagnostics. No unrelated type cleanup.
- not_run: full-repository Python suite and GitHub rerun (no commit or push requested). Affected regression completed above.
- not_applicable: real browser/cloud smoke; no product UI/runtime behavior changed.

Linux container validation: pass. Fresh `node:22.17.0-bookworm-slim` on Linux ARM64 (Node 22.17.0/npm 10.9.2), `npm ci --ignore-scripts --no-audit --no-fund`, `npm run test:harness-sidecar-coverage`, and `npm test` all exited successfully: 22 coverage tests, 1389 Node tests and 118 Vitest tests. GitHub Linux x64 rerun remains separate. No commit, push, deployment or cloud resource mutation performed.
