# Remote Sandbox Agent

- `multi_agents/agent.py`：coordinator 将任务转交给远端 sandbox 子 agent。
- `single_agent/agent.py`：直接使用远端 sandbox 作为 root agent。
- `single_agent/server.py`：通过 `AgentkitAgentServerApp` 提供 HTTP/SSE 服务。
- `single_agent/client.py`：创建会话、发送任务并展示流式结果，不需要导入 agent 或配置云端凭证。

## 配置

使用安装了当前仓库版本 VeADK 的 Python 环境。在 `examples/17_remote_sandbox_agent/.env` 中配置。两个 server 都会在导入 agent 前加载此文件，不依赖启动目录；已导出的环境变量优先：

```dotenv
AGENTKIT_TOOL_ID=你的ToolId
# 可选，不填写时通过 GetTool 自动发现；显式值必须为 Skill 或 CodeEnv。
AGENTKIT_TOOL_TYPE=CodeEnv
AGENTKIT_TOOL_REGION=cn-beijing
VOLCENGINE_ACCESS_KEY=你的AccessKey
VOLCENGINE_SECRET_KEY=你的SecretKey
```

PPE / STG 可额外配置实际控制面地址和签名 service：

```dotenv
AGENTKIT_TOOL_SERVICE_CODE=agentkit_ppe
AGENTKIT_TOOL_HOST=实际控制面域名
AGENTKIT_TOOL_SCHEME=https
```

STG 使用 `agentkit_stg` 及对应域名、ToolId。修改 `.env` 后重启 server。
CodeEnv 需要支持 Codex Worker 协议 v1 和 `tool_events` 的沙箱镜像；Skill 需要提供 A2A 服务。
单 agent 示例没有本地 coordinator 模型；远端沙箱所需的模型和技能配置由对应 Tool/镜像提供。

## 启动单 agent 服务

以下命令均从仓库根目录执行：

```bash
python examples/17_remote_sandbox_agent/single_agent/server.py
```

默认监听 `127.0.0.1:8000`，可使用 `--host` 和 `--port` 调整。

另一个终端发送任务：

```bash
python examples/17_remote_sandbox_agent/single_agent/client.py \
  "用 Python 计算 2 + 3，并展示执行结果"
```

client 会打印 `session_id`，然后展示 `[tool]`、`[tool result]`、`[progress]`、`[delta]` 和 `[answer]`。
继续同一会话：

```bash
python examples/17_remote_sandbox_agent/single_agent/client.py \
  --session-id 上一次打印的session_id \
  "把刚才的结果乘以 10"
```

可使用 `--url http://127.0.0.1:8000` 指定服务地址，`--user-id` 指定用户。
复用会话时保持 user ID 一致；传入不存在的 session ID 会报错，不会自动创建替代会话。
server 默认使用内存会话，重启后需创建新会话。client 不会自动重发执行任务。

## 启动多 agent 服务

`multi_agents` 同样提供独立的 `agent.py`、`server.py` 和 `client.py`。
沿用上面的沙箱配置，并为 coordinator 配置模型，例如在 `.env` 中设置 `MODEL_AGENT_API_KEY` 和 `MODEL_AGENT_NAME`。

```bash
python examples/17_remote_sandbox_agent/multi_agents/server.py --port 8001
```

另一个终端调用：

```bash
python examples/17_remote_sandbox_agent/multi_agents/client.py \
  --url http://127.0.0.1:8001 \
  "用 Python 计算 2 + 3，并展示执行结果"
```

client 会额外打印事件所属的 agent，方便观察 coordinator 向 sandbox 的转交。
同样支持 `--session-id` 继续对话；请使用同一个服务和 user ID。
单 agent 和多 agent 服务默认端口都是 8000，同时运行时需要为其中一个指定不同端口。

## VeADK Web

也可以从仓库根目录运行：

```bash
veadk web examples/17_remote_sandbox_agent
```

选择 `single_agent` 或 `multi_agents`。多 agent 示例还需要 coordinator 模型凭证。
