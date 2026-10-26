# MPA 协作 Agent：A2A 中心

[English](README.md)

## 职责与入口

Studio 管理员进入 **MPA → 协作 Agent → A2A 中心**，选择目标 Runtime 的账号/地域和空间。Runtime GET/PUT `/api/v1/studio/collaborators/registry/binding` 只持久化一个 MPA 与空间的关联，使用 revision CAS；registry/spaces、registry/agents 使用目标 Runtime 云身份查询。空间内包含未来新增的、运行中且兼容的成员由既有受控派发器发现。注册被接受不等于执行成功。

## 注册

POST `/web/a2a-agents?region=...` 是 Studio 控制面接口，不是 Runtime 工具。要求既有管理权限和 targetRuntimeId 的访问权。Runtime 来源还校验 runtimeId 权限，RuntimeConfig 包含 public/private 的 networkType。Standard 来源支持 importType=json（agentCard 对象）或 url（HTTPS cardUrl）。所有请求带 spaceId，来源字段互斥。Studio 使用既有服务端凭据签名 CreateA2aAgent，只返回 `{id}`。账号/地域权限错误明确返回；不增加 Runtime 创建权限或新依赖。

输入上限 128 KiB，校验 ID；JSON 要求 name/url/version；URL 不允许用户信息或锚点。导入 URL 由 AgentKit 抓取，Studio 不直接请求任意 URL。Card 和凭据不回显、不写日志、不在浏览器持久化；JSON 默认遮罩，可主动显示。创建不自动重试；网络、5xx、取消导致结果不明，必须先刷新核对。注册成功而刷新失败时保留成功结论并显示列表错误。切换 Runtime/地域/空间取消旧响应、清空输入；保留键盘和 IME 行为。

## 旧数据与兼容

旧本地列表、新建、修改、删除、检查接口鉴权后返回 410 `legacy_registration_retired`，删除其表单和本地写入/解析服务。Runtime 启动时不删除或迁移 `mpa_collaborating_agents` 中的旧记录；已有记录保留在库中，但不再用于发现或派发。保留其他 MPA、空间关联、会话、执行账本及共享 `collaborator_credential_key`。已发布迁移和表结构不改。升级或回滚二进制本身不会删除这些记录；未来如需清理数据，须另行批准操作。

## 既有派发安全

模型工具只接受关联空间中解析的 ID，不接受任意 URL/认证头。Harness 的 identity/scope/grant/fence/ledger/terminal 语义不变。安全传输继续限制 HTTPS、DNS/地址、TLS、禁重定向、响应大小和超时；私网来源需显式 Runtime allowlist 和网络连通性。仅兼容的 Card 协议、传输和认证可调用。Worker 与定时 Main 不新增注册或协作权限。

## 验证与设计

[注册及退役设计](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-center-registration.zh.md)。Python 路由：tests/cli/test_a2a_center_registration.py；UI：frontend/tests/collaboratingAgents.test.tsx、mpaBasicDetails.test.tsx。Runtime 退役接口测试：agentkit-mpa-agent/tests/test_collaborator_retirement.py。模拟测试、本地浏览器检查与真实云验证必须分别报告。自动清理旧数据不属于此合同。

## 空间管理（2026-10-22）

绑定和成员使用独立可访问区域。POST `/web/a2a-spaces?region=...` 要求管理员及目标 Runtime 授权，接受 `{targetRuntimeId, name, projectName?, intentEnabled?}`，签名调用 CreateA2aSpace 后返回 `{id}`。请求体上限 4096 字节；名称/项目去除首尾空白后非空、不超过 128 字符且无控制字符；项目默认 default，语义检索默认 false。拒绝未知字段及非布尔开关。创建后选中已确认的空间（当前列表页未返回时仍可选），不自动绑定。刷新失败保留已确认的创建成功状态。写入结果不明或取消后须刷新核对，才允许再次写入，不自动重试。切换 Runtime/地域取消旧请求。保留原有云身份/地域与派发边界。创建表单不管理标签或空间编辑；删除遵循下方成员操作合同。参见[空间管理设计](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-space-management.zh.md)。

