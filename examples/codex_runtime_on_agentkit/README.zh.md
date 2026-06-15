# codex_runtime_on_agentkit · 把 `runtime="codex"` 的 Agent 部署到 AgentKit

一个最小可部署应用：Agent 运行在 **OpenAI Codex 运行时**（`Agent(runtime="codex")`）
而非 ADK 内置 LLM 流程，通过 `veadk agentkit launch` 部署到
[火山引擎 AgentKit](https://www.volcengine.com/)。

> English version: [README.md](./README.md)

## 目录结构

```text
codex_runtime_on_agentkit/
├── app.py                       # 部署入口（ADK Agent API 服务）
├── agents/
│   └── codex_agent/             # Agent —— Agent(runtime="codex")
├── requirements.txt             # veadk-python>=0.5.39 + openai-codex
├── .env.example
└── .dockerignore
```

## codex 运行时在这里如何工作

- `agents/codex_agent` 是普通的 VeADK `Agent`，只是 `runtime="codex"`。`Runner`
  仍负责 session、记忆与 tracing；Codex 只驱动单轮（推理 + 工具调用）。
- Codex 只讲 OpenAI **Responses** API，所以 VeADK 起了一个进程内 shim，把你的
  `MODEL_AGENT_*` chat 端点（火山引擎 Ark）桥接过去。普通 Ark chat 模型无需改动即可用。
- **`openai-codex` 不是 veadk 的依赖**，所以在 `requirements.txt` 里显式列出。它会带上
  `openai-codex-cli-bin`——以 **manylinux wheel** 形式打包了 Codex 二进制，Linux
  构建里无需单独装二进制。它当前是 pre-release，连同其二进制依赖都**钉死到精确的
  预发布版本**，这样 `uv pip install` 无需全局 `--prerelease=allow` 也能装上。

> codex 运行时自 **0.5.39** 起已包含在 `veadk-python`（PyPI）中，所以镜像通过默认的
> `uv pip install -r requirements.txt` 全部从 PyPI 安装——无需构建脚本或 git clone。

## 1. 配置

```bash
cd examples/codex_runtime_on_agentkit
cp .env.example .env
# 编辑 .env：MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

## 2. 本地运行（可选）

```bash
pip install "veadk-python>=0.5.39" openai-codex
python app.py            # 或：python -m app
# 打开 http://127.0.0.1:8000；POST /run_sse，或 GET /ping -> {"status":"ok"}
```

`/list-apps` 返回 `["codex_agent"]`。首轮会因捆绑的 Codex 二进制启动而稍慢。

## 3. 部署到 AgentKit

`agentkit config` 写出 `agentkit.yaml`，`agentkit launch` 再据此构建并部署。模型
配置（`MODEL_AGENT_*`）从第 1 步的 `.env` 读取（它会被打包进镜像），所以**不必**
再写进 `--runtime_envs`。最小配置：

```bash
veadk agentkit config \
  --agent_name codex-runtime-demo --entry_point app.py \
  --language Python --language_version 3.12 \
  --launch_type cloud --region cn-beijing \
  --tos_bucket Auto \
  --runtime_name codex-runtime-demo --runtime_apikey_name Auto \
  --runtime_envs OTEL_SDK_DISABLED=true

veadk agentkit launch                       # 一步完成构建 + 部署
veadk agentkit status                       # 等到 Ready
veadk agentkit invoke "你好，你叫什么"      # 测试
```

**必填**（要设置）：

- `--agent_name`、`--entry_point app.py`、`--launch_type cloud`、`--region`。
- `--language` / `--language_version`。
- `--tos_bucket Auto` —— 不设 `Auto` 的话，上传会卡在 bucket 所有权
  （`ListBuckets`）校验，除非你的 AK/SK 有 `tos:ListBuckets` 权限。
- `--runtime_name` / `--runtime_apikey_name Auto`。

**可选**（不填由 AgentKit 自动处理）：

- `--runtime_role_name` —— 不填会自动选/建。
- `MODEL_AGENT_*` —— 从打包进镜像的 `.env` 读取，不必写进 `--runtime_envs`
  （`OTEL_SDK_DISABLED=true` 建议带上，避免 OTel 连接报错）。
- 鉴权方式 —— 默认 **API Key**；`custom_jwt` 还要额外配 JWT discovery URL 和
  client ID。

`veadk agentkit launch` = `build` + `deploy`。用 `veadk agentkit destroy` 拆除。

## 注意

- **模型**：`MODEL_AGENT_*` 的模型会被桥接给 Codex，不必是 OpenAI 模型——火山引擎
  Ark 的 chat 模型即可。
- **工具 / 沙箱**：Codex 在容器内用自己的沙箱执行工具（如 shell）。对需要文件系统/
  网络访问的重工具 Agent，运行时可能需要授予相应权限。
- **首请求延迟**：Codex app-server 二进制在首次使用时启动，首轮比后续慢。
- **构建耗时**：从 PyPI 安装 veadk + openai-codex 可能要几分钟；若 CLI 的构建等待超时，
  重跑 `veadk agentkit launch` 会复用已缓存的镜像层，很快完成。
