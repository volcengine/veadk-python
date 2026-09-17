# MPA AgentKit P0 功能迁移与落地

- Change ID：`mpa-p0-productionization`
- 状态：`approved`；已实现至 S5-08，其余 S5 P0 门禁待完成
- 创建 / 修订：2026-09-15 / 2026-09-17
- English：[2026-09-15-mpa-p0-productionization-design.md](2026-09-15-mpa-p0-productionization-design.md)
- 组件契约：[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)、[MPA Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)、[MPA Runtime 控制](../../../specs/mpa-runtime-control/README.zh.md)

## 1. 结论与边界

AgentKit Studio 是未来唯一的 MPA 管理入口；`agentkit-mpa-agent` 是执行 Runtime。本期不开发或依赖 Managed Agent CRUD、发布版本或 Session。Studio 复用现有 Agent 创建表单和资源选择器，把已接受配置规范化为不可变 MPA Profile revision，并直接应用到 mpa-agent。MPA Agent 详情页是查看 Profile 状态、应用/重新应用 Agent 级 Profile、管理 Session 执行配置、查看诊断和删除 Runtime 的统一入口。对于 MPA，不再把用户引导到依赖 `/list-apps` 的通用 Runtime update capability 路径，因为该路径无法准确表达 A2A-only 的 mpa-agent Runtime。mpa-agent 不建设模板中心、专家市场、审核安装或独立发布产品。`arkclaw-team` 只用于核对旧功能，不作为新链路依赖，也不迁移其历史数据。

本期完成 P0 核心链路：创建/更新 MPA Agent、Runtime 准备、Profile 应用、Session、对话和 worker 执行、会话执行配置、暂停/恢复/续跑、历史结果、Debug/Trace、运行时更新与故障恢复。定时任务、飞书集成、网站集成、资源库和全局搜索延后。

| 系统 | 唯一职责 | 明确不做 |
| --- | --- | --- |
| AgentKit 平台 | 现有 Studio 创作入口、Skill/Tool/Environment/Vault 等平台资源、Runtime 生命周期与账号权限 | P0 不新增或依赖 Managed Agent CRUD/version/Session |
| VeADK Studio/BFF | 校验 Agent draft、规范化 MPA Profile revision、编排 Runtime/Profile 应用并展示状态 | 不创建第二个平台产品，不直接驱动 worker |
| `agentkit-mpa-agent` | Profile 执行投影、Session/Turn、资源解析、worker 编排、运行控制与诊断 | 不提供模板/专家/审核安装/独立 Agent 版本产品 |
| `mpa-codex-worker` | 已有隔离执行协议 | 除非实测证明协议缺口，否则不修改 |
| `arkclaw-team` | 只读功能参考 | 不依赖、不双写、不迁移、不兼容旧 ID/API |

## 2. 已验证事实

2026-09-15 的静态审计版本为 VeADK `34658d75`、agentkit-mpa-agent `2f5e039`、arkclaw-team `c15d611`。使用两个测试账号做了只读验证；未执行创建、更新或删除云资源。临时 arkcli profile 已删除。

| 事实 | 证据 | 设计结论 |
| --- | --- | --- |
| Studio 已有 Agent draft，覆盖模型、系统指令、Tools、Skills、MCP、多 Agent 结构和部署设置 | `frontend/src/create/types.ts`、`CustomCreate.tsx`、`deployAgentkitProject` | 复用该 UI/数据，只新增 Profile 规范化和 Runtime 接线 |
| 当前测试账号未开通 Managed Agent create | 2026-09-15 live `CreateAgent` 返回 `ManagedAgentNotOpen` | Managed Agent 明确不在 P0 范围，不能阻塞 MPA 交付 |
| AgentKit Runtime list 可读且存在 Ready 的 MPA Runtime；SDK已有 create/get/list/update/release/delete/listVersions/listInstances/getLogs | 测试账号和本地 SDK/VeADK adapter | 复用平台 Runtime API；VeADK 只补齐编排、readiness 和错误恢复，不造第二套生命周期 |
| Skill、Environment、Vault provider 可通过真实账号查询 | 只读云验证成功 | 资源选择与授权复用 AgentKit API；mpa-agent 做引用解析和执行适配 |
| runtime 已有 `/api/v1/agents`、Session CRUD/run/SSE/events、MCP、A2A pause/resume、health/readiness/console | agentkit-mpa-agent 路由与测试 | 现有接口优先扩展；仅新增 Profile 同步、执行配置版本和 runtime-owned continuation |
| `mpa_agents` 已是单 Runtime 的配置 revision 表 | `app/stores/agent_config.py` | 复用为执行投影；补来源版本/摘要/应用状态，不另建 Agent definition 表 |
| `RunRequest` 目前只有 `content` 且 `extra=allow`；run 无 `Idempotency-Key` | `schemas/session.py`、`api/v1/sessions.py` | 需显式增加执行配置版本和强幂等，不能依赖未校验扩展字段 |
| pause/resume 只记录最后一次 command key/action | `a2a_task_control.py` | 可复用 generation 状态机，但要补 request hash 与结果持久化，才能识别同 key 不同 payload |
| Studio 超时续跑会拼接 prompt 再调用 `send` | `frontend/src/App.tsx` | 改为 runtime-owned continuation API，避免失去 Turn 关联或重复副作用 |
| “我的 Agent”已有 MPA 分类但创建入口只覆盖 general/Sandbox | `frontend/src/ui/MyAgents.tsx` | MPA Tab、Header、空态接入 AgentKit 原生创建流程 |

现有 “321 个 runtime 测试通过”只代表先前基线，本轮没有重跑，不作为本次文档整改的当前测试结果。

## 3. 用户场景与功能要求

### 场景 A：创建并首次运行 MPA Agent

**Given** 用户在 AgentKit Studio 创建 Agent，并选择 MPA Runtime 类型。

**When** Studio 校验 Agent draft、创建不可变 MPA Profile revision、准备/复用 Tool 与 Runtime，并将该 Profile 应用到 runtime。

**Then** 用户看到统一的创建进度；只有 Profile 已应用且 execution-ready smoke 通过后，状态才为“可运行”；随后可创建 Session 并获得首个流式结果。

### 场景 B：更新 Agent Profile

**Given** 已应用 MPA Profile 当前为 revision N。

**When** 用户保存模型、System、Tools、Skills、MCP 或 Multiagent 变化。

**Then** Studio 使用当前 ETag 和稳定幂等键向 runtime 提交新 digest；Runtime 原子分配 revision N+1。相同 key/digest 返回原 revision，相同 key 不同 digest 返回 `409 idempotency_mismatch`，stale ETag 返回 `412 profile_changed`。

### 场景 C：修改会话执行配置

**Given** Session 当前执行配置版本为 6，包含 Agent 默认 Profile 加会话级覆盖。

**When** 浏览器 A 将模型改为 M2，同时浏览器 B 仍以版本 6 修改 Skill。

**Then** A 成功生成版本 7；B 收到 `412 execution_config_changed` 和当前版本 7，不会覆盖 A。已经运行的 Turn 继续使用启动时记录的版本 6；下一 Turn 使用版本 7。

“会话执行配置版本”是 runtime 为一次 Session 保存的、可递增比较的执行配置记录，不是复制平台资源本体。例如它只记录 `skillId=s-1, version=3`、`environmentId=e-2, version=5` 和模型覆盖；Skill 内容、Environment Secret 仍由 AgentKit 管理。Turn 开始时把实际采用的版本号和解析结果写入 Turn 执行记录，以保证执行中配置改变不会污染当前 Turn。

### 场景 D：暂停、恢复与超时续跑

**Given** 一个 Turn 包含主执行器和两个 worker。

**When** 用户暂停。

**Then** 所有活动参与方到达安全点后才显示 `paused`；部分确认显示 `pausing` 或超时失败。300 秒内且租约仍有效时恢复原 Turn；超过边界或不可恢复时，只有用户显式点击继续才由 runtime 原子创建关联的新 Turn。

### 场景 E：刷新与故障恢复

**Given** 请求在写入执行记录后、实际 dispatch 前失败，或浏览器在流式执行中刷新。

**When** 客户端用相同幂等键重试或携带 event cursor 重连。

**Then** runtime 返回原 invocation/结果并从游标继续，不创建重复 Turn，不重复累计事件和用量。

## 4. 核心设计

### 4.1 AgentKit Profile 到 runtime 的接线

创建/更新分两层完成：

1. 浏览器把现有 Studio Agent draft 提交给 VeADK BFF；不调用 Managed Agent API。
2. BFF 校验资源引用，并把已接受 draft 规范化为 `sourceProfileId + profileDigest`；BFF 不分配 revision，且禁止把未校验浏览器字段直接转发给 runtime。
3. BFF 调用 mpa-agent 的 Profile apply 接口；runtime 校验版本、引用和权限后写入新的 `mpa_agents` revision。
4. BFF 查询应用状态；失败时保留上一个已应用 MPA Profile revision 和可重试 operation，不把 MPA Agent 标记为可运行。
5. 新 Session 固定创建时选择的 Profile revision；活动 Turn 永不热切换。

BFF 复用现有 Studio draft 解析及 AgentKit 资源 client，新增类型化 mpa-agent Profile client，而不是 Managed Agent OpenTOP adapter。Runtime 在成功的 ETag/CAS 事务内分配唯一 `profileRevision` 并返回；BFF 不预分配 revision。冲突返回 `409 profile_version_conflict` 和当前 revision，不自动覆盖。

P0 不引入新的自签 assertion 服务。Studio 在 OAuth/gateway 模式下已经持有经过验证的用户 bearer token，AgentKit Runtime 使用 custom JWT authorizer 校验同一 issuer/client；BFF 只转发已由中间件验证的 bearer token。mpa-agent 将 REST bearer JWT 和 A2A TIP 都投影为统一 `RuntimePrincipal`，并在新写接口执行业务 scope 校验。已实现的 S4-06 Runtime 子集新增共享 `RuntimePrincipalAuthorizer` 接线点，并在 `/run`、resume、`/continue`、模型/workload TIP 或 API key 解析、sandbox run 凭据准备和工具 dispatch 前复核当前授权。Runtime 在 accepted Turn/inbox recovery 中只携带规范化的非 secret principal 快照，不落盘 bearer token。本地 claim/rejection 与 fake-revocation contract 是 S1/S4-06 门禁；issuer、audience/client、TTL、JWKS 轮换、真实撤权查询和一次授权 Profile apply/status 仍是部署环境发布门禁。两个阶段都不能降级为浏览器 Header、Runtime key 或关闭 JWT。

| Studio AgentDraft 字段 | runtime 字段/行为 | 转换规则 |
| --- | --- | --- |
| Studio draft ID | `sourceProfileId` | 稳定来源标识，用于审计和幂等；不是 Managed Agent ID |
| `Name`, `Description` | `name`, `description` | 原样传递并执行长度校验 |
| `System` | `agentsMd` | 作为运行指令正文；保留来源摘要 |
| `Model.Id` | `model` | 去除空白；不得含 provider URL 或凭据 |
| `Tools[]` | `tools[]` | 保留 type/name/enabled/permission policy；不支持类型返回 `422 unsupported_profile_field` |
| `Skills[]` | `skills[]` | 固定 `SkillId + Version`；缺版本先由 BFF 解析为明确版本 |
| `MCPServers[]` | `mcp` | 转为 ID 白名单/分组授权；Secret 只传引用 |
| `Multiagent` | runtime subagent 配置 | 保留角色、Agent 引用与版本；不支持结构显式失败 |
| `Metadata`, `Tags` | `metadata` | 只保留 allowlist 的非敏感键；分类继续使用 `veadk:agent-type=mpa` |
| Managed Agent 专属字段 | 不接受 | Managed Agent CRUD/version/Session 不在 P0；MPA Session 覆盖由 runtime `session_execution_configs` 管理 |

### 4.2 接口复用、扩展与新增

