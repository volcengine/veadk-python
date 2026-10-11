# MPA worker recovery and safe diagnostics

[中文版](2026-09-20-worker-retry.zh.md)

- ID: mpa-worker-retry; created/revised: 2026-09-20; status: implemented.
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md).

## Evidence, goals and boundaries

`runner.py` discards exceptions; `tasks.py` discards stderr and resets the latest failure on manual retry. `worker.py` propagates transient API failures immediately. The user observed a first failure at worker preparation followed by progress on manual retry. Its historical root cause is unknown because the exception was discarded. This fix addresses those verified recovery/observability gaps, not a claimed reconstruction of that failure.

Automatically recover bounded transient worker failures and retain safe per-task diagnostics across manual retries. Do not replay the entire deployment, change images/configuration or ownership rules, introduce cloud resources for testing, expose raw errors, or redesign the dialog. Other cloud stages gain final diagnostics but no automatic retries.

## Requirements and scenarios

- FR-1: Worker reference lookup, discovery, idempotent create and readiness reads attempt at most 4 times, sleeping 1, 2, 4 seconds between recoverable failures. Retry timeout/connection, known throttling/service codes and HTTP 408/429/500/502/503/504. Unknown, authentication, validation, ownership and terminal resource failures stop immediately. Never classify by substring matching arbitrary error text.
- FR-2: Retry recognized not-found only while reading a worker with a persisted managed creation intent and ID. Missing reference/existing workers fail. The stage has a 600-second default deadline including discovery/retries; the overall task deadline and cancellation still win. Retries use the same persisted ClientToken and payload; failed discovery never means absence.
- FR-3: Store allowlisted diagnostic events (stage, operation, category, attempt, retrying/failed, timestamp, task ID) in the private task SQLite database; retain the newest 100 per task across manual retries. Do not persist exception messages, tracebacks, URLs, headers, payloads, credentials, arbitrary provider codes or environment values. Log the same safe fields server-side. API response shape/error codes remain compatible.
- FR-4: Runner reports classified final failures from all stages. Parent records abnormal child exits, timeouts and cancellation even when no child diagnostic arrives. Validate child diagnostic fields before logging/storage. Diagnostics must not turn a failure into success or hide cleanup.

## Design and impact

Add a small diagnostic classifier and Worker retry helper. Interpret the installed AgentKit typed errors/error_code and chained requests transport errors, including HTTP status; map only fixed known codes to fixed categories. Transient create retries retain the original idempotency token. Owned readiness 404 tolerance is bounded and does not relax ownership validation. Append a task diagnostic table without modifying old task rows or HTTP contracts; bounded retention is transactional. Runner uses a scoped diagnostic callback; supervisor revalidates events. CLI can log safe events without Studio persistence. UI and generated assets require no changes.

## Tasks, tests and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1/2 | T-1: tests, diagnostics module and worker integration | AC-1: transient recovery, exhausted retries, stable token/payload, reference 404/permission fail fast, ownership checks, cancellation/deadline | Targeted worker and diagnostic tests |
| FR-3/4 | T-2: runner/task integration and migration tests | AC-2: safe history survives retry/reopen, cap 100, reject malformed/injected events, preserve terminal states | Real child-process task tests and runner tests |
| All | T-3: paired contract/operator docs and review | AC-3: docs match implementation, checks recorded | Python regression, Ruff, Pyright, whitespace/secret checks |

Affected paths: `veadk/integrations/mpa/managed/{diagnostics,worker,runner,tasks}.py`, corresponding tests, paired component/operator docs. No frontend code or new dependencies.

## Risks and review

Unknown provider codes intentionally fail closed; a transient error outside the allowlist may still require manual retry. Cloud requests may complete after cancellation; persisted intent remains the recovery authority. SDK-internal retries may add underlying network attempts beyond the four orchestration calls. Diagnostic categories trade raw detail for credential safety. Readiness polling keeps its existing cadence.

Direct design review (review-spec unavailable): consistency, bounded retry, mutation idempotency, cancellation, input validation, confidentiality, migration and bilingual equivalence checked; no blockers. User approval: “帮我补” explicitly approves the preceding proposal for safe error records and transient automatic retries. No commit/push/deployment authorized by this design. Live historical failure reproduction is not possible without retained evidence; isolated simulation is required.

## Verification record

2026-09-20 working diff: not_run (implementation pending). Frontend/browser: not_applicable (no UI/HTTP contract change). Live cloud writes: not_run (no new cloud creation requested). Commit/pre-commit: not_applicable (no commit requested).


### Implemented verification (2026-09-20, current working diff)

- pass: initial regression run failed in 19 new cases before implementation (missing recovery/diagnostics); no live cloud calls.
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` — 244 passed; one upstream Starlette deprecation warning.
- pass: final affected tests after timeout annotation correction: `uv run --extra dev pytest tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_tasks.py -q` — 39 passed.
- pass: `uv run --extra dev --with ruff==0.11.12 ruff check` and `uv run --extra dev --with pyright pyright` for diagnostics/worker/runner/tasks plus test_worker_recovery/test_worker; no errors. Ruff format applied. Initial bare `uv run ruff` was unavailable; temporary tool dependencies resolved it without project/global changes. Pyright found an inferred int-only timeout in a fractional-deadline test; corrected the timeout annotation to float and reran checks.
- pass: repository-rule Gitleaks scan of 25 implementation/test/doc files, paired PRD links/requirement IDs, manual bilingual semantic review, `git diff --check`.
- pass: review confirms fixed safe enums, bounded operation retries, same persisted create token/payload, ownership fail-fast, unchanged API, task history cap and real subprocess cleanup coverage. T-1/T-2/T-3 and AC-1/AC-2/AC-3 complete.
- not_run: repository-wide Python regression (change isolated to managed MPA; full affected component and CLI suite passed). UI build/browser and generated assets: not_applicable, no UI/HTTP shape change. Live cloud creation: not_run; simulated recovery does not establish the discarded historical cause. Commit/pre-commit: not_applicable, no commit requested.

- pass: local Studio reloaded only after active creation count reached zero; configuration GET returned HTTP 200/configured=true. First task access initialized `task_diagnostics` while retaining existing tasks. The local unauthenticated task lookup returned 404; no authenticated UI/cloud creation smoke is claimed. The user's preceding task was already succeeded before restart.
