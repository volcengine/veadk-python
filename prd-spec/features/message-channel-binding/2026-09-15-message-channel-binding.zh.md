# 钉钉和企业微信绑定

[English](2026-09-15-message-channel-binding.md)

变更 ID：message-channel-binding。日期：2026-09-15。状态：approved。
组件契约：[MPA channels](../../../specs/mpa-channels/README.zh.md)。

## 证据与范围
Studio 当前为钉钉和企业微信显示未开放占位。MPA 已有钉钉授权以及企微 Bot ID/Secret 网关注册，但持久化 Studio 绑定接口仅支持飞书。用户明确同意开启两种渠道并测试。本次跨两个仓库联通既有能力。SDK 执行、部署和平台基础设施变更不在范围内。

## 需求与场景
- FR-1：选择钉钉可扫码授权。授权完成后服务端注册网关机器人，仅持久化成功才返回 BOUND。重启、过期、用户隔离和注册结果不确定场景维持飞书现有保证。
- FR-2：选择企微可填写 Bot ID 和密码类型 Secret。凭据只发送到鉴权服务端接口，不进入浏览器持久化或响应。成功清空表单，失败可见。
- FR-3：各渠道均支持诊断和解绑。群白名单和群权限配置仅针对飞书，钉钉与企微群消息不要求本地白名单。切换渠道取消待处理请求，隔离恢复 ID 和界面状态。不支持的新接口显示升级提示。
- FR-4：相同凭据重复注册复用既有机器人。远端注册结果不确定时明确报告，不自动重试。诊断不得将其他渠道的投递当作本渠道成功。

## 设计与边界
给既有 Studio 渠道组件增加 provider 参数。保持飞书接口兼容，新增钉钉持久化绑定和企微凭据绑定，通过 capabilities 声明支持渠道。Runtime 持有凭据，新接口统一使用 require_channel_admin 鉴权。钉钉以请求驱动轮询，加密数据库状态并使用带代数校验的租约，此路径禁用旧的后台轮询。企微复用串行 upsert 和渠道加密存储。接口错误详情不得包含密钥。真实平台测试需要隔离 Runtime 和账号，本地测试模拟全部外部服务。

## 任务、影响文件与验收
| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1 | T-1：MPA studio.py、channels.py 和测试 | AC-1：扫码、完成绑定、过期、用户隔离且不返回凭据 | MPA 定向 pytest |
| FR-2 | T-2：MPA 凭据接口及 config.py | AC-2：企微注册、空值校验、错误和凭据脱敏 | MPA 定向 pytest |
| FR-3 | T-3：RuntimeChannels.tsx、client.ts、语言包、CSS、测试 | AC-3：两类 Tab 可用，取消、表单和权限按渠道隔离 | Vitest、npm test、build、真实浏览器 |
| FR-4 | T-4：config 和 observations | AC-4：幂等与渠道隔离 | 定向 pytest |

## 评审与风险
review-spec 不可用，已直接完成设计评审：职责、兼容、鉴权、加密存储、取消、失败语义及双语一致性均已检查，无未解决设计阻塞。用户批准：“帮我改，钉钉和企微的都要开启可以绑定”。外部 MPA 仓库写入需文件系统提权。保留已有无关修改。Runtime 需与 Studio 一起更新，未授权部署。真实测试待提供目标配置，本地证据不能证明实际消息投递。

## 验证记录
初次评审：批准时待实施，最终结果见下文。必需检查：MPA 定向 pytest、变更 Python 的 Ruff/Pyright、前端 Vitest 与 npm test、npm build、webui 资源检查、浏览器正常/错误/取消/键盘/窄屏。真实 smoke：blocked（未提供 Runtime 和测试账号）。

2026-09-15 范围修订已获批准：用户明确“群聊限制只针对飞书”。FR-3/AC-3 要求隐藏钉钉/企微群权限表单并跳过权限读取，Runtime 准入只对飞书执行白名单检查。既有群会话隔离不变。直接设计评审：不改变其他鉴权或机器人绑定检查；补充非飞书允许及飞书拒绝回归测试。

## 实施与验证更新
2026-09-15，两个仓库当前未提交的渠道 diff。FR-1 至 FR-4 已实施，包含仅飞书群限制修订；本地 AC-1 至 AC-4 已验证。未提交、部署或发送真实消息。本地实施范围已完成，真实验证及仓库既有静态检查问题如下保留。

- pass：测试先行证据：新增界面用例初始 3 项失败，后端初始 3 项失败；仅飞书群限制修订在实施前分别有 2 项界面和 2 项后端失败。
- pass：MPA 渠道回归 96 项；测试类型整理后新增 9 项后端用例再次通过。覆盖绑定/所有者/持久化、凭据校验与加密、鉴权、远端错误脱敏、重复注册、机器人隔离观测、飞书白名单拒绝及非飞书跳过。
- pass：前端回归 1206 项；渠道组件 14 项（单 worker），覆盖两种绑定方式、旧 Runtime 能力、解绑、取消、渠道隔离、IME 及仅飞书群配置。
- pass：生产构建（TypeScript 和两套 Vite 输出）；资源校验 104 文件、248 引用。仅有既有大包体警告。
- pass：真实组件配合本地模拟 fetch 的浏览器检查：钉钉等待授权至 BOUND、企微凭据绑定、仅飞书群配置、错误/重试、加载/切换、键盘及 480×850 布局。临时预览文件/服务/标签页已清理，视口已恢复。浏览器解绑点击在对话框自动化中超时；两种渠道解绑由组件和后端测试覆盖，不声称浏览器验证通过。
- pass：studio.py、delivery.py、channel_control.py 及新增测试的 Ruff；这些文件（含新增测试）的 Pyright 零诊断。
- fail（既有问题）：更大范围的变更 Python 文件仍有 Ruff 27 项（channels.py 17、config.py 2、messages.py 8），相比 HEAD 无新增诊断。更大范围 Pyright 报告 channels.py/config.py/messages.py 既有 mixin/导入/类型问题；本次新增的重写参数不一致已修复。未做无关源码清理。
- pass：定向空白检查、语言包键一致性及双语文档/相对链接检查。未使用真实凭据，测试密钥均为显式占位值。
- not_run：VeADK 全量 Python 回归（未改变 VeADK Python 运行逻辑）；pre-commit/gitleaks（未请求提交，gitleaks 可执行程序不可用）。不将其称为密钥扫描通过。
- blocked：真实 Runtime/平台 smoke 需要 Runtime ID、地域及隔离测试账号。更新本地 Studio 资源不会更新已部署 MPA 镜像。实际绑定前需同步升级两端并保留 CHANNEL_STATE_ENCRYPTION_KEY。

MPA 仓库使用 dev 依赖组而非 VeADK 的 `--extra dev`；使用既有本地解释器，避免改变任一依赖锁或访问外部服务。

```bash
# MPA: repository-local interpreter; isolated from developer .env and external services
cd /tmp
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/Users/bytedance/Desktop/code/agentkit-mpa-agent /Users/bytedance/Desktop/code/agentkit-mpa-agent/.venv/bin/python -m pytest /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_multi_channel_binding.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_studio.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_binding_edges.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_control_store.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_service.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channels_auth.py /Users/bytedance/Desktop/code/agentkit-mpa-agent/tests/test_channel_message_edges.py -p no:cacheprovider -o addopts= -q
# VeADK working directory
npm --prefix frontend test
(cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1)
npm --prefix frontend run build
npm --prefix frontend run test:webui-assets
```