| 接口 | 类型 | 调整 |
| --- | --- | --- |
| `GET /web/mpa/agents/{mpaInstanceId}/view`、`POST /web/mpa/agents`、`PATCH /web/mpa/agents/{mpaInstanceId}` | 新增 MPA BFF 编排 | 浏览器只调用 BFF。create/update 接受现有 Studio AgentDraft，规范化为 MPA Profile 后调用 Runtime API；不调用 Managed Agent CRUD/version API。create/update 均要求浏览器持久化 `Idempotency-Key` 并返回 `202 + operationId` |
| `GET /web/mpa/agents/{mpaInstanceId}/delete-preview` | 新增 BFF 编排 | 浏览器在单个 MPA Runtime 删除前调用。Query 接受 `runtimeId` 和 `region`。BFF 解析已授权 MPA Runtime binding，读取 Runtime `profile-status`，调用现有 Runtime `GET /api/v1/sessions?include_a2a=true`，并返回 `canDelete`、`blockers`、可见会话计数、活动会话摘要和清理阶段 |
| 带 MPA Runtime tag 的 `POST /web/delete-runtime` | 扩展既有 BFF 路由 | 既有请求保留 `runtimeId` 与 `region`；`agentCategory` 和 `mpaInstanceId` 只是可选提示。服务端会重新检查 Runtime 标签 `veadk:agent-type=mpa` 后才使用 MPA 清理。MPA 删除会在 mutation 前拒绝 active operation 和 active session，先通过现有 Runtime API 删除可见 idle/terminal Runtime Session，再删除 AgentKit Runtime |
| AgentKit Resource/Environment/Skill/Tool/Vault API | 复用 | BFF 负责权限化读取和版本解析；runtime 仅消费稳定引用。AgentKit Managed Agent Session API 不进入 P0 主链路 |
| AgentKit Runtime create/get/list/update/release/delete/versions/instances/logs | 复用 | VeADK adapter 负责 provision、状态归一和恢复步骤 |
| `GET /web/mpa/agent-operations?status=active`、`GET /web/mpa/agent-operations/{operationId}`、`POST .../{operationId}/retry` | 新增 BFF 编排 | TOS CAS 持久 create/update operation；按 principal 授权。create/update 的首次响应丢失后通过 active list 或同 key 重放恢复；retry 从最后安全阶段继续 |
| `PUT /api/v1/agents/{mpaInstanceId}/profile` | 新增 | payload 带 `sourceProfileId` 和 digest，不携带调用方分配的 revision；Runtime 分配并返回 `profileRevision`。首次仅允许 `If-None-Match: *`，后续仅允许 `If-Match: "<runtimeRevision>"`；两者同传返回 `400`，均缺失返回 `428`；响应返回强 ETag |
| `GET /api/v1/agents/{mpaInstanceId}/profile-status` | 新增 | 返回 `pending/applying/applied/failed`、已应用版本、目标版本、安全错误与 retryable |
| `GET /api/v1/sessions/{sessionId}/execution-config` | 新增 | 返回当前会话执行配置版本、ETag、Profile 默认 revision、overrides、effective 和 invalid references。已实现的 P0 子集只为带 `mpaInstanceId + profileRevision` 的 MPA Session 初始化该状态 |
| `PATCH /api/v1/sessions/{sessionId}/execution-config` | 新增 | `If-Match` 强制 CAS；按类别 replace/clear/inherit；只影响下一 Turn。已实现的 P0 子集支持 `model` 与 `mcpServers`；其他类别在资源 resolver 存在前返回 `422 unsupported_execution_config_category` |
| `POST /api/v1/sessions/{sessionId}/profile-upgrade` | 新增 | body 含 `targetProfileRevision`，Header 含当前 execution-config `If-Match` 与 `Idempotency-Key`；目标 Profile 必须已 applied。活动 Turn 可提交但仅下一 Turn 生效；版本回退返回 `409 downgrade_not_allowed`。当前 Runtime 实现为相同 key/相同目标提供进程内 replay，并把相同 key/不同目标映射为 `409 idempotency_mismatch`；跨进程持久 replay 需要后续 SQL `runtime_operations` 实现 |
| `POST /api/v1/sessions/{sessionId}/run` | 扩展 | 请求显式增加 `executionConfigVersion`；要求 `Idempotency-Key`；返回已接受版本与 invocation |
| 现有 A2A submission | 扩展 | Agent Card 声明 `urn:veadk:mpa:execution:v1`；`params.metadata.veadkExecution` 包含 `executionConfigVersion` 与 `idempotencyKey`，两者参与规范化 request hash。缺失扩展的旧客户端只允许 default revision，不能使用 Session override |
| 现有 `GET/POST .../control` | 扩展 | 保留 URL，增加参与方状态、request hash、结果重放；不破坏旧 capability 客户端 |
| `POST /api/v1/a2a/tasks/{taskId}/continue` | 新增 | runtime 原子创建关联 Turn；要求 idempotency key 与 expected generation |
| `GET /api/v1/runtime-operations/{operationId}` | 新增 | 按 principal/target 授权查询 Profile/run/upgrade/continue 的异步状态与安全结果；不返回 Secret |
| Session CRUD/SSE/events/MCP/health/readiness/console | 复用 | 补 scope 校验、cursor 与结构化关联；不另建重复接口 |

Profile apply 请求的最小形态：

```json
{
  "sourceProfileId": "studio-agent-example",
  "sourceProfileDigest": "sha256:example",
  "profile": {
    "name": "Research Agent",
    "system": "...",
    "model": {"id": "model-example"},
    "tools": [],
    "skills": [{"skillId": "s-example", "version": "3"}],
    "mcpServers": [],
    "multiagent": null,
    "metadata": {}
  }
}
```

首次 apply 只带 `If-None-Match: *`；已有投影只带 `If-Match: "<runtimeRevision>"`。两者互斥，成功响应与 status 均返回 `profileRevision` 和 `ETag: "<runtimeRevision>"`。相同 operation key/digest 幂等返回原 revision，相同 key 不同 digest 返回 `409 idempotency_mismatch`，stale ETag 返回 `412 profile_changed`。

BFF 在 Runtime 创建/Profile apply 前把 MPA lifecycle operation 写入 TOS，key 为 `veadk-studio/v4/users/{principal}/mpa-agent-operations/{operationId}.json`，使用 `forbid_overwrite` 创建与 ETag 条件更新。create 与 update 均要求客户端先持久化 `Idempotency-Key`；BFF 以 `principal + operationKind + mpaInstanceId/createIntent + key + requestHash` 唯一创建 operation，两个入口都返回 `202 + operationId`。相同请求返回原 `operationId`，同 key 不同内容返回冲突。`GET /web/mpa/agent-operations?status=active` 是首次响应丢失后的刷新兜底。创建状态机为 `runtime_preparing -> profile_applying -> smoke_running -> runnable`；更新状态机为 `profile_applying -> succeeded`，均可进入 `failed_retryable|failed_terminal`。记录 MPA instance ID、from/target Profile revision、Profile digest、Runtime ID、Profile operation ID、阶段、重试次数、安全错误和时间戳，不保存凭据。恢复时按 Runtime binding 与 Profile status 对账，从最后安全阶段继续。

本地 Studio 开发态可在 `veadk studio --dev` 且未配置 Studio TOS 时使用进程内 operation repository。它让本地 Profile apply 与 retry 流程可以对真实 Runtime 做验证，同时保留相同的 operation ID、request-hash 幂等和 ETag compare-and-swap 语义。该 store 不具备持久化能力，也不能作为发布证据；非 dev 部署仍要求 Studio TOS，缺失时 Profile 写路由返回 `mpa_operation_service_unavailable`。

### 4.3 幂等、错误与性能

Profile apply、profile-upgrade 和 continuation 在需要可复用异步状态/replay envelope 时使用 `runtime_operations`，按 `principal + operation + target + Idempotency-Key` 唯一，保存规范化 request hash、response snapshot、资源 ID 和 24 小时过期时间。Run acceptance 使用专用的 `turn_execution_records` 作为 Turn ledger，因为持久重放值是已接受的 `turnId/invocationId/operationId` 与冻结 execution configuration。execution-config PATCH 只使用 revision/ETag CAS；pause/resume 只使用 `a2a_task_controls` 的 generation、request hash 和 replay result，不重复写 ledger。相同 key/相同 hash 返回原结果；相同 key/不同 hash 返回 `409 idempotency_mismatch`。pending Profile 不进入 `mpa_agents` current revision；成功事务才切换 applied revision。Run 与 continuation 在同一数据库事务内写 `turn_execution_records` 和 dispatch intent，再由幂等 dispatcher 执行。不得承诺与外部 AgentKit/A2A TaskStore 的分布式 ACID。

统一错误体为 `error.code/message/requestId/retryable/currentState`。关键错误包括 `profile_version_conflict`、`execution_config_changed`、`session_busy`、`unsupported_profile_field`、`resource_unavailable`、`idempotency_mismatch`、`not_execution_ready`。旧接口的 envelope 只在 capability 版本升级后改变。

MPA 删除刻意不声明为新的分布式事务。预览和执行都会从服务端当前状态重新计算阻断原因。active operation 和 active Session 的阻断以执行时为准，因此过期浏览器预览不能强制删除。重复删除时，如果某个 Session 已被清理并返回 `404`，视为该 Session 已完成清理并继续剩余阶段；AgentKit Runtime 删除仍是最后一个平台副作用。当前预览范围是已授权调用方在目标 Runtime API 中可见的 Session，不是跨用户全局 Session 索引。

| 操作 | P0 服务端目标（不含调用方网络） | 约束 |
| --- | --- | --- |
| Profile apply 接受/幂等重放 | p95 ≤ 500 ms | 外部资源详情校验异步化；同步验证 ID、版本、摘要和权限 |
| Session execution-config GET/PATCH | p95 ≤ 300 ms | 单次事务；远程资源读取不持有数据库锁 |
| Run 接受 | p95 ≤ 500 ms | 返回 accepted/operation ID，不等待模型完成 |
| pause/resume/continue 接受 | p95 ≤ 500 ms | 返回目标状态；多参与方收敛异步观察 |
| SSE 首事件 | p95 ≤ 2 s | Runtime 已 warm 且不包含模型首 token SLA |
| 列表与详情 | p95 ≤ 1 s | 服务端分页，默认 20、最大 100；禁止 N+1 Runtime/资源扫描 |
| MPA 删除预览 | p95 ≤ 1 s | 一次 Runtime binding/profile 查询和一次有界 Runtime Session 列表；传入 `runtimeId` 时不做跨 region 扫描 |

性能结果以 warm-up 5 次后至少 100 次请求、并发 10、固定 20 项列表和同 region 测量；报告 p50/p95/max、错误率和测试 revision。外部模型首 token、Runtime 冷启动分别统计，不混入 API 接受延迟。未执行基准前这些数值是目标而非通过证据。

### 4.4 状态机

Profile 应用：`pending -> applying -> applied | failed`。失败可用相同 operation 重试；更高 Profile revision 可替代失败目标，低 revision 拒绝。

Runtime 准备：`prepared -> resource_created -> transport_ready -> profile_applied -> execution_ready -> verified`，任一步可进入 `failed_retryable` 或 `failed_terminal`。只有 `verified` 对用户显示“创建成功且可运行”。

