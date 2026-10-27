# 托管 MCP 沙箱生命周期

[English](2026-10-23-managed-mcp-sandbox.md)

- 变更 ID：`sandbox-lifecycle`；创建/修订日期：2026-10-23。
- 状态：superseded；以下保留历史实现与验证。当前接入见 [Agent 原生设计](2026-10-23-agent-owned-mcp-sandbox.zh.md)。
- 组件契约：[sandbox-lifecycle](../../../specs/sandbox-lifecycle/README.zh.md)。

## 背景和范围

标准 ADK `McpToolset` 可以调用沙箱工具，但不管理底层 AgentKit Session 的
创建、暂停、恢复和删除。此前独立原型验证了创建、MCP 文件读写、模型调用和清理，
但位于仓库外，未交付 SDK 能力。用户明确要求将实现放进 `veadk-python`，
继续使用标准 `McpToolset`，不增加专用沙箱 Toolset。

现有 `veadk/agents/_remote_sandbox/session.py` 为另一条远程 Agent 路径解析
执行租约，只复用 Starting/Ready，可能轮换物理实例。本功能不改变该现有契约。

## 需求与场景

| ID | 前提 / 触发 / 结果 |
| --- | --- |
| FR-1 | 新会话获取沙箱：先保存创建意图，创建一个 Session 并等待 Ready。 |
| FR-2 | 绑定实例处于 Paused：acquire 恢复同一实例，返回刷新的 MCP URL。 |
| FR-3 | 应用暂停/删除：与活跃 acquire 互斥，确认远端状态，保留删除标记。 |
| FR-4 | 创建响应丢失：按持久化的唯一 UserSessionId 恢复；零个或多个匹配均不自动创建替代实例。 |
| FR-5 | 复用 Agent/Runner：每次调用重连标准 McpToolset，持久化 ADK session 保留对话。 |
| FR-6 | SDK/API、轮询或取消异常：保留不确定状态，脱敏错误，不把普通错误当成删除成功。 |
| FR-7 | SDK 导出、示例、离线测试和双语文档均在本仓库；不包含私人地址或凭据。 |

非目标：专用 MCP Toolset、自动空闲暂停、分布式锁、后台任务登记、远端命令取消、
自动续租、到期后自动替换、接管外部实例、Studio/生成项目接入，以及迁移现有远程 Agent 租约。

## 设计

从 `veadk.sandbox` 导出 `SandboxManager`、`SessionKey`、`SandboxLease`、
`SandboxError`。Manager 管本地持久化绑定和 AgentKit 控制调用；Runner 的可选接入层
管理每次调用的标准 McpToolset 连接，应用复用 Agent/Runner。复用已有 AgentKit SDK 依赖，

不增加依赖或默认运行时钩子。公开参数和不变量由组件契约定义。

POSIX 文件锁覆盖完整一轮执行和生命周期操作，支持共享本地目录的多进程。
凭据继续由 SDK 配置提供；带鉴权 Endpoint 仅驻留内存，不进入 lease repr 或状态文件。
不支持的平台在构造 Manager 时明确失败，不影响普通 `import veadk` 或
`import veadk.sandbox`。

创建 RPC 前持久化意图和唯一 UserSessionId。删除意图即使未确认完成，也阻止新
acquire。生命周期通过 GetSession 确认远端状态。取消时等待同步 SDK 请求结束后
才释放锁；这不等于取消远端命令。

## 任务与验收

| 任务 | 需求 | 验收 | 验证 |
| --- | --- | --- | --- |
| T-1 | FR-1–4、FR-6 | AC-1：SDK 导出和生命周期不变量 | `tests/sandbox/test_manager.py` |
| T-2 | FR-2、FR-5 | AC-2：标准 MCP 重连并保留 ADK 历史 | `tests/sandbox/test_mcp_integration.py` |
| T-3 | FR-7 | AC-3：仓库内可运行示例与双语文档 | 导入、CLI help、链接、Ruff |
| T-4 | FR-1、FR-5–6 | AC-4：区分离线与云端验证 | 下方验证记录 |

## 评审与批准

用户已同意标准 McpToolset/Manager 方案、要求实现第一版，并明确纠正实现位置为
本仓库，构成本次迁入的授权，无需重复询问。没有可用的 `review-spec` 技能；
直接评审覆盖职责、状态流转、取消、部分成功、隔离、兼容性、可测性和双语一致性。
保持旧远程 Agent helper 行为不变，明确 POSIX 边界，保留不确定/已删除记录。
没有未解决的设计阻塞项。

## 初版生命周期验证（历史记录）

范围：本功能未提交的新增文件，日期 2026-10-23。没有修改共享 Agent/Runner、
远程 Agent 实现或依赖元数据。验证环境：Python 3.13、`google-adk==2.7.1`、
`agentkit-sdk-python==0.8.9`、`mcp==1.26.0`。

