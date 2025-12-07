---
title: 埋点字段说明
---

## 埋点时机

为适配 Google ADK 埋点规范，VeADK 中的埋点时机与 Google ADK 保持一致，主要在以下几个时机进行埋点：

- [调用 Agent 时](https://github.com/google/adk-python/blob/v1.17.0/src/google/adk/runners.py#L373)：在 Runner 的 `_run_with_trace` 函数中埋点，Span 名称为 `invocation`
- [运行 Agent 时](https://github.com/google/adk-python/blob/v1.17.0/src/google/adk/agents/base_agent.py#L285)：在 Agent 的 `run_async` 函数中埋点，Span 名称为 `invoke_agent {agent.name}`
- [调用模型时](https://github.com/google/adk-python/blob/v1.17.0/src/google/adk/flows/llm_flows/base_llm_flow.py#L728)：在 BaseLlmFlow 的 `_call_llm_with_tracing` 函数中埋点，Span 名称为 `call_llm`
- [调用工具时](https://github.com/google/adk-python/blob/v1.17.0/src/google/adk/flows/llm_flows/functions.py#L308)：在 BaseLlmFlow 的 `_execute_single_function_call_async` 函数中埋点，Span 名称为 `execute_tool {tool.name}`

在每个时机时，都会创建对应名字的 Span，用于记录该时机的详细信息。当某阶段结束时，会调用对应的打点函数，将该阶段的信息记录到 Span 中：

- Google ADK [打点文件](https://github.com/google/adk-python/blob/v1.17.0/src/google/adk/telemetry/tracing.py)
- VeADK [打点文件](https://github.com/volcengine/veadk-python/blob/main/veadk/tracing/telemetry/telemetry.py)

## 埋点字段说明

VeADK 的 Span 属性命名和值规范遵循 [OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/) 社区以及火山引擎 CozeLoop、APMPlus 等产品要求。VeADK 中的 Span 属性主要分为三类：

- 通用类：在所有类型的 Span 中存在
- LLM 类：在 `call_llm` Span 中存在
- Tool 类：在 `tool_call` Span 中存在

!!! note "埋点字段注意事项"
    由于 OpenTelemetry 社区对生成式 AI 的字段规范还在发展完善中，因此部分字段含义可能会发生变化。

### 通用类

| 序号 | 埋点字段名 | 含义 | 注释 |
| - | - | - | - |
| 1  | `gen_ai.system` | 生成式 AI 系统提供商名称，用于识别模型提供方 |  缺省值为 `<unknown_model_provider>` |
| 2  | `gen_ai.system.version` | VeADK 框架版本号，用于版本追踪与兼容性分析 | 固定返回 `veadk.version.VERSION` |
| 3  | `gen_ai.agent.name` | Agent 名称，用于区分不同实例 | 缺省值为 `<unknown_agent_name>` |
| 4  | `openinference.instrumentation.veadk` | VeADK 的 OpenInference 标准化埋点版本标识 | 固定返回 `veadk.version.VERSION` |
| 5  | `gen_ai.app.name` | Agent 系统中的 `app_name` | 缺省值为 `<unknown_app_name>` |
| 6  | `gen_ai.user.id` | Agent 系统中的 `user_id` | 缺省值为 `<unknown_user_id>` |
| 7  | `gen_ai.session.id` | Agent 系统中的 `session_id` | 缺省值为 `<unknown_session_id>` |
| 8  | `agent_name` | Agent 名称 | 同 `gen_ai.agent.name`，用于 CozeLoop 平台 |
| 9  | `agent.name` | Agent 名称 | 同 `gen_ai.agent.name`，用于 TLS 平台 |
| 10 | `app_name` | Agent 系统中的 `app_name` | 同 `gen_ai.app.name`，用于 CozeLoop 平台 |
| 11 | `app.name` | Agent 系统中的 `app_name` | 同 `gen_ai.app.name`，用于 TLS 平台 |
| 12 | `user.id` | Agent 系统中的 `user_id` | 同 `gen_ai.user.id`，用于 CozeLoop 平台、TLS 平台 |
| 13 | `session.id` | Agent 系统中的 `session_id` | 同 `gen_ai.session.id`，用于 CozeLoop 平台、TLS 平台 |
| 14 | `cozeloop.report.source` | Trace 数据来源标识 | 固定返回 `veadk`，表示来自 VeADK 框架，用于 CozeLoop 平台 |
| 15 | `cozeloop.call_type` | CozeLoop 调用类型 | 缺省值为 `None` |

### LLM 类

| 序号 | 埋点字段名 | 含义 | 注释 |
| - | - | - | - |
| 1  | `gen_ai.request.model` | 模型名称，用于识别调用的具体模型 | 从 `params.llm_request.model` 获取；缺省值为 `<unknown_model_name>` |
| 2  | `gen_ai.request.type` | LLM 请求类型，标识交互方式 | 固定返回 `chat`，表示对话式交互 |
| 3  | `gen_ai.request.max_tokens` | 所配置的响应最大生成 token 数 | 从 `params.llm_request.config.max_output_tokens` 获取 |
| 4  | `gen_ai.request.temperature` | 采样温度参数，控制生成随机性 | 从 `params.llm_request.config.temperature` 获取 |
| 5  | `gen_ai.request.top_p` | 云上推理时的 top-p 参数 | 从 `params.llm_request.config.top_p` 获取 |
| 6  | `gen_ai.request.functions` | 请求中定义的函数/工具元数据 | 提取每个工具的名称、描述及参数定义，用于 CozeLoop 平台 |
| 7  | `gen_ai.response.model` | 实际响应使用的模型名称 | 与请求模型一致时表示正常返回 |
| 8  | `gen_ai.response.stop_reason` | 响应生成停止原因 | 当前返回占位符 `<no_stop_reason_provided>`，待后续实现 |
| 9  | `gen_ai.response.finish_reason` | 响应完成原因 | 当前返回占位符 `"<no_finish_reason_provided>"`，用于区分自然结束/截断等情况 |
| 10 | `gen_ai.is_streaming` | 是否为流式响应 | 返回 `None` |
| 11 | `gen_ai.operation.name` | 操作名称 | 固定返回 `chat`，用于统一标识操作类型 |
| 12 | `gen_ai.span.kind` | Span 类型 | 固定返回 `llm`，符合 OpenTelemetry 语义约定 |
| 13 | `gen_ai.prompt` | 请求输入内容结构化信息 | 按消息顺序记录角色、内容、函数调用、图片等输入 |
| 14 | `gen_ai.completion` | 模型响应内容结构化信息 | 记录模型生成的文本、函数调用等输出内容 |
| 15 | `gen_ai.usage.input_tokens` | 输入 token 数量 | 从 `params.llm_response.usage_metadata.prompt_token_count` 提取 |
| 16 | `gen_ai.usage.output_tokens` | 输出 token 数量 | 从 `params.llm_response.usage_metadata.candidates_token_count` 提取 |
| 17 | `gen_ai.usage.total_tokens` | 总 token 数量 | 从 `params.llm_response.usage_metadata.total_token_count` 提取 |
| 18 | `gen_ai.usage.cache_creation_input_tokens` | 缓存创建所用 token 数量 | 从 `params.llm_response.usage_metadata.cached_content_token_count` 提取 |
| 19 | `gen_ai.usage.cache_read_input_tokens` | 缓存读取所用 token 数量 | 从 `params.llm_response.usage_metadata.cached_content_token_count` 提取 |
| 20 | `gen_ai.messages` | 完整对话消息事件 | 包括系统指令、用户消息、工具响应和助手回复的结构化事件序列 |
| 21 | `gen_ai.choice` | 模型选择事件 | 表示模型生成的候选响应（含函数调用或文本内容） |
| 22 | `input.value` | 完整 LLM 请求体 | *（供调试使用）*序列化输出请求对象 |
| 23 | `output.value` | 完整 LLM 响应体 | *（供调试使用）*序列化输出响应对象 |

### Tool 类

| 序号 | 埋点字段名 | 含义 | 注释 |
| - | - | - | - |
| 1  | `gen_ai.operation.name` | 操作名称 | 固定返回 `execute_tool`，统一标识工具调用操作 |
| 2  | `gen_ai.tool.name` | 工具名称 | 从 `params.tool.name` 获取；若无则为 `<unknown_tool_name>`，用于 TLS 平台 |
| 3  | `gen_ai.tool.input` | 工具输入内容 | JSON 序列化包含：`name`、`description`、`parameters`，用于记录工具调用参数，用于 TLS 平台 |
| 4  | `gen_ai.tool.output` | 工具输出内容 | JSON 序列化包含：`id`、`name`、`response`，记录工具执行结果，用于 TLS 平台 |
| 5  | `cozeloop.input` | 工具输入 | 同 `gen_ai.tool.input`，用于 CozeLoop 平台 |
| 6  | `cozeloop.output` | 工具输出 | 同 `gen_ai.tool.output`，用于 CozeLoop 平台 |
| 7  | `gen_ai.span.kind` | Span 类型 | 固定返回 `tool`，遵循 OpenTelemetry 语义约定，用于 APMPlus 平台 |
| 8  | `gen_ai.input` | 工具输入 | 同 `gen_ai.tool.input`，用于 APMPlus 平台 |
| 9  | `gen_ai.output` | 工具输出 | 同 `gen_ai.tool.output`，用于 APMPlus 平台 |
