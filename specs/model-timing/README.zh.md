# 模型计时

[English](README.md)

组件 ID：`model-timing`；修订日期：2026-11-02；状态：active。

## 职责与接口

负责 `veadk/tracing/telemetry/timing.py` 中的原生请求/模型 Span 及标准流式 TTFT，配合模型适配器、Runner 和 VeADK HTTP 工厂。`portal_metrics.py` 管理现有 Histogram instrument；已配置的全局 MeterProvider 负责导出。不引入新配置、凭证、依赖或 Agent 响应字段。

## 契约

- CON-1：VeADK AgentKit/Harness HTTP 工厂在 ASGI 入口、请求体解析前创建原生 `http_request` SERVER Span，应用执行结束时关闭。直接执行 Runner 时拥有 `runner_request` Span。Runner 复用继承的 HTTP 请求 Span。两种边界均不含入口之前的客户端、网络和网关耗时。
- CON-2：每次可观测 SDK 请求，在当前模型/Agent 上下文下拥有 `model_request` CLIENT 子 Span。原生开始时间就是 TTFT 计算使用的本地 SDK 起点。VeADK 发起的重试/降级分别创建 Span；供应商/LiteLLM 内部不可观测重试仍计入同一次 SDK 请求。这不是服务端开始推理时间。
- CON-3：首输出为首个非空文本、推理或工具调用 delta。空增量、角色/id/签名元数据、usage、心跳和仅完成时返回的聚合内容不计入。一个 chunk 可含多个 token。首输出接收时间仅作为内部状态锁定一次，不依赖 usage，也不保存内容。
- CON-4：`gen_ai.request.stream` 为实际 SDK 布尔模式。`gen_ai.chat_completions.streaming_time_to_first_token` 为 SDK 起点到首输出的浮点秒数。非流式/无输出/未埋点路径省略 TTFT。实际 SDK 模式未知时不从 Runner 配置推导。
- CON-5：Span 在完成、失败、取消和主动关闭生成器时结束。仅在推进/关闭生产者时绑定请求上下文，不跨生成器 yield 保留。模型失败设置原生 Status `ERROR`，`error.type=llm_error`、`timeout` 或 `cancelled`。请求失败使用 `request_error`、`timeout` 或 `cancelled`；HTTP 5xx 使用 `http_error`。主动关闭生成器不算错误。保留原始输出、异常及清理行为。
- CON-6：原生起止时间戳采用 OpenTelemetry 单位。TTFT 将本地 Unix 纳秒差值换算为秒，不引入跨主机或单调时钟保证。负间隔省略并产生有限诊断；真正零耗时有效。后续中断不影响已经观测的 TTFT。
- CON-7：SDK Span 携带 `gen_ai.span.kind=llm` 和 `gen_ai.request.model`。标准模型字段属于每次 SDK Span，不属于聚合的所属 Span。不导出 `veadk.request.*`、`veadk.model.*` 或自定义首 Token 事件，不在属性中重复原生 Span 时间。根据用户明确授权，不保留兼容别名。
- CON-8：同一 TTFT 观测在现有 `gen_ai.chat_completions.streaming_time_to_first_token` Histogram 中恰好记录一次，单位为 `s`，独立于 usage 和 Trace 采样。没有观测就没有样本。指标记录失败时产生不含后端详情的有限诊断，不替换模型输出/异常。
- CON-9：TTFT 指标维度为实际 `gen_ai.request.model` 和既有对话操作 `gen_ai.operation.name=chat`。未知供应商/响应模型省略。不添加提示词、响应、异常正文或逐请求标识。导出配置仍由现有 MeterProvider 管理。

## 兼容与安全

本变更有意用原生 Span 边界和标准遥测替代自定义计时字段及其聚合镜像字段。调用方应查看请求/SDK Span 和标准 TTFT；不保留旧别名。应用响应与公开 Agent 调用签名不变。HTTP 中间件不缓存请求体。新增请求 Span 可能改变 Trace 父子关系。本埋点不记录异常正文。回滚需要整体还原计时、钩子、测试和文档改动。

## 验证与变更记录

测试：`tests/test_model_timing.py`、`tests/test_model_ttft.py`、`tests/models/test_model_timing_adapters.py` 以及受影响的 Runner/应用/导出器测试。覆盖原生起点/父子关系、无自定义字段/事件、实际 SDK 模式、首输出分类、失败/隐私、重试/关闭/取消、yield/任务隔离及真实内存 Histogram 数据。生产变更行覆盖率至少 95%，不得为达标新增排除。

[设计与执行证据](../../prd-spec/bugfixes/apmplus-ttft/2026-11-02-apmplus-ttft.zh.md)。仅标准字段修订取代前序自定义字段契约。历史云端结果不证明本修订；除非明确另行记录，本次验证均为本地验证。
