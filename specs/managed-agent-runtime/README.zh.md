# Managed Agent Runtime

[English](README.md)

组件 ID：`managed-agent-runtime`。状态：`active`。修订日期：2026-10-10。
关联已批准 PRD：[managed-agents-upstream](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.zh.md)，`FR-1`、`FR-2`、`FR-6`、`T-1`、`T-4`、`AC-1`、`AC-5`。
本组件将自托管 Managed Agents 执行循环移入正式包，扩展现有 runtime provider，不改变其公开契约。

## 职责与接口

`veadk/runtime/managed_agents/` 负责 Worker 轮询、Work 执行、事件对账、原生工具及凭据缓存。`dispatcher.py` 使用 SDK 公开原始请求执行 poll，并用生成接口执行 ack/heartbeat/stop，无需相邻 SDK checkout 或私有 dispatcher 导入；只有轮询成功且响应有效后才宣布就绪。`veadk/integrations/mpa/session_client.py` 负责 Anthropic Session 传输，`session_resources.py` 负责固定版本 Skill 落盘和 Session 绑定的 MCP 工具集。正式包不导入示例模块；示例调用正式包并加载自己的可选 dotenv 配置。

`ManagedAgentsLoop` 消费待处理的 `user.message`，发布模型与工具事件。`serve_managed_agent_worker` 轮询 Work，`serve_claimed_managed_agent_work` 执行外部已认领的 Work。`SelfHostSandboxClient` 保留环境变量优先级及注入的 Work 认证；旧示例模块保留为兼容适配器。

## 状态与隔离

冻结的 Session 快照决定模型、系统指令、启用工具、权限、Skills 和 MCP 服务。每个 Work 拥有本地 ADK 状态及独立的原生工具上下文、Skill 工作目录和 MCP 工具集；不修改共享 Agent 来应用 Session 绑定。事件 ID 和游标用于对账既有轮次，避免重复执行已完成输入。Ark response ID 支持 Worker 更换后恢复对话上下文；Worker 状态始终使用本地 ADK 后端，忽略旧数据库配置。

## 工具、失败与清理

直接执行 Anthropic 原生工具。文件工具保留原始内容并拒绝工作目录逃逸。原生 bash 可执行宿主操作系统允许的命令，文件工作目录不构成操作系统沙箱。互不信任的 Session 必须使用独立容器或操作系统隔离，共享 Worker 中并发上下文不提供 shell 隔离。Session ID 必须使用字母、数字、下划线、点或连字符且不以点开头或结尾；拒绝不安全 ID，避免映射到冲突目录。`always_ask` 等待匹配的权限响应，自定义工具等待关联结果。默认工具预算为 300 秒，外层 action timeout 必须覆盖此预算。取消、超时、Session 终态和传输失败保持可见。模型轮次失败时发布脱敏错误并传播异常，保留输入以供恢复；对账不会把 `session.error` 视为成功完成。Worker 停止时排空 dispatcher 任务并关闭 MCP 工具集与原生工具上下文。Skill 下载失败或取消时删除部分工作目录，Work 完成后清理已跟踪的下载根目录，不跟随目录符号链接。即使某次关闭失败，也尝试关闭所有工具集和原生工具上下文。

## 凭据与诊断

Runtime、Session 模型和 MCP 凭据仅保存在进程内，并按身份上下文隔离。Session 模型缓存容量为 2000、TTL 为 3600 秒。凭据不写入环境变量或持久存储。显式 Work 凭据优先于 Runtime Identity；对外 Identity 错误经过脱敏，认证重试刷新凭据且遵守停止信号。可选事件、模型和轮询诊断对凭据字段脱敏，不开启通用 HTTP 日志。

## 验证

| 契约 | 验证 |
| --- | --- |
| `CON-1`：正式包导入与 CLI 不需要示例路径或凭据 | 包导入与安装包/CLI 检查 |
| `CON-2`：合法轮询就绪、租约栅栏、Session FIFO 与有界停止 | dispatcher HTTP 与生命周期测试 |
| `CON-3`：权威历史与 Ark 续接在 Worker 更换后恢复已完成轮次 | 新 Worker 重放与真实 SDK 传输测试 |
| `CON-4`：Session 独立工具/资源，失败或取消后完整清理 | 原生工具、MCP、Skill 工作目录与取消测试 |
| `CON-5`：作用域内认证与脱敏诊断 | 凭据刷新、隔离与错误脱敏测试 |
| `CON-6`：可移植 Worker 与 claimed 启动入口 | 进程监督、本地镜像构建与隔离容器检查 |

正式包测试覆盖事件对账、跨 Worker response 恢复、取消、认证重试、真实原生文件及 bash 工具、自定义与 MCP 结果关联、本地归档流式下载及清理。云端部署验收是独立步骤，不能由这些测试推定已完成。

## 官方 SDK 兼容性

dispatcher 组合未修改的官方 SDK。环境级轮询使用 `work.with_raw_response.poll`，
账号级模型轮询通过公开 `get` 访问 VeADK 专属网关端点。HTTP client hooks 实现
网关 Identity 轮转，生成接口保留 Work 认证。镜像在哈希锁定安装后，将 SDK Python
文件与 wheel RECORD 校验。工具清理保留 close/aclose 和额外 context-manager
退出，仅记录异常类型。发行包内部的 Skill 解包与工具 context-manager 属性仍为
版本敏感依赖，由集成测试覆盖。详见[官方 SDK 设计](../../prd-spec/refactors/managed-agents-official-sdk/2026-10-10-official-sdk.zh.md)
与[构建指南](../../docker/managed-agents/README.zh.md#官方-sdk-扩展方案)。

`MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE` 默认 `session`。显式 `environment` 仅允许
非 AgentKit 且无 `ark_api_key_provider` 的 Session 使用 `MODEL_AGENT_API_KEY`；
显式 provider 引用及 AgentKit 始终要求 Session Identity。未知来源或缺少本地 Key
明确失败。使用此选项的本地 Kubernetes 验收不证明云 Runtime Identity。
