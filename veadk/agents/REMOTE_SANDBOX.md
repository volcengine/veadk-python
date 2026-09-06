# AgentKit remote sandbox agent

```python
from veadk import Agent, AgentkitRemoteSandboxAgent

root_agent = Agent(
    name="coordinator",
    instruction="Transfer sandbox execution tasks to sandbox.",
    sub_agents=[AgentkitRemoteSandboxAgent(
        name="sandbox",
        description="Execute tasks in the remote sandbox and report results.",
        tool_id="your-tool-id",
        # tool_type="CodeEnv",  # optional: CodeEnv or Skill
        request_timeout=900,
        expiry_buffer=90,
    )],
)
```

The entry is a BaseAgent, not an AgentTool. Native transfer hands the invocation
to the child. The child yields ADK events directly; the coordinator does not
summarize its tool trace. It works with the standard Runner and `veadk web`.

Explicit `tool_type` wins and skips GetTool discovery. Otherwise GetTool must
return Skill or CodeEnv; Private/All-in-one/VibeSkill/unknown values fail with a
message to specify the compatible protocol explicitly. Construction/import does
not perform network requests. Omitted tool_id uses AGENTKIT_TOOL_ID. Existing
AgentKit region and credential resolution applies. GetTool permission is needed
only for discovery; Session permissions are always needed for managed sessions.

Skill uses A2A streaming when advertised, or polls non-streaming tasks. The
adapter preserves structured ADK/A2A tool parts and partial artifact updates.
It cannot reconstruct tool traces a remote service never emits. CodeEnv uses
Sidecar HTTP/SSE protocol v1 with a tool_events capability, available in the
actb-mono code-env 1.1.2.3 image. No A2A wrapper is required for CodeEnv.

Calls/results retain child author and matching IDs. Tool stdout progress is
shown as thought/progress text, separate from the final response. Errors are
explicit. Only text task input is currently supported. The new invocation sends
the latest user text; it does not forward the entire parent system prompt or
parent reasoning history. Follow-up context lives in the remote thread/context.

An optional pre-provisioned `endpoint` requires explicit tool_type and bypasses
GetTool/CreateSession; this is useful for local fixtures. It has no platform TTL
management. `api_key` supplies the optional X-API-Key header. Runtime inbound_auth
credentials are resolved per invocation; clients are not shared between users.

Session binding includes application, user, conversation and agent identity.
Physical Session rotation discards the old A2A context. Logical IDs are hashed;
creation responses lost on the network are recovered by querying the platform.
Before submission, remaining lifetime is checked again after data-plane readiness.
request_timeout bounds execution, ready_timeout bounds readiness, expiry_buffer
reserves remaining platform lifetime. A running task is never resubmitted merely
because its stream disconnected. Cancellation of the owning invocation attempts
remote cancellation; acknowledgement is not proof all external effects stopped.
A browser disconnect and explicit Runner cancellation are different operations;
the hosting application owns their relationship.

Skill context is instance-local (up to 256 conversations and 64 invocations per
physical binding); no cross-process recovery is claimed. Code Sidecar stores
turns/events in SQLite and refuses uncertain reruns after restart. Neither
transport migrates filesystem state to a new physical sandbox. For mutually
untrusted users allocate separate physical sandboxes; threads are not filesystem
security boundaries. Shared explicit endpoints are intended for trusted callers.

Validated with ADK 2.2.0 using deterministic models and HTTP fixtures. Native
/run_sse plus a real Code image verifies pre-completion deltas, structured tools
and a single final without parent summarization. SDK tests cover A2A streaming
and polling, two-turn context reuse, type precedence, cancellation, error results,
Session pagination/rotation and ambiguous create recovery. Cloud/provider
acceptance requires separately configured Tools and model credentials.
