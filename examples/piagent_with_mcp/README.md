# piagent_with_mcp

A minimal `runtime="piagent"` example that exposes several local stdio MCP
servers and one ADK skill to PiAgent through VeADK's normal runtime paths.

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

The skill is loaded through `SkillToolset(load_skill_from_dir(...))`. The
PiAgent runtime materializes it into a temporary directory and starts Pi with
`--no-skills --skill <path>`.

## Layout

```text
piagent_with_mcp/
├── agent.py                         # local frontend / script root_agent
├── main.py                          # local CLI runner
├── mcp_server.py                    # weather stdio MCP server
├── mcp_air_server.py                # air-quality stdio MCP server
├── mcp_order_server.py              # order-status stdio MCP server
├── skills/
│   └── piagent-e2e-style/
│       └── SKILL.md                 # skill marker for E2E verification
├── app.py                           # deployable FastAPI app on :8000
├── Dockerfile                       # AgentKit cloud build image
├── requirements.txt
├── piagent-mcp-agentkit.yaml        # veadk agentkit launch config
├── vendor/
│   ├── pi-linux-x64.tar.gz          # Pi Linux binary archive for cloud image
│   └── veadk_python-*.whl           # local VeADK build installed by Dockerfile
└── agents/
    └── piagent_mcp_agent/
        ├── __init__.py
        └── agent.py                 # AgentKit / ADK app-loader wrapper
```

## Run Locally

Set model credentials first. If you already have a Pi binary, point
`PIAGENT_BINARY` at the executable inside a fully extracted Pi release
directory; otherwise the runtime uses `PIAGENT_INSTALL_DIR/pi/pi` (default
`~/.cache/veadk/piagent/pi/pi`) and downloads Pi there when it is missing.

```bash
# Optional: export PIAGENT_BINARY=/path/to/pi
export PIAGENT_AGENT_DIR=/tmp/veadk-piagent-mcp-home
export MODEL_AGENT_API_KEY=...
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=deepseek-v4-flash-260425
```

Then run from the command line:

```bash
uv run python examples/piagent_with_mcp/main.py
```

Or run it in the VeADK frontend from the repository root:

```bash
veadk frontend --agents-dir examples
```

Select `piagent_with_mcp` in the app dropdown and ask:

```text
Please check Beijing weather, Beijing air quality, and order A10086 status. You must call the relevant tools before answering. Also use the PiAgent E2E skill and include the skill marker.
```

You can also test each MCP independently:

```text
北京天气怎么样？你必须调用 get_weather。
北京空气质量怎么样？你必须调用 get_air_quality。
请查询订单 A10086 的状态。你必须调用 get_order_status。
请使用 PiAgent E2E skill，并输出 skill marker。
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

It also expects exactly one local VeADK wheel at:

```text
vendor/veadk_python-*.whl
```

Build the wheel from the repository root and copy it into this example before
launching:

```bash
rm -rf dist
uv build
rm -f examples/piagent_with_mcp/vendor/veadk_python-*.whl
cp dist/veadk_python-*.whl examples/piagent_with_mcp/vendor/
```

The AgentKit image installs this vendored wheel directly, so the cloud runtime
uses the same local VeADK code that produced the wheel. Re-run `uv build` and
copy the wheel again whenever the PiAgent runtime code changes.

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
  -m "Please check Beijing weather, Beijing air quality, and order A10086 status. You must call the relevant tools before answering. Also use the PiAgent E2E skill and include the skill marker."
```

Expected runtime logs should include lines similar to:

```text
piagent MCP AgentKit startup: veadk_version=... veadk_path=/usr/local/lib/python3.12/site-packages/veadk/__init__.py
piagent: bridging 3 agent tool(s): ['get_weather', 'get_air_quality', 'get_order_status']
piagent: generated tool extension for ['get_weather', 'get_air_quality', 'get_order_status']
piagent: materialized 1 skill(s) into ...
piagent runtime: starting pi rpc provider=... model=... skills=1
```

The response should include:

```text
PI_SKILL_E2E_MARKER
```
