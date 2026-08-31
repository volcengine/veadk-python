# 16. 自建沙箱 Agent 示例 (Self-Hosted Sandbox)

本示例由 `veadk web` 处理用户消息和模型循环。每个新建的 VeADK Web Session 只创建一个远端 Managed Session；仅将 VeADK 模型产生的 `agent.tool_use` 发送给 Self-Hosted Runtime dispatcher，再由它为配置的 TAE Sandbox 创建 Tool Session。

---

## 🎯 架构拓扑

```text
       【用户指令】: "在沙箱中写个快速排序并运行测试"
              │
              ▼
   ┌───────────────────────┐
   │      VeADK Web        │
   │   模型与 Agent 循环     │
   └──────────┬────────────┘
              │ POST agent.tool_use
              ▼
   ┌───────────────────────────┐
   │ Runtime 7hw8g3yr          │
   │ 仅负责 dispatcher          │
   └──────────┬────────────────┘
              │ 为每个 Session 创建 Tool Session
              ▼
   ┌────────────────────────────────────────┐
   │ TAE Sandbox Tool m3m24zxs              │
   │ 执行 Runtime 产生的工具调用              │
   └────────────────────────────────────────┘
```

---

## 🚀 运行方法
 
### 1. 配置环境变量

复制环境配置文件示例并填入对应的配置与密钥：

```bash
cp examples/16_self_host_sandbox/.env.example examples/16_self_host_sandbox/.env
```

或直接在终端中导出环境变量：

```bash
export ANTHROPIC_BASE_URL="https://<runtime-gateway>"
export ANTHROPIC_ENVIRONMENT_ID="env_01SLqXHseguCmohifEqeUAYu"
export ANTHROPIC_ENVIRONMENT_KEY="your-runtime-token"
export SANDBOX_AGENT_ID="agent_your_managed_agent_id"
export X_TOP_ACCOUNT_ID="your-account-id"
```

本地 VeADK 进程需要正常的模型配置。模型推理由 VeADK 完成，只有 Tool 执行委托给远端 Runtime 与 Sandbox。


### 2. 启动示例

#### 方式一：Web 界面交互模式（`veadk web`）

在浏览器中启动可视化 Web 调试交互界面（默认端口为 **8067**，支持在 `.env` 中通过 `PORT` 或 `--port` 自定义）：

```bash
# 方式 A：通过 run.sh 快捷启动（自动切换到 agents 目录并使用 8067 端口）
bash examples/16_self_host_sandbox/run.sh --web

# 方式 B：进入 agents 目录直接运行
cd examples/16_self_host_sandbox/agents
veadk web --port 8067
```




#### 方式二：CLI 命令行模式

```bash
# 使用 run.sh 运行
bash examples/16_self_host_sandbox/run.sh

# 或使用 uv
uv run --extra sandbox python examples/16_self_host_sandbox/main.py

# 或指定一个本地到远端的 Session 映射 ID
python examples/16_self_host_sandbox/main.py \
  --session-id "my-local-session" \
  --prompt "请在 /workspace 下创建一个 quick_sort.py 并运行验证"
```


每个新建的 VeADK Session 都通过 `POST /v1/sessions` 创建一个远端 Managed
Session。用户消息和模型循环留在 VeADK；`DispatchRuntimeProvider` 拦截模型生成的
Tool call，以 `agent.tool_use` 发送给 Runtime，等待匹配的 Tool result 后交还给本地
VeADK 模型继续生成最终回复。

## Docker 与 Kubernetes 部署

Docker 构建上下文必须使用仓库根目录：

```bash
docker build \
  -f examples/16_self_host_sandbox/Dockerfile \
  -t <registry>/veadk-self-host-sandbox:<tag> \
  .
docker push <registry>/veadk-self-host-sandbox:<tag>
```

将 `k8s.yaml` 中的镜像和 Ingress 域名替换成目标环境的值。然后从本地 `.env`
显式创建白名单 Secret，再部署工作负载：

```bash
set -a
source examples/16_self_host_sandbox/.env
set +a

kubectl create secret generic veadk-self-host-sandbox-env \
  --from-literal=ANTHROPIC_BASE_URL="$ANTHROPIC_BASE_URL" \
  --from-literal=ANTHROPIC_ENVIRONMENT_ID="$ANTHROPIC_ENVIRONMENT_ID" \
  --from-literal=ANTHROPIC_ENVIRONMENT_KEY="$ANTHROPIC_ENVIRONMENT_KEY" \
  --from-literal=SANDBOX_AGENT_ID="$SANDBOX_AGENT_ID" \
  --from-literal=X_TOP_ACCOUNT_ID="$X_TOP_ACCOUNT_ID" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f examples/16_self_host_sandbox/k8s.yaml
kubectl rollout status deployment/veadk-self-host-sandbox
```

不要使用整个 `.env` 创建 Secret；Deployment 只注入上述白名单内的 Runtime 连接配置。

## 开发验证

如果仓库虚拟环境仅安装了运行时依赖，其中可能没有 `pytest`。请先同步开发依赖组，
再运行 Tool dispatch 的定向测试：

```bash
uv sync --group dev --extra sandbox
uv run pytest -q tests/runtime/test_self_host_sandbox_client.py \
  tests/runtime/test_self_host_sandbox_agent.py
```
