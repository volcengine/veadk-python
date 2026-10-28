# 模型计时

[English](README.md)

组件 ID：`model-timing`；修订日期：2026-10-28；状态：active。

## 职责与接口

负责 `veadk/tracing/telemetry/timing.py`、模型适配器、Runner 和 VeADK HTTP 应用工厂中的 SDK 侧请求开始、模型开始及首输出时间戳。消费者是现有 OpenTelemetry 导出器和 Trace dump。无需新增配置、凭证、依赖或响应载荷字段。

## 契约

- CON-1：VeADK AgentKit/Harness 应用在 HTTP ASGI 入口、请求解析前记录 `veadk.request.start_time_unix_ns`，`veadk.request.start_source` 为 `http`。直接调用 VeADK Runner 时以 Runner 执行入口为起点，来源为 `runner`。继承的 HTTP 时间戳优先。不包含 ASGI 入口之前的客户端、网络和网关耗时。
- CON-2：每次适配器 SDK 请求（`LiteLLMClient.acompletion` 或 Ark `aresponses`）之前记录 `veadk.model.start_time_unix_ns`。每次请求在所属模型 Span 下建立 `model_request` 子 Span，其模型属性标识请求模型。Provider/LiteLLM 内部重试和 fallback 不可见，计入本次 SDK 请求；VeADK 发起的重试和 fallback 分别建立子 Span。成功或最近一次尝试的字段同时写入所属模型 Span。这不是模型服务端开始推理的时间。
- CON-3：流式请求的 `veadk.model.first_token_time_unix_ns` 为首个非空生成内容增量在本地收到的时间，`veadk.model.first_token_type` 为 `text`、`reasoning` 或 `tool_call`。空增量、角色/id/签名元数据、心跳、usage 和仅完成时返回的聚合内容不计入。一个 chunk 可含多个 token，不声称取得服务端生成 token 的时间。仅记录一次，不依赖 usage，也不存储内容。
- CON-4：`veadk.model.streaming` 表示实际 SDK 请求模式。`veadk.model.first_token_status` 为 `observed`、`non_streaming`、`no_output` 或 `unsupported`。非流式请求不使用完整响应时间伪造首 Token 时间。不支持的自定义/外部执行引擎明确标记模型计时缺失，不把 invocation Span 起点当成模型开始。
- CON-5：每次尝试在完成、异常、取消或生成器关闭时结束。已观测到的时间戳在中断后保留。模型/请求上下文不会在并发调用之间或通过异步生成器 yield 泄漏。原有输出、异常、取消、重试规则和关闭行为保持一致。
- CON-6：时钟时间戳统一为 UTC Unix 纳秒，用于 Trace 关联；不引入跨主机相减、单调时钟耗时或 TPOT 保证。时间戳写入 Trace 属性，现有 JSON dump 可以保留；首输出另产生带时间戳的 `veadk.model.first_token` 事件。

## 安全与兼容性

只添加时间、有限状态/类型标签和现有模型标识。计时采集不存储提示词、输出内容和凭证。HTTP 中间件不缓存请求体，也不改变 SSE。现有内容采集控制仍适用。公开接口及 Agent 事件序列化保持兼容。回滚只需移除新增采集，无需迁移历史数据。未安装中间件的通用 ADK/自定义应用，仅在使用 VeADK Runner 时提供 Runner 时间，否则不提供请求时间；不伪造更早的起点。

## 验证

CON-1/5：ASGI 入口、异步生成器/上下文/取消测试。CON-2/3/4/5：控制外部 Provider 边界的真实适配器测试，以及真实云端 Runtime/Provider E2E。CON-6：导出与 dump 契约断言。相对分支基线，生产代码变更可执行行覆盖率必须至少 95%，不得为了满足门槛新增覆盖率排除。

变更设计与证据：[first-token-timestamps](../../prd-spec/features/first-token-timestamps/2026-10-28-first-token-timestamps.zh.md)。

契约验证：55 项计时/适配器测试、244 项受影响测试及 6 项真实云端用例通过；生产变更行覆盖率为 100%（208/208）。无关的默认回归失败记录于所链接 PRD。
