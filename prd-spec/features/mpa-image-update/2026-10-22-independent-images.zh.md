# MPA 独立镜像更新

[English](2026-10-22-independent-images.md)

变更 ID：mpa-image-update。创建/修订：2026-10-22。状态：implemented。
组件：[MPA 镜像管理](../../../specs/mpa-image-update/README.zh.md)。

## 背景和证据

AgentWorkspace.tsx 当前对 MPA 隐藏通用更新流程。studio_profile.py 已定义国内/海外公共 mpa_agent 与 mpa_codex_worker 仓库。已验证四个仓库均支持匿名 OCI 标签读取；标签接口仅提供名称，不提供发布时间。UpdateRuntime 支持 ArtifactUrl/ArtifactType 和 ReleaseEnable；UpdateTool 支持 ImageUrl。参见 [UpdateRuntime](https://docs.volcengine.com/docs/86681/1923461) 和 [UpdateTool](https://docs.volcengine.com/docs/86681/1913799)。

## 目标、非目标和场景

FR-1：MPA 导航依次为基本信息、镜像更新、协作 Agent，遵循现有管理权限。普通 Agent 导航不变。
FR-2：Runtime 与 Worker 分别具有当前元数据、版本加载、选择、确认、提交、错误和结果核对状态。更新任何一项只发送一次对应云更新，另一项保持不变。
FR-3：只从固定供应商公共仓库选择标签，显示完整目标地址。分页保持仓库顺序，不声称按最新排序；搜索明确只过滤已加载版本并提供继续加载。刷新清空版本选择。
FR-4：更新前重新验证授权 Runtime 身份、MPA 类型、部署锁/状态、Worker 绑定/归属/独占引用、乐观修订和标签存在性。拒绝歧义、任意主机/路径/标签和多余请求字段。
FR-5：提交成功不等于应用健康。Runtime 请求立即发布；Worker 更新模板，已有沙箱会话可能保留旧镜像。分别显示配置镜像和云状态。更新响应丢失时阻止重复提交，直至读取核对；绝不静默重试写入。
FR-6：明确处理加载、空、无权限、错误、重试、过期选择、取消/导航、迟到响应、键盘/输入法和窄窗口。

对于有权限的 MPA，选择并确认 Runtime 版本只更新 Runtime；选择 Worker 版本只更新独占归属模板。预览过期、Worker 共享、部署进行中或仓库读取失败时不写云。离开页面中止浏览器读取；关闭弹窗不会回滚已经提交的云操作。

## 设计和影响

使用领域 React 组件、类型化 API 客户端和独立 Studio 后端模块。复用 Select、Button、FormLabel、InputWithTailIcon、TextShimmer、ModalButton。以现有 Agent 详情导航为布局锚点。组件契约维护接口、校验、持久化、失败/并发语义和限制。不改变生成的 Agent 源码、Python SDK 签名、依赖、会话协议、Worker 绑定或云凭据。

复用现有账号/区域部署 advisory lock 和注册记录验证更新归属并持久化镜像更新意图。Runtime、Worker 意图分别保存。提交云操作前记录意图；只有读取到目标镜像和可用资源状态时才核对完成。结果不确定时保留意图并阻止冲突管理操作；明确云拒绝时清除意图。不改写创建请求哈希。托管部署和删除必须拒绝未解决镜像意图。读取失败不能转为空列表或权限成功。

标签名称可变。更新前立即重新验证标签存在性，以文档支持的标签语法提交。未验证 AgentKit 对摘要引用的支持，因此不实现 digest 固定；界面不声称镜像身份不可变。显式刷新平台状态和仓库；测试不自动执行真实云更新或写入。

## 任务和影响文件

T-1 / FR-4,5：frontend/server/mpa_images.py 和 cli_frontend.py 实现版本目录、归属、修订、意图核对及路由；托管部署/删除增加保护。
T-2 / FR-1,2,3,6：类型客户端、MpaImageUpdates 组件/样式、AgentWorkspace 导航、双语文案。
T-3 / FR-1..6：先写失败的后端/UI 回归，断言独立写入，覆盖恶意仓库和归属边界；模拟浏览器流程。
T-4：同步文档、生成 Web 产物和验证记录。

## 验证和验收

AC-1：MPA 第二个页签；普通导航不变；无权限不能访问镜像页。
AC-2：两个供应商的目录正确映射组件；分页/搜索/刷新及空/错/重试正常。
AC-3：独立 Runtime/Worker 更新保留全部无关配置；过期/共享/归属不明/忙碌资源零写入。
AC-4：不确定结果不能显示成功或自动重试；说明旧沙箱行为；迟到读取不能覆盖新 Agent。
AC-5：如实记录目标 Python 测试、Ruff、Pyright、npm --prefix frontend test、npm --prefix frontend run build、check:i18n、TypeScript、构建资源校验、模拟浏览器键盘/窄窗口/错误/取消、双语/链接校验、diff 空白和范围密钥扫描。不授权真实云写入。

## 风险和恢复

云状态收敛有延迟；标签可变，Update 成功不能证明应用健康。未解决意图需要读取核对或运维调查，不能盲目重试。8000 端口 Studio 在之前重启后缺少原进程云凭据，这是已记录的先前代理操作引入的运行问题。不得再次重启或选择其他 CLI 身份；依赖账号的验证仍需恢复原启动环境。

## 评审和批准

2026-10-22：用户批准功能并明确要求独立更新。未安装 review-spec 技能；已直接检查双语等价、可行性、固定主机安全、权限、归属、锁、不确定结果、兼容和可测试性，无设计阻塞。实现和本地验证完成；未授权提交/推送或云更新。

## 交付验证 — 2026-10-22

验证范围：feat/from-upstream-main-20261020 工作树镜像管理改动（基础 HEAD 9ab0ef2d），保留既有本地修改。T-1 至 T-4 和 AC-1 至 AC-5 的本地实现已完成。

- pass：后端/UI 尚不存在时初始回归收集失败；第二页签加入前导航回归失败。
- pass：`uv run --extra dev pytest tests/cli/test_mpa_images.py tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed -q` 共 1345 项通过。后续安全/超时修订：受影响路由/删除测试 189 项通过；最终镜像契约文件 35 项通过。
- pass：`npm --prefix frontend test`，1389 项 Node 测试、202 项 Vitest 用例通过。
- pass：`npm --prefix frontend run build -- --emptyOutDir false`，TypeScript 和两项生产构建通过。保留旧哈希资源，避免破坏运行中服务缓存的 HTML；仍有既有包体积提示。
- pass：`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`，2 个语言/23 个命名空间、177 个构建文件/695 个引用通过。
- pass：使用仓库 pre-commit 环境对修改 Python 执行 Ruff check/format；新模块/测试和托管文件的 Pyright 零诊断。CLI/代理测试文件仍有 57 项既有诊断，均未指向新增代码块。
- pass：真实浏览器模拟验证键盘选择、取消/焦点返回、只更新 Runtime 且 Worker 不变、分页/搜索、错误/重试、空目录、未知结果禁止重复提交、390px 页面/弹窗（342px/310px 内容宽度等于滚动宽度）。预览：`/tmp/veadk-mpa-image-updates.png`。临时测试页面和 Vite 已清理。
- pass：四个固定公共仓库均匿名真实只读验证分页及 latest manifest；目录读取未使用云凭据。
- pass：双语契约/标识符、相对链接、diff 空白和范围 Gitleaks（1.79 MB，无泄漏）。
- blocked：账号连接的 Studio 验证/启用，因先前重启遗失凭据环境。本次没有重启 Studio，启用前需恢复原启动环境。
- not_run：真实 Runtime/Worker 写入、发布/应用健康及新沙箱验证，未授权云变更。本次范围为 Studio/托管镜像管理，运行受影响托管集成覆盖，未运行全仓库并行回归。全文件 pre-commit 留待另行授权提交时运行。本次未提交或推送。
