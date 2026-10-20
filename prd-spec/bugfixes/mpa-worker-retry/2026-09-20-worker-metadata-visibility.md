# Worker initialization metadata visibility

[中文版](2026-09-20-worker-metadata-visibility.zh.md)

- ID: mpa-worker-metadata-visibility; date: 2026-09-20; status: implemented.
- Predecessor: [Worker API recovery](2026-09-20-worker-retry.md).
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).

## Background and evidence

A monitored creation failed with safe category `ownership` in the same second its Worker was created. Eleven seconds later the Worker was Ready; read-only checks confirmed matching ID, project, ownership tags and agent environment. Manual retry reused that Worker and passed. The exact initial missing/conflicting field was not captured, so delayed metadata is a strongly supported hypothesis, not a complete historical response reconstruction. Code currently treats absent tags/ID or an empty project as a permanent conflict before considering initialization status. SDK GetTool fields are optional.

## Scope and requirements

- FR-1: Separate missing ownership metadata from present conflicting values. During recognized initialization states (Creating, Pending, Starting, Initializing, Provisioning, or omitted/empty status), a managed Worker with persisted worker_id, worker_token and worker_hash may wait for missing ToolId, ProjectName, managed_by or mpa_agent_key. At most 4 incomplete observations, waiting 5/10/20 seconds; budget is not reset by intervening complete observations. Existing 600-second stage/task deadlines and cancellation remain authoritative.
- FR-2: Present conflicting ID/project/tag/MPA_AGENT_ID fails immediately, even if other fields are missing. Failed/Error/Deleted/Deleting and unknown nonempty statuses do not receive metadata grace. Ready with missing required metadata fails. Unmanaged/existing workers or incomplete creation intent receive no grace. Retain existing compatibility for omitted default project on unmanaged workers and absent optional agent environment; never accept a managed Worker without ID/project/tags verified.
- FR-3: Safe diagnostics distinguish fixed fields `worker_id`, `worker_project`, `worker_managed_by`, `worker_agent_key`, `worker_agent_binding`, `worker_state`; categories `metadata_pending`, `metadata_missing`, `ownership`, `resource_failed`, with existing bounded attempt/outcome fields. Do not log actual values. Report all missing fields on each bounded observation, but check all conflicts first. Successful readiness is required after metadata becomes complete.
- FR-4: Query retry/idempotency and resource bindings remain unchanged. No new Worker is created during metadata waiting. No UI/API/schema change or live cloud test creation.

## Design and affected files

Add one local validation helper in `worker.py` that reports fixed field operations, returns missing fields, and preserves fail-fast conflicts. The readiness loop owns the bounded missing-metadata counter and sleeps; terminal validation precedes waiting. Extend diagnostics allowlists and fixed internal exception category mappings. Keep raw SDK values private. Update paired component/operator documents. Tests in `test_worker_metadata.py` cover metadata transitions, every conflicting field, ready/terminal/unknown states, persisted-intent boundaries, exhaustion, cancellation/deadline, stable create count and redaction. Existing worker/task/CLI tests remain gates.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1/2 | T-1: regression tests and worker state handling | AC-1: partial initial response reaches Ready without manual retry; conflicts and unsupported cases fail immediately; exhaustion/cancel/deadline bounded |
| FR-3 | T-2: safe field diagnostics and tests | AC-2: pending/missing/conflict field identifiable without values, no secrets in logs/storage |
| FR-4 | T-3: full affected suite and paired docs | AC-3: original idempotency/owner/task contracts pass, no cloud mutations or running-task interruption |

## Review, risks and approval

User approval: “帮我修复这个问题把” approves the preceding proposal to wait only for incomplete initialization metadata while rejecting explicit conflicts. Direct review (review-spec unavailable) checks safety, bounded waits, cancellation, schema compatibility, tests and bilingual equivalence; no blocker. Slow metadata beyond the 35-second accumulated grace still fails safely and can be retried. A conflicting initial value will now be identified but not silently accepted. No global deployment replay or UI changes. Restart local Studio only after all active creations finish.

## Verification

2026-09-20 working diff: not_run (implementation pending). Frontend/browser/build: not_applicable (no UI/HTTP change). Real cloud creation: not_run (no authorization to create test resources); existing user's task is monitored read-only. Commit/pre-commit: not_applicable (no commit requested).


## Delivery review and verification (2026-09-21)

Scope: current worker/diagnostics implementation and worker metadata/recovery tests, plus paired docs. T-1/T-2/T-3 and AC-1/AC-2/AC-3 are complete. Direct implementation review confirms that explicit conflicts are checked before any grace, no missing required managed identity can succeed, the counter never resets, cancellation and stage deadlines bound all waits, and no new create call occurs during metadata waiting. Fixed diagnostics pass the existing parent allowlist validation and retain no provider field values. No schema or HTTP/UI change.

- pass: test-first regression produced 21 failures and 4 passes before implementation, including incomplete initial metadata and field-level diagnostic coverage.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` — 272 passed, one upstream Starlette deprecation warning. Includes 28 metadata cases plus existing recovery, ownership, durable task and CLI coverage; no external cloud writes.
- pass: `uv run --extra dev --with ruff==0.11.12 ruff check` and `uv run --extra dev --with pyright pyright` on worker.py, diagnostics.py, test_worker_metadata.py and test_worker_recovery.py; Ruff format applied. Pyright initially found an overly narrow inferred test dictionary type; corrected to `dict[str, object]`, rerun returned zero errors.
- pass: repository-rule Gitleaks scan of 10 affected code/test/doc files, relative PRD links, paired-language/identifier review and `git diff --check`.
- pass: read-only monitoring confirmed the user's existing retry reached succeeded; no active creation remained before planned local service reload.
- not_run: live reproduction of fresh cloud creation (not authorized), full-repository regression (complete affected component/CLI suite passed), pre-commit (no commit requested). UI/build/browser: not_applicable, no UI/HTTP contract change.
- Remaining limitation: the original first-response field was not retained. The new missing-metadata regression is fixed and field diagnostics now distinguish a future explicit conflict. This is not a claim of live first-create validation.

- pass: local Studio reload completed after confirming zero active creations; configuration endpoint returned HTTP 200 with configured=true. No cloud creation was triggered.
