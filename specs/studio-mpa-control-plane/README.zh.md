# Studio MPA 控制面

- Component ID：`studio-mpa-control-plane`
- 状态：剩余 P0 修订为 `draft`；基线第一期、第二期部分能力以及 P0 S1/S2 Studio 切片至 S2-08、S4-05/S4-07、S5-02 BFF view model、S5-03 前端消费、S5-05 diagnostics 消费、S5-06 compatibility preflight、S5-07 删除预览/分阶段清理和 S5-08 Profile 管理入口已实现
- 修订日期：2026-09-17
- English：[README.md](README.md)
- PRD：[MPA Studio Turn 控制与资源工作台](../../prd-spec/features/mpa-studio-control-plane/2026-09-13-mpa-studio-control-plane-design.zh.md)

## 职责

负责 Studio 到 mpa-agent 的方舟模型发现、不可变 Turn 快照、完整 Turn 生命周期命令/状态、Session 资源挂载、typed runtime 拓扑、Studio 工具发现和角色保护 Secret 复制契约。mpa-agent 是生命周期权威；Studio 是客户端和展示层。

## 契约

- `CON-1`：账号模型仅服务端发现，浏览器 Payload 无凭据，经过兼容过滤，带新鲜度缓存并明确失败。
- `CON-2`：接受 Turn 时冻结模型和已提交资源 Payload；非终态 Turn 不观察后续浏览器侧 Session 编辑。服务端 Session 资源 revision 尚未实现。
- `CON-3`：生命周期持久化且受 generation 控制；Studio 只暴露幂等 pause/resume；只有主执行器及所有活动 worker 到达安全点才可 `paused`。
- `CON-4`：暂停、继续与发送共用 Composer 主按钮。五分钟内继续同一 Turn；超时或不可恢复时，只有用户点击继续才在同一 Session 创建增量 Turn。断连与超时本身不会启动工作。
- `CON-5`：Studio 当前在浏览器 localStorage 中保存 Session 挂载选择，并随下一 Turn 提交稳定的 Skill Space ID 和版本。服务端 revision、冲突检测及失效资源保留仍为后续工作。
- `CON-6`：拓扑只包含配置/观测节点和 typed edge；缺失可选资源是入口而非活动节点。
- `CON-7`：Agent Card capability 控制模型、生命周期、挂载和拓扑的向后兼容。
- `CON-8`：环境列表响应绝不包含 Secret；授权复制 no-store、审计不含值，Studio 不渲染或持久化。
- `CON-9`：Composer 以一排 Footer 承载附件、Agent 目标、模型、用量/状态和一个状态化主按钮。主按钮根据权威 Turn 状态表示发送、暂停、等待或继续；响应式布局不得重叠。
- `CON-10`：当前 Turn 和 Session 累计均提供输入/输出/推理/缓存/总量；重放使用单调正增量。
- `CON-11`：会话投影将 `reasoning` 与 Agent `thought` 保持为不同语义类型。优先使用稳定事件身份；跨通道文本去重仅限同一 task/invocation 和类型内的完全或累计前缀传输重放。
- `CON-11a`：持久会话历史重放必须为每个由用户消息分隔的 assistant 分段分配在整个 Session transcript 内唯一的身份。只有当 projector 本地序号的前缀包含单调递增的历史分段索引时才可复用该序号；后续轮次不得通过 upsert 覆盖更早的 assistant turn。流式执行完成后，只有当持久历史包含触发本次对账的精确最终 assistant event，且没有更新的本地 assistant turn 已开始时，Studio 才可用持久历史替换实时 transcript。浏览器验收必须在延迟持久化刷新前后及整页重载后，按顺序统计并检查 `.turn--assistant` 节点；仅在整个页面中找到预期文本不构成通过，因为同一文本也可能出现在用户提问或 reasoning 中。
- `CON-11b`：MPA `sandbox_task` 活动在实时流和持久历史重放中都必须进入 UI 终态。Runtime 持久历史可能包含 sandbox `invocation.completed` 事件，随后再有 `status=completed`、`finalAlreadyEmitted=true` 的 wrapper `functionResponse`；而实时订阅可能在回答增量之后只暴露 wrapper response。Studio 将该 wrapper 作为控制终态：如果同一 invocation 仍有 active projected turn，则把既有父级 `sandbox_task` block 标记为 completed，保留已推流的回答和工具 block，以 wrapper event 作为 Turn 完成栅栏并关闭 streaming；如果持久化 `invocation.completed` 已关闭该 Turn，则忽略同一 wrapper，且不得生成重复工具卡。
- `CON-12`：工具活动展示工具特定的安全动作和对象；未知工具展示具体名称，不使用通用完成标签。
- `CON-13`：已脱敏工具输入/结果可通过显式复制/下载完整获取；预览渲染有界、截断有提示，所有详情路径共享同一脱敏规则。
- `CON-14`：Turn 模型选择支持搜索和键盘访问，并在非终态 Turn 拥有不可变模型快照期间保持禁用。
- `CON-15`：Runtime 列表暴露 `agentCategory`，并接受 `agentCategory=general|mpa` 在可见分页前执行服务端分类过滤。MPA 的权威且唯一来源是 Runtime 标签 `veadk:agent-type=mpa`；镜像名和 artifact URL 不参与分类。`agentCategory=mpa` 必须先通过 Volcano Tag 服务正向标签过滤获得候选 Runtime ID，再按 Runtime ID 补齐详情，避免 MPA 结果稀疏时扫描无关 Runtime 页。

