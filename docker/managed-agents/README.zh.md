# Managed Agents Worker 构建

[English](README.md)

镜像运行安装后的 `veadk.runtime.managed_agents.worker` 包与 AgentKit 健康监听器。
dispatcher 和 Session 适配器包含在 VeADK 内，构建不依赖相邻仓库、私有 SDK wheel、
前端构建或线上部署。

## 本地构建与验证

在仓库根目录运行：

```bash
uv sync --extra dev --extra sandbox --extra extensions
uv run --extra dev --extra sandbox pytest tests/runtime/managed_agents tests/integrations/mpa
bash docker/managed-agents/build.sh veadk-managed-agents-worker:local
docker run --rm --entrypoint python veadk-managed-agents-worker:local \
  -m veadk.runtime.managed_agents.worker --help
```

构建脚本默认 `--load`。发布必须显式增加 `--push`，并由操作者选择镜像仓库/tag。
镜像构建不更新 AgentKit Runtime、Tool、Session 或 Kubernetes Deployment。
`MANAGED_AGENTS_PLATFORM` 可覆盖默认 `linux/amd64` 平台。

## 依赖与 SDK 注意事项

旧来源镜像复制相邻 SDK checkout 构建的
`examples/16_self_host_sandbox/.docker-dist/anthropic-*.whl`，并导入
`anthropic.lib.environments._dispatcher`。普通 Anthropic 1.3.0 安装包含 Managed
Sessions 与原生工具，但不包含该私有 dispatcher，导致包导入成功而 Worker 启动失败。
新 dispatcher 使用生成的 Work API 与既有账号级模型 Work 轮询协议；Docker 构建结束
前验证其导入与原生工具可用性。

镜像默认使用 `https://pypi.org/simple`。如果批准的镜像源没有 `uv.lock` 中全部版本，
通过 build args 使用完整镜像源；不能放宽版本、删除哈希或重建锁文件掩盖缺失：

```bash
PIP_INDEX_URL=https://packages.example.com/simple \
UV_DEFAULT_INDEX=https://packages.example.com/simple \
  bash docker/managed-agents/build.sh veadk-managed-agents-worker:local
```

包源只作为构建输入，不写入运行时环境。本脚本只接受无认证镜像源，调用 Docker
前拒绝用户名密码、查询字符串与 fragment。认证镜像源必须单独配置 BuildKit secret
集成；凭据不能写入 build args、镜像 tag、源码或日志。冻结导出保留依赖哈希。组件使用
独立命名且锁定的 BuildKit 缓存，避免与无关镜像构建共用缓存。专用 Worker 镜像只
安装 sandbox extra。飞书和可选数据集成使用安装 extensions extra 的独立 SDK 环境；
Worker 镜像不包含开发或 Codex 包。

## 运行时配置

通过平台 Secret 和环境配置提供网关、凭据及 Identity 信息。最小 Worker 需要
`ANTHROPIC_BASE_URL`、Runtime 凭据（`ANTHROPIC_ENVIRONMENT_KEY` 或配置后的
Runtime Identity）与 Work 作用域。账号 Worker 默认
`MANAGED_AGENT_WORK_SCOPE=account` 和 `MA_AGENT_LOOP_RUNTIME_TYPE=agentkit_runtime`；
Environment Worker 必须显式设置 `MANAGED_AGENT_WORK_SCOPE=environment` 与
`ANTHROPIC_ENVIRONMENT_ID`。创建 Session 还需要配置 Agent ID。Session 快照是模型、
工具、Skills、MCP 与凭据的权威来源。

镜像默认 `MANAGED_AGENT_WORK_CONCURRENCY=500`，它限制包含等待时间的 Work handler
数量，不允许同一 Session 同时执行多个轮次。只有成功完成合法 Work 轮询后才创建
就绪文件，排空时删除。HTTP 健康端点不能单独证明 Worker 就绪。启动入口同时监督
Worker 与监听器，任一进程停止会终止另一个。

对于执行已领取 Work 的 AgentKit Tool，镜像保留 `/opt/gem/run.sh`，选择
`MANAGED_AGENT_ENTRYPOINT_MODE=claimed`，使用注入的 Work/Session/租约配置，并默认
在 Tool 隔离中本地执行工具。镜像常规命令选择持续 Worker 模式。

进程以 UID/GID 10001 运行。使用只读文件系统时，挂载可写 `/workspace` 与 `/tmp`。
原生 bash 必须在部署提供的 OS 隔离中执行；文件路径限制不能替代 shell 安全沙箱。

[Kubernetes 示例](k8s/worker.yaml) 引用操作者创建的 Secret；应用前替换镜像占位符。
模板不提供密钥值或真实部署标识。Kubernetes、AgentKit 和真实模型验收需要独立部署
授权，本地测试或构建不能证明线上验收。

## 官方 SDK 扩展方案

当前镜像安装 `uv.lock` 选定的 **未修改的官方 PyPI `anthropic==1.3.0`**，不会安装
历史相邻仓库的定制 wheel。锁定 SHA256 与[官方发行版](https://pypi.org/project/anthropic/1.3.0/)
一致。安装器验证发行物哈希，`verify_anthropic_sdk.py` 再将所有已安装 SDK Python
文件与 wheel RECORD 对比，拒绝文件被修改、缺失或额外覆盖。RECORD 是完整性校验，
若 wheel 与 RECORD 同时被替换则不能独立证明来源；此边界由锁定发行物哈希保障。

VeADK 采用组合，无需继承或全局修改 SDK 方法：

| 行为 | 实现 |
| --- | --- |
| 环境级 Work 轮询 | 官方 `beta.environments.work.with_raw_response.poll`，先检查 HTTP 204 再校验 Work |
| 账号级模型 Work 轮询 | 公开 `AsyncAnthropic.get` 请求 `/v1/model-work/poll`；这是 VeADK 网关扩展，非 Claude API 端点 |
| ack / heartbeat / stop 与 Session 事件 | 官方 SDK 生成接口 |
| 账号/Runtime 路由头 | 公开 `default_headers` / `extra_headers` |
| Runtime Identity 轮转 | 公开 HTTP client 请求/响应 hooks，保留 Work Bearer 与网关 Identity 双重认证 |
| 原生工具执行 | 官方 `agent_toolset` 工厂与公开 `ToolError` |

官方文档说明了[原始响应、自定义请求及 HTTP client](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python#advanced-usage)。
官方 `EnvironmentWorker` 没有任意 VeADK handler 回调；继承需要覆盖私有执行方法。
本实现不覆盖 SDK 源码或方法。每个 Work 使用清除父认证的客户端副本；必须设置
副本公开属性 `api_key=None`，因为 SDK 1.3.0 的 `copy(api_key=None)` 会继承父 Key。

仍有两个版本敏感的 SDK 内部接口：官方发行包内的 `_skills._download_and_extract`
保留 Skill 下载失败即失败的语义，公开 helper 会跳过失败；工具 decorator 的
`_context_manager` 用于额外的退出清理。VeADK 在本地执行清理，避免 SDK helper
直接输出异常文本。真实 SDK 的归档、工具、认证与 dispatcher 测试覆盖这些边界。
锁定官方 SDK 版本不等于需要定制 SDK fork。

本地 VKE Worker 没有 Session Identity 引用时，可显式设置
`MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE=environment`，通过独立 Kubernetes Secret
提供 `MODEL_AGENT_API_KEY`。默认 `session`；AgentKit 及带 provider 引用的 Session
始终使用 Identity，不会兜底。此路径证明配置的模型凭据，不证明云 Identity 下发。
