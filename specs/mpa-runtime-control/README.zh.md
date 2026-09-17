# MPA Runtime 控制

- Component ID：`mpa-runtime-control`
- 状态：`draft`；S1、S2、S3、S4、S5-01、S5-01a、S5-04 与 S5-08 Session 创建修复已实现；S5-06 与 S5-07 no-impact 记录已补充；其余 S5 仍为目标契约
- 修订日期：2026-09-18
- English：[README.md](README.md)
- PRD：[MPA AgentKit P0 功能迁移](../../prd-spec/features/mpa-p0-productionization/2026-09-15-mpa-p0-productionization-design.zh.md)
- 负责代码：`agentkit-mpa-agent` 的 Agent、Session、A2A、worker、鉴权与诊断模块

## 职责与权威边界

AgentKit Studio 持有 MPA 创作入口以及 Skill、Tool、Environment、Vault 等平台资源。本期不使用 Managed Agent CRUD/version/Session。mpa-agent 持有不可变的可执行 Profile revision、会话执行配置版本、Turn 执行记录、参与方状态和诊断关联，不提供模板、专家、审核安装或独立发布服务。Studio/BFF 是客户端和编排层，不成为执行状态权威。

代码基线 `2f5e039` 已有 Agent config revision、Session CRUD/run/SSE/events/MCP、A2A generation/lease 与 pause/resume、worker interrupt、health/readiness 和 Runtime Console，这些是复用点。当前 P0 分支已实现下文所述 S1 Profile/readiness/auth 基础、S2 Session execution-config/Profile-upgrade Runtime 子集、S3 Turn acceptance、dispatcher recovery 与刷新 cursor 子集、S4-01/S4-02 的 participant 数据模型和 pause-barrier 子集、S4-03 lease-aware resume 边界、S4-04 Runtime linked continuation API/outbox，以及 S5-08 MPA Session 创建初始化修复。Studio 控制接线和最终诊断仍是后续目标契约。

## CON-1：身份与授权

P0 统一使用 `RuntimePrincipal v1`：`iss`、`aud`/authorized client、`sub`、`account_id`、`workspace_id`、`agent_id`、`actions[]`、`iat`、`nbf`、`exp`、`jti`，允许时钟偏差 30 秒。Studio OAuth/gateway 中间件先验证用户 bearer token，BFF 只转发这份已验证 token；AgentKit Runtime custom JWT authorizer 和 mpa-agent 通过同一 issuer discovery/JWKS 按 `kid` 校验签名、轮换、audience/client 和时效。token TTL 由现有 issuer 策略决定，M0 必须记录实测值，不能在 BFF 自签或假定 5 分钟。每次副作用前都通过可注入的 `RuntimePrincipalAuthorizer` 接线查询当前授权/撤权状态。不得信任浏览器 owner/account Header，也不得把 Runtime key-auth 当最终用户身份。

REST 使用 `Authorization: Bearer <runtime-assertion>`；A2A 使用 `X-Ve-TIP-Token`，但 TIP verifier 必须映射出同一 `RuntimePrincipal`，不能只保留 `sub`。现有 `X-Jwt-Token` 仅作为旧 capability 路径：缺少 v1 scope claim 的请求可读取旧资源，但不能调用 Profile、execution-config、run/continue 等新写接口。`DISABLE_JWT_AUTH` 只允许本地测试 profile，AgentKit mode 启动时若开启则 execution-ready 失败。

当 `MPA_AGENTKIT_MODE=true` 时，仍依赖 `require_auth` 的旧 ADK endpoint（包括 `GET /list-apps`）复用同一个 AgentKit `Authorization` Runtime principal，不再单独强制要求 `X-Jwt-Token`。这是 adapter 兼容规则，不是第二套身份机制。非 AgentKit mode 继续保持既有 `X-Jwt-Token` 契约。无论直连 Runtime 还是经过 Studio BFF proxy，缺失或非法的 AgentKit 凭据都必须 fail closed。

在 Profile apply、Session 创建/读取、执行配置修改、Turn 接受、resume/continue、Secret 解析和外部工具 dispatch 前检查对应 scope。已实现的 S4-06 子集只在 accepted Turn dispatch payload 与 inbox metadata 中持久化规范化的非 secret `RuntimePrincipal` 快照，使后台执行和重启恢复无需保存 bearer token 也能复核授权。撤权阻止后续副作用；已发出的外部副作用不声称可撤销。普通响应、日志、trace、错误和诊断不包含 Secret 原值。已实现的 S5-01a 子集会把 Secret reference migration 读到的 legacy 明文 Secret 字面值注册到进程内脱敏 registry，然后在 API access log、Session 对用户可见输出/events、Runtime Console 响应、lifecycle details 和 trace-step 持久化中遮盖这些精确值。该 value-aware redaction 会保留 `flow_id`、`user_code` 等非 Secret 业务标识。

