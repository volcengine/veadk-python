# Deployment-account Ark key discovery

[中文](2026-10-10-account-ark-key.zh.md)

- Change ID: mpa-model-key-discovery; created/revised: 2026-10-10; status: implemented.
- Owner: managed MPA creation; contract: [Studio creation](../../../specs/studio-mpa-creation/README.md), CON-1/CON-16.

- Successor: [newest-created selection](2026-10-10-latest-created-key.md) supersedes the default multiple-key rejection; the original implementation record below is retained.

## Background and evidence

The built-in profile currently resolves `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY` during local inspection. This requires plaintext configuration and permits an unrelated account's key. Existing `get_ark_token` supports ListApiKeys/GetRawApiKey but defaults to the first key and can include raw errors. A dedicated bounded adapter will reuse the stateless signed-request utility without changing general Agent authentication. ArkCLI documents that ListApiKeys contains masked values and GetRawApiKey retrieves the actual key: https://github.com/volcengine/ark-cli/blob/main/skills/arkcli-profile/references/arkcli-profile-keys.md. The legacy ArkClaw client supports Id/Name without Status and returns Total; current VeADK supports TotalCount. Neither proves that a selected key can invoke the configured model.

## Goals, non-goals and scenarios

Automatically read an existing Ark key with deployment AK/SK or rotating STS; retain explicit private CLI configuration. Do not create/rotate keys, change existing Runtimes, modify general Agent behavior, or perform paid inference to test model access. All cloud verification in this change is simulated. If no key exists, the operator creates one in Ark; multiple matches require an exact selector.

## Requirements

- FR-1: Built-in local inspection needs no model secret or cloud call and ignores the obsolete model-key environment override. Add `managed.model-key` with mode `explicit` (CLI default) or `ark` (Studio default), optional mutually exclusive api-key-id/api-key-name and project-name=default. Studio selectors use `VEADK_MPA_ARK_API_KEY_ID` / `VEADK_MPA_ARK_API_KEY_NAME`; these are identifiers, not raw keys.
- FR-2: Ark mode only accepts a fresh OpenAI-compatible Ark template in the selected region and rejects model-key/provider/base environment overrides. After STS verification and before resource mutations, read keys using the same refreshed, account-checked credential source. List all pages (100 items, at most 100 pages), validate totals/IDs and deduplicate overlapping IDs. Select an exact ID/name or exactly one candidate; zero/multiple matches fail. A present Status must be Active; legacy absent Status is supported without claiming active-state verification. Use only GetRawApiKey.ApiKey, never masked Key fields.
- FR-3: Each HTTP read has 10-second connect and 30-second read timeouts. Retry connection/timeouts, throttling and availability at most three attempts with asynchronous 0.2/0.5-second delays. Permanent errors and malformed responses fail immediately. Cancellation stops new requests and mutations; an already-running read may finish within its timeout, but its result is discarded. Refresh credentials before each attempt; account changes fail. No CreateApiKey or inference call.
- FR-4: Raw values stay in a copied in-memory profile and the authorized Runtime environment. No values in logs, exceptions, config summaries, task/SQLite records or repository files. Emit allowlisted operation/category diagnostics. Existing pending deployment hashes continue rejecting changed keys/configurations on retry; discovery is repeated and never silently bypasses ambiguity. Runtime-held secrets remain platform-owned.
- FR-5: Keep explicit CLI key/reference/template behavior. Remove only the two obsolete local .env assignments after tests; retain other configuration and file permissions. No frontend fields/build artifacts or dependencies change.

## Design and affected files

Add managed/model_key.py; update config.py, studio_profile.py, service.py and diagnostic allowlists. Reuse volcengine_signed_request with local signing state; do not use the global-state signer or generic get_ark_token fallback. The adapter returns a fresh Profile. Deployment permissions already include ark:ListApiKeys and ark:GetRawApiKey; customer roles must grant them. Selection does not certify model activation, IP allowlists or model permissions; these remain deployment prerequisites. Configured=true means local validity, not successful live access. API response types and task stages are unchanged. Maintain paired managed READMEs and Studio component contract.

## Tasks and acceptance

T-1 / AC-1 (FR-1/FR-5): failing loader/route tests, then local configuration changes; preserve explicit CLI tests.
T-2 / AC-2 (FR-2/FR-3): adapter tests for STS, pagination, ambiguity, exact selectors, legacy/status responses, malformed/empty responses, transient/permanent failures, account changes and cancellation.
T-3 / AC-3 (FR-4): service ordering and safe injection tests; errors, diagnostics and summaries exclude raw values; retries retain existing hash conflict semantics.
T-4 / AC-4 (FR-5): targeted and full managed/CLI authentication regressions, changed-file Ruff/Pyright, paired document/link/whitespace review, scoped secret scan; safely remove obsolete local assignments. Live cloud and browser checks are not_run: no cloud mutations authorized and no UI change.

