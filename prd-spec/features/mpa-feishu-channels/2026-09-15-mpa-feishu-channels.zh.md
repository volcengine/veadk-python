# MPA 飞书渠道

[English](2026-09-15-mpa-feishu-channels.md)

变更 ID：mpa-feishu-channels。日期：2026-09-15。状态：实现及本地验证完成，真实部署待测试环境。

## 背景与批准

MPA Runtime 已提供 `/api/v1/channels`、群权限和两步扫码流程。Studio Runtime 代理注入 Runtime 凭据，但 MPA 渠道管理此前要求管理员 JWT。用户在 2026-09-15 明确批准按飞书分阶段方案实施，包括 Studio 适配。真实部署目标与测试租户尚未指定。

## 目标、场景与范围

FR-1：管理员从 Agent 接入页面为每个独立 MPA 渠道数据库配置一个飞书 Bot。兼容 Runtime 扫码授权后由 MPA 注册并保存，只有 BOUND 表示完成。FR-2：管理允许的群 ID 和会话策略，新权限默认 group_sender。FR-3：如实展示配置与投递诊断、等待、失败和重试状态。FR-4：凭据留在服务端；即使用户拥有 Runtime，非管理员也不能管理渠道。兼容现有 JWT 和旧扫码契约。通用渠道目录、媒体、MCP 和 Skill 管理不在此次变更内。

## 设计与影响文件

遵守[组件契约](../../../specs/mpa-channels/README.zh.md)。复用 `frontend/src/adk/client.ts` 和 AgentWorkspace 接入布局；RuntimeChannels 使用已有 Button/表单样式、翻译与取消机制。Python 的两条代理路由共用渠道策略辅助函数。MPA 部署通过现有 extra_env 接收持久 CHANNEL_STATE_ENCRYPTION_KEY，更新时不自动生成新密钥。新 MPA 部署加入 CHANNEL_ADMIN_AUTH_MODE=runtime_key。凭据不进入浏览器存储。

## 任务与测试

T-1：先写代理策略与 API 客户端测试。T-2：实现代理请求头过滤与管理员检查。T-3：实现能力发现、扫码轮询、诊断、群权限 UI。T-4：验证定向 Python 测试、Ruff/Pyright、前端测试/构建及浏览器交互，同步 webui 构建产物和 frontend README。T-5：只针对明确选择的测试 Runtime/Bot/群记录真实联调结果。

## 验收与风险

AC-1：未授权调用不能触发渠道修改或注入管理请求头。AC-2：切换 Runtime 或离开页面取消轮询并忽略旧响应。AC-3：失败/过期二维码可重试或重新生成；能力或配置缺失有可操作提示。AC-4：群权限增删改和策略值符合 MPA 契约，错误保留输入。AC-5：新绑定 API 不返回 appSecret。AC-6：模拟与真实飞书验证分开报告。MPA 需要持久数据库及持久加密密钥；旧镜像返回不支持。配置完成不代表 Gateway 可达或实际投递成功。Runtime API key 模式是显式管理员能力；浏览器入口仍需 Studio 管理员授权。

## 设计审查

因未提供 review-spec 技能，已人工审查职责、安全、兼容、取消、错误处理、可测试性和双语一致性。无设计阻塞。用户批准已在实施前记录。验证记录（2026-09-15）：新增代理策略测试、MPA 部署环境和 Runtime 代理定向测试通过；`npm --prefix frontend test` 1205 项通过；新增 Vitest 契约/交互测试 5 项通过；前端 TypeScript 与生产 build 通过，webui 产物已同步。浏览器用模拟 API 验证未绑定、扫码到 BOUND、群保存、策略键盘选择和 390px 窄屏，发现的溢出已修复。真实收发/部署：blocked，未指定测试 Runtime/Bot/群。全文件 Ruff：fail，既有 cli_frontend.py 在 HEAD 与修改后均有 86 项问题；新文件与 mpa_provision.py 通过。Pyright 使用本仓库 .venv：cli_frontend.py 当前与 HEAD 基线均为 33 个错误，新增代理文件与部署模块无类型错误。默认全仓并行 Python 回归与提交前 pre-commit：not_run，本次未提交，已运行受影响链路的定向回归。

补充验证：Studio 后端定向测试最终 88 项通过。自动审批拒绝将私有源码挂载到第三方 Gitleaks 容器，因此 Gitleaks 未执行。已用本地 Python 检查两仓库新增文本的凭据模式：83 个文本输入、0 个疑似匹配，不等同完整 Gitleaks 扫描。源码 diff 空白检查通过，生成 bundle 的上游模板字符串仍有尾随空格，未手动改变字符串。