## 状态与数据

- Studio 可见 Turn 状态：`queued`、`running`、`pausing`、`paused`、`resuming`、`interrupted`、`completed`、`failed`。内部可保留终态化状态，但不作为用户操作。
- Turn 控制保存 generation、幂等、期望/观测状态、参与方确认、安全点、快照 revision 和分类失败。
- Session 资源当前把浏览器本地增量与 Agent 默认值分开；提交的 Turn Payload 保存解析后的 Skill ID/版本，并在该 Turn 内保持不可变。
- 当前拓扑合并 Runtime 配置的 Agent/Sandbox 节点和浏览器所选 Session 资源。动态 worker 生命周期节点与服务端会话执行配置版本仍为后续工作。

## 失败与安全

非法模型/资源在副作用前失败。控制过渡失败绝不显示为已暂停。冲突返回权威 generation/state。Secret 排除在普通 API、DOM、状态、存储、日志、遥测、截图和错误详情之外。剪贴板复制是有意授权披露，必须审计。

## 兼容性

旧 Agent 保留单一默认模型和既有非 MPA 停止行为，隐藏不支持的暂停/恢复控制，只展示已验证数据。原生 ArkClaw 和非 MPA Studio 契约不变。

## 验证

契约测试覆盖状态转换、幂等、竞态、模型快照、已提交挂载、拓扑、鉴权、脱敏和 Runtime 分类过滤。浏览器测试覆盖响应式布局、唯一动态主按钮、模型筛选、MPA 分类选择、Skill Space 发现和终态控制清理。真实 Runtime 测试已证明模型目录、不可变请求模型、生命周期状态/控制路径、配置态 Agent 到 Sandbox 拓扑及真实 Skill Space 发现。主 Agent/worker Skill 传递由目标契约测试覆盖。完整的真实 worker pause/resume、五分钟增量续跑、刷新恢复及失效资源执行门禁仍需后续验证。
会话投影测试还覆盖 status/artifact 重放、合法重复措辞、reasoning/thought 语义区分、嵌套工具 payload、大型脱敏值、已知/未知工具标签，以及可搜索模型的键盘行为。

## MPA 信息侧栏（2026-09-18 已实现）

- CON-16：会话侧栏仅向服务端识别的 MPA Runtime 展示。AGENTS.md 来自当前 Runtime 已认证 `/api/v1/studio/agent-info` 的 `agentsMd`，明确区分空、不支持、无权限和失败状态，不使用通用 instruction 替代。
- CON-17：绑定技能来自 Agent Card 中已配置的技能空间节点及 Runtime 地域内已授权的分页 SkillSpace API。取消 Session 临时技能挂载，已保存的临时技能选择不再发送给 MPA。刷新和取消不能混淆 Runtime 身份，不能将列表失败视为空成功。

设计：[MPA 信息侧栏](../../prd-spec/features/mpa-agent-info-rail/2026-09-18-mpa-agent-info-rail.zh.md)。

Runtime 代理为带有 `veadk:agent-type=mpa` 标签的 Runtime 处理 `GET /web/agent-info/{app}`，支持原生 app ID 和 `a2a-default`。新增的 `AgentInfo.agentCategory` 为 `mpa`；通用合成 A2A 响应为 `general`。其他既有响应可以不包含该字段，此时隐藏侧栏。