## CON-2：Studio MPA Profile 执行投影

`PUT /api/v1/agents/{mpaInstanceId}/profile` 的路径沿用现有 runtime 实例 ID，只接受 BFF 从 Studio 已接受 draft 校验并规范化的 Profile。请求包含 `sourceProfileId`、digest 及 name/description/system/model/tools/skills/MCP/Multiagent/allowlisted metadata。BFF 不分配 revision；Runtime 在成功 CAS 事务中分配并返回唯一 `profileRevision`。首次应用必须使用 `If-None-Match: *`，后续应用必须使用 `If-Match: "<runtimeRevision>"`；两者同传返回 `400 invalid_precondition`，均未传返回 `428 precondition_required`。成功响应和 status 响应返回强 ETag。

runtime 将 Profile 映射到新的 `mpa_agents` revision，并保存 source Profile ID/digest 和应用状态。相同 operation key/digest 返回原分配 revision；stale ETag 返回 `412 profile_changed`；对已分配 revision 用不同内容重放返回 `409 profile_version_conflict`；未知 Tool/Skill/Multiagent 结构为 `422 unsupported_profile_field`。`GET /api/v1/agents/{mpaInstanceId}/profile-status` 返回 `pending|applying|applied|failed`、目标/已应用 revision、runtime revision、operation ID、安全错误和 retryable。

## CON-3：会话执行配置版本

“会话执行配置版本”是单个 Session 的递增执行选择记录，并非平台资源副本。它组合固定的 MPA Profile revision 与会话覆盖，只保存 Skill/Tool/MCP/Environment/Knowledge/Vault 等资源 ID、明确版本或 digest、模型覆盖、权限 revision、失效引用和更新时间；资源正文与 Secret 仍由 AgentKit 管理。

runtime 持久化契约是 append-only。`session_execution_configs` 以 `(app_name, session_id, revision)` 为主键，保存强 `etag`、`mpa_instance_id`、`profile_revision`、`profile_default_revision`、JSON `overrides`、JSON `effective_refs`、JSON `invalid_refs`、`updated_by`、`created_at`、`updated_at`。当前版本读取使用 `(app_name, session_id, revision DESC)`。SQL 写入先用 PostgreSQL advisory transaction lock 串行化单个 Session 的 revision 流，再比较调用方 ETag 并追加 revision N+1；已有行永不原地更新。

`POST /api/v1/sessions` 在请求携带 `mpaInstanceId + profileRevision` 且没有显式携带 `executionConfigRevision` 时，会初始化第一条 execution-config revision。响应随后返回 `executionConfigRevision=1`，使 Studio 可以立即把合法版本传给第一次 MPA `/run`。如果恢复或迁移调用方显式传入 `executionConfigRevision`，Runtime 保留该值。

`GET /api/v1/sessions/{sessionId}/execution-config` 返回 revision 与强 ETag。`PATCH` 必须携带 `If-Match`，按资源类别执行 replace、clear 或 inherit。匹配则原子地产生下一 revision；缺失为 `428`；冲突为 `412 execution_config_changed` 并返回安全的当前 revision；校验失败不产生 revision。修改只影响下一 Turn，活动 Turn 不变。`POST /api/v1/sessions/{sessionId}/profile-upgrade` 携带 `targetProfileRevision`、同一 ETag 与 `Idempotency-Key`；目标 Profile 必须已 applied。活动 Turn 可存在，但新 revision 只在下一 Turn 生效；降级返回 `409 downgrade_not_allowed`；并发冲突返回 `412`。

已实现的 S2-03 子集支持 `model` 和 `mcpServers` 类别变更。其他类别在对应 AgentKit 资源 resolver 存在前返回 `422 unsupported_execution_config_category`。未知 MCP ID 返回 `422 resource_unavailable`，且不创建 revision。不带 `mpaInstanceId + profileRevision` 的非 MPA Session 返回 `404 execution_config_not_found`，不会隐式创建 MPA 状态。

已实现的 S2-05 Profile 升级子集暴露 `POST /api/v1/sessions/{sessionId}/profile-upgrade`。该接口要求 `Idempotency-Key` 和当前 execution-config `If-Match`，只接受更高且已 applied 的 `targetProfileRevision`，保留显式 override，并基于目标 Profile 重新计算 inherit 默认值。schema version 8 的 SQL `runtime_operations` ledger 会持久化 request hash 与安全结果，因此相同 key/相同目标可跨 Runtime 进程 replay；相同 key/不同目标返回 `409 idempotency_mismatch`。

