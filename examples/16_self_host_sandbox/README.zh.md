# 16. 自托管 Managed Agents

[English](README.md)

VeADK 执行模型循环；原生工具可在隔离 Worker 内本地执行，或通过 Managed Agents
网关远程派发。复用实现位于 `veadk.runtime.managed_agents` 和
`veadk.integrations.mpa`，本目录保留启动器与验收脚本，不承载生产库代码。

## 安装与运行

```bash
uv sync --extra sandbox --extra extensions
cp examples/16_self_host_sandbox/.env.example examples/16_self_host_sandbox/.env
# 启动前填写私有 .env 配置。
bash examples/16_self_host_sandbox/run.sh --managed-agent-worker
```

启动器将 `.env` 作为默认值，显式环境变量优先。库导入不加载示例配置，也不创建
远程 Session。安装后可脱离示例目录直接运行：

```bash
python -m veadk.runtime.managed_agents.worker --managed-agent-worker
python -m veadk.runtime.managed_agents.worker --managed-agent-work-item
```

Worker 模式持续轮询 Work。claimed 模式需要外部 dispatcher 注入 Work/Session ID
和租约状态。Session 快照拥有模型、权限、工具、Skills、MCP 和 Identity 绑定。
账号作用域选择配置的执行池；Environment 作用域还需要 Environment ID。
本地会话模式将每个 VeADK Session 映射到一个 Managed Session，Runner 在所有
重叠本地轮次结束后发送 idle。

## 执行与状态

Anthropic 原生工具通过自身上下文执行，保留文件编辑与读取语义。MCP 工具使用
实际 MCP transport。需确认的工具等待关联的权限事件，自定义工具等待关联结果。
网关事件账本负责跨 Worker 恢复已完成输入与 Ark response ID。Worker 始终使用进程本地 ADK 记账，忽略旧数据库环境变量；
持久恢复依赖事件账本与 Ark response ID。

Worker 在 SIGTERM 时排空，保持单 Session 顺序，并以
`MANAGED_AGENT_WORK_CONCURRENCY` 限制并发 Work。文件工具限制工作区路径，bash
依赖部署提供 OS 隔离。取消或失败关闭 Runner、MCP/原生工具上下文和临时 Skills。
Runtime 与 Session 凭据保持在进程内存。

## 飞书渠道

私下配置机器人凭据，并按需启用 `.env.example` 中的流式、思考、工具详情、卡片
和话题选项，然后运行：

```bash
bash examples/16_self_host_sandbox/run.sh --feishu
```

该命令启动常驻渠道、重连 WebSocket，并在关闭时排空回复。示例之外的渠道设置
默认关闭。

## 测试与验收脚本

```bash
uv run --extra dev --extra sandbox pytest tests/runtime/managed_agents tests/integrations/mpa
python examples/16_self_host_sandbox/local_agent_loop_test.py
python examples/16_self_host_sandbox/anthropic_gateway_e2e.py --help
python examples/16_self_host_sandbox/soak_load_test.py --help
```

单元测试使用模拟服务。`anthropic_gateway_e2e.py` 提供官方 SDK 对话检查及沙箱生命
周期模式；对话模式不需要 AgentKit inspector。可选云资源检查必须显式配置
`AGENTKIT_TOOL_DEPLOY_SCRIPT` 和 `AGENTKIT_TOOL_ID`，没有个人辅助脚本路径或部署 ID
默认值。压测、故障、分布式 Worker 和 Kubernetes 脚本属于操作者主动执行的线上
检查，运行前检查必填配置。本地结果文件与完整事件日志保持私有。

分布式脚本必须通过 `ANTHROPIC_BASE_URL`、`ANTHROPIC_ENVIRONMENT_ID`、
`ANTHROPIC_ENVIRONMENT_KEY` 和 `SANDBOX_AGENT_ID` 指定已有的隔离测试资源；测试 Agent
必须启用 Ark Session 凭据与原生 bash。脚本检查权威 Session 历史/续接，只归档自己
创建的 Session。`ark_session_e2e.py` 同样必须显式配置网关与 Agent。

镜像构建、依赖注意事项、就绪、可写挂载和 Kubernetes Worker 模板见
[构建指南](../../docker/managed-agents/README.zh.md)。镜像构建、本地测试、发布、部署
与云 E2E 是不同结果。本次迁移排除来源的独立 Managed Agents UI。

旧 `sandbox_client`、`managed_agent_loop`、`runtime_identity`、
`managed_session_resources` 和 `event_debug` 导入保留为示例兼容适配器，新代码使用
包导入。参见[运行时契约](../../specs/managed-agent-runtime/README.zh.md)与
[迁移设计](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.zh.md)。
