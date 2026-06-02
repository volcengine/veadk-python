# tunnel · 把企业内网 MCP server 接入云端 Agent

企业在内网跑着自己的 MCP server，本示例通过一条**出站**隧道把它们接到云端的
VeADK agent —— agent 能调用你内网的工具，而你**无需开放任何入站端口**。

> English version: [README.md](./README.md)

## 工作原理

```text
        企业内网                            │            云端 (ADK server)
  MCP server(s)  ◀── connector ──出站WSS──▶  /tunnel/connect ─ registry
                      (按名字注册到 agent)   │   ops_agent + TunnelToolset
                                            │     (每轮对话动态挂载工具)
```

- agent 用 `Agent(enable_tunnel=True)` 开启 → 自动获得一个 `TunnelToolset`。
- 云端 app 挂载隧道路由：`mount_tunnel_if_enabled(app, agents=[root_agent], token=...)`。
- **连接器（connector）** 跑在你的内网，**出站**连到云端，把内网 MCP server
  **按 agent 名字**（`ops_agent`）注册上去。若目标 agent 没开 `enable_tunnel`，注册被拒。
- 下一轮对话时，`TunnelToolset.get_tools()` 读取 registry，server 的工具就出现了 —— 无需重新部署。

## 鉴权（两层）

- **隧道层** —— 连接器必须带上 `TUNNEL_TOKEN`（header `Authorization: Bearer`
  或 `?token=`）才能注册到 agent。
- **单 server 层** —— 每个 `LocalServer` 可带 `headers=` / `query=`，用于鉴权访问*你自己的* MCP server。
  这些只留在连接器（企业侧），密钥不出内网。

## 本地试跑（4 个终端）

```bash
pip install veadk-python fastmcp
cp .env.example .env          # 设置 TUNNEL_TOKEN（要聊天再设 MODEL_AGENT_API_KEY）

# 1) 你的内网 MCP server（这里用 demo 顶替）
python local_mcp_server.py

# 2) 云端 agent 服务 + 隧道
TUNNEL_TOKEN=... python app.py        # http://127.0.0.1:8000

# 3) 连接器（真实场景跑在你内网）
CLOUD_URL=http://127.0.0.1:8000 TUNNEL_TOKEN=... python connector.py

# 4) 确认工具已经接进来
curl "http://127.0.0.1:8000/tunnel/servers?agent=ops_agent"
```

随后与 `ops_agent` 对话（例如 `veadk frontend --agents-dir agents` 或走 ADK API），
它就能调用跑在你本机的 `get_employee` / `add_numbers`。

## 把云端部署到 AgentKit

`app.py` 就是个普通 ADK server，可以像 `examples/basic-app` 那样部署
（`veadk agentkit launch`）。⚠️ 隧道依赖经过网关的 **WebSocket** —— 需确认网关透传 WS upgrade。
另外 registry 是**进程内**的：在引入共享 registry 之前，请用单副本（或 sticky 路由）。

## 文件

- `agents/ops_agent/` —— 云端 agent（`enable_tunnel=True`）。
- `app.py` —— ADK server + `mount_tunnel_if_enabled`。
- `connector.py` —— 企业侧连接器。
- `local_mcp_server.py` —— 顶替真实内网 MCP 的 demo server。
