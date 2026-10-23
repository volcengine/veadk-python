# MPA creation failure details

## Evidence and approval
The user approved failure-only diagnostics for all Volcengine and BytePlus MPA creation resources, explicitly excluding suggestions and changes to success, provisioning, retry or general-agent behavior. RuntimeCloud currently reports only Runtime writes, network/APIG wrappers discard identifiers, runner emits a generic final diagnostic, and the dialog only consumes configuration_changed. Approval: user request on 2026-10-20.

## Requirements
R1: Failed tasks show the failing operation, a localized safe reason, provider error code and Request ID when supplied. No suggestions. All stages (account/configuration, IAM, PG/database, VPC/subnet, APIG/IM, worker, OV, skills, Runtime/readiness) have a safe fallback.
R2: Extend diagnostic capture at existing call boundaries without adding calls, retries, sleeps or changing exceptions, ordering, cloud payloads, ownership checks or recovery decisions. Preserve the originating diagnostic when exceptions are wrapped.
R3: Hide previous-attempt diagnostics from the current result only when the existing start/resume transition accepts a new attempt. Never display diagnostics on success or cancellation; ignore mismatched stages and retrying events in failed-task UI.
R4: Never expose arbitrary exception text, SDK bodies, URLs, SQL, model/PG secrets or request payloads. Show allowlisted localized explanations from structured identifiers; unknown failures explicitly state that no detailed safe reason is available. Code/Request ID retain existing bounded validation. Full raw response dumps are not part of this change.
R5: Expand/copy error details with accessible text, handle clipboard failure, preserve success DOM and all existing action/retry behavior. General agents never use this component.

## Design and affected files
Use a terminal diagnostic annotation on exceptions for lossless safe propagation; existing report calls and retry categories remain unchanged. Capture new operations in managed/runtime.py, network_cloud.py and gateway_cloud.py; preserve already-captured PG/IAM/OV/worker/model/APM metadata. SQL failures get safe classification only, never SQL text. runner emits the originating diagnostic or a safe generic fallback. tasks.py advances an attempt cursor in its existing accepted-start transaction; old diagnostic history remains retained under the existing 100-row limit. The MPA dialog renders a separate failure component with bilingual translations, without modifying shared deployment UI. Extend diagnostics/task/resource tests and MPA frontend tests; regenerate WebUI.

## Contract assessment and design review
Update [Studio MPA creation](../../../specs/studio-mpa-creation/README.md) with failure display/propagation and per-attempt diagnostics. Existing HTTP fields remain optional and compatible. Additive SQLite tasks.diagnostic_start_id (default 0) migration preserves old records; no cloud provisioning contract change. Direct review refined R3 from deleting diagnostic rows to an attempt cursor to preserve the existing history contract. Direct design review (review-spec unavailable): security, stale attempts, fallback, exception preservation, cancellations, bilingual equivalence and testability reviewed; no blockers. Crucially, display quota classification does not change retry classification.

## Non-goals and risks
No new cloud troubleshooting requests, automatic cleanup or altered retry policy. Historical generic errors cannot be reconstructed. Unknown provider text is withheld rather than attempting unreliable free-text redaction. Preserve all unrelated local changes.

## Tasks and acceptance
1. Write failing tests for resource diagnostics, safe propagation, stale-attempt isolation, successful-task invisibility and both providers.
2. Implement capture and failure-only rendering.
3. Targeted Python tests, managed regression suite, changed-file Ruff/Pyright; frontend tests/build/i18n/assets; isolated browser error/success/copy/narrow checks.
4. Reconcile bilingual docs and record actual results. Accept when quota/permission/timeout are visible with available identifiers and all existing flow tests pass.

## Verification and final review
Scope: this working-tree failure-details diff on `feat/from-upstream-main-20261020`, 2026-10-20; unrelated collaboration-agent changes preserved.

- pass: initial red resource/propagation and frontend tests, then implementation and regressions. Final focused Python run: `uv run --no-sync --extra dev pytest tests/integrations/mpa_managed/test_creation_failure_details.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_runtime_diagnostics.py -q` (74 passed).
- pass: sequential managed suite before final hardening (1,161 passed). Final `uv run --no-sync --extra dev pytest -n 2 tests/integrations/mpa_managed -q`: 1,168 passed, two upstream OpenTelemetry deprecation warnings. Two workers limit resource use.
- pass: `npm --prefix frontend test` (1,389 Node tests and 145 Vitest tests), including general/MPA separation and existing creation/retry tests.
- pass: changed Python files checked with `uvx --from ruff==0.11.12 ruff check ...` and `uvx pyright --pythonpath .venv/bin/python ...` (zero errors/warnings). Temporary tools use the repository Python environment; no global configuration changes. Initial tool-version/interpreter-path issues were corrected and checks rerun.
- pass: real browser against an isolated fixture using the actual failure component and localization/theme: quota details, copy, keyboard expand/collapse, 360px container wrapping, missing details, success/running/cancelled suppression. Clipboard failure and retry recovery also covered by tests. Screenshot: `/tmp/mpa-creation-failure-preview.png` (synthetic data). Temporary fixtures/server removed. IME not_applicable: no input controls changed.
- not_run: live cloud create/retry/deploy; no cloud mutation required or authorized. Provider tests use fakes for both Volcengine and BytePlus. Repository-wide unrelated suites and pre-commit not_run: no commit requested, targeted managed regression plus frontend gates cover changed boundaries.

Direct final review: no added cloud calls/retry loops or payload/order changes; existing exceptions and retry classifiers remain unchanged. New metadata only affects diagnostics. Existing known IAM/OV error keys retain specific explanations. Secrets remain excluded from UI/task records. Previous-attempt diagnostics remain in bounded history and are hidden only after an accepted restart. Public success output and ordinary-agent code are untouched. PRD/spec languages and references checked together.


- pass: `npm --prefix frontend run build`, `npm --prefix frontend run check:i18n` (2 locales / 22 namespaces), `npm --prefix frontend run test:webui-assets` (114 files / 351 references); packaged WebUI regenerated.
- pass: bilingual pair/identifier/relative-link checks and `git diff --check`. No commit, push or deployment performed.
