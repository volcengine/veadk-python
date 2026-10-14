# IAM transient failure recovery and diagnostics

[中文版](2026-10-14-transient-errors.zh.md)

Change ID: mpa-iam-retry. Date: 2026-10-14. Status: implemented; live mutation not performed.
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-10 and CON-11.

## Evidence, goals and scope

IAM SDK errors are converted into IamError, preserving recognized codes only. Transport timeout/connection errors lose their category and immediately fail role preparation. A real overseas task failed with iamVerificationFailed while later read-only verification of the same role and credentials passed; its original error was not recorded, so the historical cause is unconfirmed. The user explicitly approved retaining safe operation/category/Request ID, bounded transient retry and distinct UI messages. The subsequent Worker CreateTool failure is a separate read-only investigation, not a reason to expand this fix.

## Requirements and scenarios

- FR-1: Preserve allowlisted IAM operation/category/code and a validated Request ID from structured SDK responses/errors. Never persist exception text, credentials, role/policy documents or arbitrary response data.
- FR-2: Reconcile timeout, connection, throttling and unavailable failures with at most four transient attempts and 1/2/4-second waits, inside the existing 120-second role deadline and task deadline. Permission, configuration/conflict, validation and unknown errors fail immediately. Permission is not retried.
- FR-3: Each retry restarts read-before-write reconciliation using the same fixed role/policy names. A lost create/attach response requires readback on the next cycle, preserving existing additive and collision handling. No parallel operation retries, rollback or permission expansion. Cancellation remains terminal; a SDK request already dispatched may finish, but no later reconciliation call is dispatched after cancellation.
- FR-4: Emit iamTemporaryFailure for exhausted transient requests/deadline; existing permanent error keys remain. Store operation/category/attempt/outcome and optional Request ID in bounded task diagnostics (100/task). Migrate the existing SQLite table additively; legacy four-field diagnostics remain valid.
- FR-5: Localized UI distinguishes temporary IAM/network failures from deployment permission failures. General agents, role permission sets, provider endpoints, OV and Worker behavior remain unchanged.

## Design and tasks

T-1: Add structured metadata to IamError; IamCloud extracts only safe fields using existing error classification. Capture HTTP status category when available and never parse unstructured text into user-visible messages.
T-2: Add the bounded recovery counter to ensure_runtime_role. Preserve get-or-create and Global policy readback; report safe diagnostics before retry/failure.
T-3: Extend diagnostics validator/report with optional requestId, allowlist IAM operations; tasks.py adds a request_id column with empty default, persists it and logs only validated metadata. No HTTP task schema change except the additional error enum key.
T-4: Add regression tests before code for transient recovery/exhaustion, permanent failure, unknown errors, cancellation/late response, lost create response, Request ID redaction and SQLite migration; update locale copy/docs/assets, run affected Python, Ruff/Pyright, frontend/build/browser and secret checks.

## Review, risks and acceptance

User approval: explicit '改下' accepting the three changes on 2026-10-14. Direct design review (review-spec unavailable): safe fields, finite retry/deadline, idempotent resource readback, cancellation and legacy diagnostic compatibility reviewed; bilingual pair matches. No blocker.

- AC-1: Timeout/connection/429/5xx recover; four failures terminate with iamTemporaryFailure and recorded operation/category. Missing IAM permission remains iamPermissionDenied without retry.
- AC-2: Read-before-write prevents extra role/policy creation after a lost response; existing trust/policy documents and unrelated bindings are preserved; cancellation prevents subsequent SDK calls.
- AC-3: Structured Request ID survives persisted diagnostics, malicious/non-ID strings are omitted, old records migrate without losing data; raw secrets never appear in errors/log records.
- AC-4: UI strings, tests/build/assets and bilingual contracts match; record actual checks below.

The original real failure cannot be proven retroactively. Real IAM writes and paid cloud creation are not authorized for this implementation; all tests use isolated fakes. Full verification pending. Commit/push are outside scope. Existing user changes stay intact.


## Verification (2026-10-14)

Scope: uncommitted IAM changes on base `2ffe6e14`, preserving other local work. The first new regression run reproduced 13 failures. After implementation, IAM/tasks/Worker recovery targeted checks passed (68). The complete affected suite `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py` passed 1,017 tests with four warnings. Subsequent HTTP-status extraction and thread-cancellation hardening passed all 18 IAM retry tests. Both requests with transport failures and structured 429/5xx/403 errors are covered.

pass: Ruff 0.11.12 check/format and Pyright on iam.py, diagnostics.py, tasks.py and the two changed IAM tests (0 errors/warnings). pass: frontend test (1,389 Node + 97 React), production build, i18n (2 locales/21 namespaces), assets (113 files/350 references), paired design identifiers/links and whitespace. Browser Chromium loaded the actual dialog with isolated mocked APIs, checked explicit IAM temporary failure, same-request retry, personal/default UI, existing manual recovery, domestic display, Escape and narrow viewport. Temporary fixture/server removed after verification; no real resource creation. User lockfile hash is unchanged.

not_run: full repository Python/all-files pre-commit because no commit requested and the affected MPA suite plus frontend gates cover this scope. not_applicable: Harness/Codex smoke and model/OV live integration because these contracts are unchanged. not_run: real IAM mutations, Worker CreateTool retry or cloud creation. The existing Worker failure remains provider_error with no original code/Request ID; read-only search confirms no same-name template, which does not identify the rejection reason.
