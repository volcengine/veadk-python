# A2A 注册仅保留一个必选 Runtime 控件

[English](2026-10-22-single-runtime-picker.md)

ID：mpa-a2a-single-runtime-picker。日期/修订：2026-10-22。状态：approved。
关联：[组件](../../../specs/mpa-collaborating-agents/README.zh.md)、[端点设计](../../features/mpa-collaborating-agents/2026-10-22-endpoints-and-skills.zh.md)。

## 证据、目标与范围

A2ARegistration 同时渲染 Runtime Select 和必填 Runtime ID 输入框，共用 form.runtimeId。用户指出字段重复并批准“按此调整”。手动字段原用于绕过列表分页/读取失败，但表单已有分页和重试。删除重复输入，同时保留选择、端点加载和注册 Payload。

FR-1：始终显示一个必选的已有 Runtime Select，选项来自已授权的分页 Runtime 列表，不再渲染独立 Runtime ID 文本框。ID 仍用于内部值以及已有选项标签/详情。Runtime 来源必须选择仍存在于当前列表的选项，并获得匹配端点后才允许注册。切换选择取消/丢弃旧端点读取。替换列表后已不存在的选择不得继续提交。
FR-2：区分首次加载、成功空列表和读取失败。空/错误状态提供列表重试；分页追加/去重选项并保留选择。两种语言移除手动 ID 提示。保留键盘导航、Escape/取消/焦点返回，以及 Standard JSON/URL 输入与 IME 行为。
FR-3：保留 POST 的 RuntimeId/NetworkType、后端授权、公共 API 兼容与结果不明处理。不改后端、Runtime、IAM、依赖或数据库；不执行真实云写入、提交或推送。

## 设计、任务与验收

复用 Select/FormLabel/Button/TextShimmer 和已有表单布局。将必填语义移到 Runtime 选择控件；表单挂载时聚焦首个可见来源控件。sourceRuntimeId 仅从已列出的选择推导，使列表替换能失效旧端点和提交状态。来源 API 联合类型不变。CON-RUNTIME-PICKER 是 UI 合同细化，端点及后端合同不变。

| 需求 | 任务 | 验收 | 测试 |
| --- | --- | --- | --- |
| FR-1 | T-1：先补失败回归，再删输入并限制已列出选择 | AC-1：无 ID 文本框，选择控件必选，自动提交所选 ID，迟到/缺失选择不能提交 | frontend/tests/collaboratingAgents.test.tsx |
| FR-2 | T-2：加载/空/错误/分页及键盘回归，更新语言 | AC-2：状态明确且可重试，分页保留选择，无手动 ID 提示，保留 Standard IME | UI 测试；模拟 API 的真实浏览器，含窄屏 |
| FR-3 | T-3：文档、类型、构建/产物与评审 | AC-3：前端测试/构建/i18n/assets/tsc、范围内密钥/文档检查通过，无新增后端差异 | 仓库前端门禁；git diff --check |

## 评审、批准和风险

没有 review-spec 技能，已直接评审可行性、组件归属、状态/取消、错误、安全、兼容、可测试性和双语等价，无阻塞。用户在代码/测试修改前批准上述单一选择方案。沿用 frontend-design/ui-ux-pro-max 的反馈和组件复用指导，不重新设计视觉。移除手动入口后，Runtime 列表不可用时必须重试，不能绕过，这是已批准范围。提供商资格和最终授权仍由服务端执行。全量 Python 回归及 Ruff/Pyright 对此次纯前端增量为 not_applicable；保留已有无关未提交修改。

## 验证

日期：2026-10-22。范围：9ab0ef2d 之上已有未提交 A2A 中心工作的纯前端增量。执行前检查均 not_run。真实注册/删除为 not_run，验证仅只读或隔离模拟。结果另记于下方。


## 实现与验证记录（2026-10-22）

生产/UI 实现已完成，T-1/T-2/T-3 代码与验证变更在本地，此次增量未改后端/API。实现前 4 项新增回归失败；当前协作 Agent 40 项均通过。移除 Runtime 文本字段后，将 Standard 导入 IME 覆盖移至其真实文本输入。评审核对必填语义、选择到 ID 的映射、空/错误/加载状态、追加分页、旧端点失效、焦点和取消，无范围内代码发现。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| `npm --prefix frontend test` | pass | 1389 项 Node；11 文件 187 项 Vitest，其中协作 Agent 40 项。 |
| `npm --prefix frontend run build` | pass | 已生成匹配产物；保留既有大分块提示。 |
| `npm --prefix frontend run check:i18n` | pass | 2 语言 / 22 命名空间。 |
| `npm --prefix frontend run test:webui-assets` | pass | 114 产物文件 / 351 引用。 |
| `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json` | pass | 无诊断。 |
| 隔离模拟 fetch 的真实浏览器 | pass | 单一必选控件，无手动 ID 输入；自动加载端点；列表失败后重试；确认空状态；键盘选择和取消/焦点返回。390px 下表单 clientWidth 与 scrollWidth 均为 342px。夹具、Vite 和标签已移除。 |
| 仓库配置的范围内 gitleaks；双语文档链接/编号；`git diff --check` | pass | 未发现秘密；保留既有扫描排除项。 |
| Python 测试/Ruff/Pyright | not_applicable | 此增量未改 Python 实现或测试；先前认证/端点验证留在所属设计。 |
| 提交门禁和真实云写入 | not_run | 未授权提交、推送或云注册/删除。 |
| 本机启动/当前构建入口 | pass | Studio 页面与当前 JavaScript 资源均 HTTP 200。 |
| 本机重启后的云账号环境 | blocked | Agent 为清除缓存旧入口优雅重启了 Studio，但新进程未继承原云 AK/SK 环境；本地 .env 无对应凭据，空间只读查询现返回 409。这是 Agent 引入的运行环境回归，不是云 IAM 拒绝。未输出、落盘或替换凭据，未代选其他 CLI profile。已询问用户原启动/配置路径，或请其用原终端环境恢复，目前待恢复。 |

运行环境回归恢复并验证前，生命周期保持 approved，不宣称全部完成。UI 实现和测试可评审，但当前云访问不可用。保留全部原有无关修改。未提交、推送或部署 Runtime。
