# MPA Runtime 集成加固与 Studio 诊断能力

- **Change ID：** `mpa-runtime-integration-hardening`
- **状态：** 已批准实施
- **创建 / 修订日期：** 2026-09-12
- **变更类型：** Bug 修复及用户可见诊断扩展
- **English version:** [2026-09-12-mpa-runtime-integration-hardening.md](2026-09-12-mpa-runtime-integration-hardening.md)
- **受影响组件：** [MPA Runtime Provisioning](../../../specs/mpa-runtime-provisioning/README.zh.md)、[Studio Runtime Diagnostics](../../../specs/studio-runtime-diagnostics/README.zh.md)

## 1. 背景与证据

`veadk mpa create` 创建的 mpa-agent 不依赖 ArkClaw 控制面资源，而是明确使用兼容值 `CLAW_SPACE_ID=csi-<account_id>`、外部 PostgreSQL 和外部 OpenViking。Runtime 日志仍显示 `arkclaw:ListResources` 每 120 秒返回一次 `403 AccessDenied`，普通 A2A Session 启动时也会调用一次。已确认调用点为 `McpToolsCache._load_candidate_resources()` 和 `SessionService._query_appcenter_mcp_ids()`。异常被捕获后聊天仍能继续，但 ArkClaw MCP 发现不可用，且完整堆栈持续污染日志。

同一次真实运行还证明了四个相邻的集成缺陷：

1. Runtime 第二阶段更新只写入 `A2A_PUBLIC_URL`，没有把真实 key-auth 凭据写为 `CODEX_MCP_RUNTIME_API_KEY`，因此内置 MCP 源警告 worker 调用可能被拒绝。
2. `IDENTITY_STARTUP_ENABLED=false` 跳过了启动期身份元数据加载，但 lazy sandbox login 仍然开启。Sandbox 回合尝试生成登录链接并记录 `IdentityConfig.UserPoolConfig missing fields: user_pool_id`。
3. Sandbox 进度的首个 artifact update 使用 `append=true`。A2A SDK 因 artifact 尚不存在而拒绝每个 chunk：`Received append=True for nonexistent artifact index ... Ignoring chunk.` Worker 最终完成，但渐进工具输出丢失。
4. Runtime `r-yeuujrrcowb21078p9jh` 返回 `apmplus_enable=false`；Studio 的 `/web/runtime-trace` 正确返回 404，无法展示 Span。

另有两个 Studio 缺口已经验证。Runtime 日志服务只请求 500 行，而 UI 承诺 1,000 行，且弹窗没有下载入口。A2A sandbox 的 `usage.updated` 已到达桥接层，但 `A2AStreamDecoder` 未将其映射为 Studio `usageMetadata`，现有 Token 指示器因此无法统计。

当前也不支持按会话选择模型。主 Agent 从持久化 Agent 记录或 Runtime 环境解析模型，而 Codex 委托使用独立的 `modelOverride`。若没有统一的请求级契约就增加选择器，会导致同一回合使用两个不同模型。

## 2. 目标

- `FR-1`：VeADK 创建的 Runtime 未采用 ArkClaw 资源发现模型时，不得调用 ArkClaw `ListResources`；原生 ArkClaw 部署保持当前默认行为。
- `FR-2`：第二阶段部署必须把已解析的公网 URL 和 Runtime key 原子发布到 Runtime 环境，且不得在输出或源码产物中泄露 key。
- `FR-3`：VeADK 模式没有用户池时，不得尝试用户池登录。
- `FR-4`：首个 sandbox artifact update 必须创建 artifact；后续更新才可 append，并保持事件顺序和去重。
- `FR-5`：Runtime 日志保持实时刷新，展示最近 1,000 行脱敏日志，并允许用户下载当前同一份脱敏快照。
- `FR-6`：Studio 必须复用现有 Token 统计 UI 展示 mpa-agent 主模型和委托 worker 用量，不得重复累计快照。
- `FR-7`：Studio 可为单次对话回合选择允许的模型。覆盖值必须一致作用于主 Agent 与委托 worker，不暴露凭据；未设置时回退到配置默认值。
- `FR-8`：`veadk mpa create` 默认开启 AgentKit Runtime 的 APMPlus 链路观测；Studio 保留现有未开启、采集中、无权限、就绪和失败状态。
- `FR-9`：可选控制面配置缺失应避免输出完整 warning 堆栈；非预期基础设施故障仍须可见。

