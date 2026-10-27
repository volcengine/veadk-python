# 沙箱生命周期契约

[English](README.md)

组件：`sandbox-lifecycle`；修订：2026-10-23；状态：active。
归属：`veadk.sandbox` 与 `veadk/agent.py` 的可选接入；设计：[托管 MCP 沙箱](../../prd-spec/features/sandbox-lifecycle/2026-10-23-agent-owned-mcp-sandbox.zh.md)。

## 职责与接口

`SandboxManager(*, tool_id, state_dir, region="cn-beijing", ttl=1800,
ready_timeout=120.0, poll_interval=1.0, client=None)` 管理其自身创建的 AgentKit Session。
`SessionKey(app_name, user_id, session_id)` 标识逻辑绑定，本地查询键还包含 region
和 ToolId。不同账号/控制面配置使用独立状态目录，不接受模型生成的身份信息。
注入 client 时必须配置相同 region，并实现 Manager 使用的同步 AgentKit SDK 方法。

- `async with manager.acquire(key) as lease`：创建/恢复绑定、唤醒实例并等待 Ready，
  使用期间持有本地独占锁。`SandboxLease.session_id` 是物理 ID；`.mcp_url` 是
  保留查询参数的临时连接 URL。
- `await manager.resume(key)`：仅已有绑定，返回 Ready lease。
- `await manager.pause(key)`：仅已有绑定，确认 Paused。
- `await manager.delete(key)`：仅已有绑定，确认终止/不存在并保留删除标记；
  删除远端 Session，不删除 ADK 聊天历史。
- `await manager.status(key)`：返回安全绑定状态和当前远端状态；
  恢复不确定创建结果时可能持久化已经存在的物理 ID。
- `SandboxError`：脱敏异常；可选 `.code` 为结构化后端错误码。

使用标准 ADK `McpToolset` 连接 `lease.mcp_url`，生命周期方法不暴露为模型工具。
手动 acquire 时，应用在退出上下文前关闭 MCP；使用 Agent(sandbox=manager) 时，
Agent 管理每次调用的 MCP 连接，应用复用 Agent、Runner 和 ADK SessionService。
Runner.close 不暂停或删除沙箱。

## 状态、失败与隔离

本地记录版本为 1，包含 ToolId、唯一 UserSessionId、物理 SessionId、阶段和最近
使用时间，不包含 Endpoint 凭据或用户消息。JSON 原子写入使用 0600 权限；
文件锁串行化同一本地 POSIX 文件系统上的进程。状态目录应私有可信。
不保证 Windows 或多机锁语义；不支持的平台仍可以导入模块。

阶段：creating → ready → pausing → paused → resuming → ready；deleting → deleted
阻止 acquire。已删除工作区需要新的逻辑会话键才能开始新工作。到期、NotFound、
网络或鉴权错误均不自动替换实例。创建意图先于请求持久化，响应丢失/重启后分页
匹配 UserSessionId，必须恰有一个物理匹配。缺失或歧义保持待核实，不能删记录重试创建。

创建/恢复/暂停均通过 GetSession 等待目标状态，请求被接受不代表完成。
带签名 Endpoint 改路径时保留路由/鉴权查询参数。轮询和等锁受 ready_timeout
约束；已发出的同步 SDK 请求使用自身传输超时，可能超过轮询截止时间。
取消时等待其线程结束再释放锁，不等于取消远端工具执行。普通错误不会被当作
删除成功；删除/不确定状态跨重启保留。

限制：仅前台同步任务，不含后台任务检测、空闲调度器、自动 TTL 续租或分布式租约。
调用方必须确认后台工作空闲后再 pause/delete。云端 TTL 仍是权威约束。
后端是否支持暂停，以及文件/进程保留范围，必须按 Provider 做真实验证。

## 兼容性与验证

这是增量 API，保留 Runner 默认行为和远程 Agent 路径，不增加依赖。流拦截器
在提前关闭时现在会显式关闭底层生成器。
框架凭据和本地状态不进入模型上下文。`tests/sandbox/test_manager.py` 验证
生命周期和失败边界；`tests/sandbox/test_mcp_integration.py` 使用真实本地 MCP、
离线模型和持久化聊天验证接入；`tests/sandbox/test_agent_binding.py` 验证共享
Agent 在普通 ADK/VeADK Runner 下的并发、异常/取消清理、clone 与配置；
同 key 沙箱锁仍由 test_manager.py 验证；`examples/sandbox_mcp/` 是用户入口。
具体验证结果及有条件的云端检查记录在关联 PRD。


## CON-8：Agent 原生执行（active）

`Agent(sandbox=manager, tools=[], ...)` 开启托管 MCP 工具。manager 必须是
SandboxManager 实例；Agent 保存从 repr/model_dump 排除的 Python 活引用，
不是可序列化的远端配置。仅支持 ADK runtime 的独立 VeADK Agent，没有父/子
Agent，tools 为空且没有 code executor。构造和执行时均校验，包括 clone 和
重新配置。run_live 显式拒绝。

Agent._run_async_impl 按可信 session 身份 acquire，在模型/工具循环内管理标准
McpToolset。ContextVar 保存本次执行的绑定；canonical_before_model_callbacks
前置工具注入，不修改用户回调字段或共享 Agent.tools。注入检查 session、invocation
和 agent 身份，并注册当前请求的工具声明和执行分发表。继承上下文的后台任务不能
复用已关闭绑定。执行完成、异常、取消或显式 aclose 时，先关闭 MCP、还原上下文，
再释放沙箱锁。Agent 作用域不覆盖 before/after-agent 回调及 Runner 的历史写入/
压缩；before-agent 提前返回时不分配沙箱。

普通 google.adk Runner 和 VeADK Runner 均不需要 sandbox 参数、插件注册或
自定义 Toolset。未发布的 Runner(sandbox=...) API 被替换，不保留为别名。
应用只创建一次 Agent/Runner。不同 session 可并发；同一聊天内必须顺序提交，
因为沙箱锁不能串行化 Runner 更早的写入。Agent/Runner 执行结束不自动暂停/删除。
提前停止消费流时应显式关闭，活跃调用结束后再关闭 Runner。不提供 Python manager
活对象在 Studio UI/配置中的往返序列化支持。
