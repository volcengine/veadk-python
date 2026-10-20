# 新增飞书群权限沿用服务端默认策略

[English](2026-10-12-server-default-scope.md)

变更：studio-channel-server-default-scope。日期：2026-10-12。状态：implemented。
契约：[mpa-channels](../../../specs/mpa-channels/README.zh.md)，CON-17。

## 依据和范围
RuntimeChannels 默认选中 group_sender，并在每次群权限 POST 中提交，导致管理员仅想允许一个群时也覆盖 Runtime 默认值。用户已明确授权删除隔离选择器、不提交该字段、保留已有群。本次只改 Studio 调用方；Runtime API 类型、可选策略能力和后端优先级保持不变。

## 需求和设计
FR-1：新增群表单不含隔离选择器或隐藏策略状态。FR-2：POST 仅包含 channel、去空白 chatId，以及选择账号时的 appId；不包含 groupSessionScope，包括 null 或空字符串。FR-3：已有群继续显示服务端返回的策略；渲染、刷新或新增其他群不会自动更新已有群。FR-4：保留加载、禁用、IME、取消、失败重试及多机器人目标选择行为。

仅删除选择器及其状态、选项、导入和提交属性。不强制 group、不清空持久策略、不改数据结构或迁移、不加依赖、不触碰执行和流式。API 调用方仍可显式使用可选字段。最终默认值由 Runtime 决定，Studio 不承诺所有部署都默认 group。再次添加已有 ID 仍按 Runtime 原 upsert 行为处理，不虚构迁移保证。

## 任务和验收
| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1/FR-2 | T-1：先回归再最小修改 RuntimeChannels | AC-1：没有选择器，单/多机器人 POST 精确请求体均无策略字段 | runtimeChannels.test.tsx |
| FR-3 | T-2：保留返回策略展示 | AC-2：已有 group_sender/话题策略正常显示且无写入 | runtimeChannels.test.tsx |
| FR-4 | T-3：执行既有交互测试及本地浏览器检查 | AC-3：正常/失败/重试/键盘/窄窗口及账号身份保留 | npm test、定向 Vitest、npm run build、浏览器 |

## 评审和授权
直接设计评审：现有可选接口可实现，无后端或迁移变化；所选账号鉴权和取消逻辑不变；既有列表回退显示不变。无阻塞项。授权依据为本聊天用户明确要求，无需对相同最小改动重复确认。仓库引用的 frontend-design/ui-ux-pro-max 在仓库和本地技能目录搜索后仍不存在；本次删除控件遵循 frontend/SPEC.md 及组件基础规范，不新增视觉设计。VeADK 本地/全局 review-spec 缺失，在此直接记录等价检查，不套用其他仓库的报告工作流。

## 验证和交付
2026-10-12 在 HEAD 812faadf 加本次工作区差异上验证。生产代码仅从 RuntimeChannels 删除 31 行，中英文群说明改为只描述准入。沿用原 Button、输入框、表单样式和返回策略标签，不新增样式或依赖；frontend/README.md 和 CON-17 已同步两种语言。

- pass：改前定向回归 2 failed / 3 passed / 61 skipped，复现选择器及多机器人请求中多出的策略属性。
- pass：在 frontend 运行 `./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx tests/feishuAccounts.test.tsx` 对应定向命令，runtimeChannels.test.tsx 66 passed；未匹配独立 feishuAccounts 测试文件，多机器人测试位于 RuntimeChannels。
- pass：`npm --prefix frontend test`：Node 1377 passed，Vitest 67 passed。保留既有 i18next/localStorage 告警，无失败测试。
- pass：`npm --prefix frontend run check:i18n`：2 种语言、21 个命名空间一致。
- pass：最终 `npm --prefix frontend run build`：TypeScript 及两次 Vite 构建成功，veadk/webui 生成物已更新；资源分组变化属于构建输出，并未编辑其他业务源码。
- pass：`npm --prefix frontend run test:webui-assets`：113 个文件、350 个内部引用校验通过。
- pass：真实浏览器挂载实际组件、使用隔离 HTTP fixture，检查空输入禁用、无隔离控件、执行中控件禁用、失败保留群 ID、Enter 重试、成功清空输入、原 group_sender 标签保留；390px 视口流程可用。记录三次实际 POST 均仅含 channel/chatId，未写入已有群。多机器人 appId 请求回归由 Vitest 覆盖，此浏览器 fixture 为单机器人。验证后恢复视口、移除临时文件并停止 fixture 进程。
- pass：仓库 pre-commit 的 gitleaks 扫描变更源码/测试/文档；`git diff --check`。
- not_applicable：Python 测试/Ruff/Pyright，无 Python 改动。
- not_run：真实云/飞书 E2E、部署、远端 CI、完整 pre-commit/all-files；未授权发布，保留无关工作区改动。

本地日志和浏览器证据为 `/tmp/mpa-studio-default-scope-*`，包含表单截图；未使用凭据或真实生产数据。已有 package-lock.json 的 512 行删除保持原样，没有修改。未提交/推送/部署。剩余风险：不同部署的 Runtime Bot 级继承可能不同，省略字段就是将默认选择交给它；再次添加已有 ID 仍按原 Runtime upsert 语义，不增加新保留保证。