Turn 接受前，Runtime 会把选定的 execution-config revision 解析为不可变 `SessionExecutionConfigSnapshot`。snapshot 包含已接受的 revision 与 ETag、MPA instance、Profile revision、Profile 默认 revision、overrides、effective references、invalid references 和 accepted timestamp。它是 Turn acceptance 与 trace 关联使用的值对象，不是第二份可变配置记录。

示例：Session revision 6 使用 Skill `s-1@3`。客户端 A 把模型改为 M2，生成 revision 7；客户端 B 仍基于 ETag 6 更新 Skill，收到 412。正在运行的 Turn 仍使用 revision 6，之后新 Turn 使用 revision 7。

## CON-4：Turn 接受与幂等

`POST /api/v1/sessions/{sessionId}/run` 显式接受 `executionConfigVersion` 与 `Idempotency-Key`。A2A Agent Card 声明 `urn:veadk:mpa:execution:v1`，`params.metadata.veadkExecution` 携带同名字段；缺失扩展的旧调用只允许默认 revision 且不允许 Session override。runtime 在事务外解析资源版本，在事务内比较 Session revision/权限版本、占有活动 Turn、写入不可变 `turn_execution_records` 和 dispatch intent，再触发外部执行。物化时复核资源版本/digest 和权限；漂移在副作用前失败。

Run 幂等范围为 `user_id + app_name + session_id + source + Idempotency-Key`，由 `turn_execution_records` 唯一约束，并保存规范化 request hash、冻结 config snapshot、`accepted|dispatching|succeeded|failed_retryable|failed_terminal` 和持久 `turnId/invocationId/operationId`。相同 key/hash 返回原 accepted invocation；相同 key 不同 payload 返回 `409 idempotency_mismatch`。pending Profile 不成为 `mpa_agents` current revision；成功事务才切换 applied revision。崩溃恢复复用 dispatch key，不能产生第二个 Turn。

已实现的 S3 子集使用 `turn_execution_records` 作为持久 run-acceptance ledger。REST `/run` 对 MPA Session 要求幂等键和请求的 execution-config revision，保存冻结的 `SessionExecutionConfigSnapshot`，返回 `turnId`、`operationId` 和 `executionConfigRevision`，并保持非 MPA Session 的旧响应形态。A2A 通过 `params.metadata.veadkExecution` 接受相同 metadata，把已接受的 invocation ID 绑定到 ADK request，将 dispatch status 推进到 `dispatching`，再记录 `succeeded` 或 `failed_retryable`。相同 A2A key/hash replay 返回 completed 幂等重放提示，不再次执行模型。`dispatch_payload` 支持重启后重建缺失/error inbox，不引入第二套 dispatcher。Studio 会把上一条已完成事件 ID 传给 Runtime SSE，使浏览器刷新后从 cursor 之后续接而不是从头重播。

## CON-5：完整 Turn 生命周期与 continuation

状态为 `queued -> running -> pausing -> paused -> resuming -> running -> completed|failed|cancelled`。`a2a_task_controls` 保持聚合 generation；每个活动主执行器/worker 在 `a2a_turn_participants` 登记 lease、状态、安全点和 checkpoint。只有同 generation 的所有活动参与方确认后才是 `paused`；部分确认保持 `pausing` 或产生分类超时。

已实现的 S4-02 子集在存在 `a2a_turn_participants` 时通过 `ParticipantBarrierService` 处理 pause 请求。pause 命令推进聚合 task generation，并从上一 generation 复制活跃参与方。单个 participant ACK 只更新自己的行；只有当前 generation 的所有活跃参与方都处于 `paused` 或终态后，服务才调用 task-level `acknowledge_safe_point` 推进聚合状态。旧 generation 或 owner 不匹配的 ACK 被忽略。若 Codex worker 在聚合 task 已经 `paused` 后才启动，它仍会登记到当前 generation，收到 worker pause，ACK 当前 generation，并等待 resume 后再继续。completed、failed 或 cancelled 的 worker turn 会把 participant 行标为终态，因此后续 pause generation 不会等待已经结束的 worker。resume ACK 后，Runtime 会从上一代 paused generation 生成下一代 running participant 记录。