`AgentInfo.mpa` 包含 `agentsMd: string | null`、`agentsMdStatus`、`skillSpacesStatus` 和 `skillSpaces: {id: string, region: string}[]`。状态值为 `ready`、`unsupported`、`forbidden`、`error`。正文读取的网络超时为 10 秒，连接超时为 4 秒；401/403 为无权限，404/405/501 为不支持。Studio 使用服务端解析的 Runtime key，通过专用 `X-MPA-Studio-Key` 调用新只读元信息接口。404/405 时可尝试旧 `/api/v1/agents` JWT 接口，但不转发专用头；此时认证失败表示 Runtime 需要升级。不得将 API key 当作 JWT。非法响应和传输失败为错误。上游详情仅允许透传正文、name、description、model 字符串。空间发现与正文读取失败相互独立。

空间 ID 来自 `urn:veadk:mpa:resource-topology:v1` 中通过 `mounts` 边与 `agent` 节点连接且已配置的 `skill-space` 节点。缺失拓扑表示不支持，不能视为空绑定成功。空间列表复用已授权的 `/web/skill-spaces/{id}/skills` 路由，每页请求 100 项；无进展或超过 100 页时标记为不完整错误。各请求保留现有 30 秒客户端超时并支持取消。仅完整列表显示数量；降级结果和部分失败保留可读内容并提示，无权限则清除已有技能。不修改 Runtime 凭据、绑定或部署。绑定技能名称可打开按权限控制的[技能正文编辑器](../studio-skill-document/README.zh.md)。

## 托管创建边界

Studio MPA 创建和 `veadk mpa provision` 由 [Studio MPA 创建](../studio-mpa-creation/README.zh.md)负责。该路径准备账号资源并通过真实 Runtime 元数据初始化。本文原有职责和旧入口保持不变。

会话投影测试还覆盖 status/artifact 重放、合法重复措辞、reasoning/thought 语义区分、嵌套工具 payload、大型脱敏值、已知/未知工具标签、可搜索模型的键盘行为、连续持久 assistant 轮次的唯一身份，以及以最终事件为栅栏的实时/持久 transcript 对账。

## 拟议 AgentKit P0 修订

由 [P0 功能迁移 PRD](../../prd-spec/features/mpa-p0-productionization/2026-09-15-mpa-p0-productionization-design.zh.md) 管理。上文描述基线行为/要求与历史验证，不证明以下变更已完成。拟议 runtime 协议归 [MPA Runtime 控制](../mpa-runtime-control/README.zh.md)，Studio 消费该协议，不另建状态权威。以下修订仅在新 AgentKit 模式实现后替代基线浏览器本地资源权威。