Turn：`queued -> running -> pausing -> paused -> resuming -> running -> completed|failed|cancelled`。部分参与方确认保持 `pausing`；generation 变化后旧 ACK 无效。已实现的 S4-02 Runtime 子集把现有控制 API、A2A 主执行器和 Codex worker interruption 路径接入 `ParticipantBarrierService`：pause 创建下一代参与方 generation，只有当前 generation 的所有活跃参与方都确认安全点后，聚合 task 才进入 `paused`；在 task 已经 `paused` 后才启动的 late worker 仍会收到 worker pause，并在当前 generation ACK 后才能 resume；completed/failed/cancelled worker 会写入终态，不会阻塞后续 pause。已实现的 S4-03 子集在 task owner lease 仍有效时，允许恰好 300 秒边界内的 same-Turn resume；暂停超过 300 秒、task owner lease 丢失，或当前 generation 存在 `lost|failed` participant 时，resume 返回 `new_turn_required`；相同 key 的 `new_turn_required` 重试会幂等 replay。resume 会把聚合 task 恢复为 `running`，并从上一代 paused generation 生成下一代 running participant 记录。已实现的 S4-04 Runtime 子集暴露 `POST /api/v1/a2a/tasks/{taskId}/continue`：在 `new_turn_required` 后，通过旧 task 的 invocation 找到上一条业务 Turn，写入带 `continuation_of=<oldTurnId>` 的新 `turn_execution_records` 行，复用冻结的 execution-config snapshot 和 dispatch payload，关闭旧 active dispatch 行，并使用现有 inbox/outbox worker 调度。已实现的 S4-05 Studio 子集移除 prompt-based continuation fallback：当 resume 返回 `new_turn_required` 时，Studio 调用 Runtime `/continue`，再用返回的 `invocationId` 和当前 `lastEventId` 订阅 Runtime `/sse`，不再发普通 `/run`，也不再拼接 prompt。已实现的 S4-06 Runtime 子集会在接受 run/resume/continue 副作用前，以及后台 secret/tool 副作用前复核当前 RuntimePrincipal 授权。若注入的 authorizer 判定授权已撤销，resume 和 continue 会在状态变更或 continuation 接受前返回 `403 runtime_action_forbidden`；已接受的 inbox 执行也会在模型 TIP、workload TIP、OpenViking API key、sandbox run 凭据或 sandbox/tool dispatch 使用前失败。已实现的 S4-07 浏览器门禁验证了端到端 Studio loopback 行为：部分 worker ACK 时仍保持 `pausing`；所有参与方到达安全点后才显示恢复；same-Turn resume 回到 `running`；`resumeDisposition=new_turn_required` 的中断 task 在 UI 中显示为用户可理解的检查点续跑状态；浏览器刷新不会自动创建 continuation；只有用户显式点击恢复时才调用 Runtime `/continue` 并继续订阅 `/sse`。

会话执行配置：每次成功 PATCH 产生单调 `revision`；不存在独立业务 status。校验失败不产生 revision，并在响应中返回 invalid reference；Turn 记录 accepted revision 后不可变。

Session Profile 升级与普通配置修改共享同一配置 revision，但升级必须走专用 API。以目标 Profile 为新 base，保留显式 override/clear，inherit 类别采用目标 Profile 默认值，再重新解析 effective refs。任何资源缺失、撤权或不兼容均在事务前原子拒绝，旧 revision 完整保留，不生成“不可执行 revision”。成功事务同时把 `session_meta.profile_revision/execution_config_revision` 指向新 revision；重复 key/hash 返回同一新 revision；并发 ETag 变化返回 `412`。

删除状态机：`preview -> blocked | ready -> cleaning_sessions -> deleting_runtime -> deleted | failed_retryable`。当 MPA operation store 中存在 active create/update operation、Runtime binding 缺失或重复、Runtime Profile orphan，或 Runtime Session 处于 `queued|running|pausing|paused|resuming` 时，删除在任何 mutation 前进入 `blocked`。`cleaning_sessions` 只删除可见 idle/terminal Runtime Session，并把单个 Session 的 `404` 视为已清理。`deleting_runtime` 只在 Runtime 侧清理成功后调用 AgentKit Runtime delete API。

## 5. 数据模型

### 5.1 复用原则

- Studio 是已接受 MPA Profile 的创作权威；mpa-agent 的 `mpa_agents` 保存不可变执行 revision。不新增 Managed Agent、模板/专家/definition/review/install 或发布版本表。
- AgentKit Skill、Tool、Environment、Vault、Resource 保持各自权威；runtime 只保存 ID、固定版本、摘要和 Secret reference。
- 不修改 AgentKit 平台自有表，不迁移 ArkClaw 表，不建立旧 ID 映射。
- 新列为 additive；新 store 同时实现 PostgreSQL 与内存版本。

### 5.2 P0 最小调整

| 模型 | 调整 | 用途 |
| --- | --- | --- |
| `mpa_agents` | 增加 `source_profile_id`、`source_profile_digest`、`apply_status`、`apply_operation_id`、`apply_error_code`、`agent_api_key_ref`、`model_api_key_ref`、`secret_migration_status`、`secret_migration_operation_id`；现有 Runtime 分配的 revision 即 `profileRevision` | 保存不可变 MPA Profile revision 和应用状态，不引入第二个 revision allocator。S5-01 仅把 legacy 明文字段保留为迁移输入和一个版本的兼容读取；AgentKit mode 禁止新明文写入，并且只有受保护引用创建成功后才清空旧值 |
| `mpa_meta` | 增加 `agentkit_mode`、`workspace_id`、`bootstrap_manifest_revision`、`readiness_phase`、`finalization_operation_id`、`last_error_code`；凭据仍使用现有受保护字段或服务端引用 | 禁止 AgentKit 模式回退 ArkClaw，并支持分阶段恢复 |
| `session_meta` | 增加 `account_id`、`workspace_id`、`mpa_instance_id`、`profile_revision`、`execution_config_revision` | 建立 Session 所属范围及当前配置版本 |
| `session_execution_configs` | 新表：`app_name`、`session_id`、`revision`、强 `etag`、`mpa_instance_id`、`profile_revision`、`profile_default_revision`、JSON `overrides`、JSON `effective_refs`、JSON `invalid_refs`、`updated_by`、timestamps。主键为 `(app_name, session_id, revision)`；当前版本读取使用 `(app_name, session_id, revision DESC)`。SQL CAS 在读取当前 revision 并追加下一条不可变记录前，先获取 Session 维度的 PostgreSQL advisory transaction lock。 | 保存“会话执行配置版本”，替代浏览器 localStorage 权威。它只保存稳定引用和执行选择，不保存 AgentKit 资源正文或 Secret。例如 revision 1 记录 Profile 3 默认值和 Skill `skill-1@3`；revision 2 记录模型覆盖和 Skill `skill-1@4`；已被 Turn 接受的 revision 1 仍可读取且不会被修改。 |
| `turn_execution_records` | 新表：task/invocation/session、accepted config revision、resolved refs、model、policy revision、secret refs、dispatch key/hash/status、`continuation_of`、timestamps | 冻结每个 Turn 实际配置并支持崩溃恢复/续跑 |
| `a2a_turn_participants` | 新表：task、generation、participant ID/kind/status、安全点、checkpoint、lease、ACK/终态时间 | 证明主执行器与所有活动 worker 均已暂停 |
| `a2a_task_controls` | 增加 command request hash/result reference；只有实际接入高风险工具审批时才增加 approval 字段 | 完整实现 pause/resume 幂等；避免预建通用 policy 产品 |
| `runtime_operations` | 新表：principal/operation/target/key 唯一键、request hash、state、response snapshot、resource IDs、expiry | 承载 Profile 生命周期和后续长耗时控制操作的强幂等与通用状态查询；run acceptance 自身由 `turn_execution_records` 负责 |
| trace/lifecycle stores | 按需增加 task、config revision、runtime/worker version 等索引列 | 通过结构化关联完成 Debug，不复制正文大字段 |

不新建 `mpa_agent_definitions`、`mpa_agent_definition_versions`、`turn_continuations`、`policy_evaluations` 或通用 `approval_requests`。MPA Profile revision 使用现有 `mpa_agents` 表；continuation 关系放入 `turn_execution_records.continuation_of`；授权在每个副作用前实时重查并记录到 Turn/trace。只有真实 P0 高风险工具流需要持久审批时，才在 `a2a_task_controls` 增量扩展。

正式 migration 按 `runtime_operations -> mpa_agents/mpa_meta/session_meta 增量列 -> session_execution_configs -> turn_execution_records -> a2a_turn_participants -> Secret reference 列/索引 -> 其余索引/约束` 顺序执行，并保存 schema version。部署先扩 schema、再上线双版本可读代码、最后启用新写路径；旧代码无法安全读取新状态时禁止回滚。AgentKit mode 禁止新写 `agent_api_key/model_api_key` 明文；现有新平台值转为受保护引用后清空。S5-01a 还会在迁移读到 legacy 明文后、任何 provider 调用或诊断输出前，把这些明文注册到进程内 value-aware redaction registry。API access log、Session 对用户可见输出、Runtime Console 响应、lifecycle details 和 trace 持久化只按已注册字面值与已知 secret key 字段脱敏，保留 `flow_id`、`user_code` 等业务参数。`runtime_operations` 当前只保存 operation 幂等元数据，没有落地任意 response snapshot，因此 S5-01a 不额外增加 operation snapshot 脱敏路径。

## 6. Studio 页面适配

| 入口 | P0 处理 | 原因 |
| --- | --- | --- |
| 我的 Agent / MPA Tab | 复用 Studio 现有创建表单，把 draft 作为 MPA Profile 提交，再启动 Runtime/Profile 应用编排 | 当前 MPA 分类可见但无法创建 |
| 创建与部署进度 | 用阶段化 operation 展示 Runtime 准备、Profile 应用、execution-ready；支持失败重试 | Profile 接受和 Runtime 就绪是异步阶段 |
| MPA 详情/Profile revision | BFF `GET /web/mpa/agents/{mpaInstanceId}/view` 返回 `MpaAgentView`：scope、MPA instance ID/current Profile revision、Runtime ID/version/readiness、active operation/stage、capabilities、safe error。详情页为 MPA Agent 提供专属 `Profile 配置` 分区，基于当前 Studio draft/profile projection 展示配置，并通过 `/web/mpa/agents` 或 `/web/mpa/agents/{mpaInstanceId}` 应用变更 | 0 个 Runtime 显示 `runtime_missing`；唯一 MPA Runtime 可管理；多个返回 `binding_ambiguous` 且禁止写。`orphan_runtime` 表示 Runtime 存在但尚未应用 MPA Profile，因此 Studio 仍可用 `If-None-Match: *` 执行首次 Profile apply；Session 配置和诊断在 Profile 应用前继续阻塞 |
| 新对话/Composer | 创建/选择 mpa-agent 业务 Session，提交明确的执行配置版本和幂等键 | mpa-agent 是 Session/Turn 唯一权威，避免双 Session 映射 |
| 暂停/恢复/历史 | 使用 runtime 权威状态与 continuation API；刷新按 event cursor 恢复 | 当前前端拼 prompt 会丢失关联 |
| 会话配置/MCP/拓扑 | 服务端 CAS 管理会话执行配置，显示继承、覆盖、失效、下个 Turn 生效；展示真实参与方 | 替代 localStorage 执行权威 |
| Workspace/Environment | 区分资源集合 ID、授权 workspace scope 和 worker mount ID，经 BFF 解析 | 三种 ID 语义不同，不能互换 |
| 用量/Debug/Trace/系统页 | 复用现有页面并增加 Agent/Session/Turn/runtime/worker 关联和脱敏 | 核心链路需要可定位和可恢复 |
| MPA 删除 | 确认前展示删除影响预览；存在 active operation 或 active session 时禁止确认；执行通过 BFF 清理 | 不可逆 Runtime 删除前，用户必须知道会清理哪些 Runtime Session 与诊断数据 |
| Review Center | 保留现有非 MPA 功能；P0 不增加 MPA 模板/专家审核入口 | 本期仅建设 MPA Profile 执行链路，不建设目录产品 |
| Applications/GitHub/coding | 保留并对 MPA target 做 capability 门禁 | 这些流程不是 MPA runtime 管理 |

资源库、搜索、定时任务、飞书和网站集成页面本期保持原行为，不增加 MPA adapter，也不作为验收门禁。

## 7. 开发项与顺序

