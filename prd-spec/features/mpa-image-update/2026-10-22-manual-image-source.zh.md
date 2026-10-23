# 手填镜像地址或公共版本

[English](2026-10-22-manual-image-source.md)

变更 ID：mpa-image-source-choice。创建/修订：2026-10-22。状态：implemented。
前序：[独立镜像更新](2026-10-22-independent-images.zh.md)。
组件：[MPA 镜像管理](../../../specs/mpa-image-update/README.zh.md)，拟扩展 CON-IMAGE-SOURCE。

## 背景和证据

MpaImageUpdates 当前在公共版本选择器上方显示搜索输入框。ImageManager 仅接受 tag 和 revision，总是从固定仓库构造地址。只修改标签不能启用手填地址。用户要求将搜索框换为手填镜像地址，与公共版本选择二选一。Runtime 与 Worker 仍须独立。

## 目标、非目标和场景

FR-1：将已加载版本搜索换为手填完整镜像地址。下方保留公共版本选择器并标明另一种方式。输入地址清空公共标签；选择公共标签清空手填地址。清空一项不会自动选择另一项。确认框准确显示最终目标。
FR-2：允许显式手填其他仓库地址。接受有长度限制的 host/namespace/repo:tag 引用，可包含数字仓库端口；不接受协议、凭据、查询、片段、空白和摘要。格式错误在输入旁显示。不收集仓库凭据。镜像兼容性和拉取权限由 AgentKit 验证。
FR-3：公共版本选择仍使用固定国内/海外仓库、分页、manifest 检查和刷新。公共目录加载/错误/空状态不能阻止有效手填地址；刷新公共版本不能清除手填内容。移除搜索文案和行为。
FR-4：POST 在 tag、image 中严格二选一，均携带 revision，兼容现有 tag 调用。写入前拒绝同时提供、均未提供或非法地址。手填地址绝不导致 Studio 请求任意仓库主机。Runtime 手填自定义镜像使用 ArtifactType=image，对应固定公共仓库仍使用 public_image；Worker 仅发送 ImageUrl。现有归属、修订、意图、不确定结果和独立更新保护均保留。
FR-5：保留取消、迟到结果隔离、防重复提交、键盘/输入法和窄窗口行为。选择来源不能触发更新，仍需显式确认。

已手填地址而公共目录失败时，有权限用户仍可确认更新所选组件。先选择公共版本再输入地址会清空公共版本；再次选择公共版本则清空手填内容。非法或双来源请求不写云。更新一项不影响另一项表单或资源。

## 设计和契约影响

复用 InputWithTailIcon、Select、FormLabel 和现有确认框，不新增模式导航或重复表单。最终来源遵循最近一次显式输入，并清除非活动来源，不使用隐藏优先级。前端领域 API 模块统一校验和最终目标计算，Python 独立执行同样校验。手填请求跳过目录读取及 manifest 验证，由 AgentKit 验证自身镜像拉取。不新增 Studio 任意 URL 请求、鉴权变更、依赖或生成代码。

现有 POST 联合类型扩展为 {image, revision}，保留 {tag, revision} 兼容。目标校验在持久化和提交前完成。两个来源复用部署锁、乐观重查及组件独立的持久化意图。不改变发布/会话语义和权限策略。手填镜像不自动认定与 MPA Runtime/Worker 兼容；用户显式选择组件并确认完整地址。

## 任务和影响文件

T-1 / FR-1,3,5：修改 MpaImageUpdates.tsx、CSS 和双语 mpaImages.json，移除已加载版本过滤，实现来源互斥且不联动两个组件。
T-2 / FR-2,4：在 frontend/src/adk/mpaImages.ts 增加类型化目标校验，在 frontend/server/mpa_images.py 扩展请求解析和镜像提交，现有客户端传输不变。
T-3 / FR-1..5：先写失败的前后端回归，覆盖双向互斥、两个组件手填更新、目录独立、非法/歧义输入、自定义/公共 ArtifactType、过期/不确定/取消/输入法边界和原标签路径兼容。
T-4：同步组件双语契约和 frontend/README.md；保留运行中 Studio 缓存资源引用完成构建，记录检查和浏览器证据。

