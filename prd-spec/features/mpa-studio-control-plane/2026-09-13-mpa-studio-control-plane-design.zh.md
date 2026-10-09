# MPA Studio Turn 控制与资源工作台

- Change ID：`mpa-studio-control-plane`
- 状态：`approved`
- 创建 / 修订日期：2026-09-13
- English：[design.md](2026-09-13-mpa-studio-control-plane-design.md)
- 组件：[Studio Runtime Diagnostics](../../../specs/studio-runtime-diagnostics/README.zh.md)、[Studio MPA Control Plane](../../../specs/studio-mpa-control-plane/README.zh.md)

## 背景与证据

真实验证发现：Agent 与模型选择器重叠；部署时模型 allowlist 不完整；Token 分类没有分开展示；环境错误过于泛化；单 Agent 拓扑没有体现 Sandbox 和 Session 资源；Skill Space 与 Studio 工具难以发现；Studio 也缺少 mpa-codex-worker 已提供的完整 Turn 生命周期控制。mpa-agent 已支持请求级模型校验并具有 A2A 控制存储；VeADK 已具有账号模型目录、Skill Space 路由、Session 环境挂载、Studio 工具选择及结构化用量。本变更组合和扩展这些契约，而不是建立平行系统。

## 目标

- `FR-1`：服务端查询当前账号方舟模型，过滤兼容的对话模型，缓存成功结果，不向浏览器暴露云凭据。
- `FR-2`：发送时把模型、Skills、工具和环境冻结为不可变 Turn 快照；模型同时应用于主 Agent 和委托 worker，非终态期间不可切换。
- `FR-3`：Agent 目标、Turn 模型、用量、生命周期控制和发送拥有独立响应式布局槽位，禁止重叠。
- `FR-4`：按 Turn 和累计分别展示输入、输出、推理、缓存命中和总 Token，重放不得膨胀。
- `FR-5`：mpa-agent 是主模型、工具、Sandbox 委托和 worker 的唯一生命周期权威。
- `FR-6`：提供持久、幂等的 pause 和 resume，采用协作式安全点暂停并支持刷新恢复。本版本 Studio 不暴露 cancel 或 interrupt 操作。
- `FR-7`：持久化 Session 级 Skill Space Skill、Studio 工具和环境挂载；变更从下一 Turn 生效，不修改默认值。
- `FR-8`：返回并展示真实 Agent-Sandbox-worker-资源拓扑，提供可操作详情，不伪造活动节点。
- `FR-9`：展示 Studio 工具用途、场景、参数、权限、示例、来源/revision 和 Session 挂载状态。
- `FR-10`：区分环境失败；授权管理员/开发者可复制但不可渲染 Secret，普通用户只看已配置状态。
- `FR-11`：声明 capability，并让旧 Runtime 真实降级。
- `FR-12`：每个工具调用展示 human-readable 动作及其最有用的安全对象，不把不同工具都折叠成通用完成文案。
- `FR-13`：保留完整、可复制、已脱敏的工具输入/结果，同时限制初始渲染；截断必须明确，且不得静默导致唯一可用数据不完整。
- `FR-14`：区分模型 reasoning summary 与 Agent 工作 thought，仅抑制经证明来自 A2A status/artifact 通道的传输重放。
- `FR-15`：Turn 模型选择器支持按模型 ID 和展示文本搜索，同时保留键盘可访问性与非终态 Turn 锁定。

## 非目标

- 从聊天修改 Runtime/Agent 默认值或账号模型开通状态。
- 在前端硬编码季节性模型列表，或信任浏览器模型 ID。
- 抢占正在执行的 Provider 请求；暂停在下一个安全点完成。
- 恢复 cancelled/completed/failed Turn。
- 让 Studio 分别协调 mpa-agent 与 worker。
- 渲染或持久化 Secret，或让普通用户获取 Secret。
- 伪造 Sandbox、Skill、知识、工具或子 Agent 关系。

## 场景

