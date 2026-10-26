# 协作页面分区与 A2A 空间创建

[English](2026-10-22-space-management.md)

变更 ID：mpa-space-management。日期：2026-10-22。状态：implemented。前置设计：[中心注册](2026-10-22-center-registration.zh.md)。组件合同：[MPA 协作 Agent](../../../specs/mpa-collaborating-agents/README.zh.md)。

## 证据、范围与场景

A2ACenter 将绑定、注册和成员内容放在同一纵向流程中，统一使用 16px 间距。用户确认将绑定和成员分区，并要求新增 AgentKit 空间创建。保留已有中心相关本地修改。2026-10-22 读取的官方 [CreateA2aSpace 接口](https://docs.volcengine.com/docs/86681/2249657) 接受 Name、可选 ProjectName 和 IntentEnabled，返回 Result.Id。尚未真实验证云创建。

FR-1：空间选择、绑定、解绑归入“空间绑定”；注册、刷新和成员列表归入“空间成员”。使用独立语义区域、32px 组间距、共享左右对齐、可换行操作，以及已有主题变量和字体。注册标明目标空间。保留原有加载、错误、空状态、CAS 和注册行为。

FR-2：空间选择器旁新增“新建空间”，无空间时仍可操作。内联表单填写名称、项目（默认 default）和语义检索（默认关闭）。创建成功后选中新空间并刷新成员，绑定仍须单独明确操作。即使分页或最终一致性列表暂未返回新空间，也保留它的可选项。创建成功后刷新失败仍须表达创建成功。

FR-3：POST /web/a2a-spaces?region=... 接受 targetRuntimeId、name、projectName（默认 default）、intentEnabled（默认 false）。云写入前执行现有 Studio 管理员和目标 Runtime 授权。Studio 使用现有签名云身份调用 CreateA2aSpace，传入 Name、ProjectName、IntentEnabled，仅返回 {id}。不改 Runtime API 或部署。名称/项目去除首尾空白后须非空、不超过 128 字符且无控制字符（Studio 策略，并非声称官方限制）。拒绝未知字段及非布尔 intentEnabled。请求体上限 4096 字节。提供商拒绝经过脱敏；不确定失败返回带结果不明代码的 502，绝不自动重试。

FR-4：禁止并发创建，兼容输入法；打开时聚焦表单，关闭后恢复焦点。取消或卸载会中止浏览器请求，不声称云端回滚；提交期间取消或结果不明时，在刷新核对前锁定写操作。切换 Runtime/地域丢弃旧响应。只读刷新不执行创建。不在浏览器持久化凭据或暴露原始提供商错误。

非目标：编辑/删除空间、标签管理、创建 Runtime、自动绑定、派发/Harness 改动、云部署、验证时真实创建云资源。SDK、依赖和生成项目不受影响。

## 设计与备选

保留 AgentWorkspace 详情布局，复用 Button/Select/FormLabel/InputWithTailIcon/Checkbox 基础组件。CardLayout 强制无关的图标与关闭操作，因此在现有布局内使用两个语义区域，不嵌套另一个页面布局。复用 collaborators 表单样式，仅新增分组、标题行和选择器容器间距。不增加 Tab：空间选择和成员需要同时可见。不新增依赖、图标、字体或配色；沿用 14px 文字及 studio 文字/边框变量。

在 frontend/server/a2a_center.py 新增空间路由；在 adk/client.ts、adk/a2aSpace.ts 新增客户端、类型与响应解析器。A2ASpaceCreation 管理提交、中止和结果不明状态；A2ACenter 管理选择、绑定和列表刷新。共享写操作门禁避免创建、注册、绑定重叠。不自动重试结果不明的创建。新空间 ID、名称、项目仅为临时 UI 状态，云端是权威来源。仅在表单关闭且父级不忙时恢复焦点。卸载后不得应用迟到响应。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1 | T-1 中心分区与双语文案 | AC-1 绑定和注册具有不同可访问区域及操作 | frontend/tests/collaboratingAgents.test.tsx；桌面/窄屏浏览器 |
| FR-2 | T-2 创建表单/客户端与选择刷新 | AC-2 无空间/分页时可创建；成功不写绑定 | UI 测试与模拟浏览器 |
| FR-3 | T-3 校验并授权的服务端路由 | AC-3 精确 Payload、输入边界、拒绝授权、错误脱敏、不重试 | tests/cli/test_a2a_center_registration.py |
| FR-4 | T-4 异步与键盘测试 | AC-4 无重复创建/旧响应污染；取消/不明须核对；焦点/输入法正常 | React 测试与浏览器 |
| 全部 | T-5 双语文档/构建/评审对齐 | AC-5 记录测试/构建/i18n/产物/Ruff/Pyright 与差异检查 | 下述命令 |

测试先行：生产修改前先补失败的 UI/API 定向测试。门禁：uv run --extra dev pytest tests/cli/test_a2a_center_registration.py；npm --prefix frontend test；npm --prefix frontend run build；npm --prefix frontend run check:i18n；npm --prefix frontend run test:webui-assets；uv run ruff check frontend/server/a2a_center.py tests/cli/test_a2a_center_registration.py；仓库本地 Pyright 检查上述 Python 文件；使用模拟接口的真实浏览器，不写云资源。本次未请求提交，因此不触发提交前 pre-commit 与分支同步。

## 评审、批准、风险与交付

用户批准：“帮我改下”接受上方绑定、下方成员的方案；“然后也加上agentkit这里新建空间的功能”授权创建能力。review-spec 技能不可用；直接评审覆盖双语范围、接口字段、授权、输入边界、不重试、取消/迟到响应、显式绑定及可测试性。无设计阻塞项。实现前更新双语组件合同。

风险：提供商可能在超时前已接受请求，因此再次创建前须读取核对。列表可能延迟或分页隐藏新项；保留确认的 ID 可选，不声称已被列表返回。Studio 凭据和 Runtime 身份必须有一致的账号/地域权限，不跨提供商/账号降级。回滚 UI/服务端变更不删除已创建空间。真实提供商集成明确未验证；本地测试模拟它。

验证状态：实现前 not_run。日期/范围：2026-10-22，已有未提交中心实现之上的空间管理增量。本次未授权提交、推送或部署。


## 最终验证（2026-10-22）

本地增量实现已完成 T-1 至 T-5 及 AC-1 至 AC-5。测试先行证据：实现前，18 项新增 Python 用例因路由不存在而失败，6 项 UI 用例因新控件/区域不存在而失败。补充测试覆盖显式项目/检索开关、无空间时创建及权限纠正。评审修正关闭焦点恢复：结果不明导致打开按钮禁用时，焦点转到刷新；互斥表单不会争抢焦点。选择器容器对齐现有 372px Select 基础组件，不覆盖基础组件样式。没有新增组件样式例外。

| 检查 | 结果 | 证据与范围 |
| --- | --- | --- |
| uv run --extra dev pytest tests/cli/test_a2a_center_registration.py tests/test_mpa_collaborator_proxy_policy.py -q | pass | 41 passed；模拟云端，未创建真实资源 |
| npm --prefix frontend test | pass | 1389 项 Node 测试、164 项 Vitest 用例，11 个文件 |
| 定向 collaboratingAgents.test.tsx | pass | 17 项，包括最终焦点/输入法/取消/不明/错误及不自动绑定 |
| npm --prefix frontend run build | pass | 匹配的 veadk/webui 产物；已有大分块警告 |
| npm --prefix frontend run check:i18n | pass | 2 种语言，22 个命名空间 |
| npm --prefix frontend run test:webui-assets | pass | 114 个发布文件、351 个内部引用 |
| frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json | pass | 无诊断 |
| 对 a2a_center.py、test_a2a_center_registration.py 执行 pre-commit ruff-check、ruff-format | pass | 使用仓库 hook 环境；项目环境不提供独立 uv run ruff 命令 |
| 使用 .venv/bin/python 对两个 Python 文件执行 Pyright | pass | 0 错误/警告；复用相邻仓库已有 Pyright 可执行文件，解释器使用本项目环境 |
| 浏览器 | pass | 隔离真实浏览器与模拟 API：桌面分区、创建选中但不绑定、空状态、权限拒绝、结果不明锁；检查键盘焦点和 390px 窄视图 |
| git diff --check 与双语文档检查 | pass | 范围内文档路径、ID、翻译合同对齐 |
| 本机路由发现 | pass | 127.0.0.1:8000/openapi.json 包含 POST /web/a2a-spaces；未发送创建请求 |
| 密钥扫描 | pass | 对范围内源码/文档执行 gitleaks dir，使用仓库 .gitleaks.toml；既有白名单排除测试与生成的 Web 产物 |
| 全量 Python 回归 / 真实云创建 | not_run | 独立路由变更由定向 API/策略测试覆盖；云写入不属于隔离验证范围 |

实现评审检查了云写入前授权、严格字段和请求体边界、返回 ID 校验、不泄露原始提供商错误、不重试、创建后刷新失败、取消/卸载，以及分页时保留选择。真实 AgentKit 创建仍未验证。保留已有无关本地修改。未提交、推送或部署。验证后删除临时浏览器夹具。

本机生效：运行中的 Studio 缓存了旧 HTML 入口。沿用原 `veadk studio` 启动方式重启，不额外打开浏览器；确认当前构建入口、引用 JS 产物（HTTP 200）及实时 OpenAPI 中的 POST /web/a2a-spaces。未修改云端 Runtime。

用户于 2026-10-22 批准名称展示优化：空间选择器、已接入空间状态、正在查看的空间、创建确认和注册目标仅显示空间名称，不显示资源 ID。请求和选择值中的 ID 保持不变。元数据缺少名称时显示本地化的名称暂不可用提示，不回退展示 ID。本次仅改展示，不影响 API、持久化或授权合同；直接评审无阻塞项。

已批准后续需求 FR-5 / T-6 / AC-6（2026-10-22）：只有选中空间的 ID 等于当前绑定空间 ID 时，才能解绑。选中未绑定空间时，不得提供可用的解绑操作。切换选择（包括创建后选择新空间）清除旧确认。同时在写入处理函数和可见控件上校验。API/CAS 与权限不变。回归：绑定 A，打开解绑确认，选择未绑定 B，确认提示和操作消失且无写入；重新选 A 并明确确认，仅发送一次带当前 revision 的空绑定。直接评审确认这会阻止操作 B 时解绑 A，不改变后端归属。验证待执行。

后续验证（2026-10-22）：pass — npm test（1389 项 Node 测试、167 项 Vitest 用例）、构建、i18n（2 种语言/22 个命名空间）、tsc --noEmit、产物检查（114 个文件/351 个引用）、git diff --check、范围内 UI 源码密钥扫描。只显示名称的回归先有 2 项失败，修复后通过；按所选空间解绑的回归先失败，修复后通过。模拟 API 的真实浏览器确认，选中未绑定 Other 时，解绑操作与此前 Default 确认一起消失，空间名称不带资源 ID。沿用原命令重启 Studio；启动完成后确认当前入口和 JS 产物返回 HTTP 200。未修改云端绑定。已删除临时夹具。此纯前端优化的 Python 测试为 not_applicable，沿用此前后端证据。FR-5 / T-6 / AC-6 已完成。