resume 时重查权限与参与方可恢复性。已实现的 S4-03 边界只在 task 暂停不超过 300 秒、task owner lease 仍有效，且 participant generation 中没有 `lost|failed` participant，也没有 lease 过期/缺失的 running participant 时恢复原业务 Turn。仍处于 running 但 lease 有效的 participant 会让 resume 返回 `409 invalid_state`，要求调用方等待安全点；它不会被直接转为 continuation。超过 300 秒、owner lease 丢失、participant lost/failed 或重启后无法恢复时返回 `new_turn_required`。`new_turn_required` 转换会记录 resume 幂等 key，相同 key 可安全 replay。

`POST /api/v1/a2a/tasks/{taskId}/continue` 只有在用户显式操作后调用。已实现的 S4-04 Runtime API 要求 `Idempotency-Key` 与 `expectedGeneration`，只接受 `interrupted|orphaned` 控制状态，通过旧 task invocation 找到上一条业务 Turn，并插入带 `continuation_of=<oldTurnId>` 的 linked `turn_execution_records` 行。continuation 复用冻结的 execution-config snapshot 和 dispatch payload，关闭旧 active dispatch 行，并通过 `enqueue_once` 调度现有 inbox/outbox worker。相同 key/相同请求返回同一 continuation；相同 key 不同请求返回 `idempotency_mismatch`。不承诺与 SDK `DatabaseTaskStore` 的分布式 ACID；已接受的 continuation dispatch 继续由现有 outbox 恢复。S4-05 接线完成后，Studio 不再拼 prompt 调用普通 send。

## CON-6：事件、刷新与诊断

SSE 重放复用 ADK 持久 Session events 和 inbox terminal fence，内存 StreamHub 只负责低延迟直播，不是刷新后的权威。cursor 为持久 event ID；服务端按 Session events 的持久顺序从游标后重放，随后接入 live stream。找不到非空 cursor 时返回 `410 cursor_expired`，不再从头静默重放。相同 event/invocation/type 去重，不重复累计文本、usage 或 artifact；缺少 terminal 保持未知/失败态而非成功。

Runtime Console/trace 复用现有存储，并提供 MPA instance、Profile revision、session execution-config revision、Turn、worker run/session 的结构化关联。详情统一脱敏，有界返回，不通过解析任意 JSON 才能定位核心链路。已实现的 S5-04 子集在 invocation trace 响应和每个 trace step 上暴露规范化 `correlation` 对象，从已脱敏 details 中抽取 MPA instance、Profile revision、execution-config revision/ETag、业务 Turn、A2A task、Runtime ID/version，以及 Codex/subagent worker session/turn/profile 标识。

执行配置和事件持久化只服务 mpa-agent 的业务 Session。P0 不创建 AgentKit Managed Agent Session，也不建立双 Session ID 映射；AgentKit `AgentWithOverrides` 仅作为平台能力记录，不进入本契约。

## CON-7：API 与错误

| API | 状态 | 契约 |
| --- | --- | --- |
| `PUT /api/v1/agents/{mpaInstanceId}/profile` | 新增 | 始终要求 `Idempotency-Key`；首次只用 `If-None-Match: *`，后续只用 `If-Match: "<runtimeRevision>"`，二者互斥；payload 携带 Studio Profile 的 `sourceProfileId` 和 `sourceProfileDigest`，不携带调用方分配的 revision |
| `GET /api/v1/agents/{mpaInstanceId}/profile-status` | 新增 | Profile 应用状态与可恢复 operation |
| `GET /api/v1/sessions/{sessionId}/execution-config` | 新增 | 权威会话执行配置版本与 ETag |
| `PATCH /api/v1/sessions/{sessionId}/execution-config` | 新增 | CAS 更新，影响下一 Turn |
| `POST /api/v1/sessions/{sessionId}/profile-upgrade` | 新增 | 显式 Session Profile 升级；目标 Profile 必须已应用 |
| `POST /api/v1/sessions/{sessionId}/run` | 扩展 | 增加 `executionConfigVersion` 与强幂等 |
| A2A submission | 扩展 | `urn:veadk:mpa:execution:v1` extension 使用同一 Turn 接受服务 |
| `GET/POST /api/v1/a2a/tasks/{taskId}/control...` | 扩展 | 保留 URL，增加参与方聚合与 request-hash 幂等 |
| `POST /api/v1/a2a/tasks/{taskId}/continue` | 新增 | runtime-owned 关联续跑 |
| `GET /api/v1/runtime-operations/{operationId}` | 新增 | 按 principal/target 授权查询 Profile/run/upgrade/continue 的异步状态和可安全重放结果 |
| Session CRUD/SSE/events/MCP/health/readiness/console | 复用 | 补 scope、cursor 与关联字段 |