1. 空闲时选择兼容模型，发送后模型冻结，直到 Turn 终态前选择器禁用。
2. Pause 进入 `pausing`，只允许当前不可抢占操作完成，不启动下一步；主执行器和所有 worker 到达安全点后才进入 `paused`。
3. 刷新后从 mpa-agent 恢复权威 paused/running 状态和允许操作。暂停、继续与发送共用 Composer 唯一主按钮，不渲染重复生命周期工具栏。
4. Turn 暂停后的五分钟内允许恢复原 Turn；超过五分钟，或 owner 已无法恢复时，只有用户再次点击继续，才把旧 Turn 终结为 interrupted，并在同一 Session 创建携带增量继续指令的新 Turn。超时本身不会自动执行。
5. 内部终态化可以停止无法恢复的旧 Turn，但本版本 Studio 不暴露 interrupt 或 cancel 操作。
5. Skill/工具/环境挂载持久化到 Session，进入下一 Turn 快照，不改变活动 Turn。
6. 环境错误明确指出鉴权、Runtime、版本、Manifest 或 Secret 权限边界。
7. 授权 Secret 复制通过 no-store 审计接口直接写剪贴板，不渲染；未授权返回 403。
8. 拓扑只展示真实 Agent、Sandbox、worker、Skill Space、Studio 工具、MCP、环境、知识和子 Agent 关系。
9. 工具活动说明具体动作与安全对象；完整脱敏数据可通过显式详情操作获取。
10. 同一 reasoning summary 同时经 A2A status 与 artifact 重放时只展示一次；不同的 Agent thought 独立标注。
11. 模型选择器接受输入过滤，且不能修改非终态 Turn 已冻结的模型。

## 架构

### 四层配置

1. Agent 默认配置只读。
2. Session 配置保存 Skill、Studio 工具和环境挂载。
3. Turn 快照原子冻结模型/资源 ID 和版本。
4. Turn 生命周期由 mpa-agent 持久化并拥有。

非终态期间的 Session 编辑明确标记为下一 Turn 草稿。已删除或无权资源保持可见失效状态，直到移除或替换。

### 模型目录与 Turn 冻结

Studio 服务端使用服务端凭据查询方舟，筛选已开通且兼容 mpa-agent 的对话模型，并缓存最近成功结果及新鲜度。失败时返回标记过期的缓存，或明确不可用。mpa-agent 在副作用前校验模型 ID 并持久化 Turn 快照；主模型和 worker 委托只读取该快照。

### 完整 Turn 生命周期

```text
queued -> running -> completed | failed
             | -> pausing -> paused -> resuming -> running
             |                    \-> interrupted -> 新增量 Turn
```

mpa-agent 持久化控制 generation、幂等键、期望/观测状态、参与方状态、安全点、暂停时间、恢复截止时间和失败详情。Studio 只调用 mpa-agent；mpa-agent 下发 worker 控制并聚合确认。暂停意图后，正在执行的原子操作可完成，但禁止启动下一模型/工具/委托。五分钟内 Resume 从已证明的持久安全点继续，不重放已完成工具或已接受用户消息。超过截止时间或无法原 Turn 恢复时，由用户点击继续触发旧执行中断，并在同一 Session 创建新增量 Turn。

### Session 资源与拓扑

Session 挂载保存不可变 Skill 版本及 Space ID、Studio 工具 ID/revision、环境/Workspace 绑定。Typed topology 节点为 `agent`、`sandbox`、`worker-session`、`skill-space`、`skill`、`studio-tool`、`mcp`、`environment`、`knowledge`、`sub-agent`，关系包括 `delegates-to`、`runs-on`、`mounts`、`provides`、`calls`。未挂载可选类别只作为图外入口，不伪造为活动节点。节点详情展示来源、配置/观测状态、生命周期、能力、最近调用和安全导航 ID。

### Composer 与用量

Composer 使用一个常规输入面和一排 Footer：附件、Agent 目标、Turn 模型、紧凑状态/用量与唯一主按钮。主按钮在空闲/终态表示发送，在运行时表示暂停，在 pausing/resuming 时表示进度，在 paused 时表示继续。Agent 与模型选择器统一为无边框 36 px trigger；不渲染第二组生命周期工具栏、cancel 或 interrupt。长 ID 可访问地省略，发送/控制槽位不得与模型选择器重叠。用量展示当前 Turn 与 Session 累计五类数据；缺失显示 `—`，累计快照仅贡献正增量。

### 环境与 Secret

普通环境响应返回名称、来源、敏感性、配置状态和允许的非敏感值，绝不包含 Secret。Secret 复制是管理员/开发者专用 POST，设置 `Cache-Control: no-store`，只审计操作者、Runtime、变量、时间和结果，不记录值。前端直接调用 `navigator.clipboard.writeText`，不渲染、持久化、缓存或写入遥测/错误。

