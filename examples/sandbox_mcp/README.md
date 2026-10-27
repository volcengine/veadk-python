# One Agent, one sandbox per session

[中文](README.zh.md)

Create Agent and Runner once. The example uses an unmodified
`google.adk.runners.Runner`; `veadk.Runner` also works. `Agent(sandbox=manager)` binds each
`(app_name, user_id, session_id)` to its own AgentKit sandbox on first execution.
Later turns reuse that sandbox; pause/resume preserves the binding. Every turn
uses an ordinary ADK `McpToolset` with the current endpoint. No specialized
SandboxMcpToolset is required, and shared `agent.tools` is never modified.

## Run

From this `veadk-python` checkout on Linux/macOS:

```bash
cp examples/sandbox_mcp/.env.example examples/sandbox_mcp/.env
# Fill in ToolId, control-plane credentials and model configuration locally.
uv run python examples/sandbox_mcp/main.py --session-id demo --list-tools
uv run python examples/sandbox_mcp/main.py --session-id demo "Run Python print(1 + 1)." --follow-up "Run Python print(2 + 2)."
uv run python examples/sandbox_mcp/main.py --session-id demo --action status
uv run python examples/sandbox_mcp/main.py --session-id demo --action pause
uv run python examples/sandbox_mcp/main.py --session-id demo --action resume
uv run python examples/sandbox_mcp/main.py --session-id demo --action delete
```

`--follow-up` is repeatable: these messages reuse the exact same Agent/Runner in
one process. Re-running the CLI reopens persisted chat/sandbox bindings.
`SANDBOX_TOOL_ID` falls back to `AGENTKIT_TOOL_ID`; `MODEL_AGENT_API_KEY` falls
back to `ARK_API_KEY`. Other model settings follow VeADK configuration.
`ensure` and `--list-tools` create/resume without invoking a model. Use an existing
MCP-capable Tool; cloud pause/resume requires backend snapshot support.

## Embed in an application

```python
import asyncio
from contextlib import aclosing
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types
from veadk import Agent
from veadk.sandbox import SandboxManager, SessionKey


async def main():
    manager = SandboxManager(tool_id="your-tool-id", state_dir=".state/bindings")
    agent = Agent(name="assistant", tools=[], sandbox=manager)
    async with DatabaseSessionService(
        db_url="sqlite+aiosqlite:///.state/chat.db"
    ) as service:
        runner = Runner(
            agent=agent,
            app_name="my_app",
            session_service=service,
            auto_create_session=True,
        )

        async def send(session_id, message):
            async with aclosing(
                runner.run_async(
                    user_id="u1",
                    session_id=session_id,
                    new_message=types.Content(
                        role="user", parts=[types.Part(text=message)]
                    ),
                )
            ) as events:
                async for event in events:
                    if event.is_final_response():
                        print(event.content)

        try:
            await asyncio.gather(
                send("s1", "Run Python print(1 + 1)."),
                send("s2", "Run Python print(2 + 2)."),
            )
            await send("s1", "Continue our task.")
            await manager.pause(SessionKey("my_app", "u1", "s1"))
        finally:
            await runner.close()  # Application shutdown, after active runs finish.


asyncio.run(main())
```

The Agent holds a sandbox lock through its model/tool loop and MCP cleanup.
Different sessions can run concurrently. Submit messages sequentially within one
chat: this Agent-level lock cannot serialize the Runner's earlier history writes
or later compaction. MCP tools are registered in each LlmRequest, including its
execution dispatch map. Existing Agent callback fields remain unchanged; callbacks
that short-circuit before Agent execution do not allocate a sandbox. Lifecycle
functions stay outside model context. Close a partially consumed run_async stream
with aclose or contextlib.aclosing, so Agent cleanup can run.

`.state/bindings/` holds physical SessionIds; `.state/chats.db` holds chat history.
Use `--state-dir` to choose a private local directory, separate for each cloud
account/control plane. Use authenticated user/session identity, not model input.
Signed endpoints stay transient; do not log them. Deleting a managed Session
permanently removes its sandbox data; the local history and deleted binding
remain. Use a new session ID after deletion. Runner.close does not pause/delete.

## First-version scope and verification

The Agent integration supports one standalone VeADK Agent using the ADK runtime
with empty tools, no parent/sub-agents and no code executor. Mixed local tools, other runtimes and run_live are rejected.
The lower-level `SandboxManager.acquire` API is still available for custom callers.
The POSIX lock coordinates one local filesystem, not multiple hosts. There is no
automatic idle pause, TTL renewal, background-job detection or replacement of
missing/expired sandboxes. Check detached work before pausing/deleting. Unknown
creation outcomes are recovered through the saved UserSessionId; do not remove
pending records to force another create. SDK transport timeouts remain separate
from polling deadlines; local cancellation does not cancel remote jobs.

```bash
uv run --extra dev pytest tests/sandbox tests/runner -q
```

Local tests use real MCP HTTP and VeADK/SQLite with an offline model and fake
control plane. See the [contract](../../specs/sandbox-lifecycle/README.md) and
[verification record](../../prd-spec/features/sandbox-lifecycle/2026-10-23-agent-owned-mcp-sandbox.md)
for current cloud results and the unverified cloud pause/resume boundary. The
manager is a live Python object excluded from Agent serialization; configuring it
through Studio UI or generated configuration is outside this example.
