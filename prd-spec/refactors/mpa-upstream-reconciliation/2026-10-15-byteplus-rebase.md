# BytePlus change reconciliation after upstream history consolidation

[中文版](2026-10-15-byteplus-rebase.zh.md)

- Date: 2026-10-15
- Scope: reconcile original local commit `078602ec` onto remote branch base `08197629`.
- Authorization: the user requested resolving rebase conflicts and committing the result.
- Status: reconciled; the unchanged macOS MIME regression failure is recorded below.

## Evidence and approach

The interrupted rebase replayed seven commits, starting with `7f2ae0f8`. The remote base already consolidated the six historical lifecycle commits, including generic/MPA deployment separation, deletion, automatic OV creation, maximum instances, dependency-lock repair and license headers. Replaying them caused redundant documentation/test-script conflicts and generated-asset rename conflicts. The original tip and interrupted state were backed up before aborting that rebase. Rebase was restarted with `--onto 08197629 2ffe6e14`, replaying only the local BytePlus commit.

## Preserved behavior and affected files

Retain upstream TOS mounting configuration, image-selection rules and `ensure_tos_mount_permissions` together with local BytePlus OV provisioning, IAM transient diagnostics, Runtime diagnostics, original-request name recovery, provider-specific default images and server-side APM AppKey injection. Resolve `names.py` using the approved local Worker provenance check: matching `MPA_AGENT_ID` environment plus canonical `managed_by` and `mpa_agent_key` tags; contradictory ownership cannot authorize retry. Runtime tagless recovery remains limited to the authenticated original creation account. Retain the complete remote `frontend/package-lock.json`, since no package dependency change was requested. Regenerate `veadk/webui` from merged frontend source; never manually combine minified bundles.

Four Pyright findings in existing upstream test doubles were resolved with non-null assertions in `test_iam.py` and `test_service.py`. These assertions do not change production behavior. Shared database/network resources and deployed Runtimes are outside scope. Existing component contracts are unchanged; their already approved bilingual BytePlus additions are preserved. No new public API, provider permission, dependency or cloud mutation is introduced by this reconciliation.

## Review and acceptance

Direct review substitutes for the unavailable review-spec skill. History scope, ownership checks, provider separation, TOS/APM ordering, complete lock data, generated assets, test coverage and paired documentation were reviewed. Acceptance requires a single local feature commit above the remote base, no conflict markers, preservation of both upstream TOS and local BytePlus behavior, regenerated assets and the checks below. Live Worker dispatch, OV data-plane compatibility and overseas tracing remain separate Runtime/image work; local tests cannot establish those outcomes.

## Verification (2026-10-15)

- pass: targeted conflict/integration tests, 383 passed; test-only assertion follow-up, 204 passed.
- pass: `npm --prefix frontend ci --ignore-scripts --no-audit --no-fund` using the complete lock file.
- pass: `npm --prefix frontend test`, 1,389 Node tests and 111 component tests.
- pass: `npm --prefix frontend run build`, TypeScript and both production bundles.
- pass: `npm --prefix frontend run check:i18n` and `npm --prefix frontend run test:webui-assets`, 113 files and 350 internal references.
- pass: Pyright on 25 changed Python files after the four test-only assertion corrections.
- pass: `uv run --extra dev pre-commit run --all-files`, initial and final staged-source runs; documentation-only final repeat follows this record.
- fail: `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`, 7,441 passed, 1 failed, 53 skipped, 4 xfailed in 509.32 seconds. Two workers limit local resource pressure. The sole failure is `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`: this macOS Python reports no MIME for `.md`, so unchanged code emits `application/octet-stream` instead of `text/markdown`. Writer, MIME helper and test are identical to remote base `08197629`; the isolated unmodified test file reproduces the failure (48 passed, 1 failed). No unrelated production change or global MIME configuration was made.
- pass: a separate process adding only the expected `text/markdown` mapping for `.md` runs all 49 artifact-writer tests successfully. This controlled environment check does not replace the recorded full-suite failure.
- pass: `uv build --wheel --out-dir /tmp/veadk-rebase-wheel`; the new BytePlus modules and relocated contract JSONs are present, `.env` is absent. All seven newly added local Python modules remain byte-identical to `078602ec`.
- blocked: existing Studio process caches pre-build HTML referencing removed assets, yielding HTTP 404. Browser opened the page but could not exercise the creation dialog. The active user service was not restarted; restart is needed to load the rebuilt HTML.
- not_run: real cloud creation/deletion and Runtime smoke; no cloud writes are authorized by this Git reconciliation task.
