# 按 MPA 管理协作 Agent

> 以下凭据输入/存储决策已由 2026-10-20 direct-credentials 方案取代；其他注册行为保持。

日期：2026-10-20。状态：已实现，本地验证见下文，未发布。

## 授权与范围
用户已授权为指定 MPA 注册其他 Agent，并明确要求本次包含 Studio 配置页面。范围包含新增管理 API 和持久化。任务派发、流式事件回收、目标 Agent 部署、Main/Worker 改动和 `dispatch_a2a_task` 由其他负责人实现，本次不做。

## 现状与目标
Runtime 的 subagent binding 是 Worker 执行句柄，不是外部 Agent 注册信息。Studio 已有 Runtime 访问授权和服务端注入凭据的代理，复用该边界。不建立全局目录，不在 MPA 间自动共享。

## 需求与任务
- R1/T1：按 MPA 持久化协作 Agent 的名称、描述、Agent Card URL、启用开关、鉴权配置、版本；支持增删改查。删除仅解除关联，不删除目标 Agent。
- R2/T2：显式连接验证，有界读取 A2A Agent Card，记录名称、描述、技能、端点和协议版本。验证通过只代表发现成功，不代表任务执行成功。修改使原验证失效；并发编辑和验证采用版本条件更新。
- R3/T3：支持无认证、Bearer 和 API Key，密钥引用限定为 Runtime 中 `MPA_COLLABORATOR_` 前缀的环境变量。密钥值不进入数据库、响应、浏览器持久化或日志；缺失时报错。通过现有 Runtime 环境变量管理配置密钥，本版不新建密钥库、不接受明文密钥输入。
- R4/T4：选中 MPA 的 Studio 信息面板打开配置，支持加载、空状态、错误重试、新建、编辑、启停、验证和确认移除。切换 Runtime 关闭并取消请求，过期响应不能覆盖新选择。旧 Runtime 的 404 明确提示升级，不伪装为空列表。与渠道管理一致，仅管理员可管理。
- R5/T5：服务端内部 `resolve_for_dispatch(mpa_id, registration_id)` 仅对启用且验证通过的记录返回不可变配置快照，解析当前密钥引用；不发起任务，不通过 HTTP 暴露密钥。派发方仍需校验调用者权限，并在实际执行时再次使用受保护的传输。

## 契约
管理入口 `/api/v1/studio/collaborators`，归属来自当前 Runtime 的 `MPA_AGENT_ID`，不接受浏览器指定归属。`X-MPA-Studio-Key` 必须匹配数据库中的当前 Runtime 密钥；Studio 仅对管理员在服务端注入。GET 列表、POST 新建；PATCH/DELETE `/{id}` 和 POST `/{id}/check` 要求正整数 `revision`，DELETE 通过查询参数传递。版本冲突 409、记录缺失 404、未认证 401、缺持久化后端或 Runtime 身份 503。响应不含密钥值。

数据库新增 `mpa_collaborating_agents`，以 MPA/id 为联合主键，JSON 配置和递增版本。不提供内存降级。使用 Runtime 业务 PG。迁移仅新增，回滚保留表并部署旧二进制。旧 Studio/Runtime 的行为不变。

连接验证仅允许 HTTPS，拒绝用户信息、查询参数、fragment；显式填写 Card 地址。解析并固定 DNS，默认拒绝非公网地址，始终禁止云元数据、loopback、link-local；运维配置 `MPA_COLLABORATOR_PRIVATE_ORIGINS` 仅允许列出的 HTTPS origin 访问私网 VPC。禁用跳转和环境代理、限制超时和响应大小、验证 TLS。Card 的执行端点必须与 Card 地址同源。仅保存有界的白名单元数据，不存任意 Card JSON。明确拒绝不支持的传输和鉴权机制，本版不实现 OAuth 刷新。

## 方案审查
已核对归属、凭据、SSRF/跳转/DNS 重绑定、取消、跨 MPA、过期结果、旧 Runtime 兼容及双语一致性。复用现有依赖。Runtime 注册接口与 Studio 代理分别测试鉴权。frontend/SPEC.md 引用的 UI skills 在本 checkout 和本地 skills 目录均缺失，直接遵循已有组件及 Foundation 规范。不会假接执行器。