## 3. 非目标

- 给合成兼容 Space 授予 `arkclaw:ListResources`，或创建 ArkClaw 用户池。
- 删除 `CLAW_SPACE_ID`、改变 PostgreSQL/OpenViking 归属或改变 APIG key-auth。
- 下载无限历史日志；Runtime 只提供有界快照。
- 把模型 API Key 发送给浏览器，或允许请求传入任意 Endpoint/Provider 凭据。
- 改变原生 ArkClaw 部署行为。

## 4. 场景

1. **外部资源 Runtime：** 给定 VeADK 创建的 Runtime，当缓存刷新或 Session 解析 MCP 源时，不发送 AppCenter 请求，也不记录 `ListResources` 警告。
2. **内置 MCP：** 给定 key-auth Runtime，当 Codex 调用内置 MCP Endpoint 时，内部请求头使用第二阶段写入的 Runtime key。
3. **无身份池：** 给定 `IDENTITY_STARTUP_ENABLED=false`，当回合委托给 sandbox 时，不尝试登录 URL，并使用配置的共享凭据继续执行。
4. **Sandbox 进度：** 给定首个规范化 worker 事件，当通过 A2A 中继时，首个 artifact update 使用 `append=false`；后续使用 `append=true` 且均可被 Studio 展示。
5. **日志：** 给定已解析的 Runtime 实例，当日志刷新时，Studio 替换有界快照、最多保留 1,000 行，并以确定的 `.log` 文件名下载相同文本。
6. **用量：** 给定主模型 ADK 用量或 worker `usage.updated`，当 Studio 收到事件时，现有指示器只对每次权威更新统计一次当前值和累计值。
7. **模型覆盖：** 给定 Studio 选择了允许模型，当发送消息时，BFF 将模型 ID 放入 A2A metadata，mpa-agent 按请求同时应用于主模型解析和委托 worker；非法或不可用 ID 在模型执行前失败。
8. **链路：** 给定新部署 Runtime 且具备 APMPlus 读取权限，当打开已完成 Session 的链路时，Studio 从采集中进入 Span 树；缺少权限仍明确返回 403，而不是伪装为空数据。

## 5. 设计

### 5.1 部署模式与凭据

复用窄粒度开关，不引入宽泛的部署模式枚举：

- VeADK 环境设置 `APPCENTER_RESOURCE_DISCOVERY_ENABLED=false`。mpa-agent 新增该配置，原生默认值为 `true`；它同时控制 Session fallback 查询以及传给 `McpToolsCache` 的 AppCenter 依赖。`MCP_TOOLS_CACHE_ENABLED` 继续开启，使显式缓存或非 AppCenter 来源仍可受益。
- 在 `IDENTITY_STARTUP_ENABLED=false` 的同时设置 `MPA_LAZY_LOGIN=false`，避免不带用户池的 Runtime 进入 lazy login 路径。
- 默认设置 `APMPLUS_TRACE_CONTENT=false`，保留 Span 时序和结构化详情，但不导出原始 Prompt/Response。
- Runtime 第二阶段合并 `A2A_PUBLIC_URL` 和 `CODEX_MCP_RUNTIME_API_KEY=<resolved key>` 后调用 `UpdateRuntime(ReleaseEnable=True)`；VeFaaS 第二阶段写入相同键值。Runtime key 加入 secret redaction 集合。
- Runtime 创建及复用更新时传入 `ApmplusEnable=true`。这是 Runtime 控制面字段，不是环境变量。

相比授予 ArkClaw 权限（资源模型错误）或仅降低日志级别（仍会进行无效调用并保留功能缺口），该方案解决根因。

### 5.2 可选配置缺失

资源发现关闭时，mpa-agent 依赖构造向下传递 `appcenter_client=None`。`SessionService` 与 `McpToolsCache` 已将 `None` 视为不发现。Sandbox 脱敏配置查询将 `AgentNotFound` 视为 Agent 配置缺失的预期情况，以 debug/info 级回退；传输或数据库错误仍保留 warning 堆栈。

