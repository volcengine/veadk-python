# MCP session dispatch

[中文版](README.zh.md)

Component ID: `mcp-session-dispatch`; status: implemented; revised: 2026-10-27.

## Responsibility and interfaces

`TrustedMcpToolset` selects tools and `TrustedMcpSessionManager.create_session(headers=None)` dispatches the transport. Google ADK owns ordinary MCP session pooling, native cache metadata and lifecycle. The existing TrustedMCP branch owns vendor transport selection. This component does not grant authentication, define business Task state or implement Sandbox execution.

## Contracts

- `CON-1`: For ordinary Streamable HTTP, SSE or stdio, delegate to Google ADK before acquiring the custom lock. Do not duplicate the parent's pool layout or acquire its lock recursively.
- `CON-2`: Use the vendor branch only for Streamable HTTP with the exact merged `x-trusted-mcp=true` marker. Preserve input dictionaries, authentication headers and existing vendor behavior.
- `CON-3`: Preserve parent errors, cancellation, concurrency and cleanup semantics. No new timeout, retry or configuration default is introduced.
- `CON-4`: Initialization logs expose the transport class only, excluding connection representations, headers and full URLs. Credentials are not diagnostic evidence.

No public signature, dependency range, credential source or persistent data schema changes. Both modes use the existing manager state; ordinary session metadata remains parent-owned. Vendor live compatibility is not established by mock tests and is not claimed here. Trace correlation is verified separately from successful transport.

## Verification and change record

[Bugfix design](../../prd-spec/bugfixes/mcp-session-delegation/2026-10-27-standard-mcp-session-delegation.md) owns requirements, acceptance and delivery evidence. `CON-1/3` map to bounded normal delegation/concurrency/cancellation tests; `CON-2` to existing vendor selection/cache regressions; `CON-4` to synthetic-secret constructor logging regression. An authorized existing receiver is used for actual discovery/call/close verification without models, new cloud resources or credential persistence. Contracts are implemented and verified on the test branch; the paired design records remaining cloud receiver correlation work.

The private `_create_client` adapter forwards native positional and keyword transport arguments unchanged for ordinary connections, including parent-provided mTLS transport and session metadata.

## Preparation timing contract extension

- `CON-5`: `mcp.tools.prepare` and nested `mcp.session.acquire` are INTERNAL observed boundaries, not separate durations to sum or network-only timing. Native pooling, tool cache and retries remain owned by ADK/vendor dispatch.
- `CON-6`: New attributes contain only fixed phase/transport categories and error types; no messages, connection data or tool content. OTel parent context is restored and telemetry failures never repeat/prevent business calls.

[Preparation timing design](../../prd-spec/features/mcp-preparation-timing/2026-10-27-mcp-preparation-timing.md) owns acceptance and delivery. These additional contracts are approved for implementation; existing CON-1/4 remain implemented.

## Agent-owned native preparation extension

Approved extension [mcp-preparation-native-extension](../../prd-spec/features/mcp-preparation-timing/2026-10-27-mcp-preparation-native-extension.md): native and VeIdentity instances assembled by VeADK Agent retain the same manager, callbacks, auth, cache and retry semantics while preparation/acquisition are observed. Instance-local binding must be idempotent and preserve deepcopy ownership; Trusted spans must not duplicate. Instance adapter and Agent assembly pass local regression; native V26 and automatic Agent V27 cloud acceptance passed.

## VeIdentity request Trace context extension

Approved [VeIdentity per-call context](../../prd-spec/bugfixes/veidentity-mcp-trace-context/2026-10-27-veidentity-mcp-trace-context.md): only current W3C context belongs in request meta; credential headers and cache keys remain unchanged. Preserve no-context behavior, extraction-failure isolation, cancellation and retry count; log error type without private exception messages. Implementation, local regression/HTTP and isolated V28 APMPlus checks pass with synthetic credentials and distinct exact calling parents. Real credential-provider authorization remains unverified.
