# Studio MPA Runtime 定时任务

[English](README.md)

日期：2026-09-15。变更：studio-mpa-cron-tasks。状态：设计已审阅；当前用户请求已授权实现。

## 依据和范围
Studio 通过 /web/cronjobs 查询按所有者隔离的 TOS 任务。MPA 独立提供 GET /api/v1/esa-cron-tasks，按其验证后的用户身份过滤。为当前选择的 Runtime 新增只读来源页签；不合并、迁移、创建、编辑、删除或执行任务。

## 需求和设计
FR-1：将选中云 Runtime 的 ID、名称和地域从 App 传到 CronJobs，明确显示目标。未选择时不请求，不回退其他 Runtime。
FR-2：复用 Runtime 代理和 API Key 处理，转发遮罩输入框中可选的 X-Jwt-Token。仅保存在组件内存，切换 Runtime/地域或卸载时清除。不推导或伪造身份、不持久化凭据、不降低鉴权。
FR-3：展示名称、启停、计划、下次执行和最近结果。每页 20 条且包含停用任务，提供上一页、下一页和刷新。区分加载、空数据、不支持接口、鉴权和其他失败，失败不展示为空列表。
FR-4：变化和卸载时取消请求并忽略迟到响应。立即清除旧目标数据，同页刷新时保留可读内容。现有 Studio 任务行为保持不变。

## 文件和任务
T-1：新增类型化客户端和 Runtime 面板；接入 App/CronJobs，增加双语文案。
T-2：先写 HTTP/组件回归测试，覆盖分页、错误、取消和切换目标。
T-3：执行 npm test、构建、国际化检查和超过 95% 的增量覆盖率；检查浏览器布局、产物和密钥；提交推送并更新本地 Studio 产物。

## 审阅和验收
设计审阅：现有组件和代理足够，无新增依赖和后端变更。双语内容等价。Studio 任务和 MPA 任务保持分离。用户已明确授权模块，当前会话授权提交推送。仓库引用的 ui-ux-pro-max 技能不可用，直接遵循 frontend/SPEC.md 和可用 frontend-design 指导。
AC-1：选中目标与真实请求路径一致，分页与状态通过测试。AC-2：无旧目标数据或持久化凭据。AC-3：UI 和构建通过；真实数据需要有效 MPA JWT，独立报告模拟与真实验证。

## 验证 — 2026-09-15

通过：1095 项前端测试；34 项独立 HTTP/组件测试；新增适配器和面板语句、分支、函数、行覆盖率均为 100%；TypeScript 和两次 Vite 构建；国际化检查（2 个语言、17 个命名空间）；打包资源检查（102 个文件、246 条引用）。Pre-commit 的 Ruff 和密钥扫描通过。浏览器验证了未选目标状态、选择传递，以及选中 Runtime 的真实代理请求返回 401 并显示需要 JWT 的提示。现有 Studio 页签保持独立。本地 Studio 产物已更新，旧产物备份在仓库之外。带有效身份的真实任务数据和窄视口截图未验证；真实数据需要有效用户 JWT。未修改任何线上定时任务。

## 风险和限制
按 Runtime 选择不代表可看所有用户任务。缺少 JWT 属于鉴权状态，不是没有任务。不修改调度器或 MPA 业务逻辑。包含构建产物以交付本地 Studio。交付前在此记录验证结果。

## 自动凭证修订 — 2026-09-15
当前用户授权将手动 JWT 输入替换为服务端调用 TOP GetMpaInstanceToken（2026-03-01）。从已授权的所选 Runtime 读取 MPA_AGENT_ID、MPA_SPACE_ID/CLAW_SPACE_ID、MPA_IS_DEBUG_RUNTIME 和 ARKCLAW_TOP_SERVICE。使用可信企业身份 user_pool_user_uid；本地管理员在服务端配置 VEADK_STUDIO_MPA_USER_UID。禁止使用浏览器传入的身份申请凭证。JWT 由 TOP 签发。转发 Authorization 和 X-Jwt-Token 前校验其 HTTPS 地址与所选 Runtime 相同。每次列表请求获取新凭证，不缓存、持久化或向浏览器返回凭证。保持只读范围，参照 mono SharedAgent/Cron 增加任务提示词详情、执行次数与成功率。配置缺失和 TOP 失败需明确展示。测试覆盖身份、地址不匹配、上游错误、凭证隔离和取消，增量覆盖率超过 95%。本修订替代旧手动 JWT 契约；此前验证结果仅针对旧版本。

## 修订验证 — 2026-09-15

通过：43 个前端契约/组件测试、31 个 Python 测试；新增模块范围的语句和分支覆盖率均为 100%。全部 1095 个前端回归测试、TypeScript/Vite 构建、国际化与 102 个打包资源检查通过。新增 Python 模块 Pyright 通过。CLI 文件有 34 个原有 Pyright 问题，基线对比确认诊断信息相同，没有新增问题。本地 Studio 已更新并重启；浏览器确认没有 JWT 输入框，所选 Runtime 正确，缺少企业用户 UID 时给出明确提示。使用现有 AK/SK 单独进行的只读 TOP 探测返回 403 AccessDenied，缺少 arkclaw:GetMpaInstanceToken 权限。真实任务数据仍需补齐该权限及企业 UserPoolUserUid。当前环境原有 Studio TOS 任务来源也加载失败，本次没有修改该来源。窄屏验证未执行。
