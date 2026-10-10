# Select the newest existing Ark key

[中文](2026-10-10-latest-created-key.zh.md)

- Change ID: mpa-latest-created-key; created/revised: 2026-10-10; status: implemented.
- Predecessor: [account-key discovery](2026-10-10-account-ark-key.md).
- Component: [Studio creation](../../../specs/studio-mpa-creation/README.md), CON-16.

## Background and evidence

`resolve_model_key` currently rejects multiple candidates without an exact selector. The user requests automatic selection of the latest-created key to preserve one-click creation. Existing pagination, account checks, status filtering and secret handling already belong to the discovery adapter. A read-only metadata probe could not load local deployment credentials; the live timestamp shape is unverified. The adapter will accept creation metadata explicitly and fail if it cannot establish which key is newest; list order is not evidence of creation order.

## Goals, non-goals and scenarios

Select the newest creation time among eligible keys in the configured project without extra configuration. Preserve explicit ID/name selection, generic Agent authentication, CLI explicit mode and existing Runtime credentials. Do not create keys, perform inference, persist raw keys, or migrate existing tasks.

## Requirements and design

- FR-1: With no selector and multiple eligible keys, read all existing bounded pages and select the maximum creation instant. Accept `CreateTime` (or `CreatedAt` / `CreationTime` compatibility fields), positive finite Unix seconds/milliseconds including numeric strings, or timezone-qualified ISO 8601. Normalize to UTC. Missing/invalid metadata on any eligible candidate fails before GetRawApiKey. Exactly one eligible key needs no timestamp.
- FR-2: Creation-time ties use the lexicographically greatest string ID, independent of page order; this is deterministic tie-breaking, not inferred chronology. Explicit ID/name selectors retain precedence and require exactly one match, including failure on duplicate names. Inactive keys are filtered before timestamp comparison; legacy absent Status remains supported without claiming active-state verification.
- FR-3: Account verification, refreshing credentials, cancellation, bounded retry, safe diagnostics and Runtime-only raw-key injection remain unchanged. Retry rediscovers keys; if a newer key appears after partial deployment, existing payload hashes may reject the change rather than silently replacing credentials. Existing agents are untouched.

Affected files: `managed/model_key.py`, `test_model_key.py`, paired managed READMEs and Studio creation specs. No API shape, frontend, dependency or schema change. Timestamp parsing is an adapter concern; configuration selectors remain optional.

## Tasks, tests and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1 | AC-1: newest selected across pages and timestamp formats; invalid metadata fails without raw lookup | Adapter regression tests, failing before implementation |
| FR-2 | T-2 | AC-2: explicit override, inactive filtering and tie ordering preserved | Adapter tests with reversed ordering, newer disabled key and older explicit selection |
| FR-3 | T-3 | AC-3: affected complete regression and static/security gates pass; documentation agrees | Managed/CLI/auth suites, Ruff, Pyright, Gitleaks, paired links and whitespace |

## Risks and recovery

Newest does not certify model permissions, IP restrictions or inference eligibility. Creation timestamps returned by the real account remain unverified; unsupported metadata fails safely and an explicit selector remains available. A key created during a pending task can change its payload and trigger the existing hash conflict. No implicit rotation or retry fallback is introduced.

## Review and approval

Direct review because review-spec is unavailable: bounded parsing, deterministic ordering, selector compatibility, secret isolation, cancellation and bilingual equivalence checked; no blockers. User approval: “账号下有多个key，选最新创建的那个吧”. This authorizes this selection change, not commit/push/deployment. The predecessor retains its historical selection decision; CON-16 and the maintained user docs describe the successor.

## Verification record

2026-10-10; working-tree scope on f7576c40. Implementation and regression results follow. Live metadata probe: blocked before a provider request by unavailable local deployment credentials; no raw key was read and no cloud resource was changed. Frontend/browser gates: not_applicable, no UI change. Full pre-commit and repository regression: not_run, no commit requested; complete affected suites and changed-file gates required.


- pass — test-first adapter run: 35 failures reproduced the missing newest-selection/error behavior, with 29 unchanged cases passing; after implementation, all 64 adapter cases passed.
- pass — `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py tests/auth/veauth/test_ark_veauth.py -n 2 -q --no-cov --tb=short`: 773 passed, rerun after the final type-narrowing repair. Two workers follow repository resource guidance; ten existing deprecation warnings remain.
- pass — `uv tool run --from ruff==0.11.12 ruff check` and `ruff format --check` on model_key.py and test_model_key.py; `uv tool run --from pyright pyright --pythonpath .venv/bin/python` on both files: zero errors after replacing a runtime-only type check with explicit type narrowing.
- pass — Gitleaks v8.24.2 redacted directory scan of all 19 changed/new source/document files, paired requirement/acceptance/task identifiers and relative design links, and `git diff --check`.
- blocked — live account timestamp verification: local deployment credentials unavailable; no ListApiKeys result or raw key was obtained. The API field aliases and timestamp formats are isolated, tested adapter inputs, not claimed live observations.
- not_applicable — frontend build/browser and Codex smoke: no UI/generated JavaScript/harness changes.
- not_run — all-file pre-commit/full repository suite: no commit requested; complete affected suites and scoped gates passed.

Implementation review: all eligible timestamps are evaluated, inactive records do not affect selection, explicit selection skips time requirements, and ties are independent of list order. Error text never includes provider metadata or raw values. T-1–T-3 / AC-1–AC-3 are complete within the stated live-verification boundary.

## Commit preparation (2026-10-10)

User authorization: “把当前的修改都提交吧”. Commit only; no push or deployment. Fetched origin/upstream, then ran `git rebase --autostash upstream/main`: the upstream-based branch was already current and the autostash restored successfully. All 172 changed/deleted/untracked file states matched their pre-sync hashes; no production or test files changed during hooks. The user-authorized existing package-lock changes are included; `npm ci --prefix frontend --dry-run --ignore-scripts --offline` passes without changing the lockfile.

- pass — `uv run --extra dev pre-commit run --all-files`: Ruff check/format, hardcoded-secret detection and YAML-secret scan.
- pass — changed Python production/test files checked with `uv tool run --from pyright pyright --pythonpath .venv/bin/python`: zero errors/warnings.
- pass — frontend full suite rerun after synchronization: 1,377 Node tests and 65 Vitest tests; multi-bot/channel/task regression rerun: 162 passed. Previous build, localization, coverage, asset and isolated browser evidence remains valid because synchronization/hooks changed no source or artifacts.
- fail, pre-existing baseline issue — `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 6,933 passed, 53 skipped, four xfailed, one failed, 55 warnings, 412.63 seconds. The sole failure is `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`: expected `text/markdown`, received `application/octet-stream`. The writer and test match HEAD byte-for-byte. An isolated `git archive HEAD` baseline using the repository Python environment reproduces the same failure; this host's `mimetypes.guess_type("summary.md")` returns `(None, None)`. Independent current writer suite reproduces it with 48 other tests passing. No unrelated MIME implementation/test change was added to this commit; the full suite is not represented as passing. This does not identify a regression in the submitted feature scope.
- pass — staged whitespace check and secret hooks; local `.env` remains ignored and excluded. Live Ark/Feishu/cloud verification and native browser confirmation/IME limits remain as recorded above; skipped tests do not establish live behavior.
