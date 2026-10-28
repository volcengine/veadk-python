# Model timing

[中文版](README.zh.md)

Component ID: `model-timing`; revision: 2026-10-28; status: active.

## Responsibility and interfaces

Own SDK-observed request/model/first-output timestamps in `veadk/tracing/telemetry/timing.py`, model adapters, Runner, and VeADK HTTP application factories. Consumers are existing OpenTelemetry exporters and trace dumps. No new configuration, credentials, dependencies, or response payload fields are required.

## Contracts

- CON-1: `veadk.request.start_time_unix_ns` is captured at HTTP ASGI entry, before request parsing, in VeADK AgentKit/Harness applications. `veadk.request.start_source` is `http`. Direct VeADK Runner calls use Runner execution entry and source `runner`. An inherited HTTP timestamp takes precedence. This excludes client/network/gateway delays before ASGI entry.
- CON-2: `veadk.model.start_time_unix_ns` is captured immediately before each adapter SDK request (`LiteLLMClient.acompletion` or Ark `aresponses`). Each request has a child `model_request` span under the owning model span; its model attribute identifies the requested model. Internal provider/LiteLLM retry/fallback activity is opaque and included in that SDK request. VeADK-issued retries/fallbacks create separate child spans. Successful/latest attempt fields also annotate the owning model span. This is not provider inference start.
- CON-3: For streaming requests, `veadk.model.first_token_time_unix_ns` is the local receipt time of the first nonempty generated content delta. `veadk.model.first_token_type` is `text`, `reasoning`, or `tool_call`. Empty deltas, role/id/signature metadata, heartbeats, usage, and completion-only aggregates do not count. A chunk can contain several tokens; no provider-side token generation timestamp is claimed. Record once, without requiring usage or storing content.
- CON-4: `veadk.model.streaming` describes the actual SDK request. `veadk.model.first_token_status` is `observed`, `non_streaming`, `no_output`, or `unsupported`. Non-streaming requests never synthesize a first-token timestamp from their complete response. Unsupported/custom/external engines explicitly expose absent model timing rather than treating an invocation span start as model start.
- CON-5: Each attempt ends on completion, error, cancellation, or generator closure. Already observed timestamps survive interruption. Model/request context does not leak between concurrent invocations or through async-generator yields. Original outputs, exceptions, cancellation, retry rules, and close behavior remain intact.
- CON-6: Wall-clock timestamps are UTC Unix nanoseconds. They may be used for trace correlation; no cross-host subtraction or monotonic-duration/TPOT guarantee is introduced. Trace attributes carry timestamps so existing JSON dumps retain them. First output also emits a timestamped `veadk.model.first_token` event.

## Security and compatibility

Only timing, bounded status/type labels, and existing model identifiers are added. No prompts, response content, or credentials are stored by timing instrumentation. HTTP middleware does not buffer bodies or alter SSE. Existing content-tracing controls remain applicable. Public APIs and serialized agent events stay compatible. Rollback removes additive instrumentation without migrating stored data. Generic ADK/custom application factories without the middleware can only provide a Runner timestamp when using VeADK Runner, or no request timestamp; no earlier start is fabricated.

## Verification

CON-1/5: ASGI boundary, async-generator/context/cancellation tests. CON-2/3/4/5: real adapter tests with controlled provider boundaries, plus real cloud Runtime/provider E2E. CON-6: exporter/dump contract assertions. Changed executable production lines must reach at least 95% coverage against the branch base, with no coverage exclusions added to satisfy the gate.

Change design and evidence: [first-token-timestamps](../../prd-spec/features/first-token-timestamps/2026-10-28-first-token-timestamps.md).

Contract verification: 55 focused timing/adapter tests, 244 affected tests and 6 real cloud cases passed; changed production-line coverage is 100% (208/208). The unrelated default-regression failure is documented in the linked PRD.
