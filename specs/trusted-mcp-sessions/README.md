# Trusted MCP sessions

[中文版](README.zh.md)

- Component ID: `trusted-mcp-sessions`
- Status: `active`; scoped routing contracts verified by isolated component tests.
- Revision: 2026-10-26
- Related PRD: [Standard MCP deadlock](../../prd-spec/bugfixes/trusted-mcp-session-routing/2026-10-26-standard-mcp-deadlock.md)
- Owned code: `veadk/tools/mcp_tool/trusted_mcp_session_manager.py`.
- Consumer: `veadk/tools/mcp_tool/trusted_mcp_toolset.py`.
- Tests: `tests/tools/mcp_tool/test_trusted_mcp_components.py`; `tests/tools/mcp_tool/test_trusted_mcp_session_routing.py`.

## Responsibility and entry points

`TrustedMcpSessionManager` extends Google ADK's `MCPSessionManager`. It owns trusted transport selection and trusted session creation/pooling; standard sessions delegate to Google ADK. `TrustedMcpToolset` installs this manager for tool discovery and execution.

The session entry point is `async create_session(headers: Optional[Dict[str, str]] = None) -> ClientSession`. Dependencies are Google ADK connection parameters and parent lifecycle methods, MCP `ClientSession`, and `bytedance.jeddak_trusted_mcp.trusted_mcp_client`. Inherited `close()` owns standard pool cleanup; the existing trusted-entry compatibility limitation is recorded below. Toolset argument forwarding, trusted attestation internals, cloud deployment, and general dependency policy are outside this component's scope.

## Contracts

- `CON-1`: Trusted selection requires `StreamableHTTPConnectionParams` and merged `x-trusted-mcp == "true"`. Other connection types and marker values use standard transport.
- `CON-2`: Standard `create_session` delegates before acquiring the subclass session lock or touching the pool. The parent owns standard synchronization, initialization, reuse, replacement, errors, and cleanup. The `_create_client` override accepts and forwards parent positional/keyword arguments on the standard route.
- `CON-3`: Header merge precedence is inherited: per-call values override connection values. Routing inspection must not mutate input dictionaries. Authentication headers remain available to the selected transport. The trusted marker is removed from the private merged copy only after computing the trusted session key.
- `CON-4`: Trusted creation uses `trusted_mcp_client` and stores the initialized session with its `AsyncExitStack`. Healthy sessions reuse the same key; disconnected sessions are removed and replaced under the session lock. Existing cleanup failures are reported by the current logger.
- `CON-5`: Standard errors and cancellations propagate with parent semantics. Cancellation while waiting for the lock must not leave the subclass holding it. No new timeout, retry policy, or success fallback is introduced.

Example inputs: a streamable HTTP connection with `headers={"Authorization": "Bearer test-placeholder"}` selects standard MCP. Adding `x-trusted-mcp: "true"` selects trusted MCP; a per-call `"false"` override selects standard MCP.

## State, data, and concurrency

Session state is process-local in inherited `_sessions`: the current parent stores key → `(session, exit_stack, loop)` for standard sessions; the unchanged trusted branch stores key → `(session, exit_stack)`. There is no persistent schema or new environment variable. Session keys and connection timeouts use the parent implementation.

Relevant transitions are absent → initialized/cached → reused, disconnected → cleaned/removed → replaced, and cached → closed/removed through inherited `close()`. Standard transitions belong to the parent. Trusted transitions use the subclass lock exactly once. A failed creation does not cache a successful session. Lock-wait cancellation releases any context-managed lock already acquired.

This change does not adjust event-loop lock allocation, cross-loop session handling, late transport events, or cleanup on trusted cancellation after resource entry; these remain upstream/existing implementation limitations.

On the verified Google ADK 2.7.1 baseline, inherited `close()` expects three-element pool entries and is incompatible with the unchanged trusted two-element entries. The scoped fix preserves trusted creation/reuse; tests explicitly close trusted stacks without claiming inherited final-close compatibility. Resolving this existing trusted lifecycle issue requires a separate approved change.

## Security, failures, and compatibility

Trust is selected by explicit connection type and marker, not by a Bearer header alone. Do not add credential values to diagnostics, specifications, or fixtures. Verification replaces real transports and does not read local AICC configuration or invoke attestation/cloud services.

Public imports/signatures and authentication configuration remain compatible. Dependency support follows [runtime dependency compatibility](../runtime-dependency-compatibility/README.md), currently Google ADK `>=2.7.0,<2.8.0` and repository MCP `1.26.0`. The reported Google ADK 2.1.0 combination is source context, not verified current support.

Existing session creation/cleanup logs remain the available diagnostics. The standard path removes the subclass-held lock that previously prevented connection entry; transport failures remain visible as parent exceptions. It does not guarantee successful connection to an unavailable server or repair unrelated upstream cancellation cleanup.

## Verification and change record

| Contract | Validation | Evidence |
| --- | --- | --- |
| `CON-1`, `CON-3`, `CON-4` | Routing, header, trusted creation/reuse tests plus existing component tests | `pass`, included in 24 targeted tests; related PRD |
| `CON-2` | Bounded pre-fix failure and post-fix success using real parent locking; standard transport/lifecycle tests | `pass`, two pre-fix timeouts and post-fix successes; related PRD |
| `CON-5` | Standard failure retry and cancellation while waiting for the lock | `pass`, included in 24 targeted tests; related PRD |

Command: `uv run --extra dev pytest tests/tools/mcp_tool`. Broader checks and final results belong to the PRD. Real trusted attestation is `not_applicable` to the isolated lock regression.

2026-10-26: User approved the scoped PRD; implemented standard-session delegation and parent factory-argument forwarding while preserving trusted routing. Verified on Python 3.11.14, Google ADK 2.7.1, and MCP 1.26.0 against baseline `c662cc8d` plus the working-tree routing diff. Targeted tests passed; broader verification and limitations are recorded in the PRD.