- `CON-16`: 本期复用 Studio 现有创建表单和 AgentKit 平台资源，补齐 MPA Runtime 部署、Profile 应用、会话执行配置、会话结果与 Debug；不使用 Managed Agent CRUD/version/Session，不为 MPA 新建模板/专家/审核安装产品。定时任务、飞书、网站集成、资源库、搜索延后；不导入历史 ArkClaw 数据。
- `CON-17`：管理后端从已验证的 Studio OAuth/gateway bearer 派生身份，并只向 custom-JWT Runtime 转发该已验证 token；不自行签发新 token。CLI 认证到同一 BFF。不信任浏览器 owner/account Header，不向 UI 暴露 runtime 凭据，不用云 service role 代替用户身份。启用前通过 M0 证明 issuer/audience/client、JWKS 轮换、claim 映射与撤权。
- `CON-18`：以 runtime `CON-3` 的“会话执行配置版本”替代浏览器本地 MPA 执行配置权威。未保存编辑只能作为明确 draft，GET 刷新权威状态。PATCH 使用强 ETag，处理 `428`、`412`，展示当前状态并显式 retry/reapply，不静默覆盖其他客户端。Turn 创建使用已接受 execution-config revision。资源正文仍归 AgentKit/Studio，Runtime 只保存稳定引用与 Turn 执行记录。
- `CON-19`：UI 按 runtime `CON-4` 展示 allowed action 和参与方 observed state。部分暂停/deadline 失败不是 paused。`new_turn_required` 仅由用户显式继续调用 runtime 幂等 continuation API，不自行提交 fallback prompt。断连和轮询超时不启动执行。
- `CON-20`：Studio 将已接受 Agent draft 校验并规范化为权威 MPA Profile revision；Runtime 持久化不可变执行 revision。同 revision 同摘要幂等，低 revision 或同 revision 不同摘要冲突。既有 Session 固定创建时的 Profile revision，显式升级成功后从下一 Turn 生效。创建后显示部署中；Runtime、Profile 和 execution-ready smoke 全部通过前不得显示可运行。
- `CON-20a`：浏览器只调用 VeADK BFF 的 `/web/mpa/agents`。BFF 校验现有 Studio Agent draft 并调用类型化 mpa-agent Profile API。本期不调用 Managed Agent CRUD/version API，也不使用服务端 arkcli 子进程。create/update operation 使用 Studio TOS 的 `forbid_overwrite` + ETag 持久化；两个写入口均要求客户端先持久化 `Idempotency-Key` 并返回 `202 + operationId`。相同 principal/operation/target/key/hash 返回同一 operation；刷新通过 operation ID 或 `GET /web/mpa/agent-operations?status=active` 恢复，retry 从最后安全阶段继续。
- `CON-20b`：本地 Studio 开发态可在 `veadk studio --dev` 且未配置 Studio TOS 时使用进程内 MPA operation repository。它必须保持 UI 所需的 operation ID、request-hash 幂等和 ETag compare-and-swap 语义，但不具备持久化能力，也不能作为发布证据。非 dev 部署缺少 Studio TOS 时，Profile 写路由继续返回 `mpa_operation_service_unavailable`。
- `CON-21`: 本期交互/Debug 执行委托 runtime service，保证授权与隔离。渠道/job 管理及资源库全局产物/adapter 延后，保留既有行为。
- `CON-22`：BFF/CLI 共用 `MpaControlPlaneClient` 的 schema/auth/error/capability 协商，CLI 不导入 server route。区分 normal/loading/empty/error/denied/stale/retry；继续遵循模型锁定、IME/键盘和窄屏规则。Runtime capability 不支持时明确 read-only/unsupported，不做不安全 fallback。

仍要求新平台数据/版本兼容，仅排除历史 ArkClaw 迁移。`CON-16` 至 `CON-22` 映射 PRD `AC-1`、`AC-2`、`AC-4`、`AC-5`、`AC-7`、`AC-8`、`AC-10`，覆盖 unit/BFF、真实浏览器和隔离云 E2E。状态：S1 创建/进度、S2 execution-config BFF/UI、S3 run/cursor 刷新恢复、S4-05 Studio continuation 接线、S4-06 Runtime 授权/副作用前复核，以及 S4-07 浏览器生命周期门禁已实现并完成本地验证；S2 浏览器并发已通过 loopback scenario fixture 的 BC-04/05，S3 刷新恢复已通过 BC-06，S4 pause/resume/continue 已通过 BC-09。真实云和完整 Debug/Trace 收口仍待完成。前后端与构建门禁仍遵循 [frontend/SPEC.md](../../frontend/SPEC.md)。

2026-09-15：新增 P0 功能迁移草案。

2026-09-15：已实现 Studio S2 BFF/client/UI 子集：类型化 `/web/mpa/sessions/{sessionId}/execution-config` GET/PATCH、类型化 `/web/mpa/sessions/{sessionId}/profile-upgrade`、profile-status 查询、ETag/`Idempotency-Key` 转发、`412 currentState` 透传、MPA Runtime 分类透传、MPA tab 创建入口，以及只在当前 Runtime 与当前业务 Session 下可用的 MPA-only Session configuration 面板。

## 页面入口与 adapter 契约

PRD 第 6 节记录实际 `frontend/src/App.tsx` 与 `frontend/src/ui/MyAgents.tsx` 入口审计。当前事实：MPA 列表与创建入口已按 P0 路径接线；S4-05 已把原先的 prompt-based Session continuation fallback 替换为 Runtime-owned `/continue` + `/sse` 流程。网站与飞书仅是后续范围证据。