仅当所选空间就是已绑定空间时提供解绑操作。切换空间清除旧确认；写入处理函数拒绝解绑与所选空间不匹配的绑定。空间资源 ID 保留在选择值和请求中，但不显示在面向用户的名称、状态及目标标签里。

## 成员操作与删除

已本地实现：[成员操作设计](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-member-actions.zh.md)。Studio 提供脱敏 GET 及经确认的 DELETE /web/a2a-agents/{agentId}，按 targetRuntimeId、spaceId 和 region 限定，返回 ID 必须匹配。DELETE /web/a2a-spaces/{spaceId} 在云删除前检查目标当前绑定、空间身份及成员列表为空。不级联、不自动解绑、不删除来源 Runtime、不自动重试写入。仅 A2A 开启结构化云错误，区分明确拒绝与结果不明；其他 helper 调用保留原行为。详情排除原始 Card、未脱敏 URL 和提供商错误。关闭在途写入须刷新核对；身份切换中止旧 UI 更新。


## 删除前置检查认证

CON-DELETE-AUTH：Runtime JSON 协作请求与专用协作代理共用仅管理员、由服务端持有的 `X-MPA-Studio-Key` 策略。浏览器凭据不能替换该 Key，无关路径不添加协作 Key。绑定读取 401/403 保持原状态并返回 `runtime_auth_failed`，不调用云接口，在 UI 中仍是可重试的明确前置失败。云权限拒绝保留独立行为。参见[认证修复](../../prd-spec/bugfixes/mpa-a2a-space-deletion/2026-10-22-runtime-auth.zh.md)。


## 端点与技能元数据

CON-ENDPOINTS：GET /web/a2a-runtime-endpoints/{sourceRuntimeId} 校验管理员及 region 中 targetRuntimeId/sourceRuntimeId 的访问权限。返回 runtimeId，每种 public/private 类型最多一个已配置、安全的 HTTP(S) URL。注册仅列当前配置类型，阻止迟到/不可用选择；Payload 仍为 RuntimeId/NetworkType，不接受任意端点 URL。

CON-CARD-VIEW：Agent 详情增加 serviceAddress（string|null）、skills（array|null）、skillsTruncated（boolean）。仅投影有界名称/描述/标签/示例/ID，不返回原始 Card 或认证内容。null 为不可用，[] 为已确认无技能；超过 100 项明确提示截断。移除 query/fragment，拒绝 userinfo、无效、控制字符及非 HTTP(S) URL。元数据解析仅影响查看，不影响注销。参见[端点与技能设计](../../prd-spec/features/mpa-collaborating-agents/2026-10-22-endpoints-and-skills.zh.md)。


## Runtime 注册选择控件

CON-RUNTIME-PICKER：Runtime 注册使用一个必选 Select，选项来自已授权的分页 Runtime 查询，不再提供独立手动 ID 字段。所选 ID 保留为内部请求值；仅当选择仍存在于当前列表且有匹配端点时才允许提交。加载、成功空列表和读取失败明确区分，空/错误支持重试，追加分页保留选择。Standard 导入和后端 API 不变。参见[单一选择修复](../../prd-spec/bugfixes/mpa-a2a-runtime-picker/2026-10-22-single-runtime-picker.zh.md)。

## 2026-10-22 Agent alias correction

已注册 Agent 别名属于当前 MPA 业务库，按 MPA/地域/空间/Agent 隔离；列表、发现和 @名称解析读取相同数据，不依赖 SHARED_APIG_DATABASE_URL 或 AGENTKIT_ACCOUNT_ID。Studio 保留 revision CAS 和所有者鉴权，仅放行绑定与 Agent ID 合法的精确别名 PUT。旧 Runtime 未声明能力时禁用并提示升级；共享别名不自动导入；中心名称和 Card 不变。参见[设计](../../prd-spec/bugfixes/mpa-agent-alias/2026-10-22-agent-alias-business-store.zh.md).
