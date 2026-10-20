# Lark 渠道绑定与消息投递

[English](2026-10-15-lark-binding.md)

日期：2026-10-15。状态：已实现，本地验证完成，未执行线上发布。
用户批准：按已审阅方案同时适配 Studio/Runtime，不改变国内飞书。

## 背景与证据
Studio 只有飞书入口；Runtime 注册固定从飞书开始，消息客户端使用飞书域名。IM Channel Gateway 设计 3.3.2 明确要求 Lark 使用 adapter=lark、adapter_config.domain=https://open.larksuite.com。参数表与示例在 bot_name、入站 platform 上不一致；保留飞书请求，真实联调后才能判定可发布。旧插件支持域名切换，但不能证明已部署网关版本兼容。

## 目标、范围及非目标
支持 BytePlus Lark 扫码/手动绑定、持久化重试、账号管理和入站/回复。保留飞书默认值和已有记录。本任务不授权数据库迁移、Worker 协议调整、部署、云资源创建或提交。Worker 内 Lark CLI 用户授权不属于消息绑定契约。

## 要求与设计
FR-1：Studio 在 BytePlus 增加 Lark 页签。仅当 Runtime 声明 feishuDomains 包含 lark 且 multiBotChannels 包含 feishu 时开放配置。旧镜像使用现有升级提示。复用 /feishu 管理接口，新扫码/手动请求带 domain=lark；缺省仍为 feishu。按 config.domain 过滤列表，缺失按 feishu。操作始终携带 appId；保留管理员校验、不在浏览器持久化凭据、取消和迟到响应保护。
FR-2：Runtime 限定 domain 为 feishu/lark，使用对应注册域名发起及轮询，持久化品牌，Lark 授权返回不匹配的租户品牌时拒绝绑定，国内飞书保留原有租户元数据处理，只公开安全品牌元数据。同 App 跨品牌重绑在外部操作前拒绝。同凭据重试保留幂等复用。
FR-3：Lark 注册用 adapter=lark，固定 domain=https://open.larksuite.com，加 app_id/app_secret。飞书请求保持不变。沿用 agent_id、Upstream 和 APIG 路由。注册结果未知沿用 uncertain/核对流程，不盲目重试。
FR-4：兼容保留存储 channel=feishu，以 domain=lark 区分品牌。已绑定 Lark Bot 接受 lark 及旧 feishu 事件格式；核验 Bot 后映射到共用飞书执行语义。保留原始事件/request ID 用于持久化去重和网关回复。国内 Bot 拒绝 lark 事件。账号、权限和会话仍由 appId/Bot UUID 隔离。
FR-5：直接消息客户端始终使用已绑定账号品牌，包括 Token、回复、卡片、图片/媒体、Bot 信息、历史和定时投递。Lark 仅用固定 Lark 域名；国内读域名配置不变。不接受用户任意 URL 作为 API 域名。

## 文件与任务
T-1：Runtime schema、binding/studio/config/messages/delivery、消息/注册客户端及账号客户端调用点和回归测试。
T-2：Studio RuntimeChannels、FeishuAccounts、账号读取、能力类型、本地化、自动化入口云提供方透传及 UI 测试；重建发布资源。
T-3：更新渠道契约，执行检查并核对双语。Runtime CHANGELOG 记录交付状态。

## 设计审查
直接审查（review-spec 不可用）：接口增量及兼容默认值；无迁移；固定域名；公开结果不含密钥；保留管理和网关鉴权；跨品牌拒绝；二维码过期/取消/未知结果沿用生命周期。细化内容在用户已批准范围内。本地实施无设计阻塞，网关实测仍是发布验证前提。

## 测试与验收
AC-1/FR-1：UI 测试覆盖 BP Lark、国内页签、旧 Runtime、账号过滤、请求、取消及重试。
AC-2/FR-2/FR-3：模拟注册及真实 SQLite 验证重建服务后的品牌持久化、租户不匹配、注册幂等、飞书请求不变及跨品牌保护。
AC-3/FR-4/FR-5：验证 Lark 入站、Bot 校验、回复寻址、客户端域名及国内回归。
执行前端测试/构建/i18n/发布资源与真实浏览器模拟；Runtime 定向测试后 make lint/make test。记录结果和基线失败。真实扫码/私聊/群聊/流式/解绑需发布新镜像及获授权测试 Bot；模拟结果不证明线上网关支持 Lark。