新接口错误体为 `error.code/message/requestId/retryable/currentState`。旧客户端按 capability 版本保持现有 envelope；旧 Runtime 保持可发现并显示 read-only/unsupported，AgentKit P0 不允许关闭鉴权或退回浏览器/ArkClaw 权威。

## CON-8：数据模型

| 模型 | 拟议调整 |
| --- | --- |
| `mpa_agents` | 增加 source Profile ID/digest、apply status/operation/error、`agent_api_key_ref`、`model_api_key_ref`、`secret_migration_status`、`secret_migration_operation_id`；现有 Runtime 分配的 revision 是唯一 `profileRevision` |
| `mpa_meta` | 增加 AgentKit mode、workspace、bootstrap revision、readiness phase、finalization operation、last error |
| `session_meta` | 增加 account/workspace/MPA instance/Profile/execution-config revision |
| `session_execution_configs` | 新 append-only 表；保存 `(app_name, session_id, revision)`、强 ETag、MPA instance、Profile revision、Profile 默认 revision、overrides/effective/invalid references、updater 和 timestamps |
| `turn_execution_records` | 新表；保存 accepted config、resolved refs、model/policy/secret refs、dispatch key/hash/status、`continuation_of` |
| `a2a_turn_participants` | 新表；保存每个 generation 的参与方、lease、安全点、checkpoint、ACK/终态时间 |
| `a2a_task_controls` | 增加 command request hash 和 result reference；只有真实 P0 审批流需要时才增加 approval 字段 |
| `runtime_operations` | 新表；保存 Profile 生命周期和后续长耗时控制操作的唯一 principal/operation/target/key、request hash、状态、response snapshot、resource IDs、expiry；run acceptance 使用 `turn_execution_records`，execution-config PATCH 使用 revision/ETag，pause/resume 使用 `a2a_task_controls`，不重复写 ledger |
| trace/lifecycle | 按需增加可索引的 task/config/runtime/worker 引用 |

不新增 Agent definition/version、template/expert、review/install、独立 continuation、通用 policy evaluation 表。已实现的 S5-01 子集向 `mpa_agents` 增加 `agent_api_key_ref`、`model_api_key_ref`、`secret_migration_status`、`secret_migration_operation_id`。AgentKit mode 禁止向现有 `agent_api_key`、`model_api_key` 明文字段写入新值。已有新平台值按 reference-first 方式迁移：先用稳定幂等键创建外部 Secret reference，再在一个数据库事务内清空明文；provider 或数据库更新失败时保留明文，保证可重试；成功后同一 MPA Agent 的行只保留引用。Runtime 执行在 Secret 使用边界解析 `agentApiKeyRef`/`modelApiKeyRef`，resolver 缺失时 fail closed，不降级使用其他凭据。S5-01a 增加进程内 value-aware redaction，用于迁移时读到的 legacy 明文值以及未来显式注册的 Secret 字面值。已注册字面值会在嵌套值和自由文本进入 API/log/Runtime Console/trace 暴露前被遮盖，而非 Secret 引用与业务参数保持可见。Runtime operation response/resource snapshot 使用同一脱敏边界，状态接口不返回 principal、幂等键或 request hash。旧 mode 在一个兼容版本内只读明文字段，下一主版本删除明文读路径。所有结构变更使用显式顺序 migration，SQL 与 in-memory store 同步；不扩展 AgentKit 自有表，不迁移 ArkClaw 数据。

migration 顺序为 `runtime_operations -> mpa_agents/mpa_meta/session_meta 增量列 -> session_execution_configs -> turn_execution_records -> a2a_turn_participants -> 索引/约束`，每步记录 schema version。先扩 schema，再上线双版本可读代码，最后启用新写路径；旧镜像无法安全读取时拒绝回滚。

## CON-9：性能与保留

- Profile apply、run、pause/resume/continue 接受：p95 ≤ 500 ms；异步完成通过 operation/status 查询。
- execution-config GET/PATCH：p95 ≤ 300 ms；远程资源查询不持有数据库锁。
- warm Runtime SSE 首事件：p95 ≤ 2 s，不含模型首 token SLA。
- list/detail：p95 ≤ 1 s，默认 20、最大 100，禁止 N+1 平台扫描。
- 幂等结果至少 24 小时；终态执行证据默认 30 天；活动 Session 和被引用配置版本不自动清理。具体生产保留策略在部署配置中显式设置。

## 验证

