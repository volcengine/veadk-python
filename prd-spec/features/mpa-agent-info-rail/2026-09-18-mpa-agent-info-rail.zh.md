# MPA 会话信息侧栏

- 变更 ID：`mpa-agent-info-rail`
- 日期：2026-09-18
- 状态：已实现；真实浏览器验证受阻
- 英文：[English design](2026-09-18-mpa-agent-info-rail.md)
- 契约：[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)

## 背景与证据

`frontend/src/ui/AgentTopology.tsx` 将通用 graph/draft instruction 标为 AGENTS.md，并混合通用技能与 Session 选择。`veadk/cli/cli_frontend.py` 的 A2A 适配返回空技能列表。已检查的本地 agentkit-mpa-agent `f14fa39` 提供 `GET /api/v1/agents`，包含 `agentsMd`；其 Agent Card resource-topology 扩展发布已配置的技能空间资源 ID。Studio 已有分页 `/web/skill-spaces/{space_id}/skills`。未查询真实 Runtime。

## 目标与非目标

在现有会话侧栏展示权威 MPA 配置及绑定空间技能。非 MPA 或类型未知智能体隐藏整个侧栏。保留 Session 环境控制，移除临时 Session 技能挂载。允许按权限编辑 SKILL.md，并补充 MPA 只读鉴权接口。不编辑 AGENTS.md、不修改技能空间绑定、不部署服务、不新增依赖。

## 需求与场景

- FR-1：仅带有 `veadk:agent-type=mpa` 标签的 Runtime 返回 MPA 侧栏元信息。通用、本地及未知智能体不展示侧栏，也不预留侧栏宽度。
- FR-2：通过已鉴权的 Runtime 连接读取当前 MPA 的 `agentsMd`。保留文档正文，不使用通用 instruction 替代。空内容、接口不支持、权限不足和请求失败分别展示并支持重试。
- FR-3：从已发布拓扑读取 configured 的 `skill-space` 节点，通过现有账户授权 SkillSpace API 枚举技能。处理 Runtime 地域、分页、资源标识和降级结果。展示名称、描述、数量；Session 临时添加的技能隐藏且不发送到 MPA。
- FR-4：切换 Runtime 取消列表请求并丢弃迟到响应。刷新尽可能保留可读数据；权限收回则清除。错误不能伪装成空列表。长文本在现有侧栏内滚动。
- FR-5：保留既有模型与生命周期能力、Session 环境控制、普通聊天及非 MPA API 行为。沿用服务端管理的凭据，仅白名单字段进入 UI，不返回任意上游错误或配置。

## 设计与契约影响

Runtime 代理识别带 MPA 标签的元信息请求，同时覆盖原生应用名及 `a2a-default`，在归一化 AgentInfo 中添加 `agentCategory` 和可选的类型化 `mpa` 数据。独立后端辅助模块使用服务端解析的 Runtime key 读取 `/api/v1/studio/agent-info` 并支持旧 `/api/v1/agents` 回退、分类失败，并仅从 Agent Card 提取已配置的空间 ID。缺失拓扑表示不支持，而非空绑定列表。保留既有通用 A2A 能力归一化。浏览器 MPA 侧栏控制组件负责技能空间分页、刷新和取消；AgentInfoPanel 只展示数据。AGENTS.md 以转义文本展示并保留换行。正文重试重新加载元信息。现有技能分页客户端增加可选 AbortSignal。受认证的技能正文编辑器复用既有版本发布流程，详见后续设计及[正文契约](../../../specs/studio-skill-document/README.zh.md)。不改变公开 SDK 或生成 Agent 契约。在既有双语控制面规范中实现 CON-16/17。

## 任务与验收

| 任务 | 需求 | 验收 | 验证 |
| --- | --- | --- | --- |
| T-1 后端元信息 | FR-1/2/5 | AC-1 原生/A2A MPA 标签元信息、正文及错误分类；通用 A2A 不变 | 定向 Python 元信息及 Runtime 代理测试 |
| T-2 前端数据和状态 | FR-2/3/4 | AC-2 多页技能、无过期数据、部分/降级/错误/空状态及重试 | Vitest API/控制组件测试 |
| T-3 UI 集成 | FR-1/3/5 | AC-3 仅 MPA 侧栏、取消临时挂载、环境控制保留 | 面板测试、前端回归及浏览器 |
| T-4 对齐交付 | 全部 | AC-4 双语文档、生产资源、无新增 lint/type 错误 | i18n/build/assets、Ruff/Pyright、密钥扫描 |

## 风险与评审

技能空间地域沿用所选 Runtime 地域，与当前 MPA 部署契约一致。旧镜像可能缺少读取接口或拓扑，UI 明确展示不支持，不伪造数据。保留现有 SkillSpace 授权。用户通过“帮我改”批准具体方案。直接设计评审覆盖边界、取消、错误、兼容、权限安全及双语一致性，无阻塞问题。引用的 frontend-design/ui-ux-pro-max 和 review-spec 技能未安装，按 frontend/SPEC.md 及直接评审执行。无 graphify 索引，已直接检查实现。