### Studio 工具可发现性

工具详情包含用途、适用场景、输入 schema、权限、示例、来源/revision 以及默认/Session 挂载状态。添加/移除从下一 Turn 生效，浏览器数据不包含工具凭据。

### 会话活动投影与展示

A2A 投影层保留模型 reasoning summary 与 Agent 工作 thought 的语义类型。它按 task、invocation、语义类型和传输来源分别跟踪累计文本。只有内容属于完全重放或同一逻辑流经证明的累计前缀重放时才跨来源抑制；任意重复措辞必须保留。稳定来源事件 ID 仍是首选去重键。

前端从工具特定字段（包括 Runtime 的嵌套 payload）提取安全动作标题和对象。`create_goal`、`exec_command`、搜索、读取和文件修改等已知工具使用专属动作文案；未知工具展示具体名称。折叠行保持简洁，展开详情提供已脱敏输入和结果。大值采用有界 DOM 渲染及显式完整复制/下载路径，不能用未说明的截断值替代唯一可访问内容。预览和复制前都必须继续执行 Secret 遮罩和不安全控制字符清理。

Composer 复用现有可访问、可搜索的紧凑选择器，不再使用原生 `select`。过滤覆盖模型 ID 和展示文本，保留方向键/Enter/Escape 行为和无匹配提示，并在 Turn 模型不可变期间禁用。

## 接口契约

- 账号模型目录返回兼容模型、新鲜度/过期元数据和分类失败。
- Agent Card 声明带版本的 `turnModelSelection`、`turnLifecycleControl`、`sessionResourceMounts`、`resourceTopology`。
- Turn 创建携带已校验模型 ID 和 Session 资源 revision；mpa-agent 持久化解析后的快照。
- Studio 的 Turn control 提供 pause/resume，带幂等键和预期 generation。内部终态化能力保留给 mpa-agent，但不作为 Studio 操作暴露。
- Turn status 返回状态、期望状态、generation、安全点/参与方摘要、失败、暂停时间、恢复截止时间/处置方式和允许操作。409 返回相同的权威状态结构，Studio 直接吸收状态而不展示原始传输文本。
- Session resource API 返回默认值、增量、失效资源、revision 和下一 Turn 语义。
- Topology 返回一个 Session/Turn 的 typed nodes/edges。
- Secret copy 是 no-store 角色保护接口，绝不进入列表响应。

## 兼容与失败

旧 Agent 未声明 capability 时保留单一默认模型，隐藏 pause/resume，只展示已验证拓扑。Stream 断开不等于取消；Studio 重连持久状态/事件。并发控制由 generation/幂等性解决并返回权威冲突，Studio 吸收结构化 409 状态。超过五分钟或 owner 无法恢复时，不承诺进程替换恢复，而是在用户点击后创建增量新 Turn。原生 ArkClaw 和非 MPA Studio 路径不变。

## 任务

| ID | 工作 | 归属 | 依赖 |
| --- | --- | --- | --- |
| `T-1` | 持久 Turn 状态、安全点、幂等命令、参与方聚合 | mpa-agent | 无 |
| `T-2` | 在 mpa-agent 后封装 worker pause/resume 和超时恢复降级 | mpa-agent | `T-1` |
| `T-3` | 组合方舟目录、兼容性和 Turn 校验 | Studio BFF + mpa-agent | 无 |
| `T-4` | 持久 Session 挂载并原子创建 Turn 快照 | Studio BFF + mpa-agent | `T-1` |
| `T-5` | Skill Space 浏览/挂载及 Studio 工具详情/示例 | Studio | `T-4` |
| `T-6` | Typed topology endpoint、图和详情抽屉 | mpa-agent + Studio | `T-4` |
| `T-7` | Composer 布局和 Turn 模型/生命周期控制 | Studio frontend | `T-1`, `T-3` |
| `T-8` | 用量分类 UI 和环境/Secret 复制流程 | Studio | 无 |
| `T-9` | 浏览器、Runtime、竞态、刷新、安全、旧版 E2E | 双仓库 | `T-1`–`T-8` |
| `T-10` | 会话事件语义、重放安全的 thought/reasoning 投影、human-readable 工具活动、完整脱敏详情和可搜索模型选择 | Studio BFF + Studio frontend | `T-3` |

