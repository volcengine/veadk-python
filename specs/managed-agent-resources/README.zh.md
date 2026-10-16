# Managed Agent 资源适配器

[English](README.md)

组件 ID：`managed-agent-resources`。状态：`active`。修订：2026-10-10。
关联已批准 PRD：[managed-agents-upstream](../../prd-spec/features/managed-agents-upstream/2026-10-10-non-ui-migration.zh.md)，`FR-3`、`FR-4`、`T-2`、`AC-2`。
依赖组件：[managed-agent-runtime](../managed-agent-runtime/README.zh.md)。

## 范围与结构

迁移来源仓库的后端增量，不复制前端或 Studio 接口。Ark 请求行为放在
`veadk/models/ark_llm.py`，凭据 SDK 请求放在
`veadk/integrations/ve_identity/identity_client.py`，独立技能客户端放在
`veadk/skills/ma_infra.py`。运行时凭据解析由运行时适配器调用 IdentityClient，
不另建 SDK 客户端。保留官方已有的工作负载池、用户池辅助方法和环境配置行为。

## 行为约定

- `CON-1`：Ark 续接请求保留本次授权的工具声明；未声明工具时不增加工具权限。
- `CON-2`：默认请求不注入一小时的 `expire_at`。保留调用方显式保留时间；否则由服务端决定。
- `CON-3`：`retry_expired_response` 默认保留已有重试行为；托管运行时可以关闭重放，避免静默丢弃历史对话。
- `CON-4`：仅在 `MANAGED_AGENT_MODEL_TRACE=true` 时开启独立 JSON 元数据日志，记录模型与工具名称、
  工具选择、是否续接、事件与输出类型。排除提示词、回复正文、API Key、工具参数和续接 ID。
- `CON-5`：IdentityClient 的 API Key 查询接受可选 `pool_name`；省略时保留 SDK 默认行为。
  凭据只保存在进程内存。
- `CON-6`：技能客户端访问配置的 `/v1/skills`，携带账号与 API Key 请求头；提供同步和线程包装的异步接口。
  保留分页元数据；下载前把 `latest` 解析为具体版本；超过 32 MiB 的压缩包报错。
- `CON-7`：HTTP 与服务错误转换为带状态、错误码和可重试标志的技能异常；上传由 HTTP 库生成 multipart boundary。

## 入口、配置与状态

公开入口为 `veadk.models.ark_llm.ArkLlm`、
`veadk.integrations.ve_identity.identity_client.IdentityClient` 和
`veadk.skills.ma_infra.{MaInfraSkillConfig,MaInfraSkillsClient,MaInfraSkillError}`。
Ark 继续调用 SDK Responses API，IdentityClient 调用 Identity SDK 的
`get_resource_api_key`。例如 `client.get_api_key(provider_name="model",
agent_identity_token=token, pool_name="customer")` 选择对应凭据池。
凭据属于运行时输入，不序列化到本文。

`MaInfraSkillConfig.from_env()` 读取 `MA_SKILLS_BASE_URL`、`MA_SKILLS_API_KEY`、
`MA_SKILLS_ACCOUNT_ID`；缺少 base URL 时返回 `None`，表示未配置。
直接向客户端传配置时使用显式值。默认超时 30 秒，禁止跟随重定向。
接口包括 GET/POST `/v1/skills`、GET/DELETE `/v1/skills/{id}`，以及对应技能下的
版本与内容 GET/POST。控制面负责授权与注册表状态。客户端不持久缓存、不迁移版本、
不去重，也不自动重试写入。调用方负责 `close()` 同步 HTTP 客户端。
异步接口通过 `asyncio.to_thread` 调用同步方法；取消等待中的协程不会中断线程中的
HTTP 请求，该请求仍受超时约束。

## 安全、兼容与失败

技能请求携带配置的 API Key 与账号请求头，向控制面传递资源 ID 和压缩包内容。
下载返回 bytes，本组件不解压；运行时组件负责技能解压与临时目录清理。
Ark 日志只记录白名单元数据。SDK 与服务失败行为保持兼容；新增 Identity 池参数
转发不记录凭据。技能异常包含 `status_code`、`code`、`retryable`；网络失败映射为
可重试 502，429 和 5xx 可重试，其他 HTTP 错误不可重试。服务错误文本返回调用方，
技能客户端不记录它。32 MiB 下载上限在传输后检查，上传大小限制由服务端负责。

继续支持 Python 3.10-3.13。已有 Identity 调用省略 `pool_name` 时保留服务默认池。
Ark 默认允许过期重放，无法恢复完整历史的运行时显式关闭重放。
资源适配器不要求修改 schema 或 SDK 固定版本。

## 验收

本地测试覆盖续接工具保留、默认与显式保留时间、过期上下文直接失败、日志字段脱敏、
Identity 池参数转发、技能请求头、分页、版本固定、错误处理和异步辅助方法。
不需要云端写入或含凭据配置。

## 本地验证记录

2026-10-10，在目标代码树运行 `pytest tests/models tests/skills
tests/test_ve_identity_api_key.py tests/integrations/test_mpa_identity.py -q`，
**109 项通过**。新增回归测试先在官方基线上复现工具被删除、保留时间被覆盖和缺少池参数。
修改组件文件通过 Ruff 0.11.12 lint 和格式化检查。这里验证的是离线协议与模型行为，
未调用真实 Identity 或技能服务。

契约与测试对应：`CON-1`/`CON-2` 使用模型上下文与 expire-at 测试，
`CON-3`/`CON-4` 使用模型 fallback 与 trace 测试，`CON-5` 使用
`tests/test_ve_identity_api_key.py`，`CON-6`/`CON-7` 使用
`tests/skills/test_ma_infra_skills_client.py`。负向场景覆盖缺少配置或工具、
上下文过期、超限压缩包、服务与网络失败。2026-10-10 迁移只修改这些契约，
没有未解决的资源契约问题。云端 E2E 与真实注册表写入不属于本地验收。

最低版本验证：Python **3.10.20**，使用
`uv sync --frozen --python 3.10 --extra sandbox --extra extensions --extra dev`
建立独立环境；Anthropic **1.3.0**，Google ADK **2.2.0**。运行时、MPA Session、
模型、Skills、Identity 与飞书聚焦测试共 **356 项通过**，17 条弃用告警，耗时 24.24 秒。
新增真实 SDK transient-event 传输回归测试单独运行也通过。Python 3.10 的 SDK
GenericAlias 响应转换兼容问题已通过 transient publisher 和传输测试使用
`typing.Dict` 修复，不需改依赖固定版本或目标环境。这里验证本地协议行为，不代表云端部署。