- `CON-23`：导航、选择器、创建、草稿、详情、历史保留 category/Runtime/region/agent/业务 Session/认证 scope。缓存用完整 scope key，身份/目标切换时失效。Runtime tag 决定分类，capability 协商决定可用操作；全局 feature flag 和隐藏按钮不能授权请求。MPA tab 与空态必须可创建，并显式走 MPA provision。
- `CON-23a`：MPA 创建 intent 是 `{category: "mpa", region, source}`，由 Tab/Header/空态共用；不得从全局 state 猜测 category。MPA 详情使用独立 view-model，复用页面外壳/loading/error 组件，但不复用 GitHub delivery versions、通用 Runtime draft/update、评测或优化业务逻辑。
- `CON-24`：现有 `StudioWorkspace.environmentIds` 表示环境集合，其 ID 不等于授权 `workspaceId` 或 worker mount 身份。服务端解析并授权此关系，不直接替换 ID 或由 UI 派生租户。Resource/default/Session 编辑走 runtime revision 契约，不修改活动 Turn。
- `CON-25`：`GET /web/mpa/agents/{mpaInstanceId}/view` 返回 `MpaAgentView`，合并 scope、MPA instance/current Profile revision、唯一 Runtime binding/version/readiness、活动 operation/stage、capabilities 和 safe error。0 个 Runtime 为 `runtime_missing`；多个为 `binding_ambiguous` 并禁止写。`orphan_runtime` 表示存在一个已授权 Runtime 但尚未应用 Profile：`capabilities.canWrite` 保持为 true，使 Studio 可以执行首次 Profile apply；`canDebug` 保持为 false，Session 配置在 binding 变为 `bound` 前继续阻塞。MPA 编辑使用 Studio Profile，Runtime 保存其不可变 revision；Debug 使用隔离 Runtime Session。不复用通用 Python 工程、个人 Sandbox、评测或优化业务逻辑；GitHub delivery 只有经过显式 MPA compatibility preflight 才可复用。S5-02/S5-03/S5-05/S5-08 切片已实现：BFF 探测已配置 Runtime regions，只接受当前用户可见且带 `veadk:agent-type=mpa` 的 binding，返回 0/1/N binding 状态，并在唯一 binding 时通过 Runtime `profile-status` 补齐 Profile 状态；前端消费该 view 并展示 Runtime Console diagnostics。
- `CON-25a`：AgentKit Studio 是 MPA 的统一管控入口。MPA 详情页提供 Agent 级 `Profile 配置` 分区，展示当前 apply 状态、revision/ETag、模型、系统提示词，以及 Tool/Skill/MCP 摘要。该分区通过类型化 MPA BFF operation 路径应用当前 Studio Profile；MPA Agent 不再探测依赖 `/list-apps` 的通用 Runtime update capability。首次 apply 使用 create 语义和 `If-None-Match: *`；后续 apply 使用 Runtime revision/ETag。浏览器幂等键由 Runtime ID、operation kind 与规范化 Profile 的 SHA-256 确定，因此相同 Profile 重试会重放同一 operation，内容变化会得到新的 key。
- `CON-29`：MPA Runtime 写路径必须在任何 AgentKit SDK 或 GitHub mutation 前执行共享 P0 compatibility preflight。覆盖 `/web/deploy-agentkit` 直连 Runtime update、`/web/github-delivery/cicd-pipeline` GitHub Actions delivery setup、`/web/github-delivery/init-main` 首次 delivery 分支初始化、`/web/github-cicd/runtime-sync` 已绑定源码同步，以及 `/web/github-delivery/rollback-pr` rollback PR 创建。浏览器用 `agentCategory=mpa` 标记 MPA 流程；显式 `mpaCompatibilityManifest` 或兼容旧字段 `compatibilityManifest` 可覆盖本地生成的协议形态。失败返回安全的 `409` detail，包含 `code=mpa_compatibility_preflight_failed`、`status` 和 `errorCode`；不得回显 manifest 正文或 secret-like 字段。没有 pinned manifest 的本地 UI 路径只做协议形态校验，不作为发布证据；最终 release gate 必须用真实固定的 revision 和 image digest 执行 VC-19。
- `CON-30`：MPA 删除采用“先预览、再执行”的契约。`GET /web/mpa/agents/{mpaInstanceId}/delete-preview` 解析已授权 Runtime binding，读取 Runtime `profile-status`，调用现有 Runtime `GET /api/v1/sessions?include_a2a=true`，返回 `canDelete`、`blockers`、可见会话计数、活动会话摘要和清理计划。`/web/delete-runtime` 在 MPA 清理前重新检查服务端 Runtime 标签；浏览器传入的 `agentCategory` 只是提示，不能让普通 Runtime 进入 MPA 清理。存在 active lifecycle operation 或状态为 `queued|running|pausing|paused|resuming` 的 active session 时，在副作用前返回结构化 `409`。没有阻断时，Studio 先通过现有 Runtime `DELETE /api/v1/sessions/{sessionId}` 删除可见 idle/terminal Runtime 会话，再删除 AgentKit Runtime。单个 session `404` 表示已清理，会被忽略以支持安全重试。预览只统计已授权目标 Runtime API 可见的会话；若未来需要跨用户全局 session 状态，必须新增 Runtime/global admin endpoint 后再声明。
- `CON-26`: 仅后续：资源库、全局搜索、产物索引/来源 adapter。本期不开发、不验收。会话资源引用和会话结果仍在本期；MPA 模板/专家/审核不属于本方案。
- `CON-27`: 仅后续：定时任务、已有 MPA 飞书绑定、网站 visitor/A2A 集成。身份/调度/投递/API 由后续 spec 设计，本期不要求 adapter、CLI 等价功能或专项 live 门禁。
- `CON-28`：应用/开发者/全局管理页保留非 MPA 语义。限制不兼容 MPA target，不隐藏所有通用功能。MPA runtime admin 不等于平台用户管理 admin。Trace/log/usage/feedback、CLI 示例保持 runtime/worker/Session/Turn 关联与脱敏，不将不支持的 coding/GitHub 自动化改名成 MPA。