## 影响文件

`frontend/server/mpa_agent_info.py`、`veadk/cli/cli_frontend.py`、`frontend/src/adk/client.ts`、`frontend/src/create/skills/skillspace.ts`、`frontend/src/App.tsx`、`frontend/src/ui/AgentTopology.tsx`、`frontend/src/ui/mpa-agent-info/MpaAgentInfoRail.tsx`、`frontend/src/styles.css`、两份 workspaceTools 语言文案、对应 Python/Node/Vitest 测试、`frontend/package.json`、`frontend/README.md`、本双语 PRD、双语控制面契约及 `veadk/webui` 构建产物。

## 初始验证记录（后续调整前）

验证日期为 2026-09-18：`feat/from-main` 上相对 `f497cc6d` 的工作区差异，覆盖元信息辅助模块/代理、客户端、侧栏/控制组件、双语文案、文档及构建产物。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 先失败的回归测试 | pass | 新增辅助模块/控制组件测试先因模块不存在失败，实现后通过。 |
| `uv run --extra dev pytest tests/frontend/server/test_mpa_agent_info.py tests/cli/test_frontend_runtime_proxy.py` | pass | 91 项通过；覆盖 HTTP 失败、非法数据、超时、白名单、MPA 标签/原生/虚拟应用及通用 A2A 兼容。 |
| `npm --prefix frontend test` | pass | 1208 项 Node 测试和 11 项 MPA Vitest 测试通过；新套件已接入标准测试命令。覆盖分页、取消/迟到响应、部分失败重试、权限撤销、降级数据及正文转义。 |
| `npm --prefix frontend run check:i18n` | pass | 两种语言和 21 个命名空间一致。 |
| `npm --prefix frontend run build` | pass | TypeScript 和两个生产包构建通过；保留已有包体积提示。 |
| `npm --prefix frontend run test:webui-assets` | pass | 104 个打包文件、248 个内部引用。 |
| 四个变更 Python 文件的 Ruff | pass | `uv run --extra dev --with 'ruff==0.11.12' ruff check ...`；使用仓库 hook 指定版本。 |
| 四个变更 Python 文件的 Pyright | fail（基线） | `uv run --extra dev --with pyright pyright --pythonpath .venv/bin/python ...`；56 条诊断，按文件/规则/消息与 HEAD 完全一致（cli_frontend 36 条，既有代理测试 20 条），无新增诊断。新增辅助模块及其测试无诊断。 |
| Gitleaks 扫描变更文件快照，包含未跟踪代码及构建产物 | pass | `gitleaks dir <snapshot> --config .gitleaks.toml --redact`；未发现泄露。 |
| 源码空白及双语文档/链接 | pass | `git diff --check -- ':!veadk/webui'`；已核对双语标识和相对链接。 |
| 真实浏览器正常/加载/空/错误/重试/键盘/窄屏验收 | blocked | 已准备隔离本地预览；浏览器因无法验证管理员安全策略拒绝访问，未尝试绕过。临时预览和服务器已清理。组件测试不能替代视觉/浏览器证据。 |
| IME；harness 覆盖率；生成 Python/部署；完整 SDK 回归 | not_applicable | 不修改输入、sidecar、代码生成、部署或 SDK；完整前端及 Runtime 代理套件覆盖受影响共享边界。 |
| 真实云/提供方 smoke | not_run | 未授权或调用真实服务；网络回归均使用模拟。 |
| 全量 pre-commit；远端同步；提交/推送 | not_run | 本次未要求提交；未来获授权提交前仍需执行。当前已执行定向 Ruff 和变更文件密钥扫描。 |

直接实现审查已核对 MPA 可见性、原生/虚拟应用兼容、正文转义、凭据白名单、空/错误区分、多页技能读取、取消清理及双语契约一致性，无未解决代码阻断项。T-1/T-2 已验证；T-3 的浏览器证据与最终验收仍受上述阻碍。T-4 文档/产物已同步，明确记录基线 Pyright 失败而不掩盖。不声称已验证生产 Runtime 效果。

## 已批准后续：鉴权与技能正文编辑

2026-09-18 用户要求补齐 AGENTS.md 认证读取、取消临时挂载并支持编辑绑定技能空间的 SKILL.md。上文要求已按此范围更新。直接设计审查批准以下限定范围；既有 JWT 鉴权和技能空间归属规则不变。

