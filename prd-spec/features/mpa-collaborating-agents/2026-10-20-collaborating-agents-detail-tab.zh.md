# MPA 协作 Agent 详情页 Tab

## 背景、范围与批准
现有改动将管理入口放在聊天信息侧栏。2026-10-20 用户明确要求移至“智能体 → MPA → 选中智能体”的详情页，在“基本信息”下增加 Tab，仅影响 MPA。该请求批准本次位置调整；保留现有管理员权限。

## 要求与场景
1. 有 Runtime 的 MPA，管理员看到基本信息及紧随其后的协作 Agent。选中后才内联挂载管理内容。
2. 普通智能体、草稿及非管理员不增加 Tab，也不发管理请求。不支持的外部定位回到基本信息。
3. 切换 Tab、Runtime、地域或权限时卸载管理器，取消请求并清空临时表单和结果。迟到响应不能更新其他目标。
4. 删除聊天侧栏入口。CRUD、错误、版本检查、结果未知后的恢复及服务端鉴权不变。

## 设计与影响文件
在 AgentWorkspace 复用 CollaboratorManager，以地域及 Runtime ID 为 key。App 显式传递 admin/super_admin 权限；AgentTopology 移除无用入口插槽。复用 ResourceDetailLayout 导航及已有翻译标题。更新 frontend README、双语组件契约、测试及打包资源。

## 非目标与风险
不修改 API、持久化、云资源、普通智能体导航、聊天协议或鉴权。主要风险是目标切换后残留状态以及误向普通智能体开放 Tab，均加入测试。保留无关的锁文件改动。

## 设计审查
直接审查（review-spec 技能不可用）：已核对边界、权限、取消、失败语义及双语一致性，无阻塞项。[组件契约](../../../specs/mpa-collaborating-agents/README.zh.md)仅更新 UI 位置和生命周期；服务端契约不变。本设计替代[原设计](2026-10-20-collaborating-agents.zh.md)中的入口位置。

## 任务、测试与验收
- 先添加会失败的导航、权限、普通智能体及目标切换回归测试，再实现迁移。
- 执行定向测试、完整前端测试、构建、国际化及打包资源检查。
- 使用模拟数据进行浏览器正常、加载、空态、错误重试、取消、键盘/IME、窄屏检查；不写真实云资源。
- 同步双语文档及验证记录。验收：仅授权 MPA 在基本信息下看到新 Tab，旧入口移除，请求保持目标隔离。

## 验证
实现完成。直接代码审查未发现权限/分类限制、按需挂载、目标 key 或清理行为的阻塞问题。现有服务端鉴权不变。

- pass：先执行回归测试，出现 3 项预期失败；实现后定向 Vitest 通过（30 项）。
- pass：`npm --prefix frontend test`（1,389 项 Node 测试及 127 项 Vitest 测试）。
- pass：`npm --prefix frontend run build`（TypeScript 及两套生产构建）；仍有已有的大包体积警告。
- pass：`npm --prefix frontend run check:i18n`（2 种语言、22 个命名空间）。
- pass：`npm --prefix frontend run test:webui-assets`（114 个文件、351 条引用）。
- pass：真实浏览器配合隔离模拟 fetch 页面：基本信息下的新 Tab、内联加载/空态/不支持状态、刷新恢复、添加/取消表单、中文输入、Tab 焦点、普通智能体导航及 390px 布局。验证后移除临时页面及服务。
- pass：自动化测试验证离开页面、Runtime/地域切换、权限撤销时取消请求，以及普通智能体和非管理员不显示入口。
- not_run：真实输入法组合输入；已检查中文文本和键盘焦点，未改动组合输入行为。
- not_applicable：本次仅 UI 位置调整，Python/Ruff/Pyright 和云端集成不适用；本次未修改 Python 或云资源。已有协作后端改动早于本次任务。
- pass：已核对双语文档、引用路径及差异空白。

测试范围：feat/from-upstream-main-20261020 工作区中的位置调整，日期 2026-10-20。未授权提交或推送。

## 后续：输入框焦点外观（2026-10-20）

用户要求移除名称和密钥输入框内部额外的深色边框。浏览器复现确认内部有详情页施加的 `2px` 轮廓，外层已有组件焦点框。局部 CSS 覆盖仅移除协作输入组件内部的 focus-visible 轮廓，保留外层键盘焦点提示。不修改 API、状态或组件契约，属于纯视觉格式修正的例外。未新增镜像实现的行为测试。真实浏览器已核对名称/密码输入及 Tab 导航，对照输入框仍保留原轮廓。验证结果见下文。

验证：pass — `npm --prefix frontend test`（1,389 项 Node + 129 项 Vitest）、`npm --prefix frontend run build`、`npm --prefix frontend run test:webui-assets`（114 文件/351 引用）、浏览器焦点检查及 `git diff --check`。仍有已有的大包体积警告。未执行云资源操作、提交或推送。
