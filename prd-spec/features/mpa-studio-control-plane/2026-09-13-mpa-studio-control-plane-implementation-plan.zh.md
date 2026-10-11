# MPA Studio 控制面实施计划

- Change ID：`mpa-studio-control-plane`
- 状态：第一期已实现；第二期部分实现
- 日期：2026-09-13
- English：[implementation-plan.md](2026-09-13-mpa-studio-control-plane-implementation-plan.md)
- 已批准设计：[design.zh.md](2026-09-13-mpa-studio-control-plane-design.zh.md)

## 执行策略

按两期纵向切片交付。保留双仓库现有无关变更和 mpa-agent 独立分支。每个切片先写失败契约测试，再实现、目标验证和文档对齐。本地门禁未通过前不发布 Runtime 镜像。

## 第一期 — Turn 正确性与生命周期

### Slice 0 — 证明可恢复安全点

1. 刻画 VeADK Runner 在模型响应完成、工具开始/结果、worker 委托开始/结果处的边界。
2. 添加隔离 mpa-agent spike 测试，在每个边界请求 pause，记录 resume 是否会重复已接受模型/工具副作用。
3. 将边界分类为原子不可恢复或持久可恢复，只保存已证明边界所需最小 checkpoint。
4. 门禁：在一个 E2E 安全点 red/green 测试及“pause 意图后禁止下一操作”反向测试通过前，不声明生产 pause。

Spike 结果（2026-09-13）：`mpa-agent/tests/test_turn_safe_point_spike.py` 已在
同一个真实 ADK Invocation 中证明 `after_tool` 边界：已提交的副作用恰好发生一次，
暂停期间下一次模型请求保持阻塞，进程内恢复会继续同一个 Invocation，不会重放已接受
的用户消息或已完成工具。基于 Store 的 gate 另行验证 `before_tool` checkpoint 会在
操作启动前阻塞。该结果允许 Slice 1 使用协作式 callback gate，但不证明进程替换恢复
或任意在途 Provider/工具抢占；在持久 checkpoint 得到验证前，这两项继续明确为不支持。

### Slice 1 — 持久完整 Turn 控制器

1. 扩展 `app/stores/a2a_task_control.py`，增加兼容迁移的状态、generation、期望状态、命令幂等、参与方状态、安全点/checkpoint 元数据和分类控制失败。
2. 在 A2A 所有权旁新增 mpa-agent control/status 路由，不建立 Studio 私有状态。
3. 在每个下一主模型、工具和委托边界前增加协作检查。
4. 把 worker session handle 映射到 Turn，封装 worker pause/resume/cancel；只有现有 cancel/continue 不能满足批准语义时才新增 worker interrupt 契约。
5. 刷新/重连读取持久状态和事件。
6. 测试：状态转换表、旧行迁移、重复命令、过期 generation、并发 pause/cancel、worker 失败、刷新、cancel 终态、interrupt/新 Turn 继续。

### Slice 2 — 实时模型目录与不可变 Turn 模型

1. 扩展 `frontend/server/model_catalog`，增加观测时间、stale 和分类失败，复用账号 activation/model join。
2. 服务端与 mpa-agent 模型 capability 求交，不把 API Key 发送给 Runtime 或浏览器。
3. 把 Studio Session 本地模型语义改为 Turn 草稿；发送时冻结，并在执行前持久化到 mpa-agent Turn 快照。
4. 主模型和 worker 委托读取同一快照；过期/非法 ID 在副作用前拒绝。
5. 测试：缓存/stale/无缓存失败、capability 交集、Turn 不可变、主/worker 一致、非法 ID、旧 Runtime 单模型。

### Slice 3 — Composer、控制与用量

1. Composer 拆成 target/header 和响应式 footer 槽位，删除竞争定位。
2. 根据服务端 allowed actions 渲染控制；非终态禁用模型和冲突操作。
3. 展示当前 Turn 与 Session 累计的输入/输出/推理/缓存/总量，保留正增量聚合。
4. 浏览器门禁覆盖正常/窄宽度、长 Agent/模型名、全部控制态、缺失 Token、键盘/IME、刷新、重试和错误。

