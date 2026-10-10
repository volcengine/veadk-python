# Execution tracing

[中文](README.zh.md)

Component: execution-tracing; status: draft; revision: 2026-10-10.
Owns `veadk/runtime/codex/model_tracing.py` and `_remote_sandbox/request_tracing.py`; integrates the Responses Shim and Worker client. Design: [execution diagnostics](../../prd-spec/features/execution-diagnostics/2026-10-10-execution-diagnostics.md).

CON-1: `codex.model.request` covers one backend `aresponses` call including internal retries; `call_llm` remains whole-turn. No model TTFT or duplicate usage is inferred.
CON-2: Worker request Spans preserve existing retries, auth, keys and errors, and propagate W3C context without telemetry baggage.
CON-3: each SSE connection has a detached CLIENT Span, with no ambient context held across yield. Event cursor, binding checks, retry bounds and execution ownership remain unchanged.
CON-4: Fixed operation names and error types only; no credentials, URL, body or raw exception. Existing Provider owns sampling and export; no persistence or new configuration.

Tests: `tests/agents/test_worker_request_tracing.py`, model tracing tests and existing remote Sandbox regression. CON-3 completion, reconnect/cursor, early close, cancellation and HTTP failure tests pass in the draft PR. Real receiving/export/deployment evidence is required separately; this draft makes no server-side instrumentation guarantee.

## Retrieval boundaries

CON-5 (implemented locally; not deployed): `veadk.knowledge.search`, `veadk.memory.search` and `veadk.memory.save` inherit the existing context and Provider. Record backend type, effective top_k/result count or session/event count only; never query/content/user ID/index/URL. Handled memory-search backend failures must remain empty responses but mark Span ERROR; normal empty results are successful. Cancellation ends the caller boundary without claiming the synchronous thread/backend stopped. No exporter or persistent state is added. Design and pending acceptance: [retrieval diagnostics](../../prd-spec/features/retrieval-diagnostics/2026-10-10-retrieval-diagnostics.md).