## Risks and recovery

No/multiple accessible keys and missing read permissions stop at checking; configure a selector or correct Ark permissions. An active key can still lack model access or become revoked; no runtime refresh/rotation is promised. Changed key material can block a pending retry rather than silently replacing its credentials. Existing agents are untouched. Restore explicit private CLI settings to retain manual-key provisioning if required; do not restore plaintext into tracked files.

## Review and approval

Direct review (review-spec unavailable): consistent boundaries, no added dependencies, bounded reads/cancellation, redacted provider failures, explicit legacy compatibility and paired-language semantics; no blockers. User approved the automatic-account-key approach in “帮我这么改，然后需要删掉这个.env文件是不是”. This approval does not authorize commit/push/deployment.

## Verification record

Date: 2026-10-10. Tested scope: working-tree diff on f7576c40; no commit/push/deployment.

- pass — test-first loader/route run reproduced three missing-key/default failures (82 existing cases passed); new adapter test collection failed before the module existed.
- pass — `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py tests/auth/veauth/test_ark_veauth.py -n 2 -q --no-cov`: 739 passed, including discovery, simulated complete Studio creation, explicit CLI/generic Ark authentication compatibility and IAM permissions. Two workers follow the repository default resource budget. Rerun after .env cleanup also passed.
- pass — `uv tool run --from ruff==0.11.12 ruff check <11 changed Python files>` and `ruff format --check`: all pass. `uv tool run --from pyright pyright --pythonpath .venv/bin/python <11 changed Python files>`: zero errors. A baseline copy of test_iam.py reproduced its nine existing type errors; minimal test-only types/assertions and typed Worker construction resolved them without production IAM changes.
- pass — `uv build --wheel --no-build-isolation --out-dir <temporary directory>` and wheel inspection: new model_key.py and stateless signer included, .env excluded. No release artifacts were added to the checkout.
- pass — Gitleaks v8.24.2 directory scan of all changed/new tracked-scope files with redaction, `git diff --check`, paired-language requirement/acceptance identifiers and added relative links review.
- pass — private .env cleanup removed only VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY and VEADK_MPA_CONFIG_PGPASSWORD assignments, retained other lines and file mode, and verified ignored/untracked status. No values were printed or copied to evidence.
- not_applicable — frontend build/tests and Codex smoke: no frontend, generated JavaScript or harness change. Existing HTTP shapes and deployment Runtime payloads are covered by Python route and simulated provisioning tests.
- not_run — browser/live Ark/model inference/cloud deployment: no UI change and no live cloud verification authorized. Actual account permissions, key availability, model activation and network/IP restrictions remain unverified.
- not_run — all-file pre-commit and full-repository tests: no commit requested; the scoped secret scan, static gates and complete affected suites ran instead.

Implementation review: no raw secrets in persistence/results/errors; stateless signing avoids cross-request global mutations; refreshed credentials preserve account checks; no extra requests after cancellation; existing explicit model auth stays unchanged. All T-1–T-4 and AC-1–AC-4 are complete with the live-verification limit above.

## Commit preparation (2026-10-10)

User authorization: “把当前的修改都提交吧”. Commit only; no push or deployment. Fetched origin/upstream, then ran `git rebase --autostash upstream/main`: the upstream-based branch was already current and the autostash restored successfully. All 172 changed/deleted/untracked file states matched their pre-sync hashes; no production or test files changed during hooks. The user-authorized existing package-lock changes are included; `npm ci --prefix frontend --dry-run --ignore-scripts --offline` passes without changing the lockfile.

- pass — `uv run --extra dev pre-commit run --all-files`: Ruff check/format, hardcoded-secret detection and YAML-secret scan.
- pass — changed Python production/test files checked with `uv tool run --from pyright pyright --pythonpath .venv/bin/python`: zero errors/warnings.
- pass — frontend full suite rerun after synchronization: 1,377 Node tests and 65 Vitest tests; multi-bot/channel/task regression rerun: 162 passed. Previous build, localization, coverage, asset and isolated browser evidence remains valid because synchronization/hooks changed no source or artifacts.
- fail, pre-existing baseline issue — `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 6,933 passed, 53 skipped, four xfailed, one failed, 55 warnings, 412.63 seconds. The sole failure is `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`: expected `text/markdown`, received `application/octet-stream`. The writer and test match HEAD byte-for-byte. An isolated `git archive HEAD` baseline using the repository Python environment reproduces the same failure; this host's `mimetypes.guess_type("summary.md")` returns `(None, None)`. Independent current writer suite reproduces it with 48 other tests passing. No unrelated MIME implementation/test change was added to this commit; the full suite is not represented as passing. This does not identify a regression in the submitted feature scope.
- pass — staged whitespace check and secret hooks; local `.env` remains ignored and excluded. Live Ark/Feishu/cloud verification and native browser confirmation/IME limits remain as recorded above; skipped tests do not establish live behavior.
