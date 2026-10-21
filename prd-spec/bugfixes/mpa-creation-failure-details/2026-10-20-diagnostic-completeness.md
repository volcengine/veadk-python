# Complete MPA exception diagnostics

[中文](2026-10-20-diagnostic-completeness.zh.md)

- Change: mpa-diagnostic-completeness; date: 2026-10-20; status: implemented.
- Predecessor: [failure display](2026-10-20-failure-details.md).
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).

## Evidence, scope and approval
Live BytePlus retries stopped in IAM and Runtime preparation with only provider_error. IAM replaces the original exception and suppresses its chain; Runtime credential/client setup can escape operation capture. The failure summary and definition list also inherit a larger font than the 13px reason paragraph. User explicitly approved supplementing diagnostics and matching the font on 2026-10-20. No additional approval is needed for these agreed changes.

## Requirements and scenarios
FR-1: Given a wrapped SDK/HTTP failure, retain bounded exception types, HTTP status and normalized response type before a wrapper discards context, alongside existing code/Request ID. Extract structured identifiers from bounded SDK JSON arguments and response headers where available. Unknown classes normalize to Exception; arbitrary messages, response bodies, headers, credentials, SQL and stack traces are never persisted or displayed.
FR-2: Distinguish credential loading, STS identity verification and Runtime client initialization from actual Runtime operations. Preserve original exceptions, IAM error keys/categories and existing retry/control flow, with no new cloud calls or retries. Repeated outer reports preserve the original details.
FR-3: Persist optional diagnostics in an additive SQLite column, validate on write and read, return through the existing task API and include in expanded/copied failure details. Old rows/events remain valid; per-attempt cursor, owner checks and history limit are unchanged.
FR-4: Summary, labels, values and copy feedback use 13px with 1.6 line height, matching the existing reason paragraph. Reuse the existing failure component/Button; no global/shared component overrides. Success, cancellation, ordinary agents and action buttons retain behavior. No suggestions section.

## Design and tasks
T1: Add failing regression tests for wrapped HTTP errors, unknown types/secrets, STS failures, persisted/reopened diagnostics and frontend copy/visibility. T2: Extend managed diagnostics, IAM wrapper and Runtime setup boundaries, task persistence/types and MPA failure rendering/locales. T3: Run targeted then managed Python regressions, Ruff/Pyright, frontend tests/build/i18n/assets and isolated browser typography/keyboard/copy/narrow checks. T4: Update both contract languages and verification record.
Use allowlisted exception-chain tokens (maximum eight), integer HTTP status 100–599 and normalized response-type enum. Do not re-enable raw stderr capture. Existing failure_identifiers/classify_error used by retries remain behaviorally unchanged; diagnostic enrichment is separate. New fields are optional and require no cloud schema or credential changes. Cancellation remains uncaught by Exception handlers.

## Review, risks and acceptance
Direct review (review-spec unavailable) checked security, compatibility, terminal propagation, cancellation, migrations and bilingual equivalence; no blockers. Frontend design skill files referenced by SPEC are unavailable locally; use the existing component and SPEC/Foundation typography rules without introducing a new design system.
AC-1: A fake SDK error wrapping HTTP/JSON failure reaches task/UI with safe cause data and no secret text. AC-2: STS failure keeps its original exception and is identified separately, without changing call counts. AC-3: Old SQLite rows and retries remain readable; no stale diagnostics. AC-4: Real browser confirms matching font, wrapping, expand/copy and absence on success. Historical lost exceptions cannot be recovered and provider errors may lack HTTP metadata. This change improves diagnosis, not underlying provider reliability.

## Verification
See final verification below; no live resource changes authorized or required. Preserve unrelated local changes. No commit/push requested.

## Final verification and review (2026-10-20)
Scope: working-tree diagnostic-completeness change on feat/from-upstream-main-20261020; unrelated changes preserved.
- pass: initial failing regressions reproduced missing cause fields and STS origin. Final targeted `uv run --no-sync --extra dev pytest tests/integrations/mpa_managed/test_creation_failure_details.py tests/integrations/mpa_managed/test_iam_retry.py tests/integrations/mpa_managed/test_runtime_diagnostics.py -q`: 73 passed.
- pass: `uv run --no-sync --extra dev pytest -n 2 tests/integrations/mpa_managed -q`: 1,176 passed, two upstream OpenTelemetry deprecation warnings. Existing exact diagnostic expectations updated for additive fields; retry call counts/delays remain asserted.
- pass: `npm --prefix frontend test`: 1,389 Node tests plus 146 Vitest tests. After adding the final negative display case, `cd frontend && npx vitest run tests/mpaCreationFailure.test.tsx`: 18 passed.
- pass: changed-file Ruff 0.11.12 and Pyright using `.venv/bin/python`; zero errors/warnings. `npm --prefix frontend run build`, `check:i18n`, `test:webui-assets`; packaged WebUI regenerated. Build retains existing large-chunk warnings.
- pass: isolated real-browser check of actual component/localization/CSS: all reason/summary/definition labels and values measure 13px / 20.8px line-height; 320px container has no horizontal overflow; keyboard expand, copy, successful/running/cancelled invisibility and return to failure verified. Screenshot `/tmp/mpa-diagnostic-font-preview.png` contains synthetic data. Temporary fixture/server/tab removed. Input IME not_applicable.
- pass: paired-language identifiers/links and `git diff --check`.
- fail (reviewed false positive): temporary Gitleaks v8.24.2 scan of changed source/tests/design and generated WebUI found one generic-api-key candidate in minified MarkdownPromptEditor. Read-only comparison confirmed the identical unquoted JavaScript expression already exists in HEAD; it contains no string literal or credential. No scanner rule was bypassed and unrelated generated code was not rewritten to silence it.
- not_run: real cloud create/retry (requires user restarting Studio and retrying the original task); repository-wide unrelated Python suites and all-files pre-commit (no commit requested). No resource or retry-policy changes were made.
Direct review confirms safe evidence survives IAM replacement and terminal propagation, SQLite migration preserves old rows, setup labels do not alter exceptions/call counts, and no raw exception text/body/headers or secrets reach the UI. All scoped implementation tasks complete; historical root causes remain unavailable.