实现采用 TDD：先增加 Profile mapping/version/idempotency、execution-config CAS、run crash-recovery、multi-participant barrier、continuation、SSE replay、scope/redaction 测试，再实现。并新增真实 PostgreSQL 两连接/重启 lane，覆盖 CAS、唯一活动 Turn、outbox、migration 和双版本读取；内存 store 不能作为这些验收的最终证据。Runtime 起点为：

```bash
uv run --group dev pytest \
  tests/test_session_auth.py \
  tests/test_subagent_binding_store.py \
  tests/test_a2a_task_control.py \
  tests/test_turn_control_api.py \
  tests/test_codex_adapter.py
```

该命令是实现阶段要求，本次文档整改状态为 `not_run`。真实集成必须覆盖 MPA Profile 应用、双客户端 CAS、故障重试、多 worker pause/resume、300 秒边界、重连重放和撤权。

## 已确认产品决策

用户于 2026-09-15 确认：既有 Session 固定创建时的 MPA Profile revision，只有显式升级成功后才从下一 Turn 使用新 revision；活动 Turn 不切换。Studio 接受 MPA 创建后显示部署中，只有 Runtime、Profile 应用和 execution-ready smoke 全部通过后才显示可运行。两项均为 P0 验收约束。

## 变更记录

2026-09-15：删除 Managed Agent 及重复模板/专家/版本产品；明确 Studio 创作权威、Runtime Profile revision 权威，以及执行配置、API、幂等、状态机、最小数据模型和验证要求。

2026-09-15：在 `agentkit-mpa-agent` 落地 execution-config 存储/API 基础：`session_execution_configs` schema version 4、append-only store、Session 维度 PostgreSQL advisory lock CAS、`GET/PATCH /api/v1/sessions/{sessionId}/execution-config`，以及 P0 的 `model`/`mcpServers` patch 子集。

2026-09-15：新增不可变 `SessionExecutionConfigSnapshot` 作为后续 Turn acceptance 的交接值对象。

2026-09-15：实现显式 Session Profile 升级 API/service 子集，支持升级到更高且已应用的 MPA Profile revision，并覆盖 ETag/CAS、禁止降级、目标不可用拒绝、保留 override 和当前进程内幂等 replay。

2026-09-15：已用 `uv run pytest -q tests/test_session_execution_config.py tests/test_session_execution_config_service.py tests/test_agentkit_session_auth.py tests/test_agent_config_service_unit.py tests/test_agent_config_store.py tests/test_profile_apply.py tests/test_profile_apply_api.py tests/test_sessions.py::test_create_get_include_mpa_profile_pointers_when_supplied tests/test_session_mcp_update.py`（46 passed）、focused Ruff、`make test-postgres`（5 passed）以及本次文档更新前的 `git diff --check` 验证已实现的 S2 Runtime 子集。

2026-09-16：实现 `turn_execution_records` schema version 5、SQL/in-memory acceptance store、REST `/run` 的 MPA 幂等与 config-version 强校验、A2A execution metadata acceptance、dispatch status 推进，以及 Studio/BFF run metadata 转发。验证覆盖 Runtime S3 定向回归（64 passed）、Runtime Ruff、Runtime `make test-postgres`（6 passed）、VeADK MPA server/integration pytest（47 passed）、BFF bridge pytest（3 passed）、前端 source-contract 子集（14 passed）、完整前端测试（1212 passed）、i18n、build 和两仓 diff hygiene。

2026-09-16：实现 S3-03 中 accepted-turn recovery 子集。`turn_execution_records` 现在持久化 `dispatch_payload`；`SessionService.initialize()` 从 active 或 retryable Turn 记录重建缺失/error inbox 并调度既有 worker；已终态 inbox 会同步回 Turn status；running inbox lease 过期时会把关联 Turn 标为 `failed_retryable`。验证覆盖 Runtime S3 回归（72 passed）、Runtime Ruff、Runtime `make test-postgres`（6 passed）和 diff hygiene。

2026-09-16：实现 S3-04/S3-05/S3-06 刷新恢复。Runtime SSE 对未知非空 cursor 返回 `410 cursor_expired`；Studio 在浏览器刷新后恢复已持久化的 Runtime Agent 和 Session ID，拉取所选 Session，并向 MPA Runtime `/sse` 传入 `lastEventId`。真实浏览器 `BC-06` 使用 system Google Chrome via Playwright 通过；证据位于 `evidence/browser/mpa-s3-1789516481/BC-06/`。