| 任务 | 主要工作 | 交付与依赖 |
| --- | --- | --- |
| `M0` 可行性与测试基座 | 固化 Studio Profile 映射；本地验证 Studio-to-runtime principal；建立 PostgreSQL 双连接 lane、fault injection、跨仓版本 manifest 和 E2E 资源/清理脚本 | **硬门禁**：本地 contract 与 PostgreSQL 基座通过；部署后再执行 live identity/Profile release gate |
| `T-2` Bootstrap 与身份 | 修改 VeADK provision/meta seed 和 runtime startup/auth，增加 AgentKit mode、分阶段 readiness、可恢复 operation | 全新部署不访问 ArkClaw；依赖可信身份接线 |
| `S1` 创建到首轮对话 | 复用 Studio 创建 UI、持久 MPA operation、Runtime/Profile apply、确定性 smoke、失败 retry/reconcile、最小页面 | 交付 `AC-1`、`AC-2`；安全 Case 持续执行 |
| `S2` Session 版本 | execution-config、显式 profile-upgrade、ETag/CAS、Turn freeze、真实 PostgreSQL 并发 | 交付 `AC-3` 与 D-1 |
| `S3` Run 与刷新恢复 | `runtime_operations`、turn/dispatch intent、崩溃恢复；复用持久 ADK events + inbox terminal，未知 cursor 返回 `410 cursor_expired` | 交付 `AC-4`、`AC-7` |
| `S4` 多 worker 生命周期 | participant barrier、pause/resume、fake clock 300 秒、lease loss、restart、transactional outbox continuation | 单独交付 `AC-5` |
| `S5` 管理面收口 | MPA detail/version view-model、Runtime update/release/delete/rollback、Debug/Trace、CLI parity、旧 Runtime gate | 交付 `AC-8`～`AC-10` |

M0、S1 至 S5 严格串行通过各自门禁，但允许拆成独立合入和回滚单元；不把 XL 范围压成单个 PR。

## 8. 测试与验收

| ID | 必须通过的证据 |
| --- | --- |
| `AC-1` | 阻断 ArkClaw 端点后，从 Studio AgentDraft 创建 MPA Agent，Runtime 达到 execution-ready，完成首轮 A2A/worker/结果链路，且不调用 Managed Agent API |
| `AC-2` | MPA Profile revision N+1 应用成功；重复 apply 返回同结果；stale ETag、相同 revision 不同摘要、unsupported 字段均安全失败 |
| `AC-3` | Session 配置双客户端 CAS：一方成功、一方 `412`；活动 Turn 配置不变，下一 Turn 使用新版本 |
| `AC-4` | 相同 run key 不重复执行；写记录后 dispatch 前故障可恢复；同 key 不同 payload 返回冲突 |
| `AC-5` | 主执行器加两个 worker 完整/部分暂停、恢复、旧 ACK、租约丢失、重启、300 秒前后和重复 continuation |
| `AC-6` | 伪造身份、跨 owner、撤权后的 run/resume/Secret 使用在副作用前失败；普通输出无 Secret |
| `AC-7` | SSE 断线按 cursor 重放，无重复文本、终态、用量或产物；缺失终态不显示成功 |
| `AC-8` | MPA 创建、详情/版本、对话、配置、历史、Debug 页面覆盖 loading/empty/error/denied/stale/retry、窄屏、键盘/IME |
| `AC-9` | Runtime update/release/delete 使用真实平台 API；MPA update/release/rollback 写操作在副作用前执行兼容性 preflight；失败返回可恢复 ID；兼容回退后 execution-ready 和 smoke 通过 |
| `AC-10` | UI/CLI 使用同一 principal、版本和错误语义；旧 Runtime 明确 read-only/unsupported，不做不安全 fallback |
| `AC-11` | contract tests 验证 REST bearer/TIP 映射到同一 RuntimePrincipal；发布前在部署环境验证 issuer/audience/JWKS/撤权及一次授权 Profile apply/status |
| `AC-12` | PostgreSQL 双连接验证 Profile CAS、Session CAS、唯一活动 Turn、operation replay、outbox crash recovery、schema 升级与允许的双版本组合 |

文档阶段执行双语、链接、路径、标识符和 diff 检查。实现阶段先跑 agentkit-mpa-agent 定向测试，再跑 VeADK backend/frontend 测试、build、浏览器测试和授权的隔离云 E2E。所有结果按 `pass/fail/blocked/not_run/not_applicable` 记录；跳过不算通过。

### 8.1 可执行验证基座

- 故障注入：dispatcher 接口、可注入 clock、participant probe、在 operation commit/dispatch/terminal 各边界的 failpoint，测试不得依赖随机 sleep。
- PostgreSQL：M0 在 Runtime 仓新增 `docker-compose.test.yml`（固定 PostgreSQL 16）和 `make test-postgres`，执行 `tests/integration/test_p0_postgres_contract.py`。命令启动隔离容器、加载旧 schema fixture、使用两个独立连接和一次 Runtime 进程重启验证 CAS/锁/outbox/migration，最后删除容器与 volume；内存 store 不能证明 `AC-3/4/5/9/12`。
- 浏览器：使用本机已安装的 gstack/Chromium；先以 `VEADK_MPA_TEST_SCENARIOS=1` 启动隔离 fake BFF/Runtime，再执行 `browser-cases.md`。该开关只允许 `APP_ENV=test` 和 loopback bind，否则启动失败；scenario API 支持 seed/reset/barrier/call-count，生产路由中不存在。证据写入 `evidence/browser/<run-id>/<case-id>/`；浏览器不可用时 `AC-8=blocked`。
- execution-ready smoke：`POST /api/v1/readiness/execution-smoke` 不依赖模型选择工具。Runtime 先执行最小模型 prompt（禁止工具）并校验模型终态，再通过现有 `CodexWorkerClient.create_session/start_turn/stream_turn_events` 直接发起隔离 Worker Turn `printf mpa-smoke-<operationId>`；幂等键由 creation operation ID 派生，最多重试 1 次，总超时 120 秒。Worker `/v1/codex-worker/ready` 必须返回 `ready=true`，事件流必须有匹配 stdout 与 terminal；模型未完成返回 `smoke_model_failed`，Worker 未就绪返回 `smoke_worker_not_ready`，输出/终态不匹配返回 `smoke_worker_failed`。Session/workspace 清理成功后才进入 `runnable`；清理失败为 `failed_retryable`，失败证据最多保留 24 小时。
- Live E2E 环境记录：测试账号、provider/region/project、资源命名前缀 `mpa-p0-e2e-*`、镜像 digest、模型、PostgreSQL、Runtime 配额、写/删权限、120 秒单步超时、成本上限和 cleanup owner。无明确授权/配额时 live Case 标记 `blocked`，不得由 mock 替代。
- 跨仓 manifest：固定 VeADK SHA、runtime SHA/image digest、MPA Profile schema version、用于复用平台服务的 `agentkit-sdk-python==0.8.5`、worker protocol/capability version。

兼容矩阵在 M0 将 `<new-bff-sha>`、`<new-runtime-image-digest>` 固定为实际产物；未列组合默认 unsupported：

| BFF | Runtime/schema | Runtime A2A capability | Codex Worker protocol | 允许操作 / 预期 |
| --- | --- | --- | --- | --- |
| `34658d75`（旧） | `2f5e039` / schema 0（旧） | 无 execution v1 | `codex` query + 当前 REST endpoints | 既有 list/read/chat/control |
| `<new-bff-sha>` | `2f5e039` / schema 0 | 无 execution v1 | 当前基线 | list/read；新写返回 `runtime_capability_unsupported` |
| `34658d75`（旧） | `<new-runtime-image-digest>` / schema 1 | `urn:veadk:mpa:execution:v1` | 当前基线 | 既有 list/read/chat/control；不创建 override |
| `<new-bff-sha>` | `<new-runtime-image-digest>` / schema 1 | `urn:veadk:mpa:execution:v1` | `codex` query、`/health`、`/ready`、session/turn/events endpoints | 全部 P0，执行 `AC-1` 至 `AC-12` |
| 任意 | schema 1 | 缺失/不匹配 | 任意 | 禁止新 Session override/continue，返回 `runtime_capability_unsupported` |
| 任意 | schema 1 | execution v1 | `/ready` 非 ready 或缺少当前 REST endpoints | 禁止 worker dispatch，返回 `409 worker_protocol_incompatible` |
| 回滚候选 | schema 1 | 按目标镜像实际值 | 当前基线 | 仅 migration 验证的 read/chat；未通过 PG contract 则拒绝回滚 |

当前 Worker 没有独立 capability discovery/version endpoint；M0 的静态兼容基线就是上述 `codex` query、`/health`、`/ready`、session/create、turn/start、event stream 接口集合。若任一接口契约变化，必须先增加 Worker capability/version 协商并单独评审；本 P0 不修改 Worker。

共享兼容性 preflight 实现在 `veadk.cli.mpa_p0_contract`。shell runner `scripts/verify-mpa-p0-contract.sh` 调用同一代码路径，Studio 在 MPA Runtime 写操作前也调用它。接受的 manifest 是脱敏 JSON 对象，包含 `veadkRevision`、`runtimeRevision`、`runtimeImageDigest`、Profile/config schema version、AgentKit SDK version、Runtime execution capability、Worker protocol 和必需 Worker endpoints。检查失败时不会把 manifest 正文回显给浏览器。若传入 manifest 格式非法，或未命中 `contracts/mpa-p0/compatibility-matrix.json`，Studio 返回 `409`，`code=mpa_compatibility_preflight_failed`，且不会调用 AgentKit SDK 或 GitHub mutation helper。

本地 Studio 写路径防护中，如果 UI 标记目标为 `agentCategory=mpa` 但未显式提交 manifest，BFF 会使用当前 VeADK git revision，以及可用时的 `VEADK_MPA_RUNTIME_REVISION`、`VEADK_MPA_RUNTIME_IMAGE_DIGEST` 生成最小 P0 manifest；缺失的 runtime artifact 值使用语法合法的全 0 占位。这个默认 manifest 只证明当前操作仍处于已批准的 P0 协议形态内，不作为发布证据。最终 release gate 仍必须由 `S5-10/VC-19` 使用真实固定的 VeADK SHA、Runtime SHA、Runtime image digest 和协议版本执行。

Live runner 固定为 `scripts/verify-mpa-p0-e2e.sh --manifest <redacted-json>`（M0 新增）。脚本按 `AC-11 -> AC-1 -> AC-2 -> AC-6 -> AC-9` 执行，每步写脱敏 JSON/日志到 `evidence/live/<run-id>/`，状态文件允许从最后一个安全阶段继续；EXIT trap 按 operation Metadata/资源前缀列出并删除 Agent、Runtime、Tool、测试 Session/数据库 schema，最终再次 list 验证零残留。stubbed cross-repo contract 和 live cloud 结果分开记录。

Runtime 仓库的可复现门禁为 `make test` 和 `make coverage`（95%）；该仓当前没有可引用的 pre-commit/Ruff/Pyright 或仓内 CI 配置，因此不得把这些检查写成已通过或强行套用 VeADK 命令。VeADK 仍执行仓库 AGENTS.md 规定的定向 pytest、并行回归、frontend test/build、浏览器和 pre-commit 门禁。跨仓集成结果必须固定双方 revision/image digest，单仓 mock 通过不等于 E2E。

## 9. Review 结论与已确认产品决策

本轮 `review-spec` 的阻塞问题——重复建设模板/专家/version、数据权威不清、接口缺少参数/幂等、会话“资源快照”语义模糊、前端自建续跑——已在方案中整改。代码或只读实测能确认的内容均已转为结论，不再列为待确认。

以下两项业务语义已由用户于 2026-09-15 确认为方案约束：

### D-1：已有 Session 显式升级后采用新 Profile

- **已确认采用 A：已有 Session 固定创建时的 MPA Profile revision；用户显式执行“升级会话”后，新 revision 从下一 Turn 生效。**
- Studio 必须展示“有新版本”、当前/目标版本和升级动作；升级前不改变现有 Session 行为。
- 活动 Turn 永不切换版本；升级操作使用 CAS 与幂等键，失败保留原版本。
- 不采用自动跟随最新版本或按 Agent 配置跟随策略，避免同一 Session 静默变更模型、工具或指令。

### D-2：完整运行链路通过后才显示 Agent 可运行