| 检查 | 结果 | 证据 / 边界 |
| --- | --- | --- |
| 实现前回归 | pass | 新生命周期测试首先因不存在 `veadk.sandbox` 而失败。 |
| `uv run --extra dev pytest tests/sandbox -q` | pass | 16 项测试；一条上游 ADK 弃用警告。覆盖生命周期、创建歧义/分页、超时、取消、删除标记、真实本地 MCP 重连和 SQLite 历史。 |
| `uvx ruff check veadk/sandbox tests/sandbox examples/sandbox_mcp`，以及对相同路径执行 `uvx ruff format --check` | pass | 六个源码/测试 Python 文件。 |
| `uv run python examples/sandbox_mcp/main.py --help` 和 SDK 导入 | pass | 仓库内公开 API 和可运行 CLI。 |
| 双语配对、相对链接、空白检查和 `git diff --check` | pass | 三组双语文档；不含凭据或私有端点。 |
| 使用当前 SDK 和示例的云端冒烟 | pass | 创建全新临时 Session，再次 acquire 保持同一物理 SessionId，用标准 MCP 工具调用真实模型，确认 FunctionResponse 包含执行标记及成功工具输出，最后确认删除。 |
| 云端 pause/resume 与工作区保留 | not_run | 可用 Tool 未启用快照；没有修改配置。离线测试模拟了该流转。 |
| 全量回归 / pre-commit | not_run | 独立新增模块已有定向集成覆盖；未修改共享实现或依赖，且没有提交请求。 |

直接代码评审确认 T-1–T-4 验收项、远程 Agent 行为不变、异常处理、取消与锁释放、
连接关闭、绑定不存凭据，以及双语等价。无未解决的阻塞项。POSIX 本地协调与
依赖后端的暂停支持仍是明确的第一版限制。先前的仓库外原型保留为历史产物；
正式 SDK 和示例现在位于本仓库内。


## 复用 Runner 修订（已实现）

用户以“按照方案改下看看”明确批准此修订。
FR-8：`Runner(..., sandbox=manager)` 跨 session、跨轮复用同一个 Agent 和 Runner。
SessionKey 仍绑定一个物理沙箱。
FR-9：每次 run_async 获取自己的普通 McpToolset，通过内部 before-model 插件把
工具注入当前 LlmRequest，不修改 Agent.tools、凭据或回调。不同 session 可并发，
同 session 的调用通过已有锁串行执行。
FR-10：执行结束、异常、取消及显式关闭流 aclose 时，先结束 ADK 执行并关闭 MCP，
再释放绑定锁。不自动暂停或删除；删除仍通过 Manager 显式执行。

内部插件仅管理临时的 session 到连接映射，根据回调中的可信 session 身份选择
连接，签名 URL 不进入 session state。每次调用新建 Toolset，避免恢复后沿用缓存
端点。不传 sandbox 的 Runner 保持现有行为。第一版支持 tools 为空、没有子 Agent
和 code executor 的单一 ADK LlmAgent；其他 runtime、run_live、混用本地工具不在
本次接入范围内。不兼容配置显式拒绝。应用和插件仍是可信代码，已有回调继续执行。
SDK 托管资源仍可直接使用 SandboxManager 操作。

T-5 / AC-5：把每轮重建 Agent 的示例改为可复用 Runner；测试同名工具返回不同结果
的两个 session 并发、多轮加暂停恢复、Agent 对象/tools/回调不变、工具失败、模型
失败、取消和提前关闭流。run_async 包装发生变化，需运行已有 Runner 契约和 steering
测试。同步三组双语文档。此前云端结果仅代表上一版；若凭据仍可用，重新执行本版的
隔离云端冒烟。云端暂停仍受后端配置限制。

直接设计评审：ADK 2.7 支持请求级 tools_dict 分发；after_run 回调仅成功时执行，
所以需要外层生成器清理。不引入 SandboxMcpToolset。用户批准覆盖本次变更，无需
额外询问。本修订验证见下方记录。


## 最终修订验证与交付

日期：2026-10-23；范围：当前未提交的 SDK/Runner/示例/测试新增文件以及 Runner
签名、流清理 diff。依赖版本与初版记录一致，没有修改依赖。
用户批准的 FR-8–10 / T-5 / AC-5 已实现。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 测试先行回归 | pass | 四个新增复用/清理用例先因 Runner 不接受 `sandbox` 参数而失败。 |
| `uv run --extra dev pytest tests/sandbox tests/runner tests/agents/test_remote_sandbox_agent.py tests/extensions/harness/test_runner_plugins.py -q` | pass | 63 项测试；21 条上游弃用警告。覆盖共享 Agent 多 session 并发、同 session 串行、SQLite 历史保留、恢复端点刷新、回调保留、模型/工具/发现失败、取消、提前关闭、聊天缺失、配置以及已有调用方。 |
| sandbox 源码/测试/示例及 Runner 契约测试的 Ruff | pass | check 和 format 通过。 |
| Runner 全文件 Ruff | fail（已有基线） | 原有 Runner 检查项仍存在；与 HEAD 的 rule/message 对比确认没有新增问题。没有为清理历史 lint 改动无关代码。 |
| CLI help、双语配对、相对链接、Python 示例与空白 | pass | 当前 `--follow-up` 示例复用单个 Agent/Runner。 |
| 当前代码云端冒烟 | pass | 一个 Agent/Runner 并发服务两个 session，各执行两轮。同一路径分别写入不同标记，通过真实模型 MCP 调用读回各自标记；每个 session 保持自己的物理 SessionId。两个临时沙箱均已删除并确认。 |
| 云端暂停/恢复 | not_run | 可用 Tool 未启用快照；离线测试已覆盖流转。 |
| 仓库全量测试 / pre-commit | not_run | 已扩展上述 Runner、远程 Agent 和插件相关回归；未请求提交。 |

直接实现评审确认了公开 keyword-only API、共享 Agent 字段不变、请求级工具分发、
MCP 归属、流终止、不支持配置，以及双语契约/示例一致性。此接入显式开启；其他
Runner 不会自动添加模型工具或创建云端沙箱。无阻塞项。POSIX、单 Agent、run_async
和后端快照限制已记录。没有提交、发布或部署。
