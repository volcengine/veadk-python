# VeIdentity MCP 逐次 Trace 上下文

[English](2026-10-27-veidentity-mcp-trace-context.md)

变更 ID：`veidentity-mcp-trace-context`；日期：2026-10-27；状态：在现有一期实现授权内批准，尚未发布。契约：[MCP 会话分派](../../../specs/mcp-session-dispatch/README.zh.md)。

## 依据、目标与边界

VeIdentityMcpTool 当前调用 session.call_tool 仅传名称与参数；原生 ADK 已通过 MCP 请求元数据发送当前 Trace 上下文。固定的 mcp==1.26.0 支持仅关键字 meta 参数。VeIdentity 重试日志还插入异常消息，可能包含私有传输／鉴权数据。

## 需求与设计

- `FR-1`：每次调用使用 TraceContextTextMapPropagator 提取当前 W3C traceparent／tracestate；不传 baggage、鉴权头、URL 或工具正文。无有效上下文时保持原无 meta 调用形式。
- `FR-2`：上下文放入每次 MCP 请求的 meta，不放入凭据 HTTP 头或会话缓存键。保留凭据解析、会话管理器、参数、返回／异常对象及原有重试一次策略；取消继续透传。
- `FR-3`：追踪提取失败不能阻断或重复业务调用；小型内部辅助模块与准备计时分开。重试日志保留函数和错误类型，不保留原异常文本。
- `FR-4`：不增加 provider／exporter、依赖、权限、资源或凭据。合成凭据仅验证此边界，不能证明真实身份提供方授权。

## 任务、评审与验收

`T-1`／`AC-1`：先补失败回归，覆盖采样／未采样父上下文、tracestate、无 Span、排除 baggage、并发隔离、原参数／请求头、追踪故障、取消及重试／异常不变；重试日志不含私有标记。

`T-2`／`AC-2`：增加内部辅助模块及局部调用／日志改动；执行身份／MCP／Agent 回归、要求的全量 Python 回归与全文件 pre-commit，同步双语契约和文档。

`T-3`／`AC-3`：本地门禁后，以合成凭据头验证真实 HTTP 接收端父 Span，并在现有隔离 Runtime 验证；SDK／依赖／29 项配置不变。真实提供方授权单独记录。

review-spec 不可用，已直接评审。用户已授权可推进的一期实现与验证，此处记录现有授权，不宣称新增人工设计审批。已评审风险：追踪标识放凭据头会破坏会话复用，全局 propagator 可能传 baggage，追踪异常可能掩盖业务异常，重试日志可能泄露凭据；请求 meta 专用辅助模块、固定 propagator 及仅类型日志对应解决。代码／测试前已核对需求与双语一致性；有证据前验证记为 not_run。

## 验证记录

- `pass`：修复前 5 failed／2 passed；修复后 141 项相关检查通过，全量 Python 回归 7,968 passed／50 skipped／4 xfailed／88 warnings，561.61 秒；Python 差异摘要未变，格式化后全文件 pre-commit 通过。
- `pass`：常规索引／类型生成后的 types:check 与文档生产构建通过；首次构建遇到此前出现的生成 server 模块为空。未修改文档站配置或依赖 lock。
- `pass`：真实本地 HTTP 的凭据解析后路径使用合成凭据，两次不同调用 Span 与接收端直接父 Span 匹配。首版样例匿名发现后再鉴权调用导致超时；将同一合成请求头及 readonly context 交给原生 header provider，恢复实际 VeIdentity 的发现／调用方式，未改变生产行为或放宽超时。
- `not_run`：该新代码的隔离云端验收；真实凭据提供方授权未证实，不能由合成样例推导。