- **已确认采用 A：Studio 接受 MPA 创建后立即进入“部署中”；仅当 Runtime、Profile 应用和 execution-ready smoke 全部通过后才显示“可运行”。**
- 创建接口/页面返回阶段化 operation，允许刷新后继续查询；失败页面展示安全的资源 ID、失败阶段和重试入口。
- MPA operation 已存在但 Runtime 尚未可执行时，不显示“创建成功”或允许发起对话。
- 不采用同步长等待或“Agent 已创建即成功”，避免超时不可恢复及用户进入不可执行 Agent。

## 10. 风险与回滚

- M0 必须通过 bearer/TIP claim 映射与拒绝路径的本地 contract；部署态 `S5-14` 发布门禁再验证 issuer、audience/client、JWKS 轮换、撤权和授权 Profile apply/status。该门禁失败时阻止发布，但不回溯否定本地 S1 TDD。BFF 原样转发已验证 bearer，不签发新 assertion；禁止信任浏览器 owner Header、Runtime key 或回退旧服务。
- Studio operation 持久化与 Runtime Profile apply 不是分布式事务。用 operation + 幂等 Profile apply 收敛；失败保留上一个已应用 Profile revision 并显示“未应用”，不得谎报可运行。
- 会话执行配置引用的远程资源可能在提交后失效。Turn dispatch/materialize 时复核版本与权限，失效则在副作用前失败。
- Runtime 数据库采用 additive migration；回滚前检查新旧 schema/worker protocol 兼容。不兼容降级在写入前拒绝。
- 删除只处理当前 MPA Runtime/Profile 数据，并在有活动 Session/共享资源时阻止或分阶段清理；绝不触碰 ArkClaw 历史数据或 Managed Agent 数据。

## 11. 文档阶段验证记录

| 日期 | 检查 | 结果 | 说明 |
| --- | --- | --- | --- |
| 2026-09-15 | Managed Agent API 探测 | not_applicable | 已确认它是独立产品面；修订后的 P0 架构明确排除 |
| 2026-09-15 | Runtime/Skill/Environment/Vault provider 只读查询 | pass | 确认平台资源与 Runtime 可访问；不等于写链路已验证 |
| 2026-09-15 | 三仓静态接口/数据模型审计 | pass | 确认复用点与必要扩展；不等于运行时行为通过 |
| 2026-09-15 | M0 targeted tests 与 PostgreSQL 16 contract lane | pass | principal、test seam、兼容性、scenario、runner、benchmark 及 4 个真实 PostgreSQL foundation case 均通过；已删除出范围的 Managed Agent adapter |
| 2026-09-15 | Managed Agent APIs | not_applicable | 产品决策排除 Managed Agent CRUD/version/Session；此前的 `ManagedAgentNotOpen` 不再阻塞交付 |
| 2026-09-15 | Live OAuth bearer、TIP、JWKS 与 Profile endpoint | blocked | 新 Profile endpoint 部署后作为 release gate 执行；当前环境没有隔离 live bearer/TIP/JWKS fixture，不能把 AK/SK 只读验证替代为发布门禁通过 |

## 12. S1/S2/S3/S4/S5 实现阶段验证记录

