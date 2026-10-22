# Fork CI validation and frontend gate timeout

[中文版](2026-10-22-fork-ci-validation.zh.md)

Change ID: studio-fork-ci-validation. Date: 2026-10-22. Status: approved.

## Evidence and scope

PR #1178 at `86d56c47` passed unit tests, license, secrets, dependency policy,
and backend checks. Both callers of the shared frontend gate timed out during
`npm ci --ignore-scripts`. Runs `39593230026` and `39593230579` explicitly report
that the job exceeded its 3-minute limit; their aggregate gates failed because
the frontend result was cancelled. The lockfile includes npmmirror URLs. Whether
that mirror caused the delay is unproven. The existing release verifier already
uses the public npm registry and `replace-registry-host=always`.

The user requested fixing CI and first completing it in their own fork PR to
avoid upstream approval waits. Scope is CI configuration and contract tests;
runtime, UI, image selection, dependencies, and lockfile contents are unchanged.

## Requirements and design

- FR-1: Given either caller, the shared frontend job uses the public npm registry,
  replaces lockfile registry hosts, and has a bounded 10-minute budget. Keep
  coverage, frontend tests, parallel execution, and fail-closed aggregation.
- FR-2: Given a PR in a fork, run the same shared gate and Studio bundle/smoke
  verifier. Remove the upstream-repository restriction only from PR validation.
- FR-3: Given a fork PR or push, publication and notification remain disabled.
  Release allocation, publication, and notification still require manual dispatch
  from upstream `main`; workflow permissions remain `contents: read`.

Affected consumers are the standalone shared workflow and the release workflow
that calls it. No component-spec change: application APIs, persisted state,
permissions, deployment, or runtime contracts do not change. The increased CI
budget and wider validation trigger are owned by these workflows. No new secrets,
dependencies, caches, retries, or publishing capabilities are introduced.

## Tasks and acceptance

1. T-1 / AC-1: Extend existing YAML contract tests; demonstrate failure before
   changing workflows. Assert registry settings, 10-minute timeout, PR validation,
   read-only permissions, and unchanged release guards (FR-1/2/3).
2. T-2 / AC-2: Update `.github/workflows/harness-sidecar-release-gate.yaml` and
   `.github/workflows/publish-studio-release.yaml`; run contract tests, changed
   Python Ruff/Pyright, all-files pre-commit, actual frontend coverage/tests, and
   a production build in a temporary output directory (FR-1/2).
3. T-3 / AC-3: Create a fork PR against a branch pinned to upstream `main`, run
   all applicable PR CI, and verify publication/notification are skipped. Report
   any outstanding failures; do not equate local passes with hosted CI (FR-2/3).
4. T-4: After fork verification succeeds, bring the verified fix to upstream
   PR #1178 and report the fork evidence. Hosted upstream approval may remain.

## Review, risks, and delivery

User approval: “当前ci又有几个没过 先去修一下”, followed by requesting complete CI
in their own fork PR. Direct design review (no review-spec skill available):
confirmed both callers share the job, full validation remains credential-free,
release guards stay intact, tests cover all changed YAML values, and both language
versions match. No blockers. Slow public network access can still exceed the
10-minute cap; a timeout remains a failure. Fork branch protection is not proof
of upstream policy. There is no executable production-code delta, so incremental
production coverage is not applicable; YAML contract checks cover the config.

Local verification on 2026-10-22: pass, 272 Python tests across both workflow
contracts and the image snapshot/service suites; both regressions failed before
the workflow edits. Pass, repository-pinned Ruff 0.11.12, Pyright using the project
Python, and all-files pre-commit. Pass, frontend Sidecar coverage (22 tests;
100% lines, 94.44% branches), frontend tests (1389 Node tests and 118 Vitest tests),
and production build to `/tmp/studio-fork-ci-build-20261022`. Local Node 25.2.1 /
npm 11.6.2 differ from CI's pinned Node 22.17.0 / npm 10; hosted CI remains required.
The formatter modified one test file and all-files pre-commit passed on rerun.
An unpinned Ruff invocation and Pyright without the project Python were unsuitable;
the pinned/project-aware commands above passed without rule suppressions.

Hosted fork CI: pending (AC-3). No cloud MPA creation or application redeployment
is needed for this CI-only change.
