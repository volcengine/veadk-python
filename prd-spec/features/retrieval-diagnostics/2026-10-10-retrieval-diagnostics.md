# Retrieval diagnostics

[中文](2026-10-10-retrieval-diagnostics.zh.md)

Change ID: retrieval-diagnostics; revision: 2026-10-10; status: approved.

## Background and scope

`veadk/knowledgebase/knowledgebase.py:Knowledgebase.search` calls backend search and normalizes results. `veadk/memory/long_term_memory.py:LongTermMemory.search_memory` catches backend errors and returns empty memories; OpenViking calls run through `asyncio.to_thread`. `add_session_to_memory` filters events and saves them. These boundaries currently have no independent retrieval/write Span. The existing tool Span cannot distinguish retrieval from surrounding work.

The user authorized the overall performance-diagnostics implementation, local verification and draft PR delivery. This change implements those already agreed retrieval boundaries. It does not authorize production deployment.

## Goals and non-goals

Measure actual knowledge search, memory search and memory save boundaries, inheriting the existing OTel context and Provider. Preserve signatures, results, error propagation and cancellation. Do not introduce exporters, sampling configuration, storage, dashboards or backend-internal embedding/reranking stages. Existing observability owns receiving, export, storage and queries; diagnostics owns the operation boundaries and evidence used to identify slow operations.

## Requirements and scenarios

- FR-1: Knowledge search creates `veadk.knowledge.search`, ending after result normalization; records backend type, effective top_k and result count. Backend failure retains its exception and records ERROR.
- FR-2: Memory search creates `veadk.memory.search`; backend failure remains an empty response under the existing API, but Span status is ERROR with safe error type. Empty successful results remain successful.
- FR-3: Memory save creates `veadk.memory.save`, covering filtering and backend save; records backend type, session ID and filtered event count. Errors still propagate.
- FR-4: All operations inherit parent context, finish on success/error/cancellation, and restore the caller context. No raw exception events, query, memory content, credentials, user ID, index, URL or arbitrary kwargs are exported. A telemetry failure must not block or repeat business execution.

Given a tool calling knowledge search through `asyncio.to_thread`, the retrieval Span is a child of the existing tool Span. Given two concurrent memory requests, each remains under its own parent. Given a cancelled OpenViking await, the caller Span ends with cancellation; the underlying synchronous thread may continue, so the Span must not claim backend completion.

## Design and contract impact

Use a small internal helper under `veadk/tracing/` for fail-open fixed-name spans with explicit safe outcome handling and no exporter setup. Reuse `trace.get_tracer`; do not change global Provider. The helper activates a span for the operation and restores context in finally, disables automatic exception recording, and records only error class/status. Avoid catching business exceptions in the helper as success. Backend attributes come from configured backend type, never full configuration. Apply result counts only after successful normalization. Memory search marks its handled backend exception before returning the established empty response. `asyncio.to_thread` already copies context; add no extra worker propagation protocol.

Public signatures, result types, backend arguments, auth, retry behavior and memory isolation remain unchanged. There is no new persistent state or deployment configuration. Extend the bilingual execution-tracing spec with the three boundaries and their failure semantics.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification | Status |
| --- | --- | --- | --- | --- |
| FR-1 | T-1 knowledge boundary | AC-1 parent/name/effective top_k/count and unchanged errors | Targeted knowledge tests with local SpanExporter | pass (local) |
| FR-2 | T-2 memory search | AC-2 handled failure distinguished from successful empty response | Memory tests: success, empty, failure, concurrent parents, OpenViking cancellation | pass (local) |
| FR-3 | T-3 memory save | AC-3 event count/session, propagation and unchanged save arguments | Memory save tests: filtering, backend failure and cancellation | pass (local) |
| FR-4 | T-4 protections | AC-4 no sensitive content; telemetry failures do not alter business calls/context | Helper tests with failing tracer/span plus integration parent tests | pass (local) |
| FR-1–FR-4 | T-5 delivery | AC-5 bilingual docs and affected regression gates, actual PR recorded | Repository-local targeted pytest; all-files pre-commit; synchronize base before commit | pending |

Test entry points: `tests/test_knowledgebase.py`, `tests/test_long_term_memory.py`, `tests/test_openviking_long_term_memory.py`, `tests/tools/builtin_tools/test_load_knowledgebase.py`; add colocated tracing-helper tests where existing tests organize tracing. Execute through repository `.venv` using `uv run --extra dev pytest`. No real services or credentials in fixtures. Use a controlled blocking backend for thread-cancellation semantics and clean it up before test teardown.

## Risks and review

Backend internals and deployed APMPlus reception remain unverified. A cancelled thread-backed call may still run remotely; measure caller boundary only and mark cancelled, never backend success. Global telemetry setup can be absent: no-op tracing must leave execution unchanged. Do not add duplicate tokens/cost or infer unknown internal stages.

Design review: pass (2026-10-10). Verified actual public boundaries, context propagation through to_thread, existing handled-error semantics, bounded attributes and matched bilingual requirements. No blockers; thread completion remains explicitly outside caller-cancellation evidence. Production code/tests begin with TDD after this review. Approval scope comes from the user's existing active goal; no new deployment permission is inferred.

## Local implementation evidence (2026-10-10)

| Check | Result and scope |
| --- | --- |
| TDD | Helper test initially failed because the module did not exist. Initial boundary failures were fixture setup errors, not valid missing-Span evidence; corrected isolated backend fixtures before asserting the public methods. |
| Retrieval/Worker subset | 76 passed, 1 optional-dependency skip; helper 100% lines and 98% combined branch coverage. Includes concurrent parents, thread cancellation with explicit drain, telemetry mutation/end failures, attribute whitelist and actual tool-to-retrieval context. |
| Initial broad regression | fail: 6607 passed, 16 failed, 59 skipped, 4 xfailed, 2 collection errors (422.59s). All failures/errors reported missing llama_index, openai_codex or anthropic. No tests removed or reclassified. |
| Environment recovery | Installed declared dev/extensions/codex/sandbox extras. Codex binary download first timed out at 30s; retry with command-scoped UV_HTTP_TIMEOUT=180 exited 0. No global configuration changed. |
| Affected regression after recovery | pass: 199 passed, no skips/errors, seven existing dependency deprecation warnings (46.95s). Covers the failed Harness/Codex suites, both Sandbox suites, retrieval/memory/tool context and Worker requests. |
| Final source/security review | pass: backend arguments, filtering, successful empty responses, errors and cancellation preserved. No new exporter/configuration or sensitive content. |
| Base and hooks | Fresh origin/main remains 171d8d86, already rebased and an ancestor of HEAD. All-files pre-commit passed Ruff and both secret scanners with complete extras. |
| Full regression | pass: 6698 passed, 50 skipped, 4 xfailed, 88 dependency warnings, 427.41s. Skips do not prove behavior. First interrupted run had no result; restarted only after confirming absence. Local metrics export reported localhost:8000 unavailable, so remote observability reception is not proved. |
| Delivery/deployment | pending: PR draft body prepared; retrieval update not committed/pushed. Deployed APMPlus reception and real performance remain unverified. |

Evidence: `/tmp/codex-retrieval-save-tests.log`, `/tmp/codex-veadk-retrieval-broad.log`, `/tmp/codex-veadk-complete-env-retry.log`, `/tmp/codex-veadk-complete-env-retest.log`, `/tmp/codex-retrieval-extras-final-hooks.log`, `/tmp/codex-veadk-complete-broad-resumed.log`.
