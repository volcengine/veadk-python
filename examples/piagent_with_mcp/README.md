# piagent_with_mcp

A minimal `runtime="piagent"` example that exposes several local stdio MCP
servers to PiAgent through VeADK's normal ADK toolset path.

The runtime does not pass MCP configuration directly to PiAgent. Instead:

```text
MCPToolset
  -> ADK get_tools()
  -> BaseTool[]
  -> Pi custom tools
  -> local bridge
  -> BaseTool.run_async()
  -> MCP server
```

## Layout

```text
piagent_with_mcp/
├── agent.py                         # local frontend / script root_agent
├── main.py                          # local CLI runner
├── mcp_server.py                    # weather stdio MCP server
├── mcp_air_server.py                # air-quality stdio MCP server
├── mcp_order_server.py              # order-status stdio MCP server
├── app.py                           # deployable FastAPI app on :8000
├── Dockerfile                       # AgentKit cloud build image
├── requirements.txt
├── piagent-mcp-agentkit.yaml        # veadk agentkit launch config
├── vendor/
│   └── pi-linux-x64.tar.gz          # Pi Linux binary archive for cloud image
└── agents/
    └── piagent_mcp_agent/
        ├── __init__.py
        └── agent.py                 # AgentKit / ADK app-loader wrapper
```

## Run Locally

Set a Pi binary and model credentials first:

```bash
export PIAGENT_BINARY=/path/to/pi
export PIAGENT_AGENT_DIR=/tmp/veadk-piagent-mcp-home
export MODEL_AGENT_API_KEY=...
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=deepseek-v4-flash-260425
```

Then run from the command line:

```bash
python examples/piagent_with_mcp/main.py
```

Or run it in the VeADK frontend from the repository root:

```bash
veadk frontend --agents-dir examples
```

Select `piagent_with_mcp` in the app dropdown and ask:

```text
Please check Beijing weather, Beijing air quality, and order A10086 status. You must call the relevant tools before answering.
```

You can also test each MCP independently:

```text
北京天气怎么样？你必须调用 get_weather。
北京空气质量怎么样？你必须调用 get_air_quality。
请查询订单 A10086 的状态。你必须调用 get_order_status。
```

Do not set `--agents-dir examples/piagent_with_mcp`; the frontend expects the
parent directory that contains agent app folders.

## Deploy To AgentKit

This example is structured like `examples/piagent_runtime_basic`: AgentKit runs
`app.py`, which serves the ADK API from the `agents/` directory.

The Dockerfile expects a Linux Pi binary archive at:

```text
vendor/pi-linux-x64.tar.gz
```

For local pre-release testing, this can be copied from the basic PiAgent
example if both examples use the same Pi version:

```bash
mkdir -p examples/piagent_with_mcp/vendor
cp examples/piagent_runtime_basic/vendor/pi-linux-x64.tar.gz \
  examples/piagent_with_mcp/vendor/pi-linux-x64.tar.gz
```

Then launch from this example directory:

```bash
cd examples/piagent_with_mcp
veadk agentkit launch --config-file piagent-mcp-agentkit.yaml --platform linux/amd64
veadk agentkit status --config-file piagent-mcp-agentkit.yaml
```

Invoke after the runtime is ready:

```bash
veadk agentkit invoke --config-file piagent-mcp-agentkit.yaml \
  -m "Please check Beijing weather, Beijing air quality, and order A10086 status. You must call the relevant tools before answering."
```

Expected runtime logs should include lines similar to:

```text
piagent: bridging 3 agent tool(s): ['get_weather', 'get_air_quality', 'get_order_status']
piagent: generated tool extension for ['get_weather', 'get_air_quality', 'get_order_status']
```
