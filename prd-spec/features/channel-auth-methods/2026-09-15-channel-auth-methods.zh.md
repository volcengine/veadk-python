# 渠道授权方式

[English](2026-09-15-channel-auth-methods.md)

变更 ID：channel-auth-methods；日期：2026-09-15；状态：implemented。

## 背景与范围
用户明确要求将 Dashboard 已有的企微 SDK 扫码授权接入 Studio，并增加钉钉 Client ID / Client Secret 手动绑定。Studio 当前仅支持企微手动填写和钉钉扫码。保留两种已有流程及飞书，不改变网关、身份或网络配置。

## 需求与设计
- FR-1：点击时同步调用官方 SDK 0.1.0 打开企微弹窗（source=mpa-agent，关闭 debug），校验返回的 Bot ID/Secret，提交到鉴权后的 `/wecom/bindings`。不展示或持久化 SDK 凭据。每次操作使用独立 SDK 实例，切页或用户取消时销毁，忽略迟到结果，等待上限五分钟；弹窗被拦截、取消、超时及缺字段使用脱敏提示。
- FR-2：钉钉保留扫码，新增 Client ID / Client Secret 手动填写（密钥遮罩），提交 `/dingtalk/bindings/manual`。Runtime 通过 `credentialBindingChannels` 声明能力；旧镜像的新手动入口显示升级提示。拒绝空白字段、要求管理员权限、脱敏校验及上游错误；注册结果不明确时返回 409，复用现有加密存储及 Gateway 注册逻辑。
- FR-3：复用渠道表单、Button 样式、中英文翻译、IME 防误提交、重复提交锁及禁用/加载/不确定状态。成功后清空密钥；切换 Runtime 后旧操作不得写入新 Runtime。

## 契约与任务
更新 [MPA 渠道](../../../specs/mpa-channels/README.zh.md) CON-11。T-1：先补失败的前后端契约测试。T-2：SDK 适配、界面、Runtime 接口及能力声明、依赖锁定和翻译。T-3：定向测试、前端测试及构建、浏览器检查和 Runtime 发布。T-4：同步双语文档及验证结果。不改变生成的 Agent 代码；Studio 构建产物必须与源码匹配。

## 验收与验证
AC-1/FR-1：授权成功时准确规范化凭据并仅提交一次；取消、卸载、超时、弹窗被拦截、缺字段时不注册。AC-2/FR-2：手动钉钉请求准确，保留扫码，拒绝未鉴权及非法请求，脱敏密钥并处理注册不确定性。AC-3/FR-3：前端测试/构建、窄窗口/键盘浏览器检查通过；线上 Runtime 提供手动接口并保留原飞书绑定。测试仅用假凭据；真实授权和新渠道聊天需要用户操作，单独报告。

## 审查与授权
用户明确要求参考 Dashboard 实现并增加钉钉手动绑定，已授权此范围。review-spec 技能不可用，直接审查需求、接口归属、鉴权、错误脱敏、异步生命周期、兼容性及双语一致性，无设计阻塞项。本地缺少规范引用的 frontend-design/ui-ux-pro-max 技能文件，按 frontend/SPEC.md 和现有渠道组件实现。SDK 包大小 15,336 字节，无运行时依赖，固定版本 0.1.0。源码确认校验 Origin，不宣称超出实际实现的 state 校验。风险：浏览器拦截弹窗、平台可用性、SDK 兼容性及 Gateway 注册结果不确定；不自动重复注册结果不明确的机器人。

## 交付记录
实现前检查状态：not_run。用户扫码授权和真实渠道消息：需要用户操作，not_run。

### 验证完成（2026-09-15）
- pass：后端渠道测试 74 项，包含新增手动接口鉴权、校验、脱敏和注册结果不确定性检查。
- pass：`vitest run tests/runtimeChannels.test.tsx` 24 项；`npm test` 1206 项；`npm run check:i18n`；`npm run build`；`npm run test:webui-assets`（104 个文件、248 处引用）。
- pass：隔离真实浏览器组件验证企微 SDK 等待/取消、钉钉手动失败/重试/成功、键盘切换及 390px 窗口。测试凭据为假数据，不发送到云端。浏览器发现 SDK browser UMD 默认导出差异，已通过官方 ESM 显式导入及类型声明修复。
- pass：限定范围密钥模式扫描及空白检查。Ruff 报告 17 条已有 B008/RUF100 问题，上一版镜像源码产生相同问题；Pyright 报告一条已有动态 ChannelService 导入问题，旧版源码也可复现。整文件检查在基线上同样为 fail，不宣称通过。
- pass：新镜像 `studio-channels-20260915-v2` 发布到原 Runtime，版本 4 Ready。网络、环境变量和鉴权不变；能力版本 1.2 声明钉钉手动绑定；两个凭据接口空参数均返回 422。原飞书 BOUND 和已有钉钉配置保留，诊断包含此前已投递记录。
- pass：本地 Studio 按原工作目录和启动参数重启（去掉自动打开浏览器），实际首页及 JS 与最终构建匹配。
- not_run：新企微扫码授权完成、新钉钉手动凭据及后续真实消息，需要用户账号操作；未替换已有钉钉机器人。
