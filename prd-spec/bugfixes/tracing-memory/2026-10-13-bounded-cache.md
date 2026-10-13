# Bound the local tracing cache

[中文版](2026-10-13-bounded-cache.zh.md)

## Metadata

- Change ID: `tracing-memory`
- Created/revised: 2026-10-13
- Status: implemented
- Component: [tracing cache](../../../specs/tracing-cache/README.md)

## Background, goals, and scope

Published versions 1.0.9 and 1.1.14 append every sampled span to a process-lifetime list. Each tracer also registers another collector with the global provider. The session index grows independently, and `clear()` does not clear it. Large responses attached to repeatedly polled requests amplify retention. Source inspection confirms the defect; the proportion of any production process's RSS attributable to it is not yet measured.

The fix bounds local retention without disabling cloud exporters or changing span annotation, sampling, or instrumentation suppression. It preserves recent session dumps and the latest trace ID. It does not change AgentKit SDK request payloads, frontend behavior, production configuration, package versions, or deployment.

## Scenarios and requirements

- FR-1: Given sustained exports, retain at most 1,024 spans and 16,777,216 estimated bytes by default; evict oldest spans until both limits hold. Reject a single oversized span from the local cache without discarding earlier valid entries or altering cloud export.
- FR-2: Given local caching disabled, retain no spans or session index, but keep the annotation processor, latest trace ID, and cloud pipeline operational.
- FR-3: Given eviction, clear, or shutdown, do not retain stale session mappings. Retrieval returns a consistent snapshot of retained spans; concurrent export/clear/read must be safe.
- FR-4: Given several tracers using one provider, register exactly one shared local collector at the front of its processor pipeline. Each provider has its own cache, with configuration captured when its first collector is created.
- FR-5: Publish validated configuration and document that local dumps contain only retained history; cloud retention is owned by the cloud exporter/service.

## Design and contract impact

Use a lock-protected FIFO deque with parallel per-span size accounting. Estimate the known span fields, attribute values, resource, events, links, and instrumentation metadata using Python object sizes without serializing or copying large payloads. This estimate is a cache budget, not an exact process RSS limit; count bounds metadata overhead as well. Skip oversized entries locally. Derive the session-to-trace index from retained `call_llm` spans on read, avoiding an independently growing index. A trace whose session-bearing span was evicted may no longer appear in a local session dump.

Expose `inmemory_enabled`, `inmemory_max_spans`, and `inmemory_max_bytes` in `OpenTelemetryConfig`, with corresponding `OBSERVABILITY_OPENTELEMETRY_INMEMORY_*` variables. Defaults are true, 1024, and 16777216; nonnegative limits are required and either zero disables storage. Configuration follows existing startup settings/config.yaml handling; changes require a new provider/process.

The provider owns a shared exporter, initialized under a registration lock. Keep the existing annotation processor even when retention is disabled. Export, read, clear, and shutdown share a cache lock; shutdown is terminal. `force_flush()` does not clear history. No background threads, timers, new dependencies, new network calls, or permission changes are introduced.

Alternatives rejected: periodic clear leaves peak retention dependent on traffic and loses whole batches; count-only bounds do not adequately handle large responses; removing the processor would remove annotation and suppression behavior. Public tracer/exporter constructor signatures remain compatible. Local history changes from unlimited to bounded by design; no cloud span is truncated or filtered by this cache.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1, FR-3 | T-1: add failing regression tests, then implement bounded cache in `inmemory_exporter.py` | AC-1: count/byte eviction, oversized payload, session cleanup, shutdown, and concurrent operations pass | `uv run --no-sync --extra dev pytest tests/test_inmemory_exporter.py -q` |
| FR-2, FR-4 | T-2: share the collector in `opentelemetry_tracer.py` | AC-2: multiple tracers share one collector; cloud spans, annotations, and trace IDs survive disabled/limited retention | `uv run --no-sync --extra dev pytest tests/test_tracing.py -q` |
| FR-5 | T-3: add config validation and bilingual user docs/spec | AC-3: defaults, overrides, zero, and invalid values are verified | `uv run --no-sync --extra dev pytest tests/config/test_tracing_config.py -q` |
| All | T-4: inspect diff, run focused tracing regressions and Ruff, reconcile both languages | AC-4: checks pass and limitations are recorded | See delivery record |

## Risks and review

Finite local history may truncate long session dumps. A shared cache covers the entire provider, so all tracers compete for the same budget and observe the same recent history. Python object estimates exclude allocator fragmentation and memory owned elsewhere; this does not promise an RSS ceiling. No production memory plateau or cloud behavior may be claimed from local tests alone.

Design reviewed directly: ownership, errors, concurrency, compatibility, configuration, bilingual equivalence, and verification coverage have no open blockers. User approval: request on 2026-10-13 to fix the confirmed leak following the proposed bounded-cache approach. Complex tests and cloud operations require follow-up; neither is needed to implement the scoped regression fix.

## Delivery record

- Baseline: `b8038fb16`; verification date: 2026-10-13
- Scope: bounded exporter, provider registration, configuration, regression tests, and bilingual cache documentation; T-1 through T-4 and AC-1 through AC-4 complete
- Regression before implementation: fail as expected, 20 failed and 3 passed for cache/config tests; includes old-span retention and stale session state
- Core checks: pass, 46 tests via `uv run --no-sync --extra dev pytest tests/test_inmemory_exporter.py tests/config/test_tracing_config.py tests/test_tracing.py -q`
- Focused compatibility checks: pass, 75 tests total including the core checks, content collection, LLM attribute extraction, runtime tracing, and Studio telemetry; one pre-existing invalid-escape warning
- Existing exporter fixtures also attempted metric delivery to `localhost:8000` during shutdown and logged `UNAVAILABLE`; the test process exited 0. New cache/cloud integration tests use a local in-memory stand-in and no cloud service
- Ruff format/check and `git diff --check`: pass for changed Python files and the patch
- Documentation: pass, both tracing MDX pages compile with `@mdx-js/mdx`; bilingual contract/configuration consistency and relative document links reviewed
- Pre-submission checks: pass, reran 75 focused tests after synchronizing `origin/main`; `uv run --no-sync --extra dev pre-commit run --all-files` passed, including Ruff and both secret scanners
- Full regression and documentation site build/type checks: not_run; this pass is limited to focused checks under the requested workflow, with no frontend application change
- Production/cloud validation: not_run, no production access or changes requested
- UI validation: not_applicable, no frontend behavior changes
- Commit and PR: authorized; package publication and production deployment: not_run, outside this scope

## CI follow-up

The initial Python 3.12 CI run had 7023 passing tests and two failures caused by runtime tests slicing the private `_spans` list. Update those two consumers to read session snapshots through `get_finished_spans(session_id)`, avoiding assumptions about the queue type or offsets that change after eviction. Preserve the existing span and session assertions. This follow-up changes no production code or approved contract

- Failed cases: reproduced both failures locally before the update; both pass afterward
- Extended check: `uv run --no-sync --extra dev pytest tests/runtime/differential tests/runtime/piagent/test_piagent_turn_contract.py -q` finishes with 84 passed, 2 xfailed, and 1 failed after the update
- Remaining failure: `test_model_fallbacks_warn_for_external_runtime` sees empty captured logs; it also fails on the original PR commit `9671acd7`, where the same check finishes with 82 passed, 2 xfailed, and 3 failed. It is outside the cache fix and remains unchanged
