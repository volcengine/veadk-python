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