## 验证和验收

AC-1：两个组件均显示手填地址和公共版本二选一，无搜索控件。切换来源只清除同一组件的另一个输入。
AC-2：确认框和 API 目标与所选来源一致；目录加载/失败时可手填，Studio 不请求任意仓库。
AC-3：后端拒绝非法/双来源/无来源，保留原归属/并发保护；仅更新所选云组件。
AC-4：如实记录 `uv run --extra dev pytest tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py`、修改 Python 的 Ruff/Pyright、`npm --prefix frontend test`、`npm --prefix frontend run build -- --emptyOutDir false`、i18n/资源检查、模拟浏览器键盘/输入法/取消/错误/390px、双语链接/标识符、空白和范围密钥扫描。不授权真实云写入。

## 风险和待确认决策

已确认手填允许其他仓库，且不由 Studio 请求该主机。公共版本目录仍只使用既有固定公共仓库。私有镜像拉取依赖 AgentKit 现有权限，不在 Studio 新增凭据。标签可变，仍不支持摘要语法。已有沙箱会话可能保留旧镜像。8000 端口的凭据/启动问题仍未解决，本次不重启服务或改选身份。

## 评审和批准

2026-10-22：已检查现有 UI、解析器、云请求和测试。未安装 review-spec，已直接评审双语等价、API 兼容、任意主机请求隔离、来源优先级、目录独立、归属和不确定结果。用户已明确批准完整方案，包括其他仓库、双向互斥输入及 Runtime/Worker 独立更新。设计评审已通过，T-1 至 T-4、AC-1 至 AC-4 的本地实现已完成，验证如下。未授权提交、推送或真实云写入。

## 验证和交付 — 2026-10-22

验证范围：feat/from-upstream-main-20261020 工作树中本次手填来源增量，保留先前独立更新功能和无关本地改动。

- pass：实现前回归复现手填不受支持（9 个后端失败）和手填/互斥控件缺失（7 个 UI 失败）。
- pass：`uv run --extra dev pytest tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed/test_deletion.py -q` 共 215 项通过。两种来源保留归属/过期/不确定状态保护；手填写入不请求仓库。
- pass：`npm --prefix frontend test`，1389 项 Node 测试、223 项 Vitest 用例。覆盖前后端一致格式样例、双向互斥、目录加载/失败独立性、自定义请求、输入法 Enter、迟到响应/取消。
- pass：`npm --prefix frontend run build -- --emptyOutDir false`，两个生产包及 TypeScript 通过，仍有既有包体积提示。
- pass：`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`，2 个语言/23 个命名空间，177 个文件/695 个引用。
- pass：仓库 pre-commit 对 frontend/server/mpa_images.py 和 tests/cli/test_mpa_images.py 执行 Ruff check/format，两个文件 Pyright 零诊断。前序记录的未改动 CLI/代理测试基线诊断不属于本轮增量。
- pass：真实浏览器模拟验证双向来源切换、公共版本键盘选择、目录错误下手填确认/提交、Worker 选择及资源独立保留、非法手填格式、取消/焦点返回及 390px 长地址布局。页面/弹窗宽度等于滚动宽度（342px/310px）。预览：`/tmp/veadk-mpa-manual-image.png`。测试页面与 Vite 已清理。
- pass：双语需求/契约标识符与相对链接、diff 空白及使用仓库配置的范围密钥扫描。
- blocked：启用和账号连接 Studio 验证仍需恢复原云凭据启动环境。本次未重启 8000 服务。
- not_run：未授权云写入测试，因此未执行真实云写入/私有仓库拉取、镜像兼容、发布/应用健康和新沙箱验证。全文件 pre-commit/分支同步留待授权提交时执行，本次未提交或推送。
