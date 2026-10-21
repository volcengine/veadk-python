# MPA 协作 Agent 配置

管理入口 `/api/v1/studio/collaborators`，归属来自当前 Runtime 的 `MPA_AGENT_ID`，不接受浏览器指定归属。`X-MPA-Studio-Key` 必须匹配数据库中的当前 Runtime 密钥；Studio 仅对管理员在服务端注入。GET 列表、POST 新建；PATCH/DELETE `/{id}` 和 POST `/{id}/check` 要求正整数 `revision`，DELETE 通过查询参数传递。版本冲突 409、记录缺失 404、未认证 401、缺持久化后端或 Runtime 身份 503。响应不含密钥值。

数据库新增 `mpa_collaborating_agents`，以 MPA/id 为联合主键，JSON 配置和递增版本。不提供内存降级。使用 Runtime 业务 PG。迁移仅新增，回滚保留表并部署旧二进制。旧 Studio/Runtime 的行为不变。

连接验证仅允许 HTTPS，拒绝用户信息、查询参数、fragment；显式填写 Card 地址。解析并固定 DNS，默认拒绝非公网地址，始终禁止云元数据、loopback、link-local；运维配置 `MPA_COLLABORATOR_PRIVATE_ORIGINS` 仅允许列出的 HTTPS origin 访问私网 VPC。禁用跳转和环境代理、限制超时和响应大小、验证 TLS。Card 的执行端点必须与 Card 地址同源。仅保存有界的白名单元数据，不存任意 Card JSON。明确拒绝不支持的传输和鉴权机制，本版不实现 OAuth 刷新。


[Design](../../prd-spec/features/mpa-collaborating-agents/2026-10-20-collaborating-agents.zh.md)

## 配置与联调交接

Studio 以管理员身份进入「智能体 → MPA 智能体 → 选中智能体」，在「基本信息」下点击「协作 Agent」Tab →「添加 Agent」。填写目标名称、用途、**完整 Agent Card HTTPS URL**和鉴权方式，保存后点击「验证连接」。能力由 Card 的 `skills` 读取，不需要手工复制一份能力列表。此入口仅对 MPA 显示。

Bearer/API Key 在 Studio 直接填写实际密钥，新输入默认隐藏，可临时显示；已保存密钥不回传浏览器。编辑时留空，仅当鉴权方式、请求头与目标 origin 不变时保留旧值；更换 origin 必须重新输入。选择无鉴权会清除密钥。API Key 还需填写目标要求的 `X-` 请求头。Runtime API 仍兼容旧 `MPA_COLLABORATOR_` 环境变量引用。

私网目标还需在 Runtime 配置 `MPA_COLLABORATOR_PRIVATE_ORIGINS=https://research.internal.example:443`，同时保证网络可达和可信 TLS 证书；配置允许 origin 不会自动创建 VPC、路由或放行网络。公网目标无须这个配置。当前不支持跨源 Card 执行端点、HTTP 明文、OAuth 自动刷新、云 AK/SK 请求签名和非 JSONRPC 传输。

注册请求示例（经 Studio 可信代理调用）：
```json
{
  "name": "研究助手",
  "description": "检索资料并整理依据",
  "card_url": "https://research.example/.well-known/agent-card.json",
  "enabled": true,
  "auth_type": "bearer",
  "secret": "<target-agent-token>",
  "header_name": ""
}
```
响应包含 `id`、`mpa_id`、`revision` 和 `check`。新建状态为 `not_checked`；调用 `POST /{id}/check` 并提交当前 `revision` 后返回新版本。`verified` 仅说明 Agent Card 可读取且格式受支持，不能作为远端任务执行成功的证据。修改配置会回到 `not_checked`。网络断开导致写入结果不确定时，页面要求先刷新，不盲目重复创建。

`dispatch_a2a_task` 负责人与本实现的交接点：
```python
# 使用已注入的 CollaboratorService；mpa_id 必须来自可信执行上下文。
snapshot = await service.resolve_for_dispatch(mpa_id, registration_id)
# snapshot: mpa_id / registration_id / revision / endpoint /
#           headers（仅服务端，repr 隐藏） / protocol_version
```
派发方仍须检查调用者与当前 MPA 的授权关系，在真正请求前重新做目标地址/DNS 安全检查，并自行实现 task、SSE、取消、结果和 trace。禁止把 `headers` 放进模型上下文、轨迹或 API 响应；不要直接使用不受保护的 HTTP 客户端。禁用或未验证记录解析时返回 `registration_not_ready`。本次未把登记对象注入模型，也不会使 MPA 自动调用它们。

数据库由现有 Runtime 渠道存储的 engine 承载，生产使用 Runtime 业务 PG；本地允许持久化 SQLite 文件，拒绝内存 SQLite。新增迁移 `0013_collaborating_agents.sql`，并沿用存储首次使用建表模式；受限数据库账号可由迁移账号预先执行 SQL。每条记录按当前 MPA 隔离，不新建共享目录或新 PG 实例。回滚应用时保留表，不删除注册数据。

UI 生命周期：仅在选中 Tab、目标是有 Runtime 的 MPA 且具有 admin/super_admin 权限时挂载管理器，以地域及 Runtime ID 为 key。切换 Tab、目标或权限时卸载、取消请求并丢弃临时状态。普通智能体、草稿及非管理员没有入口或请求，不支持的定位回到基本信息。聊天不再提供此入口。


## 密钥存储与兼容
`secret` 为只写字段（最多8192字符、禁止控制字符）；公开 `credential_configured` 仅表示存在配置，不证明连接成功。Runtime 将密钥值及 MPA/注册 ID 归属加密后存入 `config.encrypted_secret`，在数据库事务锁下自动生成专用密钥，持久化为 `mpa_deployment_settings.collaborator_credential_key`，无需手工配置环境变量。密钥与密文必须一起备份；丢失或损坏返回 `credential_store_unavailable`，不自动轮换。这防止响应或普通配置暴露，不隔离能够读取两个表的数据库管理员。接口不回显明文或密文，校验错误不包含原始输入，浏览器仅临时持有新输入值，不使用 local storage。新版 Studio 直接密钥输入需要升级 Runtime，先部署后端再部署页面；回滚时保留两个表，使用本版或后续兼容版本管理加密记录，旧程序不支持直接密钥。

启用控制派发资格，停用保留配置。连接验证成功不表示任务派发已实现。[直接密钥方案](../../prd-spec/features/mpa-collaborating-agents/2026-10-20-direct-credentials.zh.md)。
