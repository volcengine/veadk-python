# 执行链路

[English](README.md)

组件：execution-tracing；状态：draft；更新：2026-10-10。
负责 veadk/runtime/codex/model_tracing.py 与 _remote_sandbox/request_tracing.py，对接 Responses Shim 和 Worker 客户端。设计：[执行诊断](../../prd-spec/features/execution-diagnostics/2026-10-10-execution-diagnostics.zh.md)。

CON-1：codex.model.request 覆盖一次后端 aresponses 及库内重试；call_llm 仍覆盖整轮。不据此推算模型 TTFT，不重复记录用量。
CON-2：Worker 请求 Span 保留既有重试、认证、Key 和错误，仅传递 W3C 上下文，不附加观测 baggage。
CON-3（拟实现）：每次 SSE 连接记录独立 CLIENT Span，不在 yield 期间持有当前上下文。事件游标、绑定校验、重试上限与执行职责不变。
CON-4：仅记录固定操作名与错误类型，不记录凭证、URL、正文或原始异常。既有 Provider 负责采样和导出，不新增持久化或配置。

测试：tests/agents/test_worker_request_tracing.py、模型计时测试和现有远端 Sandbox 回归。CON-3 测试待完成。真实接收、导出和部署证据单独验证；本草案不保证服务端已埋点。