### Slice 3A — 会话活动保真

1. 增加同一累计 reasoning 经 working status 与 artifact update 发出的 A2A fixture，并加入必须保留的合法重复文本。
2. 在投影和前端 Block 中保留 reasoning 与 Agent thought 元数据。
3. 为目标、命令、搜索、读取、文件修改、MCP 和未知工具增加专属展示适配，包括嵌套 Runtime payload。
4. 限制预览，同时保留完整脱敏复制/下载能力，并让所有路径使用相同脱敏规则。
5. 使用现有可搜索紧凑选择器替换 Composer 原生模型 select，并保留 Turn 锁定。
6. 测试/浏览器：实时/历史/重连一致、reasoning 不重复、thought 标签区分、工具行有意义、详情完整安全、键盘过滤、无匹配、运行时禁用及窄窗口。

### Slice 4 — 环境错误与 Secret 复制

1. 把环境读取失败拆分为鉴权、Runtime 不可用、版本不存在、Manifest 失败、不支持 Secret。
2. 增加管理员/开发者专用 Runtime Secret copy POST，no-store 且审计不含值。
3. 直接写剪贴板并丢弃，不渲染/持久化/遥测。
4. 测试：RBAC、缓存头、审计脱敏、变量不存在、上游失败、剪贴板拒绝、DOM/存储/日志无值。

### 第一期发布门禁

双仓库目标测试、mpa-agent 广泛影响测试、VeADK 适用并行回归、前端 test/build 和真实浏览器矩阵、变更 Python Ruff/Pyright、pre-commit、两轮 Review，以及隔离 Runtime E2E：目录、模型冻结、pause/resume 安全点、cancel、interrupt、刷新恢复、五类 Token、环境错误、授权/未授权 Secret copy。

## 第二期 — Session 资源与运行拓扑

### Slice 5 — Session 资源 revision 与 Turn 快照

1. 定义一个 Session 资源文档/revision，包含 Skill 版本、Studio 工具 revision、环境/Workspace 绑定。
2. 服务端校验更新并原子解析一个不可变 Turn 资源快照。
3. 删除/撤权/失效资源保持可见且禁止执行。
4. 测试：revision 冲突、活动 Turn 编辑下一 Turn 生效、刷新持久、版本删除、默认值不变。

### Slice 6 — Skill Space 与 Studio 工具工作区

1. 复用 Skill Space API，在会话中列出 Space、Skill、不可变版本和详情。
2. 增加 Session 挂载/移除并标记下一 Turn 生效。
3. Studio 工具详情展示用途、场景、schema、权限、示例、来源、revision 和挂载状态。
4. 测试/浏览器：加载/空/错误/重试、版本选择、权限、失效资源、刷新持久、下一 Turn 执行。

### Slice 7 — Typed 资源拓扑

1. mpa-agent 从 Agent 默认值、Turn/Session 快照、真实 worker handle、MCP、环境、知识和子 Agent 配置生成 typed topology。
2. 展示有边界的交互图，支持平移/缩放/适应、详情抽屉和可访问列表。
3. 未挂载可选资源保持为图外添加入口。
4. 测试/浏览器：单 Agent + Sandbox、worker 状态、Skill/工具/MCP/环境、缺失知识/子 Agent、大图边界、窄窗口、键盘。

### 第二期发布门禁

重复仓库门禁，并使用真实 Skill Space、Studio 工具、环境、worker 委托、刷新、失效资源和拓扑状态变化执行 Runtime E2E。

## 文件归属预期

- mpa-agent：`app/stores/a2a_task_control.py`、A2A executor/app/routes、invocation context、模型/委托集成、Session 资源/拓扑服务及测试。
- veadk-python 后端：`frontend/server/model_catalog`、Session 资源及环境/Secret 路由、Runtime A2A proxy/types 及测试。
- veadk-python 前端：`App.tsx`、`Composer.tsx`、Token 用量、拓扑、Skill/工具/资源选择器、i18n/styles/tests 及重新生成 `veadk/webui`。
- mpa-codex-worker：仅当 Slice 1 证明缺少 worker interrupt/checkpoint 契约时修改；编辑前遵循其独立 PRD/spec 和门禁。