## 验收

| 需求 | 验收证据 | 初始状态 |
| --- | --- | --- |
| `FR-1`, `FR-2` | 目录契约及真实双模型 Turn，证明主/worker 一致及非法 ID 无副作用 | `not_run` |
| `FR-3` | 正常/窄窗口、长模型 ID 浏览器截图与测试 | `not_run` |
| `FR-4` | 五类 Token 测试及重放/刷新证据 | `not_run` |
| `FR-5`, `FR-6` | 集成/真实 `running -> pausing -> paused -> resuming -> running`、五分钟降级、竞态和幂等 | `not_run` |
| `FR-7`, `FR-9` | 真实 Skill Space/工具 Session 挂载刷新保留并从下一 Turn 生效 | `not_run` |
| `FR-8` | 契约和浏览器证明只展示真实关系 | `not_run` |
| `FR-10` | 精确错误、Secret 不渲染、授权复制、普通用户 403、审计无值 | `not_run` |
| `FR-11` | 旧 Agent Card fixture 和浏览器降级 | `not_run` |
| `FR-12`, `FR-13` | 工具专属/嵌套/未知 fixture、大型脱敏结果复制/下载和浏览器检查 | `not_run` |
| `FR-14` | status/artifact 重放 fixture 及实时/历史/重连 reasoning/thought 展示 | `not_run` |
| `FR-15` | 键盘与输入过滤、无匹配状态、非终态禁用选择 | `not_run` |

门禁遵循 `AGENTS.md` 与 `frontend/SPEC.md`：目标测试、共享契约广泛回归、前端 test/build、变更 Python Ruff/Pyright、真实浏览器正常/错误/取消/重试/窄窗口、pre-commit、两轮 Review 以及隔离 Runtime E2E。

## 风险与批准

安全点实现必须先证明 Runner 哪些边界可继续且不重复副作用。账号资源可能已开通但与 Runtime credential/base URL 不兼容，因此交集需 fail closed。大拓扑需限制节点数、按需详情、平移缩放及可访问列表。浏览器剪贴板策略失败时不得回退为渲染。

用户已批准：分期交付、实时方舟目录、不可变 Turn 模型、完整流程协作暂停、mpa-agent 生命周期所有权、Composer 不重叠、真实资源拓扑、下一 Turn 生效的 Session 挂载、管理员/开发者复制但不渲染 Secret。包含单一动态主按钮和用户触发五分钟降级语义的双语书面设计与组件契约已于 2026-09-13 批准。

## 设计评审记录

仓库评审发现并解决以下设计阻塞项：

- **Worker 暂停契约差异：** mpa-codex-worker 的 `pause` 通过中断当前 Codex Turn 进入 paused，`resume` 通过 `thread/resume` 恢复 Session。mpa-agent 必须把该行为封装为完整流程安全点，并在五分钟后或 owner 不可恢复时只在用户点击继续后创建增量新 Turn；Studio 不直接协调 worker。
- **mpa-agent 状态缺口：** 当前 A2A store 只有 running/cancel-requested/final 状态。`T-1` 是带旧行兼容的 schema/状态机迁移，不是纯 UI 扩展。
- **安全点歧义：** 在具体 Runner 边界具备原子 checkpoint 和无重复副作用证明之前，禁止承诺进程重启后 resume。第一条纵向切片必须先完成并测试安全点 spike。
- **模型目录重复风险：** Studio 已有 `frontend/server/model_catalog`；`T-3` 扩展其 freshness/stale/compatibility 元数据并与 Runtime capability 求交，不新建目录服务。
- **Secret 接口复用风险：** 现有原始 API Key 路由仅证明 no-store 传输，不满足 Runtime 变量 RBAC/审计。Secret copy 使用独立角色保护和审计契约，不复用权限更弱的通用 resolver。
- **范围顺序：** 按已批准方案分两期交付。第一期为模型目录/冻结、生命周期控制、用量、环境错误/Secret copy 和 Composer 布局；第二期为 Session Skill/工具挂载、工具说明和资源拓扑。第二期不得弱化第一期生命周期/快照契约。

当前无 P0/P1 产品设计阻塞。实现仍需用户审核本书面双语设计，并制定从安全点 spike 开始的实施计划。
