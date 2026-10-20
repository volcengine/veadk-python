# Local tracing cache

[中文版](README.zh.md)

Component ID: `tracing-cache` · Status: active · Revision: 2026-10-13

## Responsibility and interfaces

Owns bounded diagnostic span retention in `veadk/tracing/telemetry/exporters/inmemory_exporter.py`, wired by `OpentelemetryTracer`. Cloud transport, SDK request instrumentation, and Studio storage are separate responsibilities. Consumers are `OpentelemetryTracer.dump()` and `trace_id`; constructor signatures remain compatible.

## Contracts

- CON-1: One cache per provider, shared by all VeADK tracers. Default limits are 1024 spans and 16777216 estimated bytes. Oldest entries are evicted first. Entries larger than the byte budget are not cached. Other exporters receive unchanged spans.
- CON-2: `OpenTelemetryConfig.inmemory_enabled` defaults to true. `inmemory_max_spans` and `inmemory_max_bytes` are nonnegative integers; either zero disables storage. Environment names are `OBSERVABILITY_OPENTELEMETRY_INMEMORY_ENABLED`, `OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_SPANS`, and `OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_BYTES`. Use existing startup settings and config.yaml-to-environment handling. Invalid values fail configuration validation. First collector creation captures configuration; changes require a new provider/process.
- CON-3: Disabled storage preserves the annotation processor, instrumentation suppression, latest trace ID, and existing cloud export/flush behavior. No retained span or session index remains. `dump()` writes an empty array when no matching history is retained.
- CON-4: The session index is derived from retained `call_llm` spans. Session dumps return retained spans with matching trace IDs in export order, including related spans without session attributes. Evicted session anchors can make a partial trace unavailable to session lookup. `clear()` resets spans, accounting, index, and latest trace ID. `shutdown()` clears data and permanently stops retention. Flush does not clear data.
- CON-5: Export/read/clear/shutdown are serialized by a cache lock; provider registration has its own lock. Reads return snapshots. There are no timers or new background tasks. Retention is process-local and not persistent. Limits cover estimated known span data, not exact RSS, allocator fragmentation, or other components' memory.

Example: set `OBSERVABILITY_OPENTELEMETRY_INMEMORY_ENABLED=false` before startup to keep cloud telemetry while disabling local history. A bounded enabled cache retains recent diagnostics; use cloud storage for complete history.

## Security, failures, and compatibility

The cache introduces no credentials, permissions, external writes, or network operations. Existing content collection/redaction settings remain owned by instrumentation. Eviction changes only diagnostic history, not user sessions or cloud telemetry. Oversized records are skipped locally without logging their content. Finite history and provider-wide sharing replace previous unlimited per-tracer retention. No additional packages or unsupported Python features are required.

## Verification and change record

CON-1/4/5 map to `tests/test_inmemory_exporter.py`; CON-2 to `tests/config/test_tracing_config.py`; CON-1/3/5 integration to `tests/test_tracing.py`. Run these using `uv run --no-sync --extra dev pytest <paths> -q`, followed by focused tracing compatibility checks and Ruff. Production RSS requires separate workload evidence.

Design and verification: [tracing-memory](../../prd-spec/bugfixes/tracing-memory/2026-10-13-bounded-cache.md). Contracts above are implemented and covered by the focused regression checks recorded in the linked design; package publication is separate.
