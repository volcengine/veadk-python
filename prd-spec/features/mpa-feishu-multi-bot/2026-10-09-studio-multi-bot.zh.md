# Studio 飞书多机器人管理

[English](2026-10-09-studio-multi-bot.md)

- 变更 ID：mpa-feishu-multi-bot
- 创建/修订：2026-10-09
- 状态：implemented；已记录验证限制
- 范围：仅 Studio；agentkit-mpa-agent 负责 Bot 持久化、Gateway 注册、会话路由和迁移。
- 契约：[MPA 消息渠道](../../../specs/mpa-channels/README.zh.md)、[MPA 定时任务](../../../specs/studio-mpa-cron-tasks/README.zh.md)。

## 背景与证据

本地 agentkit-mpa-agent 的 feat/feishu-bots 实现声明 multiBotChannels=[feishu] 和 accountScopedPermissions=true。GET channels 可返回多个由 appId 和 enabled 标识的飞书账号。诊断未带 appId 且存在歧义时返回 409。Studio 当前请求不区分账号的诊断/群权限，将所有 409 当作注册不确定。任务编辑器修改目标时会丢失 delivery.appId。Runtime 代理已支持 PATCH 及仅管理员可访问的渠道管理。

## 目标与非目标

支持独立飞书账号、扫码/手动新增绑定、启停/解绑、账号级诊断及群权限，并明确任务投递账号。保留旧单机器人 Runtime 以及企微/钉钉行为。不修改 MPA 持久化、Runtime 创建/镜像、聊天展示、网关鉴权，不发布服务。真实云写操作与真实消息投递不属于本地验证。

## 场景与需求

- FR-1：仅 capabilities.multiBotChannels 包含 feishu 时启用多机器人 UI。缺少声明时沿用旧行为；请求失败显示错误，不伪装为空列表。
- FR-2：GET channels 展示账号名称、appId、启停状态。仅一个账号可自动选择，多个账号须明确选择。新增使用既有扫码/手动接口，刷新后选中返回的 appId。
- FR-3：PATCH feishu/accounts/{appId} 的 enabled 和带 channel/appId 的根 DELETE 仅影响目标账号。解绑须确认。失败保留输入和现有账号；密钥不持久化或进入错误。
- FR-4：多机器人 Runtime 的诊断和群权限 GET/POST/DELETE 均携带选定 appId。组合身份避免同群冲突。区分账号歧义与 REGISTRATION_UNCERTAIN；仅注册冲突阻止绑定。
- FR-5：MPA 飞书任务创建/编辑/复制须选择 Bot，并与目标及未变更的话题元数据一起保留 delivery.appId。多个 Bot 禁止默认选择第一项。Web 投递不带 appId。停用/缺失账号阻止新增飞书写操作。旧任务缺 appId 且有歧义时须选择。未声明多机器人能力则保留旧任务行为。
- FR-6：切换账号/Runtime/渠道取消读取和轮询，迟到响应不能覆盖选择。单次写操作锁住账号切换；取消不表示撤销服务端写入。覆盖加载、空、错误、重试、键盘/IME 与窄窗口。

## 设计与边界

复用既有渠道面板用于绑定及账号详情，复用 Select/Button 和任务弹窗布局。增加能力控制的账号容器，先取列表再查指定账号详情。多机器人管理不探测无账号诊断。账号操作与新增绑定分开。React 内存仅保留非敏感账号摘要。既有可信 Runtime 代理注入渠道凭据。用户级定时任务保留当前所属身份，在既有 delivery 对象中携带 delivery.appId。任务账号选择使用已授权的渠道请求；无权限明确显示错误并阻止多机器人飞书提交，不回退全用户或其他凭据。

不新增依赖、数据库迁移、云资源或通用智能体行为。旧 Runtime 不接收新字段/接口。公开 API 为能力控制的兼容扩展。UI 沿用现有变量，不增加产品图标。

## 任务与影响文件

| 任务 | 需求 | 文件 / 验证 |
| --- | --- | --- |
| T-1 | FR-1..6 | 本双语 PRD 和两套组件契约；直接设计评审 |
| T-2 | FR-1..4,6 | adk/client.ts、ui/RuntimeChannels.tsx、新飞书账号容器、双语文案；先写失败前端回归测试 |
| T-3 | FR-5..6 | cronjobs/MpaTaskEditor.tsx、MpaCronTasks.tsx、双语文案；先写任务回归测试 |
| T-4 | FR-1..6 | 渠道/任务测试、前端 test/build、代理 Python 测试、浏览器夹具、frontend README 双语段落和 veadk/webui 产物 |

## 验收与验证