- agentkit-mpa-agent 新增只读 `/api/v1/studio/agent-info`，使用专用 `X-MPA-Studio-Key` 与当前 MPA 存储的 Runtime key 做常量时间比较。缺失或错误凭据拒绝访问；只返回 name、description、model、agentsMd。Studio 仅使用服务端解析的 Runtime key，不能将 API key 填入 JWT 头。旧镜像可使用已有 JWT 接口，否则需要升级。
- 移除 MPA 临时技能列表和选择器，MPA 消息也不再发送此前持久化的临时选择。保留环境操作和通用 Agent 行为。
- 绑定技能行保留空间/地域/技能/版本标识。弹窗展示最新 SKILL.md 及服务端写权限。保存通过既有版本服务创建新版本并发布到所选空间，保留其他压缩包成员、二进制字节和文件属性。共享/审核空间保持只读。提示更新共享配置且 Runtime 缓存刷新或新会话后才可能生效。
- 新增受认证 GET/PUT `/web/skill-management/spaces/{space_id}/skills/{skill_id}/document`；返回 `content`、`baseVersion`、`canUpdate`。PUT 接收 `content` 和 `baseVersion`，在既有进程内上传锁中用 409 拒绝过期版本，校验包大小、frontmatter、名称不变。提供方没有原子版本比较交换，外部写入仍可能在校验后竞态，不能声称具备分布式事务隔离。
- 弹窗支持取消、键盘焦点/Escape、只读、错误重试及保留未保存正文。显式保存并防止重复点击，保存中禁止关闭。切换智能体卸载编辑器并忽略迟到响应。实现验证期间不自动写真实提供方或部署。
- 新增影响文件：MPA 路由/新元信息接口及测试；Studio 技能正文服务/路由与版本上传检查、新编辑客户端/界面/测试、既有侧栏/面板/App、双语文案、文档和产物。测试覆盖缺失/错误凭据和白名单、MPA 不发送临时技能、编辑权限/保存/错误、归档字节保留、过期版本/名称拒绝；重跑相关后端、前端、类型/构建、lint、密钥检查，并记录浏览器/服务限制。

MPA Runtime 需要更新镜像才能获得该接口，仅修改 Studio 无法部署鉴权修复。本次实现要求未授权部署或提交。

## 后续验证与交付

验证日期为 2026-09-18，基线为 Studio `f497cc6d`（`feat/from-main`）及 MPA `f14fa39`（`feat/mcp-skill-adap`），覆盖上述未提交变更。用户明确批准补齐鉴权、取消临时挂载和编辑技能；直接审查覆盖鉴权边界、归属、ZIP 完整性、拒绝权限、过期版本、取消及双语一致性。

- **pass**：`npm --prefix frontend test`，1208 项 Node 测试和 17 项组件测试通过。`npm --prefix frontend run check:i18n`、`npm --prefix frontend run build`、`npm --prefix frontend run test:webui-assets`（104 文件 / 248 引用）通过。
- **pass**：`uv run --extra dev pytest tests/frontend/server/test_mpa_agent_info.py tests/frontend/server/skills tests/cli/test_frontend_runtime_proxy.py`，290 项通过；覆盖完整技能服务及 Runtime 代理套件。
- **pass**：MPA 仓库 `.venv/bin/python -m pytest tests/test_studio_metadata.py tests/test_auth.py tests/test_channels_auth.py -q`，29 项通过，覆盖新元信息接口、可空字段、缺失/错误密钥、无写路由及既有鉴权兼容。
- **pass**：两个仓库变更 Python 代码/测试的仓库指定 Ruff 0.11.12 检查。MPA 三个变更 Python 文件 Pyright 无诊断。Studio Pyright 为 **fail（基线）**：cli_frontend/代理测试仍有相同的 56 条既有诊断；新增和修改的技能/元信息模块无诊断。
- **pass**：两个仓库变更文件（含未跟踪新增文件和构建产物）的脱敏 Gitleaks 扫描未发现泄露。源码空白及双语相对链接已检查。
- **blocked**：浏览器此前因管理员策略无法校验而拒绝访问，真实浏览器验收仍不可用。组件测试覆盖编辑、重试、只读、重复保存锁、取消及 IME/Escape，但不等于视觉/浏览器证据。
- **not_run**：真实云编辑、MPA 部署和生产端到端验证。测试使用隔离模拟服务。两个仓库均未提交；未来获授权提交前仍需全量 pre-commit 和分支同步。本次不改变 SDK 或 sidecar 契约，无需其更广门禁。

验收状态：认证读取、仅展示绑定空间技能、按权限编辑的代码已实现并由本地测试覆盖；浏览器验收和真实 Runtime 验证仍待完成。要让现有智能体读取 AGENTS.md，需要发布更新后的 MPA 镜像并保留 `mpa_meta.runtime_api_key`，同时更新 Studio；旧镜像无法使用旧 JWT 接口时将明确提示升级。保存失败可能对应提供方结果未确定，重试前需检查最新版本。本次未修改真实 Runtime。