实现说明：`CON-23`、`CON-23a`/`CON-24` 的 S2 子集、S4-05 continuation client path、S4-06 Runtime authorization recheck path、S4-07 生命周期浏览器 fixture、S5-02/S5-03/S5-08 的 `CON-25`/`CON-25a` view-model 与 Profile 管理路径、`CON-20b` 的开发态本地 store、S5-05 diagnostics 消费路径、S5-06 `CON-29` compatibility preflight 和 S5-07 `CON-30` 删除预览/分阶段清理已实现，覆盖 MPA category 传递、MPA 创建入口、当前 Runtime/当前 Session 作用域、execution-config BFF/UI 调用、浏览器双客户端 CAS 处理、Runtime-owned continuation streaming、本地化检查点续跑状态展示、把 Runtime `403 runtime_action_forbidden` 作为控制面拒绝信号消费、由 BFF 返回 `runtime_missing|bound|binding_ambiguous|orphan_runtime` 的 MPA 详情状态、允许唯一可写 orphan Runtime 执行首次 Profile apply，同时继续阻止 Session 配置/诊断、在 MPA-only Diagnostics section 中展示 Runtime Console run/trace correlation、在 MPA update/release/rollback 副作用前拒绝不兼容请求，以及在 active operation 或 active session 存在时阻止 MPA Runtime 删除。