AC-1：两个账号可展示、独立选择/启停/解绑，新增 B 保留 A（FR-1..3、T-2）。
AC-2：A/B 同群的诊断及权限 CRUD 均区分账号；歧义读取不禁用注册（FR-4、T-2）。
AC-3：任务创建/编辑/复制保留 appId，切换 Web 清除，不可用 Bot 和迟到响应安全失败（FR-5..6、T-3）。
AC-4：旧飞书/企微/钉钉回归通过；正常、加载/错误/重试、IME/键盘和窄窗口浏览器夹具通过（FR-1,6、T-4）。
AC-5：执行 npm --prefix frontend test、npm --prefix frontend run build、渠道/任务定向 Vitest、uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/frontend/server/test_mpa_cron.py，记录真实结果。影响定时任务时执行既有覆盖率门禁；本次不涉及 harness-sidecar。

## 风险与上线

MPA 改动仍在本地且未发布；离线夹具不能证明真实双 Bot 投递。先部署兼容 Runtime 再启用多账号。群管理使用仅管理员可用的渠道接口，非管理员任务用户可能无法列出账号，必须显示权限错误，不能杜撰默认账号。刷新 UI 不能撤销在途 Gateway 操作。不自动回滚/删除/迁移。

## 评审与交付记录

用户于 2026-10-09 以“改改看”批准完整建议范围。review-spec 不可用，已直接评审需求、兼容、身份、权限边界、错误、取消、测试及双语等价，无设计阻塞。已读 frontend/SPEC.md 和 foundation Specification；引用的 frontend-design/ui-ux-pro-max 技能文件在仓库及已安装技能路径均不存在，沿用既有组件并直接 UI 评审，不另建竞争设计系统。

初始基线：基线 feat/from-main-20261009 的 f8c96211；设计前工作区干净；git pull --ff-only origin main 已最新。本设计不授权提交、云写操作或发布。

## 实现评审与验证（2026-10-09）

测试范围：`feat/from-main-20261009` 基于 `f8c96211` 的工作区改动。T-1 至 T-4 已实现。`frontend/README.md` 沿用既有混合双语约定，在同一文件同步两种语言，未新建第二份 README。组件契约与语言文件已同步更新，未修改 Python 生产代码。直接实现评审检查了账号身份、追加绑定、权限边界、迟到读取、取消、单次写操作和任务元数据。回归测试发现的扫码完成后账号选择竞态已修复。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| 实施前失败回归 | pass | 新渠道/任务测试在原实现上为 8 失败、50 通过。 |
| 定向前端回归 | pass | `cd frontend && npx vitest run --environment jsdom tests/runtimeChannels.test.tsx tests/feishuAccounts.test.ts tests/mpaTaskBots.test.tsx tests/mpaManagement.test.tsx tests/mpaCronTasks.test.tsx src/adk/channels.test.ts`：162 通过。 |
| 默认前端测试 | pass | `npm --prefix frontend test`：1,376 项 Node 测试和 47 项 Vitest 测试通过。 |
| MPA 任务覆盖率 | pass | `npm --prefix frontend run test:mpa-cron-coverage`：87 通过；语句 99.31%、分支 97.44%、函数 99.18%、行 99.74%，原阈值未改。 |
| TypeScript | pass | `cd frontend && npx tsc --noEmit`。 |
| 国际化 | pass | `npm --prefix frontend run check:i18n`。 |
| 构建 / 发布产物 | pass | `npm --prefix frontend run build`；`npm --prefix frontend run test:webui-assets`：校验 113 文件、350 内部引用。构建仍有既有大包警告。 |
| 后端代理 / 任务回归 | pass | `uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/frontend/server/test_mpa_cron.py`：18 通过，有一项 Starlette 弃用警告。既有代理转发 appId 与 PATCH，无需新增后端契约。 |
| 浏览器夹具流程 | pass | 真实组件搭配本地模拟 API：明确选择账号、独立启停、手动追加绑定及返回账号选择、指定账号群权限保存、任务机器人选择与载荷、加载/切换渠道、空列表/错误/重试、旧界面和键盘导航。390 px 时文档与视口等宽，诊断为单列；QA 中已修正窄容器内卡片布局。临时夹具验证后移除。 |
| 浏览器原生确认 / IME | blocked | 应用内浏览器未能完成原生解绑确认框，未操作真实账号。自动化测试覆盖确认与指定账号删除、IME 组合输入保护和取消；浏览器验证了中文输入，工具未实际操作系统 IME。 |
| 真实双 Bot 投递 | not_run | 需要另行部署兼容 MPA 镜像及明确的真实操作授权；模拟接口不能证明 Gateway 投递。 |
| Ruff / Pyright / harness-sidecar 覆盖率 | not_applicable | 未修改 Python 或 harness-sidecar 实现。 |
| 提交前同步 / pre-commit | not_run | 未要求提交；后续提交前仍须 fetch/rebase 和全文件 pre-commit。 |

初次未指定 jsdom 的命令因浏览器全局对象缺失失败，已更正，不属于运行时故障。AC-1 至 AC-3 由回归测试和适用夹具流程覆盖；AC-4 的浏览器覆盖受上述原生工具限制；AC-5 门禁通过。实现未修改通用智能体聊天展示、云资源或部署镜像。正式上线仍需兼容 Runtime 部署及真实冒烟验证。本次未提交、推送或部署。
