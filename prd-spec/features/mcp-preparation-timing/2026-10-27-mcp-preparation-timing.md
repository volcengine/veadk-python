# MCP preparation and session-acquisition timing

[中文版](2026-10-27-mcp-preparation-timing.zh.md)

- Change ID: `mcp-preparation-timing`; revised: 2026-10-27.
- Status: approved for implementation within the active phase-1 task; not released.
- Component: [MCP session dispatch](../../../specs/mcp-session-dispatch/README.md).

## Evidence, intent and boundaries

Ordinary MCP invocation and per-request receiver context have passed isolated acceptance, but `TrustedMcpToolset.get_tools` and `TrustedMcpSessionManager.create_session` have no separate preparation timing. A total tool duration cannot identify time spent obtaining the tool list or acquiring a session.

Add two INTERNAL spans through the existing provider: `mcp.tools.prepare` covers the public tool-preparation call, including native header construction/cache/listing/filtering; `mcp.session.acquire` covers the existing acquisition, including reuse checks, lock wait and initial connection/initialization when needed. The second can be nested in the first or an actual tool invocation. These are overlapping boundaries, not durations to sum; no network-only or remote-server-internal timing is inferred.

Non-goals: new authentication, endpoints, permissions, exporter/provider defaults, session pools, retries, timeout behavior, dependency upgrades, vendor authentication acceptance, VeIdentity dynamic credentials or Sandbox phases. Caller headers, URLs, tool names/arguments/results and exception messages are not new telemetry attributes.

## Requirements and selected design

- `FR-1`: Wrap `get_tools` once around native delegation; return the same tools or preserve the exact error/cancellation. Keep native cache and retry policy.
- `FR-2`: Observe `create_session` without copying parent pool metadata or changing lock ownership. Extract the existing dispatch body into a private implementation method; invoke it exactly once per wrapper call.
- `FR-3`: A small MCP-specific helper records fixed phase/transport categories and elapsed spans only; failures record `error.type` and ERROR status without exception messages/events. Existing OTel context supplies parentage; it is restored after await, cancellation and concurrency.
- `FR-4`: Telemetry setup, attributes and cleanup cannot block or repeat business work. Use guarded start/attach/end and preserve original BaseException identity.
- `FR-5`: Verify actual preparation in the existing authorized isolated Runtime. If the client runs inside that fixture, its endpoint is fixed loopback to the owned MCP service, exposes no arbitrary URL/header input, invokes only synthetic tools and closes its session. Copy only the tested MCP source patch onto the accepted image; preserve package dependencies, SDK and 29 Runtime fields. New resource/role/credential changes are not authorized by this design.

## Tasks and acceptance

1. `T-1` / `AC-1`: Failing offline regressions for success, exact errors, cancellation, concurrent callers, reused sessions and nested parent context; no new pool or duplicate call.
2. `T-2` / `AC-2`: Implement the helper and two narrow adapters. Fault-inject tracing start/attach/attribute/end failures; business results/errors and call count remain unchanged. Synthetic secret markers never enter new span attributes/events.
3. `T-3` / `AC-3`: Targeted MCP/vendor/retry/identity regressions and required full Python/pre-commit gates. Update paired component contract, design outcomes and affected user documentation.
4. `T-4` / `AC-4`: Actual HTTP preparation and calls in the existing isolated receiver, module/dependency identity checks, and exact APMPlus phase/Trace/parent/duration lookup. Preserve prior negative evidence. Local spans alone do not prove ingestion or deployment.

## Review, authority and risks

Direct review substitutes for the unavailable `review-spec` skill. The design preserves the latest ordinary-parent dispatch fix, vendor selector and all authentication/retry/cancellation boundaries. No parent cache layout is inspected and no private transport initialization is reimplemented. The active user goal explicitly authorizes phase-1 implementation and verification without broader access; this records that existing authority, not a new human review of this file.

Potential interpretation risk is addressed by naming acquisition rather than connection-only time and documenting nested boundaries. Live fixture work stays within the existing authorized isolated Runtime/image scope. Any new access requirement remains a separate approval. Verification is `not_run` until evidence below is recorded.


## Verification record

- `pass`: before implementation, 6 timing/nesting/error/cancellation regressions failed; 10 existing-behavior fault checks passed. After implementation, 72 related MCP/vendor/retry/identity/generated-agent checks pass, including actual native retry and tool-list cache behavior.
- `pass`: frozen-source full regression: 7,946 passed, 50 skipped, 4 xfailed and 6 subtests passed (556.41 seconds); smoke markers remain excluded. All-files pre-commit passed after applying formatter output.
- `pass`: a separate fixture uses an actual local HTTP MCP server and verifies one preparation, three acquisitions, two successful calls, parent context restoration and session close. Combined fixture/metadata/archive integrity checks: 16 passed. These results do not prove cloud ingestion.
- `blocked`: documentation-site types/build checks cannot currently run through its package manager: frozen installation and the command's automatic dependency check require approval of esbuild/sharp build scripts. No approval, build allowlist or lock change was made; the task-generated pnpm workspace file was removed. Both MDX languages and local links remain paired. No dependency build result is claimed.
- `not_run`: isolated source-patch image, Runtime deployment and APMPlus phase acceptance. Existing Runtime V24, SDK and dependencies remain the immutable baseline for that next step.
