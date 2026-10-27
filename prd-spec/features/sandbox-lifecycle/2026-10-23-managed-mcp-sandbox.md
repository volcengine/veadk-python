# Managed MCP sandbox lifecycle

[中文](2026-10-23-managed-mcp-sandbox.zh.md)

- Change ID: `sandbox-lifecycle`; created/revised: 2026-10-23.
- Status: superseded; implementation and results below are historical. Current entrypoint: [Agent-native design](2026-10-23-agent-owned-mcp-sandbox.md).
- Contract: [sandbox-lifecycle](../../../specs/sandbox-lifecycle/README.md).

## Background and scope

An ordinary ADK `McpToolset` can execute sandbox tools but does not create,
pause, resume, or delete the underlying AgentKit Session. The preceding local
prototype demonstrated creation, MCP file read/write, model invocation and
cleanup. Its location outside this repository did not deliver an SDK capability.
The user explicitly requested implementation in `veadk-python` and standard
`McpToolset`, without a specialized sandbox Toolset.

Existing `veadk/agents/_remote_sandbox/session.py` resolves execution leases for
a different remote-Agent path. It considers only Starting/Ready reusable and
may rotate physical sessions. This feature must not change that existing contract.

## Requirements and scenarios

| ID | Given / when / then |
| --- | --- |
| FR-1 | A new session key acquires a sandbox: save creation intent, create one Session and wait for Ready. |
| FR-2 | A bound Session is Paused: acquire resumes that same Session and returns its refreshed MCP URL. |
| FR-3 | An application pauses/deletes: serialize against active acquisition, confirm remote state, retain deleted bindings. |
| FR-4 | Create response is lost: recover by persisted unique UserSessionId; zero/multiple matches must not create a replacement. |
| FR-5 | Agent/Runner are reused: standard McpToolset reconnects per invocation while persistent ADK sessions preserve history. |
| FR-6 | SDK/API, polling or cancellation fails: preserve uncertainty, sanitize diagnostics, never treat a generic error as deletion. |
| FR-7 | Imports, examples, offline tests and bilingual documents live inside this repository; no private endpoint or credential is included. |

Non-goals: custom MCP Toolset, automatic idle pause, distributed locking,
background-job tracking, remote-command cancellation, auto renewal, automatic
replacement after expiry, attachment/adoption of externally owned instances,
Studio/generated-project integration, and migration of existing remote-Agent leases.

## Design

Expose `SandboxManager`, `SessionKey`, `SandboxLease`, `SandboxError` from
`veadk.sandbox`. Manager owns local persisted bindings and AgentKit control calls;
the opt-in Runner integration owns per-invocation standard McpToolset connections;
the application owns a reusable Agent/Runner.
Use the existing AgentKit SDK dependency; add no dependency or default runtime hooks.
Public arguments and invariants are defined in the component contract.

POSIX file locks serialize one complete turn and lifecycle operations across
processes sharing one local directory. Credentials remain in SDK configuration;
signed endpoint URLs are transient and excluded from lease repr and state files.
Unsupported platforms fail explicitly when constructing the manager, without
breaking ordinary `import veadk` or `import veadk.sandbox`.

Creation intent and unique UserSessionId are persisted before the RPC. Deletion
intent blocks new acquisition even if confirmation fails. APIs confirm remote
states through GetSession. Local cancellation waits for synchronous SDK requests
to finish before releasing the lock; it does not cancel remote commands.

## Tasks and acceptance

| Task | Requirement | Acceptance | Verification |
| --- | --- | --- | --- |
| T-1 | FR-1–4, FR-6 | AC-1: SDK exports and lifecycle invariants | `tests/sandbox/test_manager.py` |
| T-2 | FR-2, FR-5 | AC-2: ordinary MCP reconnect and retained ADK history | `tests/sandbox/test_mcp_integration.py` |
| T-3 | FR-7 | AC-3: runnable repository example and paired docs | imports, CLI help, links, Ruff |
| T-4 | FR-1, FR-5–6 | AC-4: distinguish offline and cloud validation | verification record below |

## Review and approval

The user approved the standard-McpToolset/Manager approach, asked for a first
implementation, then explicitly corrected the implementation location to this
repository. This authorizes the scoped migration without a second approval prompt.
No `review-spec` skill is available; direct review covered ownership, state
transitions, cancellation, partial outcomes, isolation, compatibility, testability
and bilingual equivalence. Keep the existing remote-Agent helper unchanged;
support POSIX explicitly; retain uncertain/deleted records. No design blockers remain.

## Initial lifecycle-only verification (historical)

Scope: this feature's uncommitted additions, 2026-10-23. No shared Agent/Runner or
remote-Agent implementation changed; no dependency metadata changed. Tested with
Python 3.13, `google-adk==2.7.1`, `agentkit-sdk-python==0.8.9`, `mcp==1.26.0`.

