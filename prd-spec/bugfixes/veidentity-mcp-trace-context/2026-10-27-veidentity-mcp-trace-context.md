# VeIdentity MCP per-call Trace context

[中文版](2026-10-27-veidentity-mcp-trace-context.zh.md)

Change ID: `veidentity-mcp-trace-context`; date: 2026-10-27; status: approved within the active phase-1 implementation authority, not released. Contract: [MCP session dispatch](../../../specs/mcp-session-dispatch/README.md).

## Evidence, goals and boundaries

VeIdentityMcpTool currently calls session.call_tool with name/arguments only. Native ADK calls already send active Trace context in MCP request metadata; pinned mcp==1.26.0 supports the keyword-only meta argument. VeIdentity retry logging also interpolates exception messages, which can contain private transport/auth data.

## Requirements and design

- `FR-1`: Extract only active W3C traceparent/tracestate per invocation using TraceContextTextMapPropagator. Never forward baggage, auth headers, URLs or tool content. No valid context means the original no-meta call shape.
- `FR-2`: Pass context as per-request MCP meta, never credential-derived HTTP headers or pool keys. Preserve credential resolution, session manager, arguments, return/error identity and existing one-retry policy; cancellation still propagates.
- `FR-3`: Tracing extraction failure must not block or repeat the business call. Keep the helper small and separate from preparation timing. Retry logs retain function/error type, not raw exception text.
- `FR-4`: No new provider/exporter, dependency, permission, resource or credential. Synthetic credentials validate this boundary only; they do not establish real identity-provider authorization.

## Tasks, review and acceptance

`T-1` / `AC-1`: Failing regressions for active sampled/unsampled parents, tracestate, no-span behavior, baggage exclusion, separate concurrent callers, original arguments/headers, tracing failure, cancellation and unchanged retries/errors; private markers absent from retry logs.

`T-2` / `AC-2`: Add the internal helper and narrow call-site/log change. Run identity/MCP/Agent regressions, full required Python regression and all-files pre-commit. Maintain bilingual contract and documentation.

`T-3` / `AC-3`: Verify actual HTTP receiver parent IDs with synthetic credential headers and the existing isolated Runtime after local gates. Preserve SDK/dependencies/29 fields. Report real provider authorization separately.

Direct review replaces unavailable review-spec. The user explicitly authorizes feasible phase-1 implementation and verification; this records existing authority, not new human design approval. Reviewed risks: putting trace IDs in credential headers destroys session reuse; global propagators may add baggage; tracing exceptions may mask business errors; retry logs may leak credentials. The selected payload-only helper, fixed propagator and type-only retry log address these risks. Requirements and paired text were checked before code/tests. Verification is not_run until evidence is recorded.

## Verification record

- `pass`: pre-fix regressions: 5 failed/2 passed. After fix: 141 related checks, full Python regression 7,968 passed/50 skipped/4 xfailed/88 warnings in 561.61 seconds, unchanged Python diff fingerprint; all-files pre-commit passed after formatting.
- `pass`: types:check and production documentation build after normal index/type generation; the first build encountered the previously observed empty generated server module. No site configuration or dependency lock was changed.
- `pass`: actual local HTTP post-credential boundary with synthetic credentials, two distinct calling Span IDs and exact receiver parents. The initial fixture's anonymous discovery plus authenticated calls timed out; supplying the same synthetic headers through the native header provider and its readonly context restored the actual VeIdentity discovery/call pattern without changing production behavior or enlarging the timeout.
- `pass`: isolated Runtime V28 with source `216c3bf3`; 36 APMPlus Spans include one preparation, three acquisitions and two internal calls with distinct exact caller parents. SDK content capture stayed off; 16 file hashes, dependency versions and 29 protected fields matched. Synthetic post-credential path only, no real provider or model call.
- `not_run`: real credential-provider authorization. It cannot be inferred from the synthetic fixture.