验证：以 P0 PRD `AC-1` 至 `AC-12` 为准，覆盖 Studio AgentDraft 规范化、MPA Profile revision 应用、会话配置 CAS、对话/worker、控制/续跑、历史、Debug/Trace、真实身份/Profile apply 和 PostgreSQL 并发。浏览器覆盖刷新恢复、双客户端 CAS、loading/empty/error/denied/stale/retry；IME/窄屏保留真实浏览器证据。资源库、搜索、定时任务、飞书、网站集成延后。S2 本地验证：BFF pytest 返回 28 passed，前端 source-contract 子集返回 95 passed，完整前端测试返回 1209 passed，i18n 检查通过，前端 build 通过，Runtime S2 focused tests 返回 46 passed，Runtime `make test-postgres` 返回 5 passed，两仓 `git diff --check` 通过。浏览器 BC-04/05 已使用 system Google Chrome via Playwright 访问 `http://127.0.0.1:18174` loopback fixture 验证通过，证据位于 `evidence/browser/mpa-s2-1789491400/`。`uv run --extra dev pyright ...` 本地为 `blocked`，因为当前环境没有 `pyright` 可执行文件或项目脚本。
S4-05 本地验证：覆盖 `runSSE`、`continueTurnSSE` 和 Composer lifecycle routing 的 frontend source-contract tests 返回 37 passed；`npm --prefix frontend run check:i18n` 通过；`npm --prefix frontend run build` 通过，生成的 `veadk/webui` 产物已清理。
S4-06 本地验证是 Runtime 侧：focused auth/secret/tool tests 返回 46 passed，broader S4 Runtime regression 返回 206 passed，Runtime focused Ruff 通过。Studio 本轮不新增产品界面；继续复用现有 Runtime error handling 处理被拒绝的 run/resume/continue。
S4-07 本地验证：loopback `turn_lifecycle` 场景覆盖 Session/task control status、pause/resume、`new_turn_required`、显式 Runtime `/continue`、continuation SSE、调用计数和状态证据。前端 source-contract 子集返回 37 passed；完整前端测试返回 1215 passed；i18n 和 build 通过。真实浏览器 `BC-09` 使用 system Google Chrome via Playwright 通过，证据位于 `evidence/browser/mpa-s4-1789532050/BC-09/`。
S5-02 BFF 验证：focused MPA BFF route 与主 app Runtime binding tests 返回 32 passed；focused Ruff 通过。本切片只实现后端 endpoint；前端详情页由 S5-03 承接。
S5-03 前端验证：focused `AgentWorkspace` source-contract tests 返回 33 passed，完整 frontend tests 返回 1216 passed，i18n 检查通过，frontend build 通过且生成的 `veadk/webui` 产物已清理。focused MPA BFF/main-app tests 仍为 32 passed。
S5-05 前端验证：focused `AgentWorkspace` source-contract tests 返回 34 passed，完整 frontend tests 返回 1216 passed，i18n 检查通过，frontend build 通过且生成的 `veadk/webui` 产物已清理。Diagnostics section 通过现有 Runtime proxy 消费 Runtime Console run/trace 数据。
S5-06 本地验证：`uv run --extra dev pytest -q tests/integrations/test_mpa_compatibility_manifest.py tests/cli/test_studio_rbac.py::test_mpa_update_rejects_incompatible_manifest_before_launch tests/cli/test_studio_rbac.py::test_mpa_update_allows_compatible_manifest_to_reach_launch tests/cli/test_github_cicd.py::test_mpa_github_delivery_cicd_rejects_incompatible_manifest_before_push tests/cli/test_github_cicd.py::test_mpa_github_delivery_init_rejects_incompatible_manifest_before_push tests/cli/test_github_cicd.py::test_mpa_github_delivery_attach_rejects_incompatible_manifest_before_push tests/cli/test_github_cicd.py::test_mpa_github_runtime_sync_rejects_incompatible_manifest_before_push tests/cli/test_github_cicd.py::test_mpa_github_delivery_rollback_rejects_incompatible_manifest_before_pr tests/cli/test_github_cicd.py::test_mpa_github_delivery_rollback_allows_compatible_manifest` 返回 12 passed；focused frontend source-contract tests 返回 41 passed；完整 frontend tests 返回 1217 passed；focused Ruff 与 `compileall` 通过；i18n 和 build 通过，只有既有 Vite chunk warning。
S5-07 本地验证：`uv run --extra dev pytest -q tests/frontend/server/mpa/test_runtime_profile_client.py tests/frontend/server/mpa/test_runtime_profile_routes.py tests/cli/test_studio_rbac.py::test_runtime_detail_proxy_and_delete_enforce_role_and_owner tests/cli/test_studio_rbac.py::test_mpa_runtime_delete_blocks_active_sessions_before_runtime_delete tests/cli/test_studio_rbac.py::test_mpa_runtime_delete_cleans_idle_sessions_then_runtime tests/cli/test_studio_rbac.py::test_delete_runtime_ignores_untrusted_mpa_category_for_general_runtime` 返回 29 passed；前端 source-contract focused tests 返回 33 passed；完整 frontend tests 返回 1217 passed；focused Ruff 与 `compileall` 通过；i18n 和 build 通过且只有既有 Vite chunk warning。build 生成的 `veadk/webui` 产物已清理。
CON-11a 回归验证：会话投影/对账 focused suite 返回 43 passed；完整前端测试返回 1236 passed；TypeScript、i18n、生产构建与 scoped diff 检查均通过。严格真实 Studio 探针在任务完成并额外等待 30 秒后观察到五个有序 `.turn--assistant` 节点，整页重载后仍为相同五个节点。既有可选本地 endpoint 404/503 已单独记录，不影响 transcript 持久展示。
CON-11b 回归验证：完整前端测试返回 1237 passed；TypeScript、i18n、生产构建与 scoped diff 检查均通过。新的真实 Studio `whoami` 执行观察到父级 `sandbox_task` 和子命令无需刷新即从 running 变为 completed，页面不再有 spinner 或 running activity，最终回答为 `root`；整页刷新后两条终态活动和回答均保持。
范围修正：上述入口审计中网站/飞书等后续项仅供未来参考，不是本期开发要求。
