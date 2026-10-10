# Execution diagnostics

[中文](2026-10-10-execution-diagnostics.zh.md)

Change ID: execution-diagnostics; date: 2026-10-10; status: in-review.
Related contract: [execution tracing](../../../specs/execution-tracing/README.md).

## Evidence and scope
The existing Codex `call_llm` Span covers a whole execution. The Responses Shim performs non-streaming `litellm.aresponses` requests. At the design baseline, Worker HTTP requests were traced, while the SSE subscription was not. This design records the scope already authorized by the performance-diagnostics goal; it does not assert a new user approval or deployed capability.

## Requirements and design
FR-1: Preserve whole-turn compatibility while recording each model backend call separately under the originating Agent context. No duplicate whole-turn usage or synthetic TTFT.
FR-2: Record Worker requests and each SSE connection, propagate only W3C tracing context, and preserve authentication, idempotency, retry limits, event validation and cursors.
FR-3: Stream Spans must not remain current across an async-generator yield. End on completion, failure, cancellation or generator close. Record no endpoint, routing IDs, bodies or raw errors.
FR-4: Missing optional telemetry must preserve execution. Reuse the existing Provider/exporter.

## Tasks and acceptance
T-1 / AC-1: Model Span tests prove parentage, retries, failures and cancellation; existing Codex indexing remains compatible.
T-2 / AC-2: Worker HTTP tests prove W3C propagation, redaction and unchanged keys.
T-3 / AC-3: SSE tests prove per-connection parentage, cursor continuity, cancellation/close and no current-context leak.
T-4 / AC-4: Synchronize bilingual contracts and user documentation, run affected tests and pre-commit, and record actual results.

## Review and risks
Direct review: no public signature, protocol, authentication, persistence, concurrency ownership or deployment configuration changes. Existing retry semantics remain authoritative. Async-generator context leakage is a blocking risk addressed by detached stream Spans. Client subscription time is not remote queue/start/execution time. Real Worker receiver propagation, APMPlus reception and deployed versions remain unverified. SSE implementation and affected-test acceptance are complete in draft PR #1161; HTTP/model evidence is also recorded there. This record reconciles existing work and precedes the SSE extension.

Verification (2026-10-10): 10 Worker tracing tests pass; 17 existing remote Sandbox tests pass (the initial combined run before adding new tests had 22 passes). SSE completion, reconnect/cursor, early close, cancellation and HTTP failure are covered. Full repository regression, live Codex smoke and APMPlus reception are not_run: isolated full-smoke dependencies and deployed receiver evidence are unavailable. Process deviation: SSE tests were added after the first implementation edit instead of first run failing; direct behavior assertions are now present. No deployed capability is claimed.

Final checks: 27 affected tests pass after formatting; all-files pre-commit (Ruff and both secret scans) pass. Requirement scope is authorized by the existing performance-diagnostics goal. Direct design review found no remaining blocker for this extension; server-side verification remains separate.