| Check | Outcome | Evidence / boundary |
| --- | --- | --- |
| Regression before implementation | pass | The new lifecycle test first failed because `veadk.sandbox` did not exist. |
| `uv run --extra dev pytest tests/sandbox -q` | pass | 16 tests; one upstream ADK deprecation warning. Covers lifecycle, create ambiguity/pagination, timeouts, cancellation, tombstones, real local MCP reconnect and SQLite history. |
| `uvx ruff check veadk/sandbox tests/sandbox examples/sandbox_mcp` and `uvx ruff format --check` on those paths | pass | Six source/test Python files. |
| `uv run python examples/sandbox_mcp/main.py --help` and SDK imports | pass | Repository-local public API and runnable CLI. |
| Paired documents, relative links, whitespace and `git diff --check` | pass | Three bilingual document pairs; no credentials/private endpoints included. |
| Cloud smoke using current SDK and example | pass | Created a fresh temporary Session, reacquired the same physical SessionId, called the real model with standard MCP tools, verified its FunctionResponse contained the execution marker and successful tool output, then confirmed deletion. |
| Cloud pause/resume and workspace retention | not_run | Available Tool has snapshots disabled; its configuration was not changed. Offline tests simulate this transition. |
| Full regression / pre-commit | not_run | Additive isolated module with targeted integration coverage; no shared implementation or dependency changes, and no commit requested. |

Direct implementation review confirmed the T-1–T-4 acceptance criteria, unchanged
remote-Agent behavior, error handling, cancellation/lock release, connection
closure, credential-free binding records, and bilingual equivalence. No blocking
findings remain. POSIX-only local coordination and backend-dependent pause support
remain explicit first-version limits. The earlier sibling prototype is retained
as a historical artifact; the canonical SDK and example now live in this repository.


## Reusable Runner revision (implemented)

The user explicitly approved the revised approach with “按照方案改下看看”.
FR-8: `Runner(..., sandbox=manager)` reuses the same Agent and Runner across
sessions and turns. SessionKey continues to identify one physical sandbox.
FR-9: Each run_async invocation acquires its own ordinary McpToolset and injects
its tools into the current LlmRequest through an internal before-model plugin.
Never mutate Agent.tools, credentials, or callbacks. Different sessions run
concurrently; same-session invocations serialize through the existing lock.
FR-10: Exhaustion, errors, cancellation and explicit stream aclose end the ADK
execution and close MCP before releasing the binding lock. No automatic pause or
delete. Session deletion remains an explicit Manager operation.

The internal plugin owns only a transient session-to-connection map. It uses
trusted callback session identity to select the connection; no signed URLs enter
session state. A fresh Toolset per invocation avoids cached endpoint reuse after
resume. Runner without sandbox keeps its existing behavior. This first version
supports a single ADK LlmAgent with empty tools and no sub-agents/code executor;
other runtimes, run_live, and mixed local tools are outside this integration.
Reject incompatible configuration explicitly. Application and plugins remain
trusted, and existing callbacks continue to run. Standard SDK-managed resources
remain accessible directly through SandboxManager.

T-5 / AC-5: replace the per-turn Agent example with a reusable Runner; test two
concurrent sessions using identical tool names but different results, two turns
plus pause/resume, unchanged Agent object/tools/callbacks, tool failure, model
failure, cancellation, and early stream close. Run existing runner contracts and
steering tests because run_async wrapping is affected. Update all three bilingual
pairs. Previous cloud results establish the earlier version only; rerun an isolated
cloud smoke for this revision if credentials remain available. Full cloud pause
is still conditional on provider configuration.

Direct design review: request-local tools_dict dispatch is supported by ADK 2.7;
outer generator cleanup is required because after_run callbacks are success-only.
No custom SandboxMcpToolset is introduced. The approved user scope covers these
changes; no additional approval required. Verification for this revision is recorded below.


## Final revision verification and delivery

Date: 2026-10-23; scope: current uncommitted SDK/Runner/example/test additions and
Runner signature/stream cleanup diff. Same dependency versions as the initial
record; no dependency change. User-approved FR-8–10 / T-5 / AC-5 are implemented.

| Check | Result | Evidence |
| --- | --- | --- |
| Test-first regression | pass | Four new reuse/cleanup cases first failed with unexpected Runner argument `sandbox`. |
| `uv run --extra dev pytest tests/sandbox tests/runner tests/agents/test_remote_sandbox_agent.py tests/extensions/harness/test_runner_plugins.py -q` | pass | 63 tests; 21 upstream deprecation warnings. Includes shared Agent with concurrent sessions, same-session serialization, retained SQLite history, resume endpoint refresh, callback preservation, model/tool/discovery errors, cancellation, early close, missing chat, configuration and existing consumers. |
| Ruff on sandbox source/tests/example and Runner contract test | pass | Check and format pass. |
| Full-file Runner Ruff | fail (pre-existing baseline) | Existing Runner diagnostics remain; comparison against HEAD confirms no added rule/message diagnostics. Unrelated code was not changed to clear legacy lint. |
| CLI help, bilingual pairs, relative links, Python examples and whitespace | pass | Current `--follow-up` example reuses a single Agent/Runner. |
| Current cloud smoke | pass | One Agent/Runner concurrently served two sessions, each for two turns. Both wrote the same pathname with distinct markers and read back their own marker through real model MCP calls; each retained its physical SessionId. Both temporary sandboxes were deleted and confirmed. |
| Cloud pause/resume | not_run | Available Tool has snapshots disabled; offline transition covered. |
| Full repository suite / pre-commit | not_run | Relevant Runner, remote-Agent and plugin regression expanded as above; no commit requested. |

Direct implementation review reconciled the public keyword-only API, unchanged
shared Agent fields, request-local dispatch, MCP ownership, stream termination,
unsupported configurations, and bilingual contract/example consistency. The
integration is opt-in; no model tools or cloud sessions are added to other runners.
No blocking findings remain. The POSIX/single-agent/run_async/backend snapshot
limits are documented. No commit, publication or deployment was performed.