| 日期 | 检查 | 结果 | 说明 |
| --- | --- | --- | --- |
| 2026-09-15 | Runtime S1 定向回归 | pass | `uv run pytest -q tests/test_agentkit_session_auth.py tests/test_runtime_principal.py tests/test_auth.py tests/test_sessions.py::test_create_get_delete tests/test_sessions.py::test_run_response_includes_session_id tests/test_execution_smoke.py tests/test_execution_smoke_api.py tests/test_codex_worker_client.py::test_codex_worker_client_ready_uses_worker_ready_endpoint tests/test_codex_worker_client.py::test_codex_worker_client_cancels_session_with_worker_control_api tests/test_mpa_meta.py tests/test_health.py tests/test_profile_apply_api.py` 返回 83 passed |
| 2026-09-15 | Runtime 定向 Ruff 与 PostgreSQL 16 门禁 | pass | touched Runtime 文件的 focused Ruff 通过；`make test-postgres` 返回 4 passed，并清理容器、网络和 volume |
| 2026-09-15 | VeADK MPA BFF 回归与 Ruff | pass | `uv run --extra dev pytest -q tests/frontend/server/mpa/test_agent_operations_service.py tests/frontend/server/mpa/test_operations_repository.py tests/frontend/server/mpa/test_runtime_profile_routes.py tests/frontend/server/mpa/test_runtime_profile_client.py tests/frontend/server/mpa/test_mpa_module.py tests/frontend/server/mpa/test_scenario_harness.py` 返回 32 passed；focused Ruff 通过 |
| 2026-09-15 | Studio 前端回归、i18n 与 build | pass | `npm --prefix frontend test` 返回 1206 passed；`npm --prefix frontend run check:i18n` 通过；`npm --prefix frontend run build` 通过。构建产生的 `veadk/webui` 产物已从源码 diff 清理 |
| 2026-09-15 | 仓库 diff hygiene | pass | `veadk-python-mpa-p0-plan` 与 `agentkit-mpa-agent` 两仓 `git diff --check` 均通过 |
| 2026-09-15 | S1 浏览器/live 门禁 | not_run | S1-10 仍负责 BC-01/02、BC-07 create/IME 子集和 live `VC-20A`；本地单测/build 结果不能替代这些门禁 |
| 2026-09-15 | S1-10 本地 runner 子集 | pass | compatibility manifest/e2e-runner/benchmark/scenario harness pytest 返回 12 passed。`scripts/verify-mpa-p0-contract.sh` 接受脱敏 manifest。`scripts/verify-mpa-p0-e2e.sh --dry-run` 返回有序阶段 `AC-11, AC-1, AC-2, AC-6, AC-9`；未设置 `VEADK_MPA_P0_LIVE=1` 时 `--execute` 按设计返回 `live_execution_not_authorized` |
| 2026-09-15 | S1-10 浏览器 fixture API smoke | partial | loopback fixture 在端口 `18173` 启动；`/__test/mpa/scenarios` list、seed、call count、barrier release、state read 均可用。强制清理后 token 文件已删除。S1 的 BC-01/02/BC-07 create/IME UI 路径仍需补专项 test-only scenario 接线后才能标记 pass；S2 的 `session_revision_6` 路径已完成接线并由 S2-08 单独覆盖。 |
| 2026-09-15 | 浏览器 runbook 漂移检查 | pass | `browser-cases.md` 与 `.zh.md` 已对齐当前实现的 `VEADK_MPA_SCENARIO_TOKEN_FILE` 和 `/__test/mpa/scenarios/...` API，不再使用早期 `/web/test/mpa/...` 草案路由 |
| 2026-09-15 | S2-01 Session metadata 指针 | pass | Runtime `session_meta` 已保存 `mpa_instance_id`、`profile_revision`、`execution_config_revision`；Session create/detail 仅在 MPA Session 中返回这些字段。`0003_session_meta_mpa_pointers.sql` 将 schema migration 推进到 version 3。focused tests 返回 17 passed、2 skipped；focused Ruff、`make test-postgres` 和 `git diff --check` 均通过 |
| 2026-09-15 | S2-02 execution-config revision store | pass | Runtime 已新增 `app/schemas/session_execution_config.py`、`app/stores/session_execution_config.py` 和 `0004_session_execution_configs.sql`。store 创建 revision 1，仅在 `If-Match` 等于当前强 ETag 时追加 revision N+1；缺少前置条件返回 `ExecutionConfigPreconditionRequired`，stale ETag 返回带安全 current record 的 `ExecutionConfigConflict`，旧 revision 保持不可变。PostgreSQL CAS 使用 Session 维度 advisory transaction lock 串行化。验证：`uv run pytest -q tests/test_session_execution_config.py` 返回 8 passed；focused Ruff 通过；`make test-postgres` 返回 5 passed，包含真实双连接 Session CAS。 |
| 2026-09-15 | S2-03 execution-config API/service | pass | Runtime 已暴露 `GET/PATCH /api/v1/sessions/{sessionId}/execution-config`，返回强 ETag header 和结构化错误体。GET 只为带 `mpaInstanceId + profileRevision` 的 MPA Session 初始化 revision 1；PATCH 要求 `If-Match`，支持 `model` 与 `mcpServers` 的 replace/clear/inherit，在 append 前拒绝未知 MCP ID，stale ETag 映射为 `412 execution_config_changed`，缺失前置条件映射为 `428 precondition_required`。验证：`uv run pytest -q tests/test_session_execution_config.py tests/test_session_execution_config_service.py tests/test_agentkit_session_auth.py tests/test_sessions.py::test_create_get_include_mpa_profile_pointers_when_supplied tests/test_session_mcp_update.py tests/test_session_mcp_resolution.py::test_create_session_persists_and_enriches_appcenter_mcp_ids tests/test_session_mcp_resolution.py::test_create_session_without_ids_uses_agent_mcp_whitelist_when_requested tests/test_session_mcp_resolution.py::test_create_session_with_empty_agent_mcp_whitelist_selects_no_mcp` 返回 24 passed；focused Ruff 通过；`make test-postgres` 返回 5 passed；本次文档更新前两仓 `git diff --check` 均通过。 |
| 2026-09-15 | S2-04 immutable resolved execution-config snapshot | pass | Runtime 已定义 `SessionExecutionConfigSnapshot` 和 `resolve_session_execution_config_snapshot(...)`。snapshot 固定已接受的 execution-config revision/ETag、MPA instance、Profile revision、Profile 默认 revision、overrides、effective refs、invalid refs 与 accepted timestamp，供后续 Turn acceptance 使用。本任务刻意不写入 `turn_execution_records`，`/run` 也要等 S3 才消费该 snapshot。验证：`uv run pytest -q tests/test_session_execution_config.py tests/test_session_execution_config_service.py` 返回 15 passed；focused Ruff 通过。 |
| 2026-09-15 | S2-05 explicit Session Profile upgrade | pass | Runtime 已新增 `POST /api/v1/sessions/{sessionId}/profile-upgrade` 和服务逻辑，显式升级到更高且已 applied 的 MPA Profile revision。流程要求 `Idempotency-Key` 与 execution-config `If-Match`，保留显式 Session overrides，基于目标 Profile 重新计算 inherit 默认值，成功后更新 Session Profile/config 指针；同版本/降级返回 `409 downgrade_not_allowed`，目标缺失或未 applied 返回 `409 profile_revision_unavailable`，相同 key 不同目标返回 `409 idempotency_mismatch`。当前 replay 是进程内能力；跨进程持久 replay 仍待 SQL `runtime_operations` 实现。验证：S2 focused Runtime command 返回 46 passed；focused Ruff 通过；`make test-postgres` 返回 5 passed；本次文档更新前两仓 `git diff --check` 均通过。 |
| 2026-09-15 | S2-06 typed execution-config BFF proxy and client | pass | VeADK 已暴露 `GET/PATCH /web/mpa/sessions/{sessionId}/execution-config` 和 `POST /web/mpa/sessions/{sessionId}/profile-upgrade`，由服务端解析 Runtime endpoint、转发已验证 bearer token，并且配置写入不走浏览器 `/web/runtime-proxy`。TypeScript client 暴露 `getMpaSessionExecutionConfig`、`patchMpaSessionExecutionConfig`、`upgradeMpaSessionProfile` 和 `getMpaProfileStatus`，覆盖 `If-Match`、`Idempotency-Key`、可取消读取，以及用于 `412` 恢复的 `MpaExecutionConfigRequestError.currentState`。最终验证：BFF pytest 返回 21 passed；focused Ruff 通过；前端 source-contract 子集返回 95 passed；完整前端测试返回 1209 passed；i18n 和 build 通过。 |
| 2026-09-15 | S2-07 MPA Session configuration and explicit upgrade UI | pass | Studio 已在 My Agents、新对话选择器、持久 runtime connection 与 Agent 详情中保留 Runtime `agentCategory`。MPA tab 可用现有 AgentKit 创建面，并显式携带 MPA intent。Agent 详情只对 MPA Runtime 显示 `Session configuration`，且只在所选 Agent 与当前 Runtime、当前业务 Session 匹配时读取 Runtime 权威配置。面板展示 config revision/ETag、Session 固定的 Profile revision、最新已应用 Profile revision、effective model/MCP refs，支持模型 replace/inherit、MCP clear/inherit，并通过确定性幂等键执行显式 Profile upgrade。`412 execution_config_changed` 会用 Runtime `currentState` 刷新 UI，并提示用户检查后重试。最终验证：前端 source-contract 子集返回 95 passed，完整 `npm --prefix frontend test` 返回 1209 passed，`npm --prefix frontend run check:i18n` 通过，`npm --prefix frontend run build` 通过，Runtime S2 focused tests 返回 46 passed，Runtime `make test-postgres` 返回 5 passed；生成的 `veadk/webui` 产物已清理。 |
| 2026-09-15 | S2-08 full S2 gate | pass | 当前 diff 的 S2 unit、BFF、frontend、browser 与 PostgreSQL 门禁已关闭。VeADK BFF pytest 返回 28 passed；focused Ruff 通过；前端 source-contract 子集返回 95 passed；完整 `npm --prefix frontend test` 返回 1209 passed；`npm --prefix frontend run check:i18n` 与 `npm --prefix frontend run build` 通过。Runtime S2 focused tests 返回 46 passed；Runtime `make test-postgres` 返回 5 passed。真实浏览器 BC-04/05 使用 system Google Chrome via Playwright 访问 `http://127.0.0.1:18174` loopback fixture：两个浏览器上下文打开同一个 MPA Session，初始 ETag 为 `"6"`；浏览器 A 保存模型覆盖 `model-browser-a` 后 config revision 前进到 7；浏览器 B 用 stale ETag 清空 MCP 时收到预期 `412 execution_config_changed` 与 current state；显式 Session Profile upgrade 随后将 profile revision 升到 7、config revision 升到 8，同时保留显式模型覆盖并继承 `mcp-upgraded`。证据见 `evidence/browser/mpa-s2-1789491400/summary.json`、`BC-04/context-a-before.png`、`BC-04/context-a-after.png`、`BC-04/context-b-before.png`、`BC-04/context-b-conflict.png`、`BC-04/network-a.json`、`BC-04/network-b.json`、`BC-04/call-counts.json`、`BC-05/before.png`、`BC-05/upgrade-after.png` 和 `BC-05/revision-transcript.json`。预期浏览器噪声仅包含 local mode `/oauth2/userinfo` 404 探测和 BC-04 刻意触发的 412；没有未预期 HTTP 或 console 错误。`uv run --extra dev pyright ...` 当前为 `blocked`，因为本地环境没有 `pyright` 可执行文件或项目脚本。验证过程中发现资源卡整卡片详情 overlay 会截获对话按钮点击，已通过提升 action 按钮点击层级修复。 |
| 2026-09-16 | S3-01 `turn_execution_records` store and migration | pass | Runtime 已通过 `turn_execution_records` 持久化已接受的 MPA Turn，字段包含 `turn_id`、`invocation_id`、`operation_id`、带作用域的幂等键、规范化 request hash、冻结的 execution-config snapshot、dispatch key/status 和时间戳。SQL 与 in-memory store 都强制相同 key replay、相同 key 不同 payload 冲突、同一 Session 只能有一个 active Turn；PostgreSQL 接受路径在 replay/busy 检查前使用 Session 维度 advisory transaction lock。schema migration `0005_turn_execution_records.sql` 将 contract lane 推进到 schema version 5。验证：`uv run pytest -q tests/test_turn_dispatcher.py tests/test_run_acceptance.py` 返回 14 passed；Runtime S3 扩展回归返回 64 passed；`make test-postgres` 返回 6 passed。 |
| 2026-09-16 | S3-02 shared REST/A2A Turn acceptance and Studio run wiring | pass | Runtime `/api/v1/sessions/{sessionId}/run` 对 MPA Session 强制要求 `Idempotency-Key` 和 `executionConfigVersion`，dispatch 前持久化 S2 resolved snapshot，返回 `turnId`、`operationId`、`executionConfigRevision`；相同 key/相同 payload 重放原始 accepted 响应，stale config 返回 `412 execution_config_changed`，payload drift 返回 `409 idempotency_mismatch`，同一 Session 并发 active Turn 返回 `409 session_busy`。非 MPA run 保持旧响应形态。A2A 声明 `urn:veadk:mpa:execution:v1`；`params.metadata.veadkExecution` 使用同一个接受服务，把 durable invocation ID 绑定到 ADK run，推进 dispatch 状态 `dispatching -> succeeded|failed_retryable`，并将相同 key replay 作为 completed 终态返回且不二次执行模型。Studio 在发送前读取当前 MPA Session execution-config revision，给 `runSSE` 传入 per-run 幂等键，MPA runtime 走 `/run` 后接 `/sse`，BFF A2A 桥接同样转发 metadata。验证：Runtime S3 定向回归返回 64 passed；Runtime focused Ruff 通过；Runtime PostgreSQL gate 返回 6 passed；VeADK MPA server/integration pytest 返回 47 passed；BFF A2A bridge test 返回 3 passed；前端 source-contract 子集返回 14 passed；完整 `npm --prefix frontend test` 返回 1212 passed；`npm --prefix frontend run check:i18n` 与 `npm --prefix frontend run build` 通过；生成的 `veadk/webui` 产物已清理。 |
| 2026-09-16 | S3-03 accepted-turn/inbox recovery | pass | Runtime 现在在 `turn_execution_records` 中持久化 `dispatch_payload`，用于进程重启后重建已接受 Turn。`SessionService.initialize()` 扫描可恢复的 `accepted|dispatching|failed_retryable` Turn 记录，把已终态的 inbox 同步回 Turn 状态，使用原始 invocation/content/source/peer/environment metadata 重建缺失或 error inbox，并调度既有 inbox worker，不新增第二套 dispatcher。Inbox `enqueue_once()` 按 invocation ID 幂等，并可把先前 error row 重置为 queued 以便重试。running inbox lease 过期时，会先把关联 Turn 标为 `failed_retryable`，再通知 channel。验证：Runtime S3 回归返回 72 passed；Runtime focused Ruff 通过；Runtime `make test-postgres` 返回 6 passed。 |
| 2026-09-16 | S3-04/S3-05/S3-06 run recovery 与刷新门禁 | pass | Runtime cursor replay 已对未知非空 cursor 返回 `410 cursor_expired`，并保留 inbox terminal fence。Studio 现在会在刷新后恢复已持久化的 Runtime Agent 和 Session ID；即使当前 Session ID 已匹配但 turns 尚未加载，也会重新拉取该 Session；MPA run 通过 Runtime `/run` 加 `/sse` 执行，并把上一条已完成 assistant turn 的 `lastEventId` 传给 Runtime。验证：Runtime 扩展 S3 回归返回 251 passed；Runtime focused Ruff 通过；Runtime `make test-postgres` 返回 6 passed；VeADK 前端 focused tests 返回 15 passed；scenario harness pytest 返回 8 passed；MPA server/integration pytest 返回 51 passed；完整 `npm --prefix frontend test` 返回 1213 passed；`npm --prefix frontend run check:i18n` 通过；`npm --prefix frontend run build` 通过。真实浏览器 `BC-06` 在 `http://127.0.0.1:18175` 使用 system Google Chrome via Playwright 通过：刷新后的 Session 恢复 `event-before-refresh`，发送请求携带 `lastEventId=event-before-refresh`，Runtime 只返回 `event-after-refresh`，页面上两个事件各出现一次，未知 cursor 返回 `410 cursor_expired`。证据：`evidence/browser/mpa-s3-1789516481/BC-06/`。最终证据未使用 gstack browser，因为其 Playwright browser cache 缺失；改用 system Chrome 执行。 |
| 2026-09-16 | S4-01 participant schema/store foundation | pass | Runtime 新增 `a2a_turn_participants` schema version 6，并补齐 SQL/in-memory store，支持按 generation 注册参与方、owner-scoped lease heartbeat、带 generation 校验的 safe-point ACK、终态标记和按 generation 有序快照。这只是 S4 数据模型基础；S4-02 仍负责全员 ACK 后的聚合 pause barrier 状态推进。验证：`uv run pytest -q tests/test_turn_participants.py` 返回 5 passed；`uv run pytest -q tests/test_turn_participants.py tests/test_a2a_task_control.py tests/test_turn_control_api.py tests/test_p0_test_seams.py` 返回 37 passed；Runtime focused Ruff 通过；`make test-postgres` 返回 7 passed 并清理 PostgreSQL 资源。 |
| 2026-09-16 | S4-02 participant pause barrier 与 worker 注册竞态处理 | pass | Runtime 现在在存在 participant store 时使用 `ParticipantBarrierService` 处理 pause 请求。A2A 主执行器和 Codex worker 会登记 participant；safe-point ACK 带 generation 校验；部分 ACK 时聚合 task 保持 `pausing`；当前 generation 的所有活跃参与方 ACK 后 task 才进入 `paused`；在 task 已经 paused 后才加入的 late worker 会收到 worker pause，并先 ACK 当前 generation 后再 resume；终态 worker 不会被复制进后续 pause generation。resume 会从上一代 paused generation 生成下一代 running participant 记录。S4-03 仍负责精确 300 秒 lease-aware resume 边界，S4-04 仍负责关联 continuation。验证：`uv run pytest -q tests/test_turn_participants.py tests/test_participant_barrier.py tests/test_turn_control_api.py tests/test_a2a_app_lifecycle.py tests/test_codex_adapter.py::test_adapter_pauses_worker_and_continues_interrupted_turn_on_resume tests/test_codex_adapter.py::test_adapter_marks_completed_worker_participant_terminal_before_next_pause tests/test_codex_adapter.py::test_adapter_late_worker_joins_paused_generation_before_resume` 返回 27 passed；Runtime focused Ruff 通过；`make test-postgres` 返回 7 passed 并清理 PostgreSQL 资源。 |
| 2026-09-16 | S4-03 lease-aware resume 边界 | pass | Runtime 现在只有在聚合 task 为 `paused`、请求 generation 匹配、暂停时长不超过 300 秒、task owner lease 仍有效，且当前 paused generation 没有 `lost|failed` participant 或仍 running 但 lease 已过期/缺失的 participant 时，才允许 same-Turn resume。若仍有 running participant 且 lease 有效，则 resume 返回 `409 invalid_state`，要求等待安全点，而不是静默继续。超时或 lease 丢失的 resume 会把 task 转为 `interrupted`，返回 `resumeDisposition=new_turn_required`，状态/重放响应都携带 continuation prompt，并记录 resume 幂等 key，保证同 key 重试安全 replay。S4-04 仍负责创建关联 continuation Turn。验证：S4-03 focused boundary tests 返回 8 passed；broader S4 control regression 返回 104 passed；Runtime focused Ruff 通过；`make test-postgres` 返回 7 passed 并清理 PostgreSQL 资源。 |
| 2026-09-16 | S4-04 runtime-owned 关联 continuation | pass | Runtime 现在暴露 `POST /api/v1/a2a/tasks/{taskId}/continue`。接口要求 `Idempotency-Key` 和 `expectedGeneration`，只接受已经需要新 Turn 的 task 状态，通过旧 task invocation 找到上一条业务 Turn，并通过 `turn_execution_records.accept_continuation(...)` 写入 continuation。新 Turn 保留 `continuationOf=<oldTurnId>`，复用冻结的 execution-config snapshot 和 dispatch payload，关闭旧 active dispatch 行，并通过 `enqueue_once` 进入现有 inbox/outbox worker。相同 key/相同请求返回同一 continuation；相同 key 不同请求返回冲突。Studio 去掉 prompt fallback 以及 UI/BFF 接线仍属 S4-05。验证：S4-04 focused tests 返回 4 passed；broader S4 control/acceptance regression 返回 125 passed；Runtime focused Ruff 通过；`make test-postgres` 返回 8 passed 并清理 PostgreSQL 资源；两仓 `git diff --check` 通过。 |
| 2026-09-16 | S4-05 Studio Runtime continue 接线 | pass | Studio 现在在 resume 返回 `new_turn_required` 时通过 `continueTurnSSE(...)` 调用 Runtime `/api/v1/a2a/tasks/{taskId}/continue`，再用 continuation 返回的 `invocationId` 和当前 `lastEventId` 订阅 Runtime `/api/v1/sessions/{sessionId}/sse`。不再构造 `continuationPrompt + Original task` 文案，也不再发普通 `/run`；continuation streaming 开始时会清理旧 control state。验证：focused frontend source-contract tests 返回 37 passed；`npm --prefix frontend run check:i18n` 通过；`npm --prefix frontend run build` 通过，生成的 `veadk/webui` 产物已清理。 |
| 2026-09-16 | S4-06 RuntimePrincipal 撤权与副作用前复核 | pass | Runtime 新增共享 `runtime_authorization` helper 和可注入 `runtime_principal_authorizer`。REST `/run`、resume、`/continue` 会在接受副作用前复核当前授权。accepted Turn 的 dispatch payload 和 inbox metadata 携带规范化非 secret RuntimePrincipal 快照，使后台执行和重启恢复无需保存 bearer token 也能复核。ADK `before_tool_callback` 会在工具调用前复核；sandbox common 会在直接 sandbox dispatch 前复核；模型 endpoint 解析、workload TIP、OpenViking API key 解析和 sandbox `begin_run` 会在使用 secret material 前复核。fake deny authorizer 已证明拒绝路径不会产生 resume/continue/tool/secret 副作用。验证：S4-06 focused auth/secret/tool tests 返回 46 passed；broader S4 Runtime regression 返回 206 passed；Runtime focused Ruff 通过。外部 AgentKit 撤权查询仍属于部署态 S5 release gate。 |
| 2026-09-16 | S4-07 生命周期、PostgreSQL 与浏览器门禁 | pass | Runtime focused auth/secret/tool tests 返回 46 passed，`make test-postgres` 返回 8 passed 且 PostgreSQL 资源已清理。VeADK `uv run --extra dev pytest -q tests/frontend/server/mpa/test_scenario_harness.py` 返回 9 passed；前端 source-contract 子集与 i18n 返回 37 passed 且 i18n 通过；完整 `npm --prefix frontend test` 返回 1215 passed；`npm --prefix frontend run build` 通过，生成的 `veadk/webui` 产物已清理。真实浏览器 `BC-09` 使用 system Google Chrome via Playwright，在 `http://127.0.0.1:5174` 前端和 `http://127.0.0.1:8001` 后端上通过。证据位于 `evidence/browser/mpa-s4-1789532050/BC-09/`：`running.png`、`partial.png`、`paused.png`、`resumed.png`、`continue.png`、`summary.json`、`network.json`、`call-counts.json`、`state.json` 与 console 日志。summary 全部关键断言为 true：部分 ACK 保持 `pausing`；观察到 `new_turn_required`；点击前和刷新后都没有自动 `/continue`；显式 continuation replay 幂等；无未预期 HTTP 或 console 错误。预期本地噪声为四次 `/oauth2/userinfo` 404 探测。 |
| 2026-09-16 | S5-01 Secret reference migration 基础 | pass | Runtime schema version 7 向 `mpa_agents` 增加 `agent_api_key_ref`、`model_api_key_ref`、`secret_migration_status` 和 `secret_migration_operation_id`。`AgentConfigService` 在 AgentKit mode 下拒绝新的明文 `agentApiKey`/`modelApiKey` 写入，但允许 reference 字段。`SecretReferenceMigrationService` 先创建 reference 再清空明文，provider/DB 失败时保留明文，并且使用同一幂等键重试不会重复创建 provider reference。Runtime 模型与内置 MCP 路径只在执行时 Secret 使用边界解析 reference，缺少 resolver 时 fail closed。验证：S5-01 focused pytest 返回 95 passed；focused Ruff 通过；`make test-postgres` 返回 9 passed 且 PostgreSQL 资源已清理。 |
| 2026-09-16 | S5-01a canary-safe value-aware redaction | pass | Runtime 现在会在 Secret reference migration 中注册 legacy 明文 Secret 字面值，并在 API access log、Session 可见文本/events、Runtime Console 响应、lifecycle/trace detail bounding 和 SQL trace-step 持久化中执行 value-aware redaction。该策略可以在非敏感 key 或自由文本中遮盖已注册 canary 值，同时保留 `flow_id`、`user_code` 等非 Secret 业务 ID。`runtime_operations` 当前只保存幂等元数据，没有需要本次处理的任意 response snapshot 字段。验证：覆盖 secret migration、session redaction、API access log、Runtime Console、runtime operations 和 trace store 的 focused Runtime pytest 返回 89 passed；broader S5 Runtime regression 返回 178 passed；focused Ruff 通过；`make test-postgres` 返回 9 passed 且 PostgreSQL 资源已清理。 |
| 2026-09-16 | S5-02 unique Runtime binding 与 `MpaAgentView` BFF | pass | VeADK 现在暴露 `GET /web/mpa/agents/{mpaInstanceId}/view`。BFF 会解析当前用户可见的 MPA Runtime binding：0 个返回 `runtime_missing`；多个返回 `binding_ambiguous`，带候选 binding 且关闭写入/debug；唯一 binding 时聚合 Runtime `profile-status`、Runtime/version/readiness metadata、capabilities 和匹配的 active operation。主 app resolver 会探测配置的 Runtime regions，只保留 `veadk:agent-type=mpa` Runtime，合并 tag service metadata，并复用现有 Runtime connection resolver；不调用 Managed Agent API。S5-03 仍负责前端详情页 UI。验证：focused MPA BFF route/main-app tests 返回 32 passed；focused Ruff 通过。 |
| 2026-09-16 | S5-03 MPA detail view-model consumption | pass | Studio 现在在 MPA Runtime-backed 详情页消费 `MpaAgentView`。TypeScript client 暴露 `MpaAgentView` 和 `getMpaAgentView(...)`；`AgentWorkspace` 会在 MPA 详情页加载该 view，展示 MPA 控制面状态提示，并且只有 `bindingStatus=bound` 时才加载 Session 配置。`runtime_missing` 和 `binding_ambiguous` 会阻塞写入；`orphan_runtime` 在 Profile 应用前阻塞 Session 配置和诊断。非 MPA 详情继续使用现有 Runtime detail/version/update 路径。Runtime delete 已由后续 S5-07 切片完成，更完整 Debug/Trace UI 已由 S5-05 完成。验证：focused frontend source-contract tests 返回 33 passed；完整 frontend tests 返回 1216 passed；i18n 与 build 通过；focused MPA BFF/main-app tests 返回 32 passed；focused Python Ruff 通过。 |
| 2026-09-16 | S5-04 Runtime Console/Trace structured correlation | pass | Runtime Console trace 响应现在包含顶层 `correlation` 和每个 step 的 `correlation`。字段从现有已脱敏 trace details 中抽取并规范化，覆盖 MPA instance、Profile revision、execution-config revision/ETag、业务 Turn、A2A task、Runtime ID/version，以及 Codex/subagent worker session/turn/profile 标识。Studio 后续可读取稳定字段，不需要解析任意 `details` JSON。S5-05 仍负责 Studio Debug/Trace/history/usage 视图。验证：Runtime Console/Trace pytest 返回 72 passed；focused Ruff 通过。 |
| 2026-09-16 | S5-05 Studio MPA diagnostics view | pass | Studio 现在在 `AgentWorkspace` 中提供 MPA-only Diagnostics section。它通过现有 Runtime proxy 读取 Runtime Console admin run history 和最新 invocation trace，展示 S5-04 的结构化 correlation 字段，列出有界 trace steps，并继续复用现有 Usage tab 承载 usage 数据。当 MPA binding 缺失、重复、orphan，或不是当前对话 Runtime，或没有当前 Session 时，Diagnostics 会明确阻塞。验证：focused frontend source-contract tests 返回 34 passed；完整 frontend tests 返回 1216 passed；i18n 与 build 通过；focused MPA BFF/main-app tests 返回 32 passed；focused Python Ruff 通过。 |
| 2026-09-16 | S5-06 Runtime update/release/rollback 兼容性 preflight | pass | VeADK 现在提供共享的进程内 MPA P0 兼容性评估器，`scripts/verify-mpa-p0-contract.sh` 和 Studio 写接口使用同一套规则。MPA 直连 Runtime update（`/web/deploy-agentkit`）、GitHub Actions delivery setup（`/web/github-delivery/cicd-pipeline`）、首次 delivery 分支初始化（`/web/github-delivery/init-main`）、已绑定源码同步（`/web/github-cicd/runtime-sync`）和 rollback PR 创建（`/web/github-delivery/rollback-pr`）都会在 AgentKit SDK 或 GitHub mutation 前拒绝 malformed/incompatible manifest，返回 `409 mpa_compatibility_preflight_failed`。浏览器在 MPA 发布/更新和回滚路径发送 `agentCategory=mpa`；非 MPA 路径保持原行为。本地检查通过：manifest 加 MPA update/GitHub release/rollback guard 的 focused pytest 返回 12 passed；前端 source-contract tests 返回 41 passed；完整 frontend tests 返回 1217 passed；focused Ruff 通过；`compileall` 通过；`npm --prefix frontend run check:i18n` 通过；`npm --prefix frontend run build` 通过且只有既有 Vite chunk warning。build 生成的 `veadk/webui` 产物已清理。 |
| 2026-09-16 | S5-07 授权删除影响预览与分阶段清理 | pass | VeADK 现在提供 `GET /web/mpa/agents/{mpaInstanceId}/delete-preview` 作为 Studio MPA 删除预览。预览会解析已授权 Runtime binding，读取 Runtime `profile-status`，调用现有 Runtime `GET /api/v1/sessions?include_a2a=true`，返回 active operation、active/idle/debug 可见会话计数、阻断原因和分阶段清理计划。`/web/delete-runtime` 会在执行前重新检查服务端 Runtime 标签 `veadk:agent-type=mpa`，只有确认是 MPA Runtime 才进入 MPA 清理；存在 active operation 或处于 `queued|running|pausing|paused|resuming` 的 active session 时以结构化 `409` 拒绝；无阻断时先通过现有 Runtime `DELETE /api/v1/sessions/{sessionId}` 删除可见 idle/terminal 会话，再删除 AgentKit Runtime。Session 清理时单个 session `404` 视为已清理，以便安全重试。浏览器会在单个 MPA 删除确认前拉取并展示预览，存在阻断时禁用确认按钮。该切片不新增 `agentkit-mpa-agent` 数据库 schema 或 API；当前预览只能统计已授权目标 Runtime API 可见的会话，不能声明跨用户全局 session 状态。Local checks 通过：MPA BFF/client/delete focused pytest 返回 31 passed；完整 frontend tests 返回 1217 passed；前端 source-contract focused tests 返回 33 passed；focused Ruff 通过；`compileall` 通过；`npm --prefix frontend run check:i18n` 通过；`npm --prefix frontend run build` 通过且只有既有 Vite chunk warning。build 生成的 `veadk/webui` 产物已清理。 |
| 2026-09-17 | S5-08 Studio 统一 Profile 管理入口 | pass | MPA Agent 详情页现在提供 Agent 级 `Profile 配置` 分区作为 Studio 管控入口。该分区读取专用 `MpaAgentView`，展示 apply 状态、revision/ETag、模型、系统提示词、Tool/Skill/MCP 摘要，通过类型化 MPA BFF operation 路径应用当前 Studio Profile，并提供 `编辑 Profile` 入口。编辑复用现有 Studio Agent 工作台的 Profile-only 模式：跳过环境/部署步骤，不调用 `/web/deploy-agentkit`，保存时通过 `applyMpaProfileAfterDeployment(...)` 写入 mpa-agent；orphan Runtime 走 create/`If-None-Match: *` 语义，已绑定 Runtime 走 ETag update 语义。MPA 详情不再探测依赖 `/list-apps` 的通用 Runtime update capability，因为它无法准确表示 A2A-only mpa-agent Runtime。orphan Runtime 保持可写以支持首次 Profile apply，但 Session 配置和诊断仍在 binding 变成 `bound` 前阻塞。本地 dev 现在在 Studio TOS 缺失时使用进程内 operation repository，保证 `veadk studio --dev` 可以对真实 Runtime 验证 Profile apply；生产仍要求 TOS 持久化。Runtime 已重新构建并发布镜像 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/mpa_agent:mpa-p0-sessioncfg-init-local-20260917` 到 Runtime `r-yeuujrrcowb21078p9jh` version 58，并修复 MPA Session create 自动初始化 execution-config revision 1。真实链路检查通过：BFF Profile update 返回 `202/succeeded/profileRevision=3`，`MpaAgentView` 返回 `bindingStatus=bound` 且 `canWrite=true`、`canDebug=true`，native Session create 返回 `executionConfigRevision=1`，native `/run` 返回 `turnId/operationId/invocationId`，native `/sse` 输出最终文本并发送具名 `event: done`，Studio BFF `run_sse` bridge 也输出最终文本，持久事件只包含一条用户消息与一条带 trace ID 的最终模型消息。使用合法 UUID `contextId` 的命令行直连 A2A JSON-RPC 返回 HTTP 200 且 task state 为 `completed`；打包的 AgentKit CLI `agentkit invoke run --runtime-id/--endpoint --a2a` 对该 A2A-only Runtime 仍返回 404，记录为 AgentKit CLI 兼容缺口，不影响 Studio 统一管控路径。本地检查通过：focused frontend source-contract tests 返回 137 passed；MPA operation/BFF pytest 返回 43 passed；Runtime Session/config/run pytest 返回 186 passed；Runtime focused Ruff 通过；VeADK focused Ruff/compileall/diff-check 通过；`npx tsc --noEmit` 通过；`npm --prefix frontend run check:i18n` 通过；完整 `npm --prefix frontend test` 返回 1227 passed；`npm --prefix frontend run build` 通过且只有既有 Vite chunk warning。浏览器静态加载通过 system Chrome 产出登录 DOM 和截图；交互式浏览器自动化受限于 gstack 的 Playwright browser cache 缺失，未声明通过。 |
| 2026-09-17 | 多轮完成回答持久展示回归 | pass | 之前的 post-SSE 事件栅栏对账可以防止过期持久数据覆盖最新实时回答，但没有覆盖持久多轮历史重放。严格 DOM 检查复现了真实缺陷：两条用户轮次重放为两个用户节点，却只剩一个 assistant 节点。根因是 `eventsToTurns(...)` 在每段历史都用相同 `adk-history` 前缀重建 projector；每个 projector 都生成 `localId=adk-history-0`，后续 assistant 轮次因此在 upsert 时替换更早轮次。Studio 现在为每个历史分段使用单调递增前缀，使 projector 本地序号在整个 Session transcript 内保持唯一。回归测试修复前稳定失败且只得到 `second answer`，修复后同时得到两条回答、两个最终事件 ID 和不同 local ID。focused tests 返回 43 passed；完整前端测试返回 1236 passed；`npx tsc --noEmit`、i18n、生产构建与 scoped diff 检查均通过。随后对真实 Studio Session 严格按顺序检查 `.turn--assistant` 节点：新增两轮实时对话完成并额外等待 30 秒后，五个 assistant turn 均保留；整页重载后仍保留五个且顺序正确。由于提问或 reasoning 也可能包含同样文本，整页文本命中被明确排除为验收证据。 |
| 2026-09-17 | MPA 实时父级沙箱活动终态收敛 | pass | 真实 Studio 执行稳定复现：命令卡片和最终回答均已完成，但父级 `sandbox_task` 卡片仍为 `running`。抓取的 SSE 帧证明，实时订阅先输出回答增量，随后只输出 `status=completed`、`finalAlreadyEmitted=true` 的 `sandbox_task` wrapper response；持久事件列表还包含 `source=sandbox,eventType=invocation.completed`，所以刷新后原本就是正确状态。Studio 不再无条件丢弃 wrapper；当 invocation 仍有 active turn 时，它用 wrapper 关闭父级工具，同时保留已推流的回答/工具 block，并以 wrapper event ID 将 projected turn 标记为非 streaming；持久重放已经由 sandbox final event 关闭 Turn 时仍忽略 wrapper，避免重复卡片。focused regression 在旧逻辑上失败，修复后通过。完整 `npm --prefix frontend test` 返回 1237 passed；`npx tsc --noEmit`、i18n、生产 build 与 scoped diff 检查均通过。新的真实 Studio `whoami` 执行先观察到父/子活动进入 running，随后在不刷新页面的情况下出现最终回答 `root`，父级变为 `data-status=completed`，spinner 消失且 remaining running activity 为 0；整页刷新后，最新两条活动仍为 completed、无 spinner，最终回答仍可见。 |

## 13. 实现变更记录

2026-09-16：关闭 S4-07 生命周期、PostgreSQL 与浏览器门禁。loopback `turn_lifecycle` 场景已提供按 Session 和 task 查询 control status、pause/resume 命令、`new_turn_required` 种子、显式 Runtime `/continue`、continuation SSE、调用计数和状态证据。Studio 会把 `new_turn_required` 显示为本地化的检查点续跑状态，不再暴露原始协议枚举。真实浏览器 `BC-09` 使用 system Google Chrome via Playwright 通过；证据位于 `evidence/browser/mpa-s4-1789532050/BC-09/`。

2026-09-16：在 `agentkit-mpa-agent` 实现 S5-01 Secret reference migration 基础。schema version 7 增加 Secret reference 和迁移状态字段。迁移服务采用 reference-first 且可重试：provider 失败或数据库更新前中断时保留明文；成功后清空明文，只记录 reference/status。Runtime 执行在模型和内置 MCP 的 Secret 使用边界通过 resolver seam 消费引用。真实 AgentKit Vault provider 接线仍留给后续 release-gate 集成。

2026-09-16：在 `agentkit-mpa-agent` 实现 S5-01a canary-safe redaction。Secret reference migration 读到 legacy 明文后，会先把这些值注册为 value-aware redaction 字面值，再创建外部引用。API access log、Session 输出脱敏、Runtime Console 脱敏、lifecycle details 和 trace-step 持久化现在都会从字符串和嵌套结构中移除已注册字面值，同时不会因为宽泛 key-name 规则误隐藏 `flow_id`、`user_code` 等业务参数。focused 与 broader Runtime 检查均通过；本次没有新增 `runtime_operations` response-snapshot 脱敏，因为当前实现只保存 operation ID、request hash、状态和时间戳。

2026-09-16：在 VeADK 实现 S5-02 BFF `MpaAgentView` 切片。`GET /web/mpa/agents/{mpaInstanceId}/view` 统一输出 0/1/N Runtime binding 判定、active operation 摘要、Runtime metadata、Profile status、capabilities 和 safe error。0 个 binding 为 `runtime_missing`；多个 binding 为 `binding_ambiguous`；唯一 MPA-tagged Runtime 会暴露 binding 状态，后续切片据此区分 Profile 写入、Session 配置和 Debug 能力。消费该 view-model 的前端详情页仍属于 S5-03。

2026-09-16：实现 S5-03 前端 `MpaAgentView` 消费切片。`AgentWorkspace` 现在会在 MPA 详情页加载专用 view-model，在基本信息区展示 binding 健康状态；当 Runtime binding 缺失、重复或 orphan 时阻止 Session 配置管理；非 MPA 详情、更新和版本流程仍走原有逻辑。

2026-09-16：实现 S5-04 Runtime Console/Trace correlation 切片。Runtime trace API 现在会在既有有界、已脱敏 details 旁返回稳定的 Agent/Profile/config/Turn/task/runtime/worker 关联字段；S5-05 的 Studio 视图可直接消费这些字段，不需要解析任意 `details` JSON。

2026-09-16：实现 S5-05 Studio diagnostics 消费切片。MPA Agent 详情页现在有 MPA-only Diagnostics section，通过现有 Runtime proxy 读取 Runtime Console run history 和最新 trace，展示结构化 correlation，并继续保持非 MPA 详情、版本、更新路径隔离。

2026-09-16：实现 S5-06 兼容性 preflight 切片。`scripts/mpa_p0_contract.py` 现在委托共享的 `veadk.cli.mpa_p0_contract` 评估器；Studio 在 MPA 直连 Runtime update，以及 GitHub delivery setup、source sync、rollback PR 创建前执行同一矩阵检查。incompatible 或 malformed manifest 会在副作用前以安全结构化 `409` 返回；compatible manifest 继续原路径。本切片不修改 Runtime 数据模型或 mpa-agent API。

2026-09-16：实现 S5-07 授权删除预览与分阶段清理切片。新的 Studio BFF 预览接口会明确展示将被清理的内容：先删除可见 idle/terminal Runtime 会话，再通过 Runtime 会话清理路径移除其诊断数据和挂载元信息，最后删除 AgentKit Runtime 资源。删除执行会在服务端重新运行同一组检查，拒绝 active operation 和处于 `queued|running|pausing|paused|resuming` 的 active session；单个 session 删除遇到 `404` 时视为已清理，便于安全重试；如果 Runtime 标签没有标记为 MPA，即使浏览器传了 `agentCategory=mpa` 也不会走 MPA 清理路径。该切片复用已有 mpa-agent session list/delete API 和 AgentKit Runtime delete API，不需要 Runtime 数据库迁移或新增 mpa-agent endpoint。

2026-09-17：实现 S5-08 Studio 统一 Profile 管理入口。MPA 详情页现在把 Profile 配置作为 Agent 级主管理面，支持状态查看、应用/重新应用和编辑，并统一走 MPA BFF Profile operation。`编辑 Profile` 复用既有 Studio Agent 创建工作台的 Profile-only 模式，用户修改的是同一份模型、系统提示词、Tool、Skill、MCP 与 Multiagent 配置；保存时只把 Profile 应用到 mpa-agent，不触发通用 Runtime 部署/更新流程。BFF view 对 `orphan_runtime` 开放写能力以支持首次 Profile apply；Debug 和 Session 配置仍需等待 Profile binding 完成。本地 `veadk studio --dev` 在 Studio TOS 缺失时使用进程内 MPA operation repository，保留幂等与 ETag 语义用于本地验证；生产仍要求 TOS 持久化。Runtime Session 创建现在会在 Studio 传入 `mpaInstanceId + profileRevision` 且未传 `executionConfigRevision` 时初始化 execution-config revision 1。该设计保持 AgentKit Studio 是统一管控入口，同时避免使用 Managed Agent API，也避免在 mpa-agent 中重复建设产品配置表单。

2026-09-17：修复已完成回答在持久多轮历史中的消失路径。第一次对账修复是必要但不充分的：严格浏览器检查表明，每个由用户消息分隔的 assistant 历史段都复用了 `adk-history-0`，导致 upsert 覆盖更早回答。`eventsToTurns(...)` 现在为每个历史分段创建带单调递增索引的唯一 projector 前缀。对账仍以精确最终事件 ID 为栅栏；如果更新的本地回答已经开始，就拒绝替换 transcript。回归和浏览器验收改为断言有序 assistant turn 节点、延迟后的稳定性以及整页重载后的持久性，不再以整页搜索预期文本作为通过条件。

2026-09-17：修复 MPA 实时父级沙箱活动终态收敛。实时 `/sse` 路径可能以 wrapper `sandbox_task` function response 结束，而不会重放持久化的 sandbox `invocation.completed` 事件。projector 现在只在 invocation 仍 active 时把 `finalAlreadyEmitted=true` 作为控制终态：关闭既有父级卡片和 Turn，同时保留已经推流的输出。持久历史重放在 sandbox final event 已关闭 Turn 后仍忽略该 wrapper，避免生成重复工具卡。
