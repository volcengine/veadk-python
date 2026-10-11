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

## 直接访问 Runtime 修订（2026-09-15）
用户已关闭 Runtime 的 JWT 校验，并授权移除 TOP 凭证申请。替代此前的凭证契约：保留所选 Runtime 的权限检查及网关鉴权，使用当前 Studio 身份的 owner_id 作为 x-user-id；从 Runtime 配置读取 x-space-id 和 x-mpa-id，缺失时沿用 MPA 的本地默认值；不再申请或转发 X-Jwt-Token。移除企业 UID 配置及凭证相关页面提示。任务仍按用户筛选。本次不修改 Runtime 配置或业务逻辑。验证请求头、不调用 TOP、分页、上游异常与取消；增量覆盖率须超过 95%。

## 最终全量读取契约 — 2026-09-15
用户明确授权在 Runtime 关闭 JWT 时开放全量用户读取，MPA 提交 833c6bc 已实现此行为。Studio 只携带网关鉴权，不发送 JWT、x-user-id、x-space-id 或 x-mpa-id，也不再要求业务用户身份。本节替代之前按用户筛选的直接访问修订。保留 Runtime 权限检查、只读范围、分页与现有错误处理。

## 最终部署与验证 — 2026-09-15
Runtime r-yetmv58y68itpb2txuvg 已发布 V9，状态 Ready，镜像标签 20260915-833c6bc-cron-all-read，digest 为 sha256:11d48baadd978f302af899b2bea5fa9b61f6b11bdca1fa9292d85526a5be02ca。配置对比确认除镜像、版本、状态、时间戳外没有变化。公网 GET 仅带网关鉴权，Studio BFF 同样返回 HTTP 200、total=0。浏览器确认目标 Runtime 正确，成功显示空列表；未创建测试任务。任务查看保留聊天/会话加载失败时选中的 Runtime，并在成功切换 Agent 时重置。1096 个前端回归、39 个专项前端用例、8 个 Python 用例通过；专项前后端覆盖率均为 100%。Python 模块 Pyright、构建、国际化、资源检查及 pre-commit 通过。CLI 原有 Pyright 问题和 Studio TOS 来源错误不在本次范围内。