## 验收与验证
| 需求 | 证据 | 状态 |
| --- | --- | --- |
| R1 | 持久化隔离、重启、版本冲突与删除测试 | 本地已验证 |
| R2/R3 | 无效 Card、SSRF、鉴权、超时、脱敏和过期验证测试 | 本地已验证 |
| R4 | Studio 代理/UI 测试、前端 test/build 和浏览器检查 | 本地已验证 |
| R5 | 内部快照启用/版本/鉴权测试 | 本地已验证 |
Runtime 必跑 `make lint`、`make test`；Studio 相关 Python 测试/Ruff/Pyright、`npm --prefix frontend test`、`npm --prefix frontend run build`。实际结果记录如下。本次实现请求不包含生产发布、云资源改动或真实第三方凭据测试。

## 配置与联调交接

Studio 以管理员身份选中一个 MPA，在会话侧边的 MPA 信息面板点击「协作 Agent」→「添加 Agent」。填写目标名称、用途、**完整 Agent Card HTTPS URL**和鉴权方式，保存后点击「验证连接」。能力由 Card 的 `skills` 读取，不需要手工复制一份能力列表。此入口仅对 MPA 显示。

例如目标使用 Bearer：先由运维通过 Runtime 环境变量配置 `MPA_COLLABORATOR_RESEARCH`，页面只填这个变量名。使用 API Key 时还需填写目标要求的 `X-` 请求头名。实际密钥不经过 Studio 表单。更新环境变量后需要按 Runtime 平台方式重新发布/重启使变量生效，然后重新验证。

私网目标还需在 Runtime 配置 `MPA_COLLABORATOR_PRIVATE_ORIGINS=https://research.internal.example:443`，同时保证网络可达和可信 TLS 证书；配置允许 origin 不会自动创建 VPC、路由或放行网络。公网目标无须这个配置。当前不支持跨源 Card 执行端点、HTTP 明文、OAuth 自动刷新、云 AK/SK 请求签名和非 JSONRPC 传输。

注册请求示例（经 Studio 可信代理调用）：
```json
{
  "name": "研究助手",
  "description": "检索资料并整理依据",
  "card_url": "https://research.example/.well-known/agent-card.json",
  "enabled": true,
  "auth_type": "bearer",
  "secret_env": "MPA_COLLABORATOR_RESEARCH",
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

## 验证记录（2026-10-20）

- Runtime：Python 3.12；新增注册模块定向 **23 passed**，包括真实 PostgreSQL 16 的迁移 SQL、连接重建持久化、跨 MPA 隔离和竞争版本更新；结合 metadata/迁移合同回归 **38 passed**。新模块行覆盖率 **93.77%（286/305）**，含分支综合覆盖 **91.99%**。`make lint`、新增代码 Ruff/Pyright、差异空白检查和生产代码密钥扫描通过。
- 完整 Runtime `make test`：首次 **9294 passed / 249 skipped / 1 failed**；失败来自旧的本地 Codex 入口，错误为 `Codex 0.155.1 is required`。安装固定 0.155.1 后该用例 **1 passed**；最终全量复跑 **9298 passed / 250 skipped / 0 failed**（635.44 秒，退出码 0）。
- Studio：代理策略与完整 Runtime proxy 模块 **133 passed**；前端 Node **1389 passed**、Vitest **123 passed（9 files）**；TypeScript `tsc --noEmit`、前端生产构建及相关 Python Ruff 通过。新增 Python helper 的 Pyright 零错误；整个 `cli_frontend.py` 的 Pyright 有 **37 项存量错误**，与 HEAD 基线对比，忽略文件名与行号后诊断完全相同，无新增错误。因此不声明整个 Studio Python 类型门禁通过。
- 浏览器：真实配置组件连接本地 Runtime 注册 API/持久化，验证新增、Card 检查、编辑停用、删除确认、关闭/重开、360px 窄窗口滚动、键盘鉴权选择和缺失密钥提示。测试夹具使用模拟远端 Card 与本地鉴权；Studio BFF 鉴权另由集成测试验证，不把本地组件测试表述为线上端到端验收。
- 未验证/非目标：真实外部 Agent 凭据与私网互通、生产发布、云资源修改、完整远端 CI formal/coverage 门禁、`dispatch_a2a_task` 执行。现有全量测试存在 event loop 清理 warning，保留报告，不将 warning 表述为业务失败。未提交、推送或部署。

UI 入口位置由[详情页 Tab 设计](2026-10-20-collaborating-agents-detail-tab.zh.md)替代。
