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
├── scripts/install_veadk.sh     # 安装 veadk（从 main）+ openai-codex
├── requirements.txt             # 空（依赖由构建脚本安装）
├── .env.example
└── .dockerignore
```

## codex 运行时在这里如何工作

- `agents/codex_agent` 是普通的 VeADK `Agent`，只是 `runtime="codex"`。`Runner`
  仍负责 session、记忆与 tracing；Codex 只驱动单轮（推理 + 工具调用）。
- Codex 只讲 OpenAI **Responses** API，所以 VeADK 起了一个进程内 shim，把你的
  `MODEL_AGENT_*` chat 端点（火山引擎 Ark）桥接过去。普通 Ark chat 模型无需改动即可用。
- **`openai-codex` 不是 veadk 的依赖**，所以构建时显式安装
  （`scripts/install_veadk.sh`）。它会带上 `openai-codex-cli-bin`——以
  **manylinux wheel** 形式打包了 Codex 二进制，Linux 构建里无需单独装二进制。

> codex 运行时的修复在 `main` 上，所以构建从 `main`（而非 PyPI）以浅克隆 + 稀疏
> 检出 `veadk/` 包的方式安装 veadk。

## 1. 配置

```bash
cd examples/codex_runtime_on_agentkit
cp .env.example .env
# 编辑 .env：MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

## 2. 本地运行（可选）

```bash
pip install "veadk-python" openai-codex
python app.py            # 或：python -m app
# 打开 http://127.0.0.1:8000；POST /run_sse，或 GET /ping -> {"status":"ok"}
```

`/list-apps` 返回 `["codex_agent"]`。首轮会因捆绑的 Codex 二进制启动而稍慢。

## 3. 部署到 AgentKit

```bash
# 交互式填写 agentkit.yaml 中与账号相关的字段
veadk agentkit config

# 一步完成镜像构建与部署
veadk agentkit launch

# 上线后查看状态 / 发测试请求
veadk agentkit status
veadk agentkit invoke "你好，你叫什么"
```

`veadk agentkit launch` = `build` + `deploy`。用 `veadk agentkit destroy` 拆除。
`scripts/install_veadk.sh` 通过 `agentkit.yaml` 的 `docker_build.build_script`
在镜像构建时执行。

## 注意

- **模型**：`MODEL_AGENT_*` 的模型会被桥接给 Codex，不必是 OpenAI 模型——火山引擎
  Ark 的 chat 模型即可。
- **工具 / 沙箱**：Codex 在容器内用自己的沙箱执行工具（如 shell）。对需要文件系统/
  网络访问的重工具 Agent，运行时可能需要授予相应权限。
- **首请求延迟**：Codex app-server 二进制在首次使用时启动，首轮比后续慢。
