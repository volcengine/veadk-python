# Remote Sandbox Agent

- `multi_agents/agent.py`: a coordinator transfers tasks to a remote sandbox child.
- `single_agent/agent.py`: the remote sandbox itself is the root agent.
- `single_agent/server.py`: serves it with `AgentkitAgentServerApp` over HTTP/SSE.
- `single_agent/client.py`: creates a session, submits text, and displays streamed events. The client needs no cloud credentials or agent import.

## Configuration

Use a Python environment with VeADK installed from this checkout. Add these settings to `examples/17_remote_sandbox_agent/.env`. Both servers load this file before importing the agent, regardless of the working directory; exported environment variables take precedence:

```dotenv
AGENTKIT_TOOL_ID=your-tool-id
# Optional: Skill or CodeEnv. Omit to discover the type via GetTool.
AGENTKIT_TOOL_TYPE=CodeEnv
AGENTKIT_TOOL_REGION=cn-beijing
VOLCENGINE_ACCESS_KEY=your-access-key
VOLCENGINE_SECRET_KEY=your-secret-key
```

For PPE/STG, configure the actual control-plane host and signing service:

```dotenv
AGENTKIT_TOOL_SERVICE_CODE=agentkit_ppe
AGENTKIT_TOOL_HOST=actual-control-plane-host
AGENTKIT_TOOL_SCHEME=https
```

For STG use `agentkit_stg`, its host, and a ToolId from that environment. Restart the server after changing `.env`.
CodeEnv requires an image supporting Codex Worker protocol v1 and `tool_events`; Skill requires an A2A service.
The single-agent example has no local coordinator model. Configure remote models and skills through the Tool/image.

## Run the server and client

Run from the repository root:

```bash
python examples/17_remote_sandbox_agent/single_agent/server.py
```

The default address is `127.0.0.1:8000`; override with `--host` and `--port`.
In another terminal:

```bash
python examples/17_remote_sandbox_agent/single_agent/client.py \
  "Use Python to compute 2 + 3 and show the result"
```

The client prints the session ID, tool calls/results, progress, text deltas, and the final answer.
Continue with the printed session ID:

```bash
python examples/17_remote_sandbox_agent/single_agent/client.py \
  --session-id previous-session-id "Multiply that result by 10"
```

Use `--url` to change the server address and `--user-id` to change the user.
Keep the same user ID when resuming. An unknown session ID produces an error; the client does not create a replacement or automatically resubmit tasks.
The server uses in-memory sessions by default, so create a new session after restarting it.

## Run the multi-agent server

`multi_agents` also provides separate `agent.py`, `server.py`, and `client.py` files.
Use the same sandbox settings and configure the coordinator model, for example with `MODEL_AGENT_API_KEY` and `MODEL_AGENT_NAME` in `.env`.

```bash
python examples/17_remote_sandbox_agent/multi_agents/server.py --port 8001
```

In another terminal:

```bash
python examples/17_remote_sandbox_agent/multi_agents/client.py \
  --url http://127.0.0.1:8001 \
  "Use Python to compute 2 + 3 and show the result"
```

The client also labels each event with its agent author so you can observe the transfer from coordinator to sandbox.
Use `--session-id` to continue with the same server and user ID.
Both servers default to port 8000; select a different port for one when running them together.

## VeADK Web

From the repository root:

```bash
veadk web examples/17_remote_sandbox_agent
```

Select `single_agent` or `multi_agents`. The multi-agent example also needs coordinator model credentials.
