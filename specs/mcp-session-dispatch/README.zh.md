# MCP 会话分派

[English](README.md)

组件 ID：`mcp-session-dispatch`；状态：已实现；修订：2026-10-27。

## 职责与接口

`TrustedMcpToolset` 选择工具，`TrustedMcpSessionManager.create_session(headers=None)` 分派传输。普通 MCP 会话池、原生缓存元数据和生命周期由 Google ADK 负责，已有 TrustedMCP 分支负责厂商传输选择。本组件不授予鉴权权限、不定义业务 Task 状态、不实现 Sandbox 执行。

## 契约

- `CON-1`：普通 Streamable HTTP、SSE、stdio 在获取自定义锁前委托 Google ADK；不复制父类池结构，也不重复获取父类锁。
- `CON-2`：仅 Streamable HTTP 且合并后的标记严格为 `x-trusted-mcp=true` 时选择厂商分支；保留输入字典、鉴权头和既有厂商行为。
- `CON-3`：保留父类的异常、取消、并发和清理语义；不新增超时、重试或配置默认值。
- `CON-4`：初始化日志仅暴露传输类名，不记录连接对象、请求头或完整 URL；凭据不作为诊断证据。

公共签名、依赖范围、凭据来源和持久化数据结构均不变。两种模式沿用既有管理器状态，普通会话元数据仍由父类维护。mock 测试不证明真实厂商兼容性，本文不作此承诺；Trace 关联与传输成功分别验证。

## 验证与变更记录

[缺陷设计](../../prd-spec/bugfixes/mcp-session-delegation/2026-10-27-standard-mcp-session-delegation.zh.md) 负责需求、验收和交付证据。`CON-1/3` 对应有超时的普通委托／并发／取消回归；`CON-2` 对应现有厂商选择与缓存回归；`CON-4` 对应使用合成密钥的构造日志回归。使用已有授权接收端核验真实发现／调用／关闭，不调用模型、不新建云资源、不持久化凭据。契约已在测试分支实现并验证；接收端云端关联的剩余工作见配对设计。

私有 `_create_client` 适配对普通连接原样透传原生位置参数和关键字传输参数，包括父类提供的 mTLS 传输对象及会话元数据。

## 准备计时契约扩展

- `CON-5`：`mcp.tools.prepare` 与内嵌 `mcp.session.acquire` 是 INTERNAL 观测边界，不能相加或作为纯网络耗时；原生会话池、工具缓存及重试仍由 ADK／厂商分派负责。
- `CON-6`：新增属性只含固定阶段／传输类别及错误类型，不含消息、连接数据或工具正文；恢复 OTel 父上下文，遥测失败不重复或阻止业务调用。

[准备计时设计](../../prd-spec/features/mcp-preparation-timing/2026-10-27-mcp-preparation-timing.zh.md) 负责验收与交付。本次扩展已批准实施；既有 CON-1/4 保持已实现状态。

## Agent 所属原生准备计时扩展

已批准扩展 [mcp-preparation-native-extension](../../prd-spec/features/mcp-preparation-timing/2026-10-27-mcp-preparation-native-extension.zh.md)：VeADK Agent 组装的原生与 VeIdentity 实例保留原管理器、回调、鉴权、缓存和重试语义，增加准备／获取计时。实例绑定须幂等并保留 deepcopy 对象归属，Trusted 不得重复计时；实例适配及 Agent 组装已通过本地回归，原生云端验收仍待完成。

## VeIdentity 请求 Trace 上下文扩展

已批准[VeIdentity 逐次上下文](../../prd-spec/bugfixes/veidentity-mcp-trace-context/2026-10-27-veidentity-mcp-trace-context.zh.md)：仅当前 W3C 上下文放请求 meta，凭据头和缓存键不变。保留无上下文行为、提取故障隔离、取消与重试次数；日志只记录错误类型，不记录私有异常消息。实现及本地回归／HTTP 检查通过，隔离云端验收待完成。
