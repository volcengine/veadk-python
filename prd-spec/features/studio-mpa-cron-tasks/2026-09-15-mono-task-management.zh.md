# 对齐 mono 的 Runtime 定时任务管理

[English](2026-09-15-mono-task-management.md)

变更 ID：studio-mpa-cron-management。创建/修订日期：2026-09-15。状态：implemented。
组件：[Runtime 定时任务查看器](../../../specs/studio-mpa-cron-tasks/README.zh.md)。

## 证据和目标

用户要求 Studio Runtime 定时任务页面参照所附截图及 mono 实现。Studio 当前通过 `frontend/server/mpa_cron.py` 仅提供列表。mono 的 `SharedAgent/Cron/index.tsx` 使用 `CronStandalonePanel`；`packages/claw-cron/src/components/` 包含列表、日历、表单、详情和操作。其 workspace 依赖使其无法直接作为独立组件导入 Studio。因此使用 Studio 现有控件复用其交互行为和字段映射，不修改 mono。

MPA 提交 `91fd6a3` 已恢复按用户读取。现有 `/api/v1/esa-cron-tasks` 操作即使关闭 JWT 也要求用户身份。此次不恢复 JWT 获取或全用户兜底。经用户确认，身份来自当前认证的 Studio 用户。

## 需求和场景

- FR-1：选择 Runtime 后展示名称/地域及列表/日历切换。以列表为主体，列为任务、上次执行、执行周期、带筛选的上次执行状态、执行 Agent 和操作。沿用截图的白色/中性底色、克制蓝色链接、绿色成功、灰色待执行和红色失败，使用现有系统字体及 Studio 变量。统计摘要放表格右上方，创建入口放页面右上角；不使用大统计卡片或把原始周期 JSON 作为主展示。
- FR-2：创建、编辑、复制、删除、启停和立即执行调用已有 MPA 接口。复制先打开预填表单，保存后才创建；删除需要确认。任务名称打开详情及分页执行记录。写入失败保留表单内容并给出可操作错误。
- FR-3：日历参照 mono 的周期语义和时区处理，支持单次与循环任务。加载所需的全部服务端分页，不能把单页冒充完整日历。上次执行列使用实际执行时间，不用 nextRunAt 替代。
- FR-4：端点及网关密钥由服务端按所选 Runtime 解析，只增加明确允许的任务路由。凭证不进入浏览器。JWT 开启时保留鉴权错误，不恢复 TOP/JWT 流程，不扩大 MPA 权限。
- FR-5：更新保留 expectedVersion；同一次创建/执行操作的重试保留 clientToken。防重复提交，版本冲突提示刷新。切换 Runtime 取消读取并丢弃过期响应；取消写请求不能宣称撤销了已发生的操作。
- FR-6：区分加载、空数据、鉴权、校验、接口缺失、网络及版本冲突状态。列表/日历、菜单、弹窗、表单支持键盘、Escape、焦点恢复、IME 和窄窗口。不为验证 UI 而擅自创建、执行或删除云端任务。

## 契约影响和实施

T-1 / FR-4：明确身份来源，更新双语组件规范。扩展 `frontend/server/mpa_cron.py` 和 CLI 路由装配，在既有 Runtime 授权后支持列表/创建/更新/删除/执行/历史；不开放任意上游 URL 或通用代理。

T-2 / FR-2、FR-5：扩展 `frontend/src/adk/mpaCronTasks.ts` 和客户端封装，补齐任务/执行响应、周期字段、版本和写入请求类型。编辑时保留未知投递配置。不把 mono TOP 响应大小写或无分页协议直接套入 MPA REST。

T-3 / FR-1、FR-3、FR-6：按需拆分现有 Runtime 页面为列表/操作、日历、编辑器和详情组件。复用 Studio 控件及变量，逐项对照 mono。统计文案依据服务端实际时间窗口；没有证据不能标记为近七日。

T-4：补回归/交互和代理契约覆盖，更新双语文档及 frontend README，重新生成 webui，安装到本地 Studio 并浏览器验证。既有 Studio/TOS 定时任务和会话行为保持不变。

## 验收和验证

- AC-1 / T-3：列表对齐截图且日历可用，状态/时间/Agent 准确，响应式布局和键盘操作正常。
- AC-2 / T-1、T-2：每个操作以一致用户身份、网关授权及正确的并发控制/幂等字段调用对应 MPA 路由。负向验证覆盖凭证泄漏、任意代理及跨 Runtime 过期数据。
- AC-3 / T-4：可执行增量覆盖率超过 95%；执行 `npm --prefix frontend test`、`npm --prefix frontend run test:mpa-cron-coverage`、`npm --prefix frontend run build`、`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`、目标 Python 测试、Ruff、Pyright 和 pre-commit。分别记录模拟与真实验证结果。

## 审核和交付记录

源码核对：pass，2026-09-15。双语设计审核：范围、端点归属、错误隔离及可测性 pass；身份来源已确定为认证的 Studio 用户。用户设计确认：2026-09-15 用户已确认实施，使用认证的 Studio 用户。生产代码和测试已实现，验证结果见下文。本次不包含部署。此前 GitHub SSH 推送失败可能仍阻碍发布；交付时重新检查并如实报告。

## 最终验证 — 2026-09-15

用户已确认实施，身份使用认证的 Studio 用户。实现审核：路由白名单、凭证、乐观版本、重试令牌、取消、时区/夏令时及双语一致性 pass。

- 前端组件/API 测试：71 项通过；行覆盖率 99.71%，分支覆盖率 97.19%。
- Studio 前端回归：1096 项通过。
- 服务端代理测试：12 项通过，行覆盖率 100%。
- TypeScript/Vite 生产构建、i18n（2 种语言 / 17 个命名空间）、打包资源（102 文件 / 246 引用）、Ruff 和 pre-commit 密钥扫描：pass。
- 服务端模块 Pyright 无新增诊断。完整 CLI Pyright 仍受此前相同的 34 项既存诊断阻碍；本次仅修改该文件的一行路由回调装配。
- 真实浏览器模拟数据验收：检查列表/操作、日历、编辑器、Escape/焦点恢复及 760px 窄窗口，pass。模拟数据文件不随产品发布。
- 已安装并重启本地 Studio。真实目标 Runtime r-yetmv58y68itpb2txuvg 列表 HTTP 200，1 条任务；详情展示 1 条成功执行记录。未进行真实任务写入。Runtime 原已为 Ready/V10，镜像 20260915-073a536，本次未部署 Runtime。
- 验证前已同步 feat/mpa-agent-oneclick-provision 基线。Git 发布结果在交付消息中报告。