2026-09-16：实现 S4-01 participant 状态基础。Runtime 新增 `a2a_turn_participants` schema version 6，并补齐 SQL/in-memory store，支持按 generation 注册参与方、owner-scoped lease heartbeat、带 generation 校验的 safe-point ACK、终态标记和按 generation 有序快照。

2026-09-16：实现 S4-02 participant pause-barrier 子集。Runtime pause 请求现在会复制当前活跃 participant 集合；A2A 主执行器与 Codex worker safe-point ACK 通过 `ParticipantBarrierService` 汇总；部分 ACK 保持 `pausing`；当前 generation 所有活跃 participant ACK 后 task 进入 `paused`；late paused-generation worker 会先收到 pause 再 resume；终态 worker 不再阻塞后续 pause；resume 会生成下一代 running participant。验证覆盖 Runtime S4-02 focused regression（27 passed）、focused Ruff 和 Runtime `make test-postgres`（7 passed）。

2026-09-16：实现 S4-03 lease-aware resume 边界。Runtime 现在只在 300 秒暂停窗口内、owner lease 仍有效且 participant 状态可恢复时执行 same-Turn resume；暂停超过 300 秒、owner lease 丢失、participant `lost|failed`，或 running participant lease 过期/缺失时返回 `new_turn_required`，并记录 resume key 以支持幂等 replay。仍 running 且 lease 有效的 participant 会以 `invalid_state` 阻止 resume，直到它 ACK 或过期。验证覆盖 S4-03 focused boundary tests（8 passed）、broader S4 control regression（104 passed）、focused Ruff 和 Runtime `make test-postgres`（7 passed）。

2026-09-16：实现 S4-04 Runtime-owned linked continuation API/outbox。Runtime 现在在 `new_turn_required` 后接受 `POST /api/v1/a2a/tasks/{taskId}/continue`，通过 `accept_continuation` 写入 linked `turn_execution_records` 行，复用冻结 snapshot 和 dispatch payload，终止旧 active dispatch 行，并调度现有 inbox worker。验证覆盖 S4-04 focused tests（4 passed）、broader S4 control/acceptance regression（125 passed）、focused Ruff 和 Runtime `make test-postgres`（8 passed）。

2026-09-16：实现 S4-06 RuntimePrincipal 撤权与副作用前复核子集。Runtime 现在提供共享授权 helper 和可注入 authorizer 接线；`/run`、resume、`/continue` 在接受副作用前复核当前授权。accepted Turn/inbox 记录携带非 secret principal 快照，用于后台执行和重启恢复。ADK before-tool callback、直接 sandbox dispatch、模型/workload TIP 解析、OpenViking API key 解析和 sandbox `begin_run` 都会在使用 secret 或外部工具副作用前复核。验证覆盖 S4-06 focused auth/secret/tool tests（46 passed）、broader S4 Runtime regression（206 passed）和 focused Ruff。真实 AgentKit 撤权查询仍是部署态 S5 release gate。

2026-09-16：关闭 S4-07 生命周期、PostgreSQL 与浏览器门禁。Runtime focused auth/secret/tool tests 返回 46 passed，`make test-postgres` 返回 8 passed 且 PostgreSQL 资源已清理。VeADK loopback `turn_lifecycle` 场景已覆盖 Session/task control status、pause/resume、`new_turn_required`、显式 `/continue`、continuation SSE、调用计数和持久状态证据。真实浏览器 `BC-09` 使用 system Google Chrome via Playwright 通过；证据位于 `evidence/browser/mpa-s4-1789532050/BC-09/`。

2026-09-16：实现 S5-01 Secret reference migration 基础。Runtime schema version 7 向 `mpa_agents` 增加 Secret reference 与迁移状态列。`AgentConfigService` 在 AgentKit mode 下拒绝新的明文 `agentApiKey`/`modelApiKey` 写入，但允许写入 reference 字段。`SecretReferenceMigrationService` 先创建受保护引用，再清空明文；provider 或数据库更新失败时保留明文，使用同一幂等键可重试。Runtime 模型和内置 MCP 执行路径在 Secret 使用边界解析 reference；resolver 缺失时 fail closed，不回退到其他凭据。

2026-09-16：实现 S5-01a canary-safe redaction 子集。Secret reference migration 在创建外部引用前，会把 legacy 明文值注册为 value-aware redaction 字面值。API access log、Session 可见文本/events、Runtime Console 响应、lifecycle details 和 trace-step 持久化会在非敏感 key 下也遮盖已注册 canary 字面值，同时保留 `flow_id` 与 `user_code`。验证覆盖 S5 redaction focused pytest（89 passed）、broader S5 Runtime regression（178 passed）、focused Ruff 和 `make test-postgres`（9 passed）。