## 风险与证据
网关表格与示例冲突，不改国内 adapter 或添加未经核实的必填字段。共用存储要求完整透传品牌。发布顺序：Runtime 镜像后 Studio。未执行真实云端写操作；验证结果如下。

## 实施审查与验证（2026-10-15）
范围：Studio `d5f9d485` 和 Runtime `1aa57dc` 之上的未提交 Lark 改动。T-1/T-2/T-3 已实现。直接审查覆盖固定服务域名、规范渠道兼容性、账号身份、持久化恢复、取消/迟到响应、密钥处理和双语一致性。仅 Lark 授权新增租户品牌拒绝规则，国内租户元数据行为保留。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| Studio `npm --prefix frontend test` | pass | 1,389 项 Node 测试和 116 项 React 测试；最终定向 UI/账号回归 85 passed。 |
| Studio build、`check:i18n`、`test:webui-assets` | pass | 已重建发布资源；2 种语言/21 个命名空间；核验 113 个文件/350 个资源引用。 |
| Studio 代理策略测试 | pass | `uv run --extra dev pytest -q tests/test_mpa_channel_proxy_policy.py`：6 passed。 |
| 真实浏览器配合隔离模拟 API | pass | 扫码等待/成功、手动绑定、失败/重试、旧镜像门控、账号过滤、加载/取消、键盘和 390 像素布局；未请求真实 Bot。 |
| Runtime 定向回归 | pass | 渠道/客户端/媒体/投递 304 项通过；最终国内绑定/服务/Lark 回归 82 passed。 |
| 新 Lark 回归对原始 Runtime HEAD | pass | 预期红灯基线：13 failed、1 passed；当前新增套件 14 passed。 |
| Runtime `make lint` 和完整 `make test` | pass | 8,846 passed、188 skipped、431 warnings、0 failed（419 秒）。使用隔离命令 `npm exec --yes --package @openai/codex@0.155.1 -- sh -c 'make lint && make test'`；未修改全局安装/配置。 |
| Runtime 静态检查 | pass / fail（基线） | F821/F811/F401 和新增测试 Ruff 通过。改动文件完整 Ruff 为 39 项、基线 40 项；Pyright 与基线同为 27 项错误，没有新增诊断类别/位置。完整静态门禁不是全绿。 |
| 密钥扫描与空白检查 | pass | Studio pre-commit gitleaks、Runtime 工作区差异 gitleaks、独立新增源码扫描和 `git diff --check`；未加入真实凭据。 |
| 真实 Lark/网关 E2E、PostgreSQL coverage、正式 CI | not_run | 需要获授权测试资源/新 Runtime 部署或 CI 环境；SQLite/模拟 API 检查不证明这些行为。 |
| 提交前 pre-commit/rebase 门禁 | pass | 用户随后授权本地提交。已 fetch 远端；Studio rebase 到 `upstream/main`、Runtime rebase 到 `origin/master` 均已是最新。Studio `uv run --extra dev pre-commit run --all-files` 五项钩子全部通过。无关的本地锁文件删除不纳入提交。未授权推送。 |

首次完整 Runtime 回归发现三项国内租户品牌回归和一项本机 Codex 版本不匹配。已收窄国内校验并通过相关回归。仓库要求 Codex 0.155.1，应用自带版本为 0.162.0-alpha.17.2，最终全量使用隔离的固定版本。跳过项不视为已验证。frontend-design/ui-ux-pro-max 和 review-spec 技能不可用，采用现有 UI 模式及直接设计/浏览器审查。发布前仍需：构建部署新 Runtime 镜像，再针对实际网关验证 Lark 扫码/手动授权、私聊/群聊投递、流式和解绑。本次未部署资源。

### 后续线上观察
用户反馈 Lark 授权页提示“链接已失效”。Runtime 能力已声明支持 Lark，但未观察到完成的 Lark 绑定。尚未取得失败授权链接/会话用于诊断，根因未确认。本次本地提交不宣称通过真实扫码/网关验收，也未解决该反馈。

同步后的提交检查：Studio 完整前端测试（1,389 项 Node + 116 项 React）及 6 项代理策略测试通过；Runtime `make lint` 和 372 项渠道/客户端/媒体/投递定向测试通过。生产差异未变，之前 8,846 项完整 Runtime 回归结果仍适用。
