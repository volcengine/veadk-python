# Studio MPA 控制面

- Component ID：`studio-mpa-control-plane`
- 状态：第一期已实现；第二期部分实现
- 修订日期：2026-09-13
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
- `CON-12`：工具活动展示工具特定的安全动作和对象；未知工具展示具体名称，不使用通用完成标签。
- `CON-13`：已脱敏工具输入/结果可通过显式复制/下载完整获取；预览渲染有界、截断有提示，所有详情路径共享同一脱敏规则。
- `CON-14`：Turn 模型选择支持搜索和键盘访问，并在非终态 Turn 拥有不可变模型快照期间保持禁用。
- `CON-15`：Runtime 列表暴露 `agentCategory`，并接受 `agentCategory=general|mpa` 在可见分页前执行服务端分类过滤。MPA 的权威且唯一来源是 Runtime 标签 `veadk:agent-type=mpa`；镜像名和 artifact URL 不参与分类。`agentCategory=mpa` 必须先通过 Volcano Tag 服务正向标签过滤获得候选 Runtime ID，再按 Runtime ID 补齐详情，避免 MPA 结果稀疏时扫描无关 Runtime 页。

## 状态与数据

- Studio 可见 Turn 状态：`queued`、`running`、`pausing`、`paused`、`resuming`、`interrupted`、`completed`、`failed`。内部可保留终态化状态，但不作为用户操作。
- Turn 控制保存 generation、幂等、期望/观测状态、参与方确认、安全点、快照 revision 和分类失败。
- Session 资源当前把浏览器本地增量与 Agent 默认值分开；提交的 Turn Payload 保存解析后的 Skill ID/版本，并在该 Turn 内保持不可变。
- 当前拓扑合并 Runtime 配置的 Agent/Sandbox 节点和浏览器所选 Session 资源。动态 worker 生命周期节点与服务端 Session 资源快照仍为后续工作。

## 失败与安全

非法模型/资源在副作用前失败。控制过渡失败绝不显示为已暂停。冲突返回权威 generation/state。Secret 排除在普通 API、DOM、状态、存储、日志、遥测、截图和错误详情之外。剪贴板复制是有意授权披露，必须审计。

## 兼容性

旧 Agent 保留单一默认模型和既有非 MPA 停止行为，隐藏不支持的暂停/恢复控制，只展示已验证数据。原生 ArkClaw 和非 MPA Studio 契约不变。

## 验证

契约测试覆盖状态转换、幂等、竞态、模型快照、已提交挂载、拓扑、鉴权、脱敏和 Runtime 分类过滤。浏览器测试覆盖响应式布局、唯一动态主按钮、模型筛选、MPA 分类选择、Skill Space 发现和终态控制清理。真实 Runtime 测试已证明模型目录、不可变请求模型、生命周期状态/控制路径、配置态 Agent 到 Sandbox 拓扑及真实 Skill Space 发现。主 Agent/worker Skill 传递由目标契约测试覆盖。完整的真实 worker pause/resume、五分钟增量续跑、刷新恢复及失效资源执行门禁仍需后续验证。
会话投影测试还覆盖 status/artifact 重放、合法重复措辞、reasoning/thought 语义区分、嵌套工具 payload、大型脱敏值、已知/未知工具标签，以及可搜索模型的键盘行为。