`/list-apps` 与 `/web/agent-info/a2a-default` 的兼容性 404 是 Studio 在成功回退 A2A agent-card 前进行的旧协议探测，不是 Runtime 故障。本次不增加伪造路由；后续日志分类可降低这些已知探测 404 的告警等级，但不改变响应语义。

### 5.3 A2A artifact 顺序

`relay_codex_event` 保存请求级状态：首个 `sandbox-<invocation_id>` artifact 使用 `append=false`，后续事件使用 `append=true`。事件 ID 继续作为去重键。只有 enqueue 成功后才推进状态，避免首个 enqueue 失败后后续事件追加到不存在的 artifact。

### 5.4 日志与下载

`RuntimeLogService.read_logs()` 请求 `Limit=1000`，脱敏后限制为最后 1,000 个逻辑行。SSE 继续每秒替换快照而非拼接。弹窗下载按钮从当前渲染快照创建 UTF-8 Blob，本地下载后立即回收 Object URL；无日志时禁用。不新增云端接口，也不扩大授权范围。

### 5.5 Token 用量投影

A2A 桥接层把两类来源映射到现有 ADK 事件字段：

- A2A `metadata.adk_usage_metadata` 映射为投影事件的 `usageMetadata`。
- Sandbox `usage.updated` 将 worker 字段（`inputTokens`、`outputTokens`、`totalTokens`、`cachedTokens`、`reasoningTokens`、`modelId`）映射为现有 camel-case ADK usage/model 字段。

Decoder 按 `(source, requestId/model)` 记录最后一次权威用量快照，只向累计统计发出正向增量，避免重复的 A2A 累计状态快照放大总量。现有 `addTokenUsageFor()` 和 `TokenUsageIndicator` 继续作为唯一展示所有者。

### 5.6 模型选择

首版采用 allowlist 请求级覆盖，而非修改 Runtime：

- mpa-agent agent card 通过新的非敏感 `MPA_SELECTABLE_MODELS` JSON/CSV 环境值，加上配置默认模型，发布模型 ID。
- Studio 仅在 A2A 虚拟 App 且广告模型多于一个时展示选择器。选择保存在 Session 本地，回合运行时禁用。
- `runSSE` 在 `custom_metadata` 中发送 `modelId`；A2A BFF 作为请求 metadata 转发。
- mpa-agent 校验模型 ID、写入 `InvocationContext`；`ModelEndpointResolver` 在当前请求优先使用它，同时保留配置的 provider/base URL/API key。Codex 委托接收同一个 `modelOverride.modelId`。
- Session 及其他渠道没有显式允许覆盖时继续使用配置默认值，不进行全局环境更新。

如果已部署模型 Endpoint 不能用相同凭据和 Base URL 支持多个模型 ID，则只广告默认模型并隐藏选择器。

### 5.7 链路观测

部署传入 `ApmplusEnable=true` 并等待新版本 Ready。现有 `/web/runtime-trace` 授权与规范化逻辑保持不变。验证区分：

- 404：Runtime 未开启链路（配置缺陷）；
- 425：链路仍在采集（可重试）；
- 403：Studio 凭据缺少 `APMPlusServerReadOnlyAccess`（权限阻塞）；
- 200：`TraceDrawer` 展示规范化 Span。

## 6. 安全、兼容与失败语义

- 所有新开关默认保持原生 mpa-agent 行为，仅 `veadk mpa create` 退出 ArkClaw 发现和登录。
- Runtime API Key 仅位于服务端，在 dry-run/输出中脱敏，不写入 agent-card metadata 或浏览器 Payload。
- 日志下载内容与 UI 当前可见的已脱敏 1,000 行快照完全相同。
- 模型覆盖只包含 ID 且必须匹配服务端广告 allowlist，不能改变 Provider、URL 或 Secret。
- 第二阶段更新失败为致命错误，因为部分配置的 Runtime 无法安全暴露内置 MCP。错误保留已创建资源 ID 供恢复，但不包含 Key。
- 除非显式覆盖，APMPlus 内容追踪保持关闭；开启链路不等同于授权 Studio 读取。

## 7. 实施任务

