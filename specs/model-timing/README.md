# Model timing

[中文版](README.zh.md)

Component ID: `model-timing`; revision: 2026-11-02; status: active.

## Responsibility and interfaces

Own native request/model spans and standard streaming TTFT in `veadk/tracing/telemetry/timing.py`, with model adapters, Runner, and VeADK HTTP factories. `portal_metrics.py` owns the existing Histogram instrument; the configured global MeterProvider owns export. No new configuration, credentials, dependencies, or agent response fields are introduced.

## Contracts

- CON-1: VeADK AgentKit/Harness HTTP factories create a native `http_request` SERVER span at ASGI entry, before body parsing, ending when the application finishes. Direct Runner execution owns a `runner_request` span. An inherited HTTP request span is reused by Runner. Neither boundary includes pre-ingress client/network/gateway delays.
- CON-2: Each observable SDK request has a `model_request` CLIENT child under the current model/agent context. Its native start is the local SDK start used by TTFT calculation. VeADK-issued retries/fallbacks have separate spans; hidden provider/LiteLLM retries remain within the observed SDK request. This is not provider inference start.
- CON-3: First output is the first nonempty text, reasoning, or tool-call delta. Empty/role/id/signature metadata, usage, heartbeats, and completion-only aggregates do not count. A chunk may contain several tokens. First-output receipt is internal state, latched once without requiring usage or storing content.
- CON-4: `gen_ai.request.stream` is the actual SDK Boolean mode. `gen_ai.chat_completions.streaming_time_to_first_token` is floating-point seconds from SDK start to first output. Non-streaming/no-output/uninstrumented paths omit TTFT. Unknown actual SDK mode is not inferred from Runner configuration.
- CON-5: Spans end on completion, failure, cancellation, and explicit generator closure. Request context is attached only during producer advancement/closure, not across generator yields. Model failures set native Status `ERROR` with `error.type=llm_error`, `timeout`, or `cancelled`. Request failures use `request_error`, `timeout`, or `cancelled`; HTTP 5xx uses `http_error`. Explicit generator closure is not an error. Original outputs, exceptions, and cleanup are preserved.
- CON-6: Native start/end timestamps use OpenTelemetry units. TTFT converts the local Unix-nanosecond difference to seconds; no cross-host or monotonic-clock guarantee is introduced. Negative intervals are omitted with a bounded diagnostic; genuine zero elapsed time is valid. Already observed TTFT survives later interruption.
- CON-7: SDK spans carry `gen_ai.span.kind=llm` and `gen_ai.request.model`. Standard model fields belong to each SDK span, not its aggregate owner. Do not export `veadk.request.*`, `veadk.model.*`, or a custom first-token event; do not duplicate native span times in attributes. No compatibility aliases are retained, as explicitly authorized by the user.
- CON-8: Record the same observed TTFT exactly once in the existing `gen_ai.chat_completions.streaming_time_to_first_token` Histogram, unit `s`, independent of usage and trace sampling. No observations means no sample. Metric-recording failures emit a bounded diagnostic without backend details and do not replace model output/error.
- CON-9: TTFT metric dimensions are the actual `gen_ai.request.model` and existing conversational `gen_ai.operation.name=chat`. Unknown provider/response-model values are omitted. No prompts, responses, exception text, or per-request identifiers are added. Export configuration remains owned by the existing MeterProvider.

## Compatibility and security

This intentionally replaces custom timing fields and their mirrored aggregate fields with native span boundaries and standard telemetry. Callers must inspect request/SDK spans and standard TTFT; no legacy aliases remain. Application responses and public Agent invocation signatures do not change. The HTTP middleware does not buffer bodies. New request spans can change trace parentage. Exception text is not recorded by this instrumentation. Rollback requires reverting the coherent timing, hook, test, and documentation change.

## Verification and change record

Tests: `tests/test_model_timing.py`, `tests/test_model_ttft.py`, `tests/models/test_model_timing_adapters.py`, and affected Runner/application/exporter tests. Cover native start/parentage, absence of custom fields/events, actual SDK mode, first-output classification, failures/privacy, retry/close/cancellation, yield/task isolation, and real in-memory Histogram data. Changed production-line coverage must reach at least 95%; no exclusions may be added to satisfy it.

[Design and executed evidence](../../prd-spec/bugfixes/apmplus-ttft/2026-11-02-apmplus-ttft.md). The standards-only revision supersedes the predecessor's custom-field contracts. Historical cloud results do not validate this revision; current verification is local unless explicitly recorded otherwise.
