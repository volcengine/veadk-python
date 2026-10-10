# 执行链路

[English](README.md)

组件：execution-tracing；状态：draft；更新：2026-10-10。
负责 veadk/runtime/codex/model_tracing.py 与 _remote_sandbox/request_tracing.py，对接 Responses Shim 和 Worker 客户端。设计：[执行诊断](../../prd-spec/features/execution-diagnostics/2026-10-10-execution-diagnostics.zh.md)。

CON-1：codex.model.request 覆盖一次后端 aresponses 及库内重试；call_llm 仍覆盖整轮。不据此推算模型 TTFT，不重复记录用量。
CON-2：Worker 请求 Span 保留既有重试、认证、Key 和错误，仅传递 W3C 上下文，不附加观测 baggage。
CON-3：每次 SSE 连接记录独立 CLIENT Span，不在 yield 期间持有当前上下文。事件游标、绑定校验、重试上限与执行职责不变。
CON-4：仅记录固定操作名与错误类型，不记录凭证、URL、正文或原始异常。既有 Provider 负责采样和导出，不新增持久化或配置。

测试：tests/agents/test_worker_request_tracing.py、模型计时测试和现有远端 Sandbox 回归。草稿 PR 中 CON-3 完成、重连游标、提前关闭、取消与 HTTP 失败测试已通过。真实接收、导出和部署证据单独验证；本草案不保证服务端已埋点。

## 检索边界

CON-5（本地已实现，尚未部署）：`veadk.knowledge.search`、`veadk.memory.search`、`veadk.memory.save` 继承既有上下文与 Provider。只记录后端类型、实际 top_k / 结果数量或会话 / 事件数量，不记录查询、正文、用户 ID、索引和 URL。记忆检索的已处理后端错误保留空返回，但 Span 标 ERROR；正常空结果是成功。取消时结束调用方边界，不声称同步线程或后端已停止。不新增导出器及持久化状态。设计及待执行验收见[检索诊断](../../prd-spec/features/retrieval-diagnostics/2026-10-10-retrieval-diagnostics.zh.md)。

## 会话持久化

CON-6（本地已实现，未部署）：VeADK 内置 SQLite、MySQL、PostgreSQL 工厂通过内部 DatabaseSessionService 子类，将非 partial 的 append_event 调用记录为 `veadk.session.append_event`。Span 包含 ADK 存储操作中的序列化、状态更新和数据库调用，不拆分各条 SQL，也不证明远端持久化提交。仅记录实际会话／执行标识与错误类型。采样和上报由现有 Provider 管理。参数、返回事件、错误、取消、缓存及调用方自定义 SessionService 保持不变。设计：[会话持久化诊断](../../prd-spec/features/session-persistence-diagnostics/2026-10-10-session-persistence.zh.md)。