## 停止条件

如果安全点 spike 无法证明无副作用 resume、方舟模型兼容性无法服务端解析，或 Secret copy 审计无法避免值进入日志/状态，则停止并返回设计评审，不得弱化验收继续。

## 验证记录 — 2026-09-13

- `pass` — 前端测试：`npm --prefix frontend test`（`1096` 项通过）。
- `pass` — 生产资源：`npm --prefix frontend run build`；最终弹窗布局修复生成并实际服务 `assets/app/index-CozNp3D8.js`。
- `pass` — VeADK Runtime proxy、A2A 投影和 RBAC 目标测试：`235` 项通过。
- `pass` — mpa-agent executor、delegation、runtime plugin、生命周期、安全点和 task-store 目标测试：`173` 项通过。
- `pass` — Runtime `r-yeuujrrcowb21078p9jh` 版本 `52` 使用镜像 `agentkit/mpa_agent_studio:resource-topology-v52b-20260913`（digest `sha256:205a82a5a32094c6da93e1a6b1ae4f7b70a883021b06489b844a28d1214eaf79`）达到 `Ready`。其 Agent Card 声明 23 个兼容模型；Studio 代理与账号激活状态求交后当前展示 14 个可选模型，并提供完整 Turn 生命周期能力和已配置的 `Agent -> Sandbox` 拓扑。使用已激活备选模型 `glm-5-2-260617` 的真实 Turn 成功完成，且 Turn UI 保持显示该模型。
- `pass` — 系统 Chrome CDP 在 1440 px 与 375 px 下均无横向溢出。模型弹层与智能体选择器相互独立，提供 `搜索模型`，输入筛选后只返回匹配的可选模型。
- `pass` — 真实 Turn 展示 `pause`、`interrupt`、`cancel`；pause 在协作式安全点进入 `pausing`，终态完成后所有生命周期按钮消失。完成 Turn 分开展示模型推理、最终回答和输入/输出用量。
- `pass` — Session Skill 操作打开真实 Skill Space 选择器，并加载账号 Space 和带版本 Skill。
- `评审中已修复` — Skill Space 弹窗标题误用了带图标的三列工具弹窗网格，导致标题逐字换行；现已使用既有无图标双列变体，并增加回归断言。
- `评审中已修复` — 仅按 Runtime capability 展示时包含三个未激活模型，真实选择会收到方舟 `NotFoundError`。Studio 代理现与账号模型目录求交，同时保留 Runtime 默认模型作为兼容回退。
- `视觉验收后已修复` — 新会话模型触发器现与 Agent 触发器统一为 36 px 无边框样式，并在 36 px 发送按钮前保留互不重叠的独立槽位。Runtime 列表新增 `agentCategory`；优先使用稳定的 `veadk:agent-type=mpa` 元数据，并以既有 `/mpa_agent*:` 镜像仓库作为兼容识别依据，归入独立的 `MPA 智能体` 类别。
- `blocked` — 仓库环境未安装 Pyright（`Failed to spawn: pyright`）。
- `被可选依赖阻塞` — 更广泛的 VeADK 回归此前得到 `4030 passed, 12 skipped, 2 xfailed`，另有七个失败和两个收集错误，原因是缺少可选 `llama_index`/`anthropic` 依赖；受影响目标测试均通过。
- `已知生成产物例外` — 排除生成文件 `veadk/webui/website-integration.js` 后 `git diff --check` 通过；该第三方 bundle 自带 trailing whitespace。

## 明确剩余的第二期范围

Session Skill/Studio 工具/环境选择当前保存在浏览器 localStorage，并随下一 Turn 提交。服务端 Session 资源文档、revision 冲突、失效资源保留和原子资源解析尚未实现；拓扑也尚未投影动态 worker 生命周期节点。不得把这些项目声明为已完成。
