# 消息渠道工作区

[English](2026-09-15-message-channel-workspace.md)

- Change ID：message-channel-workspace
- 日期：2026-09-15
- 状态：implemented（UI 范围）
- 契约：[MPA 渠道](../../../specs/mpa-channels/README.zh.md)

## 背景与范围
当前未提交的 RuntimeChannels 面板嵌在 AgentWorkspace 集成页顶部，诊断以平铺定义列表展示。用户要求新增与集成、版本平级的消息渠道，并分为飞书、企业微信、钉钉，随后授权实施（企业微信，帮我改）。

## 需求与场景
- FR-1：已有 Runtime 的消息渠道打开独立工作区，与集成、版本平级；集成不再展示渠道管理。
- FR-2：工作区区分飞书、企业微信、钉钉。保留可用的飞书绑定与权限操作；其他渠道不得暗示配置成功或调用飞书接口，本次 UI 范围内企业微信与钉钉明确标示为暂未开放。
- FR-3：绑定、渠道诊断、允许群分别形成清晰区域。Gateway 中文改为消息网关。独立展示网关配置、入站路由配置和观测到的回复投递；配置不等于投递成功。
- FR-4：保留轮询清理、重试、错误时表单值和权限校验。支持键盘、输入法、长名称和窄窗口。

## 设计与契约影响
AgentSection 与共享栏目列表增加 channels，在现有飞书管理器外增加渠道选择。复用 UI tokens、Button、Select，不增加依赖或服务端修改。未开放渠道明确显示暂未开放，且没有配置操作。MPA 渠道 HTTP、身份、存储和注册契约不变；双语组件契约增加导航与开放状态的展示义务。

## 任务与影响文件
- T-1 / FR-1：AgentWorkspace.tsx、双语 ui.json，独立导航。
- T-2 / FR-2–4：RuntimeChannels.tsx 与 CSS，渠道切换及结构化状态、绑定、群列表。
- T-3：runtimeChannels.test.tsx、agentWorkspace.test.mjs，回归、浏览器检查、构建与生成资源。
- T-4：同步双语设计、契约及 frontend README。

## 验收与验证
- AC-1：消息渠道与其他栏目平级，集成内无渠道面板。
- AC-2：渠道名称已本地化，未支持渠道无法触发飞书修改。
- AC-3：真实状态值可区分，在宽窄窗口中清晰可读。
- AC-4：现有绑定和清理回归通过；验证键盘、加载、空状态、错误及重试。
命令：frontend/node_modules/.bin/vitest run tests/runtimeChannels.test.tsx（在 frontend 执行）；npm --prefix frontend test；npm --prefix frontend run build；npm --prefix frontend run test:webui-assets；变更范围 git diff --check。浏览器使用隔离模拟响应，不授权云端绑定或删除。

## 风险与审查
当前任务之前已有未提交改动，予以保留。重新构建会更新产物哈希。不修改 MPA 服务或全局工具。frontend-design、ui-ux-pro-max 在规定及搜索路径均不可用，已披露后用户授权继续，因此依据 frontend/SPEC.md 和现有模式实施。review-spec 不可用，直接审查范围、接口、安全、清理、兼容、测试及双语一致性；导航与飞书改动无设计阻塞，可选澄清未收到回复，实施前已声明本次按页面调整范围推进。企业微信与钉钉显示暂未开放，其服务端集成不属于本次展示调整。

## 验证记录
2026-09-15，基线 HEAD f1aa2d75 加既有工作区改动；范围：渠道导航、展示、语言键、测试、文档和重新构建的资源。

- pass：先执行回归复现 3 项新增失败 / 4 项既有通过；最终 `cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1`：8 项通过，覆盖 IME/Safari keyCode 229、键盘选择、清理、错误恢复及未开放渠道。
- pass：`npm --prefix frontend test`：1206 项通过。原有精确栏目联合类型断言已随新增 channels 更新。
- pass：`npm --prefix frontend run build`：TypeScript 和两次 Vite 构建通过，仍有既有的大 chunk 警告。
- pass：`npm --prefix frontend run test:webui-assets`：104 个文件 / 248 个引用。较早一次检查在构建结束前执行，因中间产物失败；构建成功后重跑通过。
- pass：真实 RuntimeChannels 组件的隔离模拟响应浏览器验证，覆盖已绑定/空状态、加载、配置错误和重试、等待扫码、键盘渠道切换及 480px 布局。临时预览文件已删除，未执行真实云端操作。
- pass：范围内 `git diff --check`、双语渠道键一致性、设计成对完整及相对链接检查。
- not_run：真实飞书注册/投递及云端智能体导航端到端验证，未获云端操作授权；组件浏览器检查不证明这些集成。
- not_applicable：Python 测试/Ruff/Pyright 及 pre-commit/分支同步，本任务未修改 Python，也未提交。

审查：无剩余阻塞性 UI 问题。保留既有后端和依赖锁文件改动。本地预览最初遇到沙箱 EPERM，经批准的限定 localhost 启动成功，未修改机器全局配置。
