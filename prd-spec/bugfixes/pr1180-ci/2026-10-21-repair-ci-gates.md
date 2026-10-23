# Repair PR #1180 CI Gates

[中文版](2026-10-21-repair-ci-gates.zh.md)

## Metadata

- Change ID: `pr1180-ci`
- Created/Revised: 2026-10-21
- Status: implemented (publication authorized; verification in progress)
- Related component specs: none; generated metadata, license comments, and test fixture text preserve all runtime contracts.
- Predecessor: [frontend lock restoration](../frontend-lockfile-sync/2026-10-09-restore-esbuild-lock-entries.md).

## Background and Evidence

At PR head `8f9911b8`, run `39579012758` fails `npm ci --ignore-scripts`: esbuild 0.28.2 and its platform packages are missing. Commit `d2dc3da2` removed 512 lock lines; the only package.json change is a test command, so dependency declarations still match its parent.

Run `39579012740` reports missing Apache headers in the two MPA proxy modules and their policy tests. Run `39579012654` reports one unverified PostgreSQL finding in a fake connection string in `test_creation_failure_details.py`. No verified credential is reported. A follow-up commit alone cannot clear this finding because the workflow scans PR history.

## Goals and Non-goals

Restore reproducible installation, required license headers, and scanner-safe test data while preserving redaction assertions. Dependency upgrades, runtime changes, scanner exclusions, deployment, commits, pushes, and history rewrites are outside the local repair authorization.

## Scenarios and Requirements

- `FR-1`: Given unchanged dependency declarations, CI installation must accept the complete lock graph.
- `FR-2`: Given the four Python files, each must carry the standard `.licenserc.yaml` header.
- `FR-3`: Given private exception text, diagnostic events must retain origin metadata and omit private text. The fixture must not contain a credential-shaped connection string.
- `FR-4`: Local verification must distinguish working-tree remediation from the remaining historical scan failure.

## Design and Contract Impact

Restore `frontend/package-lock.json` from `d2dc3da2^` without regenerating or upgrading dependencies. Add comment-only headers to `veadk/integrations/mpa/{agents_md_proxy,collaborator_proxy}.py` and `tests/test_mpa_{agents_md,collaborator}_proxy_policy.py`. Replace only the exception fixture text in `tests/integrations/mpa_managed/test_creation_failure_details.py`; preserve all assertions.

Public APIs, permissions, state, concurrency, configuration, generated code, and component contracts are unchanged. UI/browser and live cloud checks are not applicable because no UI, network behavior, or cloud call changes. Existing CI failures provide the red baseline; use the existing diagnostic regression test rather than adding a test of comments or lock text.

Reject scanner allowlisting and dependency upgrades: neither addresses the narrow cause. A separately authorized rewrite must remove the fixture from the introducing commit and preserve authorship, with remote synchronization and lease protection before publishing.

## Tasks and Verification

