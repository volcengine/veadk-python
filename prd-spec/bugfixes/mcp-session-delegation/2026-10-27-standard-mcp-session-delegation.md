# Standard MCP session delegation without recursive locking

[中文版](2026-10-27-standard-mcp-session-delegation.zh.md)

- Change ID: `mcp-session-delegation`; created/revised: 2026-10-27.
- Status: implemented and verified on the test branch; not released.
- Component: [MCP session dispatch](../../../specs/mcp-session-dispatch/README.md).

## Evidence and scope

`TrustedMcpSessionManager.create_session` holds `_session_lock` and delegates ordinary connections to `MCPSessionManager.create_session`, which acquires the same non-reentrant lock. An authorized isolated probe stalled before tool discovery. A separate 0.3-second offline reproduction timed out before its guarded transport factory was called; cancellation released the lock. This is a local dispatch defect, not evidence of denied MCP credentials.

`TrustedMcpToolset` also logs the complete connection parameters. Those parameters can contain authentication headers. The initialization log must identify the transport without reproducing headers or credential-bearing URLs.

Goals: restore ordinary MCP discovery/calls and safe initialization logging. Non-goals: change vendor TrustedMCP authentication, upgrade dependencies, create cloud resources, alter shared roles/routes, or claim Sandbox execution timing.

## Requirements and design

- `FR-1`: Ordinary Streamable HTTP, SSE and stdio connections delegate to the parent before acquiring the custom TrustedMCP lock. The parent owns ordinary pooling, native cache metadata, concurrency and cleanup.
- `FR-2`: Only Streamable HTTP with the exact merged `x-trusted-mcp=true` marker uses the existing custom TrustedMCP branch. Preserve authentication headers, caller dictionaries and existing vendor selection.
- `FR-3`: Initialization logs contain the transport class only; no connection representation, headers, secrets or full URLs.
- `FR-4`: Parent errors and cancellation propagate, and the lock remains usable. Concurrent ordinary callers use the parent's pooling contract.

The selected fix performs mode selection before the custom lock and delegates ordinary calls directly. Replacing the lock with a reentrant abstraction or creating an unpooled transport would hide the ownership error and change resource behavior. No public signatures, configuration keys, package ranges or credential sources change. The paired component spec records proposed lock ownership and redaction guarantees.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1, FR-4 | T-1 regression; T-2 early delegation | AC-1: ordinary calls finish within a bounded test, including concurrent calls, errors and cancellation | `uv run --extra dev pytest tests/tools/mcp_tool/test_standard_mcp_session_delegation.py` |
| FR-2 | T-2 preserve vendor branch; T-3 existing regression | AC-2: exact vendor selection and trusted cache reuse unchanged; ordinary pool metadata stays parent-owned | `uv run --extra dev pytest tests/tools/mcp_tool/test_trusted_mcp_components.py tests/utils/test_mcp_session_retry.py` |
| FR-3 | T-1 log regression; T-2 transport-only log | AC-3: synthetic credential/URL markers absent from captured constructor logs | Targeted delegation regression |
| FR-1 | T-4 isolated live protocol check | AC-4: owned existing MCP receiver discovery and two normal tool calls succeed; close the client session and record Trace/Span association separately | Sanitized local probe; no model, new cloud resource or credential persistence |
| all | T-5 synchronize docs and review | AC-5: bilingual consistency, required pre-commit and relevant tests recorded; publish only to the existing draft PR | `uv run --extra dev pre-commit run --all-files` and repository regression gates |

## Risks, authorization and review

- The vendor TrustedMCP path is unchanged. Existing mock tests do not establish live vendor authentication compatibility; that is outside this defect's scope.
- Transport success does not establish upstream Trace propagation. The live check must report authentication, return values and correlation independently.
- Credentials remain in memory and go only to the already authorized receiver. Probe logs are captured in memory; no raw logs, responses, tokens or prompts enter evidence.
- Authorization comes from the active user goal to implement and verify phase-1 gaps without expanding access. No new permission, target or resource is introduced. This records the existing scope, not a separate human review of this document.
- Direct design review (the `review-spec` skill is unavailable): verified lock ownership, exact marker semantics, cancellation, unchanged public API/dependencies, safe logging, testability and bilingual equivalence. No implementation blocker remains within this scope.
- Verification status before implementation: offline reproduction `pass` (defect reproduced); new regressions/gates/live retry `not_run`. Update both language versions with actual outcomes.

## Compatibility review update

The bounded live retry now reaches native session creation but exposes another local adapter defect: Google ADK 2.7.1 calls `_create_client` with `mtls_transport` and `session_key`, while the override accepts only headers. Extend the private override to forward positional and keyword transport arguments unchanged to the parent for ordinary connections. Do not implement or replace authentication/transport behavior. Add a failing regression for argument identity and header preservation before implementation. This is within FR-1/4 and CON-1/3; the direct review confirms no new public API, dependency or permission.


## Implementation and verification record

- `pass`: all seven initial regressions failed on the original implementation. Three native keyword-argument tests then reproduced `TypeError`; the non-vendor marker regression also failed before its fix.
- `pass`: 25 targeted session/vendor/retry tests; 53 broader MCP/identity/generated-agent tests before the last header-preservation addition. Repository pre-commit passed after applying its formatter changes.
- `pass`: existing authorized isolated receiver discovery, two normal tool calls, session close and exact server tool Span lookup. Both requests carried their active call's `traceparent` in MCP `_meta`. No model, new resource, credential persistence or authorization expansion was involved.
- `pass`: final full Python regression after source freeze: 7,928 passed, 50 skipped, 4 expected failures and 6 subtests passed. The tested base is `7b247acceb5684840fab457986b27bf6c109d76f`, already rebased onto remote main `2301477104f6f77e76c8182529545950e2d8ae6e`; skips do not establish the corresponding behavior.
- Separate failure: the receiver reused its session Trace despite correct request metadata. This is not an outbound authentication failure. The SDK receiver correction is tested separately and cloud correlation remains pending; ordinary transport success is not claimed as cross-service correlation acceptance.
- Review: ordinary locking/cache stays parent-owned; native transport arguments and non-vendor headers are preserved; only a private vendor transport copy loses the selector; initialization cannot render connection secrets. The existing vendor authentication path is not claimed live-verified.
