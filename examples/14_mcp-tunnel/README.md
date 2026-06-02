# tunnel · Connect on-prem MCP servers to a cloud agent

Your enterprise runs its own MCP server(s) on an internal network. This example
connects them to a cloud VeADK agent through an **outbound** tunnel — the agent
calls your on-prem tools without you opening any inbound port.

> 中文版见 [README.zh.md](./README.zh.md)

## How it works

```text
        enterprise network                  │            cloud (ADK server)
  MCP server(s)  ◀── connector ──outbound WSS──▶  /tunnel/connect ─ registry
                      (registers to agent)   │     ops_agent + TunnelToolset
                                             │       (mounts the tools per turn)
```

- The agent opts in with `Agent(enable_tunnel=True)` → it gets a `TunnelToolset`.
- The cloud app mounts the tunnel routes via
  `mount_tunnel_if_enabled(app, agents=[root_agent], token=...)`.
- A **connector** runs inside your network, connects out to the cloud, and
  **registers** your MCP server(s) to the agent **by name** (`ops_agent`). If the
  target agent doesn't have `enable_tunnel`, registration is rejected.
- On the next turn, `TunnelToolset.get_tools()` reads the registry and the
  server's tools appear — no redeploy.

## Auth (two layers)

- **Tunnel layer** — the connector must present `TUNNEL_TOKEN` (header
  `Authorization: Bearer` or `?token=`) to register to the agent.
- **Per-server layer** — each `LocalServer` can carry `headers=` / `query=` to
  authenticate to *your* MCP server. These stay in the connector (enterprise side);
  secrets never leave your network.

## Try it locally (4 terminals)

```bash
pip install veadk-python fastmcp
cp .env.example .env          # set TUNNEL_TOKEN (and MODEL_AGENT_API_KEY to chat)

# 1) your on-prem MCP server (stand-in)
python local_mcp_server.py

# 2) the cloud agent server + tunnel
TUNNEL_TOKEN=... python app.py        # http://127.0.0.1:8000

# 3) the connector (would run inside your network)
CLOUD_URL=http://127.0.0.1:8000 TUNNEL_TOKEN=... python connector.py

# 4) check the tool is now tunneled in
curl "http://127.0.0.1:8000/tunnel/servers?agent=ops_agent"
```

Then chat with `ops_agent` (e.g. via `veadk frontend --agents-dir agents` or the
ADK API) and it can call `get_employee` / `add_numbers` running on your machine.

## Deploying the cloud side to AgentKit

`app.py` is a normal ADK server, so it deploys like `examples/basic-app`
(`veadk agentkit launch`). ⚠️ The tunnel needs a **WebSocket** through the
gateway — verify your gateway passes WS upgrade. Also note the registry is
in-process: use a single replica (or sticky routing) until a shared registry is
added.

## Files

- `agents/ops_agent/` — the cloud agent (`enable_tunnel=True`).
- `app.py` — ADK server + `mount_tunnel_if_enabled`.
- `connector.py` — enterprise-side connector.
- `local_mcp_server.py` — a demo MCP server to stand in for your real one.