2026-09-16：实现 S5-04 Runtime Console/Trace correlation 子集。Invocation trace 响应和单个 trace step 现在暴露稳定的 `correlation` 字段，用于 MPA instance、Profile/config revision、Turn/task/runtime identity 和 worker linkage。验证覆盖 Runtime Console/Trace pytest（72 passed）和 focused Ruff。

2026-09-16：S5-06 compatibility preflight 是 Studio/VeADK 写路径门禁，不改变 `agentkit-mpa-agent` Runtime API 或数据库 schema。Runtime 契约仍是上文已实现的 Profile、Session execution-config、Turn acceptance、lifecycle、Secret reference 与 diagnostics；最终发布证据仍依赖 VC-19 中固定跨仓 manifest 的执行结果。

2026-09-16：S5-07 删除预览与分阶段清理同样是 Studio/VeADK 编排切片，不需要新增 `agentkit-mpa-agent` 表或 endpoint。Studio 复用 Runtime `GET /api/v1/agents/{mpaInstanceId}/profile-status`、`GET /api/v1/sessions?include_a2a=true` 和 `DELETE /api/v1/sessions/{sessionId}`，再调用 AgentKit Runtime delete API。Studio 将 `queued|running|pausing|paused|resuming` Session 视为 active blocker，并把单个 Session 删除时的 `404` 视为已清理以支持安全重试。当前契约只能证明已授权目标 Runtime API 可见的 session；若未来要保证跨用户全局 active-session 状态，需要另行新增 Runtime/global admin API，本次 S5-07 不声明该能力。

2026-09-17：实现 S5-08 MPA Session 创建初始化修复。Runtime 现在会在 `POST /api/v1/sessions` 收到 Studio 传入的 `mpaInstanceId + profileRevision` 且未显式传入 `executionConfigRevision` 时，创建第一条 `session_execution_configs` revision，并在创建响应中返回 `executionConfigRevision=1`。恢复或迁移调用方显式传入的 revision 仍会原样保留。验证覆盖 Runtime focused tests（186 passed）、focused Ruff，以及已发布到 Runtime `r-yeuujrrcowb21078p9jh` version 58 的镜像 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/mpa_agent:mpa-p0-sessioncfg-init-local-20260917`。真实 BFF/runtime 检查显示 native Session create 返回 revision 1，`/run` 可接受 `executionConfigVersion=1`，`/sse` 输出最终文本并发送 `event: done`。

2026-09-17：实现 schema version 8，完成持久 Runtime operation/Profile CAS 合约。SQL 与 in-memory operation store 现在执行一致的 24 小时 identity/replay 策略、保存已脱敏安全结果，并以 compare-and-swap 推进状态。Profile apply 使用认证 principal 与完整规范化 payload hash，映射全部 P0 Profile 资源类别，并在同一个 PostgreSQL 事务中完成 ETag 校验与 current revision 切换。真实双连接合约证明同一 ETag 只能被一个并发 writer 消费。

2026-09-18：在 Runtime commit `eecc6e3` 中完成旧 ADK endpoint 与 AgentKit key-auth 的鉴权对齐。AgentKit mode 下，`require_auth` 现在从 `Authorization` 建立 Runtime principal；非 AgentKit mode 保留既有 `X-Jwt-Token` 行为。定向测试 49 passed，完整 `make test` 2506 passed、14 skipped，focused Ruff 与 diff hygiene 均通过。产出镜像 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/mpa_agent:mpa-p0-adk-auth-eecc6e3-20260917`（`sha256:6ac6a2712ecd1c7950125dc9afc6467373a08142fbd6c3577aba12f126079bef`）已发布为 Runtime `r-yeuujrrcowb21078p9jh` version 62，状态为 `Ready`；Runtime 直连和 Studio BFF 的 `/list-apps` 调用均返回 `200 ["default"]`。本次没有改变 Runtime schema 或持久数据模型。

2026-09-18：在 Runtime version 62 上完成真实 Studio 验收，新建 Session `bee3db38-edcc-4020-b925-3d9d6a3a7adc` 并在沙箱执行 `printf 'MPA_V62_BROWSER_OK\n'`。父级沙箱活动和子命令活动均进入 `completed`；最终回答在完成时和 30 秒后持续可见，整页刷新后恢复回答和终态工具卡，页面没有 spinner 或运行中文案。证据位于 `evidence/browser/mpa-v62-live/`。该结果只验证本次对话展示路径，不关闭 S5-12 的完整 `BC-01`–`BC-09` 门禁。
