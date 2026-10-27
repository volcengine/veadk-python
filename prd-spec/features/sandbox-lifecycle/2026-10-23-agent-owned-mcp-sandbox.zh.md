# Agent 管理 session 沙箱接入

[English](2026-10-23-agent-owned-mcp-sandbox.md)

状态：implemented。日期：2026-10-23。替代[此前设计](2026-10-23-managed-mcp-sandbox.zh.md)
中的 Runner 接入。契约：[沙箱生命周期](../../../specs/sandbox-lifecycle/README.zh.md)。

## 意图与依据

用户选择第二种方案：配置 `Agent(sandbox=manager)`，在 Agent 生命周期内部绑定
沙箱，使原生 google.adk Runner 也可运行。仅在 Agent 存配置、仍由 VeADK Runner
读取不能满足此需求。ADK 在 aclosing 作用域内调用 Agent._run_async_impl，并通过
canonical_before_model_callbacks 解析模型回调。删除现有 Runner 插件接入。
未发布的 Runner(sandbox=...) 原型 API 改为 Agent(sandbox=...)；底层 Manager
API 和未配置 sandbox 的 Runner 保持原有行为。

## 需求与设计

- FR-A1：Agent 接受存活的 SandboxManager 引用，从 repr 和序列化输出排除。
  构造及执行时均检查类型和单 ADK Agent、空 tools、无子 Agent/code executor
  的范围（clone 绕过构造校验）。显式拒绝 run_live。
- FR-A2：Agent._run_async_impl 根据可信 app/user/session 获取沙箱，创建标准
  McpToolset 并绑定到本次异步执行上下文。每个模型请求通过内置回调获取该上下文，
  注册工具声明和执行对象。保留用户回调字段及 Agent.tools，不注册 Runner 插件，
  不自定义 Toolset，不修改共享 URL。
- FR-A3：执行完成、模型/工具/发现失败、取消和流 aclose 时，先结束模型执行、
  清理 MCP，再释放沙箱锁。嵌套作用域还原上下文，签名端点不写入聊天 state。
  暂停恢复保持物理绑定，使用当前端点重建连接。
- FR-A4：同一个 Agent 可由 VeADK Runner 和普通 ADK Runner 执行，支持独立
  session 并发及多轮顺序复用。同 key 的沙箱执行持锁，但不能串行化 Runner
  更早的聊天写入：调用方需在同一聊天内顺序提交。不承诺跨进程聊天排队，也不
  改写 ADK 并发会话历史语义。

使用 ContextVar 保存 invocation 身份、Agent 身份和临时 McpToolset。计算得到的
canonical 回调列表前置工具注入，不修改传入的回调字段；默认 Agent 不增加回调。
Agent clone 时不复制持久运行时对象。Agent 只保存 manager 配置，延迟验证实际
manager 类型。沙箱仅进入默认 ADK 分支，其他 runtime 拒绝。

## 任务、验收与风险

| 任务 | 需求 | 验收 / 检查 |
| --- | --- | --- |
| T-A1 | FR-A1–3 | 实现 Agent 字段/作用域/回调，移除 Runner 注册；验证异常与清理。 |
| T-A2 | FR-A2–4 | 真实本地 MCP 测试参数化覆盖普通 ADK 与 VeADK Runner；同一 Agent 双 session 同名工具/不同结果、顺序复用/恢复和历史持久化。 |
| T-A3 | FR-A1–4 | 测试 clone/重新配置校验、序列化排除及缺失 session/live 边界；运行 Agent/runtime/Runner 相关回归。 |
| T-A4 | FR-A4 | 更新可运行示例和当前双语契约；凭据仍可用时进行原生 ADK 云端冒烟。 |

非目标仍包括分布式沙箱锁、后台任务跟踪、自动续期/暂停/删除、Studio 配置 UI/
生成器、多 Agent 共享、live/bidi，以及额外模型工具。普通 ADK 兼容不证明 Studio
UI 能往返序列化 Python manager 对象。接入位于 ADK 模型执行内；before-agent
回调提前返回时不需要沙箱。沙箱锁不覆盖 Runner 更早的写入或更晚的压缩。

## 批准与评审

用户在 Agent 原生接入提案后明确选择“第二种吧”。没有 review-spec 技能，以直接
评审替代。已评审动态作用域隔离、回调顺序、clone、schema 排除、资源关闭、生命
周期归属、后端依赖和双语一致性。聊天排队限制来自 ADK 源码，实施前已说明。
无设计阻塞项；批准覆盖替换未发布的 Runner API。

## 验证与交付

日期：2026-10-23。范围：当前未提交的 Agent 原生接入 diff 及对应沙箱代码、测试、
示例。Python 3.13、google-adk 2.7.1、agentkit-sdk-python 0.8.9、mcp 1.26.0。
没有修改依赖或云端 Tool 配置。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 测试先行回归 | pass | Agent 字段/作用域实现前，16 个原生接入用例失败。 |
| `uv run --extra dev pytest tests/sandbox tests/runner tests/runtime/test_agent_transfer.py tests/runtime/test_dispatch_runtime_provider.py tests/agents/test_remote_sandbox_agent.py -q` | pass | 70 项测试，27 条上游弃用警告。普通 ADK 与 VeADK Runner 均覆盖并发/复用、回调保留、异常、取消、提前关闭、session 缺失/live 拒绝及 before-agent 提前返回。包含 clone/序列化和已有 runtime/Runner/远程 Agent 回归。 |
| sandbox 源码/测试/示例 Ruff check/format | pass | 新代码及示例代码块通过。 |
| Agent/Runner 全文件 Ruff | fail（已有基线） | Agent 31 项、Runner 13 项，按 rule/message 与 HEAD 完全一致；没有新增问题。 |
| CLI help、双语、相对链接、Python 示例、Git 空白 | pass | 示例直接导入 google.adk.runners.Runner，只在 Agent 上配置 sandbox。 |
| 原生 ADK 云端冒烟 | pass | 断言 Runner 精确为原生类型且 Agent 持有 manager。同一 Agent/Runner 并发服务两个独立 session，各两轮；同一路径写不同内容并通过真实模型 MCP 调用各自读回。物理 SessionId 复用，两个临时沙箱均已删除并确认。 |
| 云端暂停/恢复 | not_run | Tool 未启用快照；本地流转已验证。 |
| Studio UI / 仓库全量 / pre-commit | not_run | 未请求 Studio 配置工作或提交；上述 Agent/runtime/Runner 定向回归覆盖本次变更。 |

T-A1–T-A4 与 FR-A1–4 已验收。直接评审覆盖 Agent 原生归属、上下文匹配/还原、
已关闭绑定拒绝、回调保留、clone 再校验、序列化排除及原生 Runner 分发。
Runner 仅保留通用的显式生成器关闭修复，以确保 VeADK 流清理；Runner 中没有
sandbox 参数、注册表或插件。当前文档区分了沙箱锁和聊天排队，无已知阻塞项。
未提交、发布或部署。


## 分支验证：2026-10-27

分支：`feat/agent-session-sandbox`，恢复本次改动前已通过
`git pull --rebase origin main` 同步到 `origin/main` 的 `23014771`，无冲突。
`uv run --extra dev pre-commit run --all-files`：pass，包含配置的 Ruff、密钥
扫描和依赖策略。上述定向回归命令：pass，70 项测试、27 条上游警告。双语配对、
相对链接和暂存 diff 空白：pass。本次分支操作没有重复云端测试；云端证据日期
仍为 2026-10-23。
