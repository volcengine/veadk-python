# MPA 渠道

[English](README.md)

## 契约

Studio 管理员通过现有 Runtime 代理管理 MPA 渠道。BFF 移除传入 X-MPA-Channel-Key，所有 api/v1/channels 路径要求管理员，禁止通过 Studio 调用 events 入站接口，并为管理请求注入服务端解析的 Runtime API key。MPA 通过 CHANNEL_ADMIN_AUTH_MODE=runtime_key 显式启用，默认 JWT 仍可用。缺失 Runtime key 时拒绝请求。CHANNEL_STATE_ENCRYPTION_KEY 必须首次配置并在镜像更新时保留，属于敏感配置。

GET /api/v1/channels/capabilities 返回 serverSideBinding、bindingReady、bindingError 及诊断支持。能力接口 404 表示不支持。POST /feishu/bindings 创建加密持久绑定；GET /feishu/bindings/{id} 推进状态；POST /feishu/bindings/{id}/retry 重试失败。以上相对路径加 /api/v1/channels 前缀。状态为 PENDING、SCANNED、AUTHORIZED、REGISTERING、BOUND、FAILED、EXPIRED。响应含 id、loginUrl、qrCodeImage、expiresAt、pollAfterSeconds、appId、lastErrorCode、lastErrorMessage，不含凭据。注册租约丢失时报告结果不确定，不盲目重复注册。

GET /feishu/diagnostics 返回实际保存的配置、缺失元数据及观测投递状态。沿用 GET /chat-permissions、POST /chat-permissions、DELETE /chat-permissions?channel=feishu&chat_id=... 管理群。POST 使用 channel、chatId、groupSessionScope（group、group_sender、group_topic、group_topic_sender）。已有根路径 DELETE 使用 channel 和 appId。离开页面取消绑定和轮询请求；错误保留表单，终态停止轮询。不兼容镜像提示升级。没有观测证据时不声称链路连通。

数据库边界：每个 MPA/formal-debug 需要独立渠道数据库，启动拒绝不同部署共享。新消息映射包含 Bot 身份，旧会话保留为历史，不自动迁移上下文。新密文不兼容旧镜像，回滚需恢复相应数据库快照。Studio 仅转发受信管理员身份作为绑定 owner，忽略客户端 X-User-Id。Runtime-key 模式事件入口验证 APIG 注入的 Authorization。


## Studio 导航
消息渠道是智能体详情中与集成、版本平级的独立栏目，区分飞书、企业微信、钉钉。只有已实现的渠道流程提供配置操作，未开放渠道明确标示。网关、路由配置与实际观测的投递状态保持独立语义。参见[工作区设计](../../prd-spec/features/message-channel-workspace/2026-09-15-message-channel-workspace.zh.md)。

## 多渠道绑定（2026-09-15）

CON-8：Runtime capabilities 声明支持后，Studio 消息渠道开启飞书、钉钉和企微。钉钉提供 POST `/dingtalk/bindings`、GET `/dingtalk/bindings/{id}`、POST `/dingtalk/bindings/{id}/retry`，沿用飞书不含密钥的持久化绑定结构。绑定 ID 按渠道和用户隔离。企微提供 POST `/wecom/bindings`，输入 `{botId, secret}`，仅注册并加密保存成功后返回 `{status: "BOUND", appId}`。所有接口要求渠道管理员鉴权。拒绝空凭据，远端错误脱敏。浏览器持久化和响应均不得含密钥。

CON-9：GET `/{channel}/diagnostics` 和现有 DELETE channel 接口操作所选渠道。Studio 仅为飞书请求 chat-permissions；保留非飞书旧权限接口兼容，但其不控制群准入。旧 Runtime 需升级，不回退到返回密钥的旧二维码接口。切换渠道取消前端工作。注册结果不确定时需检查网关后才能新建绑定；相同已保存凭据复用机器人。投递观测按 Gateway bot ID 过滤，不将历史未分渠道观测归属于某个渠道。

设计：[message-channel-binding](../../prd-spec/features/message-channel-binding/2026-09-15-message-channel-binding.zh.md)。

CON-10：群准入白名单及 Studio 群权限配置仅针对飞书。钉钉和企微群消息通过既有鉴权和机器人绑定检查后，无需本地群权限记录即可接收。群会话隔离行为不变。

CON-11：企微另支持官方 SDK 弹窗授权，返回的凭据提交 `/wecom/bindings`，不在浏览器持久化；切页取消，等待上限五分钟。钉钉支持 POST `/dingtalk/bindings/manual` 手动提交 `{clientId, clientSecret}`，由 `credentialBindingChannels` 声明能力，要求管理员鉴权、加密存储、错误脱敏，注册结果不明确返回 409；原扫码流程保持不变。两种凭据接口成功仅返回 `{status: "BOUND", appId}`。见[授权方式设计](../../prd-spec/features/channel-auth-methods/2026-09-15-channel-auth-methods.zh.md)。

CON-11：已配置飞书和钉钉支持通过既有 POST 绑定接口重新生成二维码。配对区说明飞书替换及授权流程中的存量/新建机器人选择。创建二维码不删除当前绑定，仅成功 BOUND 后刷新摘要。正在配对/加载/结果不确定时防止重复生成。

CON-12：已绑定企微机器人同样提供“重新生成二维码”，由用户点击重新打开既有 SDK 授权窗口，显示配对/替换说明，通过 `/wecom/bindings` 保存授权机器人。授权失败或取消不删除原绑定。

CON-13：配对二维码展示与轮询仅存在于当前挂载的渠道面板。切换渠道/页面、浏览器重载和面板刷新均丢弃配对界面；不再恢复存储的绑定 ID，并清理旧键。仍加载已有机器人配置。隐藏 PENDING 等待文案及授权页面链接。服务端绑定状态/过期不变，关闭界面不代表撤销。

CON-14：智能体详情仅在所选 Runtime 的 agentCategory=mpa 时显示消息渠道。列表分类元数据经卡片传入详情；旧列表响应可使用其明确请求筛选类目。通用、未知及本地条目隐藏栏目且不挂载 RuntimeChannels。不适用的 channels 选择回到 basic。

## 配置方式（2026-09-15）

CON-15：所有渠道提供互斥的“极速配置 / 手动配置”，挂载、切换渠道或 Runtime 时默认极速配置，不持久化选择、不自动发起授权。`credentialBindingChannels` 包含 `feishu` 时，飞书手动方式通过 POST `/api/v1/channels/feishu/bindings/manual` 提交 `{appId, appSecret}`；注册成功仅返回 `{status: "BOUND", appId}`，不含凭据。钉钉和企微的现有路由保持兼容。两种方式均支持替换已配置机器人，不先删除现有绑定。切换方式清空临时配对与凭据，取消前端轮询/SDK 工作并忽略迟到结果；注册写请求期间禁止切换，结果不确定时禁止通过任一方式再次注册。缺少手动能力时提示升级。完整方案和验证映射见[配置方式设计](../../prd-spec/features/channel-configuration-modes/2026-09-15-channel-configuration-modes.zh.md)。
