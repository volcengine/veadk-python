# Sandbox lifecycle contract

[中文](README.zh.md)

Component: `sandbox-lifecycle`; revision: 2026-10-23; status: active.
Owner: `veadk.sandbox` and the opt-in integration in `veadk/agent.py`; design: [managed MCP sandbox](../../prd-spec/features/sandbox-lifecycle/2026-10-23-agent-owned-mcp-sandbox.md).

## Responsibilities and interfaces

`SandboxManager(*, tool_id, state_dir, region="cn-beijing", ttl=1800,
ready_timeout=120.0, poll_interval=1.0, client=None)` owns AgentKit Sessions it creates.
`SessionKey(app_name, user_id, session_id)` identifies a logical binding;
the local lookup includes region and ToolId. Use separate state directories for
different accounts/control-plane configurations. Never pass model-generated identity.
An injected client must be configured for the same region and implement the
synchronous AgentKit SDK methods used by the manager.

- `async with manager.acquire(key) as lease`: create/recover/resume, wait for Ready,
  hold the local exclusive lock throughout use. `SandboxLease.session_id` is the
  physical ID; `.mcp_url` is a transient connection URL with preserved query parameters.
- `await manager.resume(key)`: existing binding only; returns a ready lease.
- `await manager.pause(key)`: existing binding only; confirm Paused.
- `await manager.delete(key)`: existing binding only; confirm termination/not-found;
  keep a tombstone. Deletes the remote Session, not the ADK chat history.
- `await manager.status(key)`: safe binding status and current remote state;
  creation-outcome recovery may persist an already-existing physical ID.
- `SandboxError`: sanitized error; optional `.code` is the structured backend code.

Use ordinary ADK `McpToolset` with `lease.mcp_url`; lifecycle methods are not model
tools. For manual acquire, the application closes MCP before leaving the context.
For Agent(sandbox=manager), the Agent owns per-invocation MCP connections while
the application reuses its Agent, Runner and ADK SessionService. Runner.close does not pause/delete.

## State, failures and isolation

The local record is version 1 and contains ToolId, unique UserSessionId, physical
SessionId, phase and last-used time. No endpoint credentials or user messages are
stored there. Atomic JSON writes use 0600; locks serialize processes on one local
POSIX filesystem. Use a trusted private state directory. No Windows or multi-host
locking guarantee is made; imports remain available on unsupported platforms.

Phases: creating → ready → pausing → paused → resuming → ready; deleting → deleted
blocks acquisition. A complete deletion requires a new logical session key to
start new work. No automatic replacement on expiry, NotFound, network or auth errors.
Create intent precedes submission. On lost response/restart, paginate matching
UserSessionIds; exactly one physical match is required. An ambiguous/missing result
remains unconfirmed. Do not delete a pending record to retry creation.

Create/resume/pause wait for GetSession target state; request acceptance is not
completion. Signed endpoint path changes preserve route/auth queries. Poll and lock
waits are bounded by ready_timeout; an in-flight synchronous SDK request uses its
own transport timeout and can outlive the polling deadline. Cancellation waits
for that worker before releasing the lock. It does not cancel remote tool execution.
Generic failures never count as successful deletion. Deleted/uncertain states survive restart.

Limits: foreground synchronous tasks; no background-task detection, idle scheduler,
automatic TTL renewal or distributed lease. A caller must verify detached work is
idle before pause/delete. Cloud TTL remains authoritative. Backend pause support
and filesystem/process retention require provider-specific live validation.

## Compatibility and verification

Additive API; Runner defaults and remote-Agent paths are preserved. The stream
interceptor now explicitly closes its underlying generator when closed early. No new
dependencies. Framework credentials and local state do not enter model context.
`tests/sandbox/test_manager.py` covers lifecycle and failures;
`tests/sandbox/test_mcp_integration.py` covers real local MCP with an offline model
and persistent chat; `tests/sandbox/test_agent_binding.py` covers shared-Agent
concurrency with ordinary ADK and VeADK runners, error/cancellation cleanup,
clone behavior and configuration. Same-key sandbox lock tests remain in test_manager.py. `examples/sandbox_mcp/` is the user-facing entrypoint.
Verification outcomes and conditional cloud checks belong to the linked PRD.


## CON-8: Agent-native execution (active)

`Agent(sandbox=manager, tools=[], ...)` opts into managed MCP tools. The manager
must be a SandboxManager instance; Agent keeps a live Python reference excluded
from repr/model_dump, rather than serializable remote configuration. Support is
limited to a standalone VeADK Agent with ADK runtime, no parent/sub-agents, empty
tools and no code executor. Validate at construction and execution, including
clones and reconfiguration. run_live is explicitly unsupported.

Agent._run_async_impl acquires by trusted session identity and owns a standard
McpToolset inside its model/tool loop. A ContextVar holds the binding for that
execution; canonical_before_model_callbacks prepends tool injection without
changing user callback fields or shared Agent.tools. Injection validates the
session, invocation and agent identity and registers the current request's tool
declarations and execution map. Closed bindings cannot be reused by inherited
background contexts. Cleanup closes MCP and restores context before releasing
the sandbox lock on completion, error, cancellation or explicit stream aclose.
The Agent scope does not include before/after-agent callbacks or Runner history
writes/compaction. A before-agent short circuit does not allocate a sandbox.

Both ordinary google.adk Runner and VeADK Runner work without sandbox arguments,
plugin registration or custom Toolsets. The unpublished Runner(sandbox=...) API
is replaced, not retained as an alias. Application code creates Agent/Runner once.
Independent sessions may execute concurrently; within one chat submit turns
sequentially because the sandbox lock cannot serialize earlier Runner writes.
No automatic pause/delete on Agent/Runner completion. Close a partially consumed
stream explicitly, and close the Runner only after active runs finish. Studio
UI/configuration round-trip support for the live manager object is not provided.
