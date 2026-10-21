# Studio AGENTS.md 编辑与生效

[English](2026-10-21-studio-agents-md-edit.md)

change-id: `studio-agents-md-edit`

## 背景与授权
用户于 2026-10-21 明确要求实现 Runtime AGENTS.md 编辑与生效，同步修改 Studio，参照 ArkClaw，不做缓存和 Bot Profile 改造。该请求授权本次范围内的增量接口与实现，不含提交、发布或云端修改。
旧 ArkClaw ModifyAgentConfig 更新 debug Runtime 配置，发布另行同步；本次 Studio 保存目标为当前所选 Runtime，不新增 debug/正式双环境发布流程。旧 MPA ADK 注入 agentsMd，Worker 复用会话时更新内容指纹。

## 目标与非目标
REQ-1: 管理员在 Studio 信息栏编辑、保存、清空 AGENTS.md，并回读持久化内容；普通用户只读。保留其他 Agent 配置。
REQ-2: 普通会话下一轮使用最新内容；正在运行的一轮保持同一份快照，Main 与 Worker 一致，已有会话无需重建。Worker 仍通过 profile 指纹更新文件。
REQ-3: 并发保存冲突明确返回，错误不冒充成功；旧 Runtime 只读兼容。无缓存、迁移、新依赖；不改 Bot Profile、MA remote-host 指令规则、工具权限或模型配置。

## 设计与边界
新增 Runtime GET/POST /api/v1/studio/agents-md。GET 返回 content:string、revision:int（未配置为0）；POST 必填 content（可空，最多40000字符）和 revision，拒绝未知字段。Runtime 以 X-MPA-Studio-Key 校验当前 Runtime 密钥。Studio 的代理从服务端取密钥，管理读写仅管理员可用，浏览器不能指定或伪造该头；原有信息栏只读路径保留。
保存沿用 mpa_agents 修订表与已有行锁/CAS，原记录不存在时使用当前 MPA_AGENT_ID 初始化；并发初始化失败返回409。保存保留模型、Skill、MCP等配置；空内容表示撤销用户自定义指令。
普通 Codex Worker 架构的 turn 开始时读取当前配置，保存仅含 AGENTS.md 的可信快照到 RuntimeEnvelope。Main 将快照注入本轮 base instructions（原生 Codex 0.155.1 的 resume developerInstructions 更新不会进入下一次模型请求），重新使用 Main thread 时明确替换本轮有效配置；经已授权 MCP 上下文传给 Worker，覆盖 Worker 本轮配置中的同一字段，避免中途重新读到不同版本。不传凭据、不扩大 grant；Bot 已有快照行为保留。MA remote-host 架构不在本次范围。

## 组件影响分析
Runtime: Studio 元数据接口、AgentConfigService、Main envelope/runner/controller、MCP可信上下文、Worker profile加载。Studio: runtime代理授权、API客户端、MPA信息栏、ModalLayout/Button/Textarea、双语文案。

## Spec review
采用 review-spec 检查：已确认空字符串清除、旧 Runtime 404/405、无记录初始化、并发409、运行中更新、复用thread、MCP身份隔离、前端晚返回/取消、40k上限。使用已有权限和存储，不添加目录注册、通用缓存或新授权体系。Main平台规则高于自定义内容。缺失的 frontend-design/ui-ux-pro-max 技能在本机未找到，视觉按现有组件与frontend/SPEC.md验证。

## 任务与验证计划
1. 文档与契约；2. API/持久化和跨turn回归RED；3. Runtime实现；4. Studio接口/UI及测试；5. 完整相关门禁与浏览器验证；6. 实现/验证/发布状态分开汇报。
测试：读取/保存/清空/无记录/重复/冲突/越权/超限；Main与Worker快照、旧会话下一轮、未保存内容；UI加载/失败保留草稿/重试/取消/清空确认/键盘IME/窄窗/切换目标。运行Runtime make test/lint/mcp-tool-gate及治理检查；Studio Python定向+相关代理回归、Ruff/Pyright、npm test/build及浏览器验证。

## 风险与验收
不声称复刻旧控制面发布拓扑。模型遵循内容是概率行为，验证代码确实传入同一配置而非保证所有模型答案。生产模型/云端验证另行记录；未经部署不可称线上生效。若已有字段超过40000字符，不静默截断保存；提示缩短后重试。阶段按上述依赖顺序推进；跨仓库兼容与真实环境为验证风险缓冲。

## 验证结果
实现已完成；定向测试、真实 PostgreSQL CAS、原生 Codex 更新/清空、Studio 全量前端测试与构建、浏览器验证已通过。Runtime 最终全量 10397 passed、306 skipped、1 failed；唯一失败为基线已复现的定时 Worker 用例，全量门禁未通过，尚未发布。历史模型切换消息可以保留旧配置文字，但本轮有效 instructions 明确替代旧版；不删除历史。详见 Runtime 的 docs/verification/studio-agents-md-edit/test-verification-report.md。

## 交付澄清（2026-10-21）

用户已授权提交本地 Studio 修改并创建到官方 main 的 PR。后续 Runtime 原生协议证据取代前文 REQ-2 已完整验证的表述：更新 Worker 文件不会让已复用的原生 Worker 线程重新加载指令。Main 下一轮更新与持久化已验证；Worker 热更新（包括清空）仍为暂缓项。本 PR 交付 Studio 编辑器及代理，依赖配套 Runtime API，不修复也不宣称 Worker 热更新完成。独立 Runtime 全量测试的基线失败仍未解决。本次发布操作不代表真实云端或模型验证。

## Studio 提交前验证（2026-10-21）

范围：rebase 到官方 `main` 的 `5e5deb6a` 后的 Studio 编辑器及代理修改；原协作 Agent/创建诊断提交无冲突重放。本仓库提交不包含配套 Runtime 代码。

- pass：`uv run --extra dev pytest tests/test_mpa_agents_md_proxy_policy.py tests/test_mpa_collaborator_proxy_policy.py tests/cli/test_frontend_runtime_proxy.py tests/integrations/mpa_managed -q`：1,313 passed，6 warnings。
- pass：`npm --prefix frontend test`：Node 1,389 个、Vitest 154 个用例通过。
- pass：`npm --prefix frontend run build`、`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`（113 个打包文件、351 个引用）。保留既有 bundle 体积警告。
- pass：接受 Ruff 格式修正后，`uv run --extra dev pre-commit run --all-files` 通过，包含硬编码密钥扫描和依赖策略检查。
- fail（基线不变）：使用仓库 Python 环境的改动文件 Pyright 共 57 项诊断：cli_frontend.py 37 项、test_frontend_runtime_proxy.py 20 项。与 rebase 后 HEAD 的严重级别/消息/规则计数完全相同；两个新增 Python 文件无诊断。不宣称全仓类型检查通过。
- pass：双语文档本地链接及 diff 空白检查。
- not_run：本次发布过程中的新云端/模型操作及重复浏览器验收；此前隔离浏览器验证记录保留于上文。本次不部署。

- fail：默认并行回归 `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：7,572 passed、53 skipped、4 xfailed、1 failed（483.08 秒）。失败为 `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`：`.md` MIME 返回 `application/octet-stream` 而非 `text/markdown`。单独复跑同样失败（0.52 秒）；该测试与 writer 实现均与官方 main 一致。保留该无关失败，不绕过或静默修改。PR 以草稿形式创建并披露此门禁失败。