| Requirement | Task | Acceptance | Command/evidence | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`: restore lock | `AC-1`: exact parent graph; clean install | `git diff d2dc3da2^ -- frontend/package-lock.json`; `npm --prefix frontend ci --ignore-scripts` | pass: no diff; 695 packages installed |
| `FR-2` | `T-2`: add headers | `AC-2`: standard header in all four files | Compare with `.licenserc.yaml` and the existing diagnostic test header; Ruff | pass: all four match |
| `FR-3` | `T-3`: repair fixture | `AC-3`: existing assertions pass | `uv run --extra dev pytest tests/integrations/mpa_managed/test_creation_failure_details.py tests/test_mpa_agents_md_proxy_policy.py tests/test_mpa_collaborator_proxy_policy.py -q` | pass: 34 tests |
| `FR-1` | `T-4`: frontend gates | `AC-4`: coverage, tests, build pass | `npm --prefix frontend run test:harness-sidecar-coverage`; `npm --prefix frontend test`; `npm --prefix frontend run build -- --outDir /tmp/veadk-pr1180-build --emptyOutDir false` | pass: 22 coverage tests; 1,389 Node and 154 Vitest tests; both builds |
| `FR-4` | `T-5`: review and report | `AC-5`: honest checks and history limitation | `uv run --extra dev pre-commit run --all-files`; diff review; `gh pr checks 1180 --repo volcengine/veadk-python` | pass locally; remote still has the original three failures and pending jobs |

Execute T-1 through T-3 first, T-4 next, T-5 last. No rollout is included. Restore the affected files from HEAD to recover the local repair if necessary, after preserving any later user changes.

## Risks and Review Record

- Local macOS/Node 26 verification differs from Ubuntu/Node 22.17.0 CI.
- Build output must be isolated so verification does not introduce unrelated packaged asset changes.
- Historical secret scanning remains unresolved until the user authorizes rewriting and publishing the PR commits.
- 2026-10-21: User approved the previously explained three repairs with “帮我修一下”.
- 2026-10-21: `review-spec` review confirms narrow scope, no contract impact, preserved assertions and bilingual equivalence. The historical scan limitation is explicitly separated from local acceptance. No local design blocker remains.
- 2026-10-21: All local acceptance checks above ran against HEAD `8f9911b8` plus this repair. No dependency declarations, scanner rules, production statements, test assertions, or tracked web assets changed. Header equality was checked using `head -14` and `diff` for all four files.
- Ruff: `uv run --extra dev ruff check` with the five changed Python paths passed. Pyright was initially unavailable via `uv run`; isolated `uvx pyright --pythonpath .venv/bin/python` with those paths passed with 0 errors and 0 warnings. Running uvx without the repository interpreter first produced missing-import errors; selecting the correct interpreter resolved them without changing configuration.
- Coverage: statements 98.55%, branches 94.44%, functions and lines 100%. `git diff --check` passed. Manual final review confirms fixture redaction coverage is unchanged and the restored lock exactly matches the complete parent blob.
- Test workflow: Step1–Step5 completed with one fixture repair/verification round (`all-pass`); no new test cases or production defect findings. Step6 Python coverage is not_applicable to this fixture/comment repair; no applicable coverage target changed. Step7 `utree flush` passed.
- Broad Python regression and backend Sidecar gates: not_run locally because no executable production logic or shared contract changed; PR Python 3.12 regression passed. Real cloud, runtime smoke, and browser checks: not_applicable to this repair. Local Apache Eyes and TruffleHog binaries: not_run, unavailable; standard header comparison and pre-commit secret gates passed, but they do not prove a clean historical TruffleHog scan.
- Installation reports 16 existing dependency audit findings; dependency remediation remains outside this restoration. Build reports large-chunk warnings and completes successfully.
- Repository helper plan/handoff runs returned `onboarding_required` because no Manifest exists; actual acceptance is recorded here using repository-native checks. No repository onboarding changes were introduced.
- 2026-10-21: The user explicitly authorized rewriting and publishing with “允许”. Both remotes were fetched: `upstream/main` remains `5e5deb6a`, and the expected remote PR head remains `8f9911b8`. Interactive rebase onto `upstream/main` places each repair in its introducing commit while preserving author identity and author date.
- First rewritten commit `03814668`: all-files pre-commit passed and 30 affected tests passed before amendment. Commit hooks passed without bypasses.
- Final second-commit working tree: all-files pre-commit passed and all 34 affected tests passed in 2.28s after remote synchronization. The six repaired files exactly match the previously verified local repair; no unrelated implementation or asset diff was introduced. Whitespace checks passed.
- Publication plan: finish the second amendment with remaining headers and this bilingual evidence, rerun all-files pre-commit and the 34 affected Python tests, verify the final diff and rewritten history, then push with an explicit lease bound to remote head `8f9911b8188c5bba20085c0ff68c6b7e5fe02050`. Cloud deployment and merging remain outside authorization.
