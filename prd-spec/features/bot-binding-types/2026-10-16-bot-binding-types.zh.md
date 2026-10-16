# Studio Bot 绑定类型

[English](2026-10-16-bot-binding-types.md)

日期：2026-10-16。基线：origin/main edae5b58。状态：implemented。

## 范围与授权

用户要求从主分支新建分支，迁入已有的私有／共享绑定选择并提交 PR，已明确授权实现、测试、提交、推送和创建 PR。后续要求私有说明固定为“私聊可召回同 Bot 的历史，包括群聊。”不部署云端，不修改 Runtime 召回或鉴权规则。

## 背景与设计

Runtime 已声明 botBindingTypes 并接受 bindingType，Studio ProviderChannel 当前仅发送凭据或 domain。复用 Radio 和配置方式 fieldset 样式，在极速／手动配置之前单独显示“Bot 类型”。仅飞书（含 Lark 品牌）且 Runtime 声明已知 shared/private 值时显示。优先默认共享；只声明 private 时选择私有。能力缺失、空数组或仅未知值时保持旧请求体。扫码、手动和扫码重试均传递所选类型，保留 domain=lark。

选择仅存在组件内存中，请求中和存在持久扫码绑定后（包括失败重试）锁定。切换 Runtime／渠道、取消后重新添加时重置。切换配置方式会取消旧扫码界面并允许重新选择，不修改旧服务端绑定。已有账号管理不显示可编辑类型。保留现有取消、迟到响应保护、管理员鉴权和错误提示；浏览器不构造或发送 owner 身份。

私有文案：“私聊可召回同 Bot 的历史，包括群聊。”共享文案：“各会话相互隔离。”英文语义一致。简短 UI 描述不替代 Runtime 授权规则。

## 需求与验收

| 需求／任务 | 验收条件 | 验证 |
| --- | --- | --- |
| FR-1 / T-1 | 按能力显示共享／私有，默认共享，使用指定简短说明；旧版本和其他渠道不显示 | RuntimeChannels 组件用例及浏览器夹具 |
| FR-2 / T-2 | 扫码／手动／重试携带类型；Lark 保留 domain；旧请求不变 | 组件请求断言 |
| FR-3 / T-3 | 请求／扫码等待／重试锁定；目标和添加生命周期重置；失败和取消不串选项 | 组件用例、键盘和窄屏浏览器检查 |
| FR-4 / T-4 | 双语契约和用户文档、重建产物、增量可执行行覆盖率 >95% | 构建、国际化、产物、增量覆盖率及 pre-commit |

涉及文件：frontend/src/ui/RuntimeChannels.tsx、frontend/src/adk/client.ts、双语 ui.json、frontend/tests/runtimeChannels.test.tsx、frontend/README.md、specs/mpa-channels/README.md 及 README.zh.md、veadk/webui 构建产物。不改 Python、存储、依赖和权限规则。

## 审查与风险

review-spec 不可用，已直接审查设计：增量能力字段、旧版和 Lark 兼容、请求归属、重试类型稳定性、不持久化密钥、双语等价、可测试性及 S1–S8 复用，无阻塞。已读 frontend-design；仓库及已安装技能目录未提供 ui-ux-pro-max，按 frontend/SPEC.md 和 foundation 执行。已有 Radio 提供焦点／键盘语义，不新增样式或图标。当前用户请求已授权此范围，无需重复确认。

仍需兼容 Runtime；类型不可变校验和召回规则由服务端负责。组件／浏览器夹具不代表真实飞书绑定验证。验证见下文。

## 验证与交付（2026-10-16）

范围：origin/main edae5b58 加本次改动。实现审查无阻塞：已检查能力缺失／未知值、仅私有选项、重试类型不可变、Lark domain、目标生命周期、不伪造 owner、已有账号不编辑类型。没有 Python 契约或权限实现改动。

- pass — TDD：新增 15 个组件用例。实现前 9 个新断言失败、78 个通过；实现后 87 个全部通过。原功能缺口已补齐，未发现额外缺陷。
- pass — `vitest run --environment jsdom tests/runtimeChannels.test.tsx tests/feishuAccounts.test.ts tests/mpaChannelsAutomation.test.tsx src/adk/channels.test.ts --coverage`：116 个通过。首次命令遗漏 jsdom，已有客户端测试报 `window is not defined`；补齐浏览器环境重跑通过。新重试夹具补齐为终态绑定，避免缺少轮询元数据。
- pass — `npm --prefix frontend test`：1,389 个 Node 测试和 118 个 Vitest 测试。
- pass — `npm --prefix frontend run build`：TypeScript 和两套生产 bundle；已包含匹配的 WebUI 产物。保留已有大包／依赖警告。
- pass — `npm --prefix frontend run check:i18n`：2 个语言、21 个命名空间一致。`npm --prefix frontend run test:webui-assets`：113 个文件、350 个内部引用。
- pass — 相对 edae5b58 的增量可执行行 6/6（100%），client.ts 仅类型声明。RuntimeChannels 全文件行覆盖率为 94.71%，与增量覆盖率分开统计。依据 V8/Istanbul JSON 和 Cobertura 行命中与 git diff 交集；utree 对此 TSX 返回零目标，不作为通过证据。原始日志和可复核增量计数：`/tmp/studio-bot-binding-types/`。
- pass — `uv run --extra dev pytest tests/test_mpa_channel_proxy_policy.py -q`：6 个通过。
- pass — 真实应用内浏览器、隔离模拟 Runtime：空列表、默认共享、ArrowRight 切换私有、指定私有说明、扫码与重试私有请求、单选框锁定、手动请求、旧能力缺失、能力错误／重试、加载态。复用 Radio／fieldset，检查 S1–S8。实际 708px 宽度无横向溢出；390px 覆盖未生效，未将 390px 记为通过。临时夹具及浏览器已清理，未使用真实凭据或执行云写入。
- not_run — 真实飞书注册、云部署、真实 IME 输入、全量 Python 回归（未改 Python 生产代码）。已有组件 IME／重复提交回归仍被覆盖。本 PR 不声称已验证线上授权或召回。
- pass — fetch origin/main 后使用 autostash rebase（基线仍为 edae5b58），改动完整恢复；`uv run --extra dev pre-commit run --all-files` 的 Ruff、硬编码密钥、依赖规则、YAML 密钥检查全部通过；最终定向复测 116 个通过。`git diff --check` 通过。
