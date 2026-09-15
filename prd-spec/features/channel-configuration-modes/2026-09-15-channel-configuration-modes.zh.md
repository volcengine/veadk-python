# 消息渠道配置方式

[English](2026-09-15-channel-configuration-modes.md)

变更 ID：channel-configuration-modes。日期：2026-09-15。状态：implemented。
契约：[MPA 渠道](../../../specs/mpa-channels/README.zh.md)，CON-15。
前序设计：[授权方式](../channel-auth-methods/2026-09-15-channel-auth-methods.zh.md)。

## 背景与证据

`frontend/src/ui/RuntimeChannels.tsx` 在未配置企微、钉钉时同时展示扫码授权和手动凭据，飞书没有手动表单。用户要求飞书支持 App ID 手动绑定，并以“极速配置”和“手动配置”作为互斥方式，默认“极速配置”。本地 MPA 的 `app/api/v1/channels.py` 已提供 POST `/api/v1/channels/feishu/bindings/manual`，且 `credentialBindingChannels` 包含飞书；`app/services/channel/studio.py` 负责凭据注册。已部署 Runtime 是否具备该能力尚未验证。

## 目标与非目标

统一三个渠道的配置方式选择，将飞书凭据接入既有 Runtime API。保留当前 Runtime 选择、诊断、解绑与飞书群权限职责。本次不修改自动化目录、独立的飞书 Runtime 创建向导、云部署、SDK 依赖、数据库 schema 或外部 MPA 源码。

## 需求与设计

- FR-1：每个渠道展示互斥的“极速配置 / 手动配置”（英文 Quick setup / Manual setup）。初次挂载、切换渠道或 Runtime 时默认极速配置，不持久化选择。仅展示所选方式的内容；选择极速配置本身不自动发起授权。
- FR-2：极速配置沿用飞书、钉钉二维码及企微 SDK 授权，保留已有机器人替换说明和重新生成二维码。手动配置分别填写飞书 App ID / App Secret、钉钉 Client ID / Client Secret、企微 Bot ID / Secret。已配置机器人也可通过两种方式替换；服务端确认成功之前保留现有绑定，并展示替换说明。
- FR-3：飞书手动配置通过 `channelRequest` 将 `{appId, appSecret}` 提交到 POST `/api/v1/channels/feishu/bindings/manual`；钉钉和企微沿用现有载荷与路由。新增手动方式须由 Runtime 能力声明启用；不支持时提示升级，已支持的极速配置仍可用。空值禁止提交；密钥输入遮罩，不持久化、不写日志、不进入错误展示。成功清空凭据并刷新诊断，可恢复错误保留当前表单。
- FR-4：切换方式取消二维码轮询和可释放的 SDK 授权，丢弃临时配对界面与凭据，并忽略迟到结果。注册写请求进行中禁止切换，保留 SDK 取消授权操作。409 结果不确定时，两种方式均禁止再次注册，直到结果得到核实。取消界面操作不代表撤销服务端绑定。保留导航清理、SDK 超时上限、IME 防护和防重复提交。
- FR-5：复用 Studio 控件和样式，方式选择支持键盘、清晰的选中与焦点状态、窄窗口布局。中英文文案与文档同步；验证后更新生成的网页资源。

## 任务与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1、FR-2 | T-1：在 `frontend/tests/runtimeChannels.test.tsx` 先补失败用例 | AC-1：三渠道默认极速配置，仅手动方式显示对应表单；已配置机器人的替换失败保留原绑定 |
| FR-3 | T-2：在 `RuntimeChannels.tsx` 接入飞书字段和载荷，更新能力模拟 | AC-2：各渠道请求准确，能力限制、空值校验、密钥遮罩、错误脱敏和成功清理有效 |
| FR-4 | T-3：实现方式状态与清理 | AC-3：切换与导航终止前端工作，迟到响应不更新当前视图，结果不确定、防重复及 IME 防护有效 |
| FR-5 | T-4：更新 `RuntimeChannels.css`、两种语言的 `ui.json`、`frontend/README.md`、契约及构建产物 | AC-4：双语文案、键盘与窄窗口浏览器检查通过，源码和生成产物一致 |

## 验证

先执行目标测试：`cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx src/adk/channels.test.ts --environment jsdom --maxWorkers 1`。再执行 `npm --prefix frontend test`、`npm --prefix frontend run check:i18n`、`npm --prefix frontend run build`、`npm --prefix frontend run test:webui-assets`。真实浏览器使用模拟 API 和假凭据验证默认方式与切换、各渠道字段、已有绑定替换、加载/错误/重试、取消、键盘/IME 和窄窗口。真实渠道授权与消息需要另行授权和隔离目标，本地测试不证明这些行为。在用户已要求的提交前，重跑仓库 pre-commit 与受影响测试，如实记录未解决的全量回归失败。

## 评审、风险与交付记录

因 review-spec 不可用，直接评审了 API 职责、载荷、权限、能力兼容、凭据生命周期、异步清理、替换行为、可测试性和双语等价。CON-15 记录变化契约。用户于 2026-09-15 明确回复“实施”，批准本方案。实现按已评审范围开展。

风险：本地已有接口不代表已部署 Runtime 支持；取消浏览器工作不代表撤销服务端操作；注册结果不确定时不可自动重试替换。配置成功与实际观测到消息投递仍是不同状态。