| ID | 工作 | 主要文件 | 依赖 |
| --- | --- | --- | --- |
| `T-1` | 在 mpa-agent 增加发现边界和预期缺失处理 | `app/core/config.py`、`app/api/deps.py`、`app/integrations/agentkit_sandbox.py` | 无 |
| `T-2` | 修正首个 A2A artifact append 语义 | `app/a2a/executor.py`、`tests/test_a2a_executor.py` | 无 |
| `T-3` | 注入 VeADK 模式环境/key 并开启 Runtime APMPlus | `mpa_provision.py`、`mpa_runtime.py`、`cli_mpa.py` | `T-1` |
| `T-4` | 对齐 1,000 行快照并增加下载 | `runtime_logs.py`、`RuntimeLogsDialog.tsx`、i18n/测试 | 无 |
| `T-5` | 投影权威 Token 用量 | `runtime_a2a_stream.py`、Token 投影测试 | `T-2` |
| `T-6` | 增加 allowlist 请求级模型选择 | mpa-agent invocation/model/A2A 文件；Studio BFF/client/composer | `T-3` |
| `T-7` | 验证真实链路和端到端行为 | Runtime/Studio 真实检查 | `T-1`–`T-6` |

## 8. 测试与验收

| 需求 | 验收标准 | 验证方式 | 初始结果 |
| --- | --- | --- | --- |
| `FR-1`、`FR-3` | VeADK 模式不调用 AppCenter/用户池；原生默认保持 | mpa-agent 配置/依赖/Session 测试及跨两个刷新周期的真实日志 | 单元测试 `pass`；新镜像真实验证 `not_run` |
| `FR-2` | 第二阶段请求包含 URL 与 key；输出不泄漏 key | `tests/integrations/test_mpa_runtime.py`、`test_mpa_provision_env.py`、CLI 测试 | `pass` |
| `FR-4` | 首个 artifact 创建，后续 append，全部到达 | `tests/test_a2a_executor.py` 及真实 sandbox 回合 | 单元测试 `pass`；新镜像真实验证 `not_run` |
| `FR-5` | 1,000 行有界实时视图与一致下载 | Runtime 日志后端/前端测试及浏览器检查 | 自动测试/构建 `pass`；浏览器检查因缺少 Playwright 浏览器而 `blocked` |
| `FR-6` | 主模型和 worker 用量只显示一次，刷新后保持一致 | Decoder/Token 测试及真实 Runtime 回合 | 自动测试 `pass`；新镜像真实验证 `not_run` |
| `FR-7` | 允许覆盖到达两条路径；非法 ID 被拒绝；默认不变 | mpa-agent 单元/集成测试及 Studio 浏览器测试 | 自动测试 `pass`；新镜像真实验证 `not_run` |
| `FR-8` | 新建/更新 Runtime 开启 APMPlus，TraceDrawer 获得 200 或报告外部 403 权限阻塞 | Runtime 测试及真实 `/web/runtime-trace` | Runtime 请求测试 `pass`；当前版本 31 仍为 `fail`（已验证 404 未开启）；未执行部署 |

仓库必需检查包括目标 Python 测试、`npm --prefix frontend test`、`npm --prefix frontend run build`、变更 Python 文件 Ruff/Pyright、适用的更广 Python 回归、浏览器验证及 pre-commit。真实云验证与模拟测试分开记录。

## 9. 评审记录

方案评审在实现前发现并解决以下阻塞项：

- **模式开关过宽：** 改为窄粒度 `APPCENTER_RESOURCE_DISCOVERY_ENABLED`，保留独立缓存及原生默认值。
- **Secret 泄露风险：** 模型选择只携带 ID；第二阶段 Key 保持服务端且加入脱敏集合。
- **Token 重复统计：** 定义权威快照/增量规范化，而不是直接转发累计值。
- **链路与隐私歧义：** 将 `ApmplusEnable=true` 与 `APMPLUS_TRACE_CONTENT=false` 分离。
- **Artifact 竞态：** 仅在首次 enqueue 成功后推进 artifact 状态。
- **日志下载无界：** 下载内容严格等于当前已脱敏 1,000 行快照。

当前无未解决的设计阻塞项。用户明确要求分析并修复已报告异常，同时增加列出的诊断能力，记录为本范围的实施批准。任何更广的鉴权、控制面或模型凭据变更均需重新评审。