2026-09-15，仅本方案：运行时/浏览器检查为 `not_run`，因为实现等待批准。此前提交检查仅针对旧 diff：前端 1208 项通过，jsdom 下渠道测试 32 项通过，目标 Python 15 项通过，构建通过，密钥扫描 hook 通过；Python 全量回归有 6 项失败、2 项收集错误（4532 项通过）。待提交前仍需调查这些失败；尚未创建提交。


## 实现与验证（2026-09-15）

范围：`feat/my-feature` 分支基于 `f1aa2d75` 的当前渠道改动，含此前待提交的 MPA 渠道 diff。T-1 至 T-4、AC-1 至 AC-4 已在本地完成。前端复用 Radio 组件及各渠道的 Runtime 路由；本轮未修改 MPA 后端源码或已部署 Runtime。既有 Python 改动仅由 Ruff 调整格式。浏览器评审还发现并修复了飞书群表单在 390px 下的溢出，使用网格尺寸约束与 Select 公开 style 属性。

- pass：实现前测试为 17 项失败、28 项通过。最终 `./frontend/node_modules/.bin/vitest run --root frontend tests/runtimeChannels.test.tsx src/adk/channels.test.ts --environment jsdom --maxWorkers 1`：47 项通过。覆盖所有渠道、默认方式、互斥内容、凭据、旧能力响应、替换失败、迟到的二维码/SDK 响应、扫码/手动注册结果不确定、IME、防重复与导航。
- pass：`npm --prefix frontend test`：1208 项通过；`npm --prefix frontend run check:i18n`：2 种语言 / 21 个命名空间一致；`npm --prefix frontend run build`：两份输出和 TypeScript 均通过，仅有既有包体积警告。最终构建后的资源验证记录在下方。
- pass：真实浏览器配合模拟 Runtime API 和 SDK：三个渠道手动绑定、飞书错误/重试/成功与密钥清空、企微授权等待及切换取消、原生单选键盘切换、切换渠道默认重置、旧镜像手动升级提示且保留极速配置、390×844 布局。飞书群输入与 Select 已无溢出，预览滚动宽度等于可用宽度（379px）。已移除临时预览文件、服务与标签页，并恢复视口。
- pass：目标 Python 命令 `uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py tests/integrations/test_mpa_provision_env.py -q`：15 项通过。补充 sandbox extra 及临时 `llama-index-core`、`llama-index-embeddings-openai-like`、`llama-index-llms-openai-like` 后，`tests/cloud/test_harness_app_contract.py`、`tests/runtime/test_self_host_sandbox_agent.py`、`tests/runtime/test_self_host_sandbox_client.py` 共 73 项通过。
- fail：同一临时依赖配置下全量回归 `uv run --extra dev --extra sandbox --with llama-index-core --with llama-index-embeddings-openai-like --with llama-index-llms-openai-like pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：4546 项通过、3 项失败、7 项跳过、2 项 xfailed。失败为 `test_harness_app_exposes_agent_info`、`test_harness_session_create_accepts_id_and_get_agent_config`、`test_run_wraps_child_with_sidecar_environment`（模型/端口值不符），相关源码和测试未修改。单独重跑两个受影响测试文件共 26 项全部通过；全套执行顺序/环境交互问题尚未解决。使用两个 worker 限制本机资源占用；跳过项不算行为已验证。
- fail（基线）：`uv run --extra dev --with pyright pyright veadk/cli/cli_frontend.py veadk/integrations/mpa/channel_proxy.py veadk/integrations/mpa/mpa_provision.py tests/test_mpa_channel_proxy_policy.py`：33 项诊断，均位于 cli_frontend.py。对 HEAD 副本执行 Pyright 得到完全一致的 33 条诊断消息。渠道/部署配置/测试文件无新增诊断；无关类型清理不在范围内。
- 已复核误报：额外 Gitleaks 默认规则扫描覆盖变更文件、测试和生成资源，命中编辑器压缩表达式 Lexical 选区 anchor/focus 的节点 key 比较。HEAD 的 MarkdownPromptEditor 资源包含完全相同表达式，它是代码而非凭据。未放宽扫描配置或 hook；必需的仓库 pre-commit 结果记录在下方。
- pass：双语标识、相对链接和范围内 diff 空白检查。第三方生成 JavaScript 保留既有空白格式，不手工修改。
- not_run：真实渠道授权、替换和消息收发，本轮未授权。本地源码支持不证明已部署 Runtime 的能力。配置方式变更不涉及 sidecar 契约，因此 Harness/sidecar 覆盖率门槛为 not_applicable。

评审：鉴权仍由既有 BFF 负责；密钥不进入浏览器持久化；切换方式释放所属资源并保留结果不确定状态；双语设计和 CON-15 与实现一致。此前用户提交授权仍有效，未授权推送或部署。

### 最终提交检查（2026-09-15）

- pass：获取 origin 并 rebase 到 `origin/feat/my-feature`；HEAD 已是最新，改动内容完整保留。
- pass：同步后 `uv run --extra dev pre-commit run --all-files`（Ruff 检查、Ruff 格式、Gitleaks）、15 项目标 Python 测试、47 项渠道/客户端测试、语言键一致性和资源验证（104 个文件 / 248 处引用）全部通过。
- pass：20 个变更 PRD/spec 文件均有语言配对，需求标识一致，相对链接有效。临时调试文件保留本地，不纳入提交。
