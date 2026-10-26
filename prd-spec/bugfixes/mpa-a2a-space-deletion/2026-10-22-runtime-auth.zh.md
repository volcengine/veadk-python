# A2A 空间删除的 Runtime 认证

[English](2026-10-22-runtime-auth.md)

变更 ID：mpa-a2a-space-deletion-runtime-auth。创建/修订：2026-10-22。状态：implemented。
关联：[组件](../../../specs/mpa-collaborating-agents/README.zh.md)、[前置功能](../../features/mpa-collaborating-agents/2026-10-22-member-actions.zh.md)。

## 证据、范围与需求

新空间 DELETE 通过 `_runtime_json_request` 读取目标绑定，但未携带 `X-MPA-Studio-Key`。已有协作代理提供这一服务端持有的凭据；MPA 绑定端点要求该凭据。隔离复现返回 401，尚未调用任何云接口。经已有代理读取成功。这证明实现存在缺陷；未捕获用户原失败删除的原始响应。

FR-1：Runtime JSON 请求访问协作路径时应用已有 `collaborator_management_headers` 策略。使用获授权的服务端 Runtime Key，过滤浏览器提供的凭据，要求管理员权限，缺少 Key 时在上游 I/O 前拒绝。无关 JSON 路径不变。
FR-2：绑定前置检查返回 401/403 时，保持状态码并返回有界原因 `runtime_auth_failed`。UI 说明 Runtime 认证失败、尚未执行删除。云端拒绝保留现有权限提示。此前置认证失败不返回原始上游错误，不自动重试，任何前置失败后均不执行云操作。
FR-3：保留绑定/非空/身份检查、超时/不确定结果及取消行为。验证期间不删除真实空间、不改云 IAM、不部署 Runtime、不提交或推送。

## 设计与影响文件

在 `veadk/cli/cli_frontend.py` 的 `_runtime_json_request` 中复用 `veadk/integrations/mpa/collaborator_proxy.py`。不新增 Key 参数、不信任用户请求头、不新增依赖、数据库状态或 API 路由。在 `frontend/server/a2a_center.py` 中仅对绑定读取增加新原因。在 `frontend/src/adk/a2aSpace.ts` 接受该原因，`A2AResourceActions.tsx` 映射并增加等价 en-US/zh-CN 文案。沿用 ModalButton、alert/焦点/重试控件及布局。更新组件合同、frontend README 和构建产物。SDK 公共合同、生成项目、Runtime/Harness 代码与派发不受影响。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1 | T-1：先补真实 Studio 路由/MockTransport 失败回归，再补认证头 | AC-1：绑定收到服务端 Key 而非浏览器伪造值；空且未绑定夹具可进入模拟云删除 | tests/cli/test_frontend_runtime_proxy.py |
| FR-2 | T-2：先补前置错误和 UI 回归，再映射原因 | AC-2：绑定认证拒绝时云调用为零；UI 显示 Runtime 失败并可重试；云 403 保留原提示 | tests/cli/test_a2a_center_actions.py；frontend/tests/collaboratingAgents.test.tsx |
| FR-3 | T-3：回归、安全和交付评审 | AC-3：保留已有检查、授权、脱敏、取消及无关 helper 行为 | 定向 Python；npm test/build；i18n/assets/tsc；变更 Python Ruff/Pyright；模拟 API 的真实浏览器；密钥扫描；git diff --check |

## 风险、评审与批准

共享 helper 必须由已有策略限制路径，禁止向无关路径广泛添加凭据。修复认证后仍可能遇到独立云 IAM 拒绝，应准确报告。单元/模拟测试不能证明真实云 DELETE 成功。后端生效需要重启当前本机 Studio；必须先检查，避免中断用户正在进行的工作。

可用技能目录没有 review-spec，已直接评审合同归属、错误边界、服务端凭据、兼容性、可行性、负面用例及双语等价，无阻塞。用户在生产/测试编辑前以“能修复吗”批准此前提出的认证/错误区分方案。新增端点/技能需求另行确认，不通过此记录隐式批准。

## 验证记录

测试范围：分支 feat/from-upstream-main-20261020 当前未提交 A2A 中心差异；基线 HEAD 9ab0ef2d。日期：2026-10-22。最终检查记录于交付证据。无真实云写入。


## 交付证据（2026-10-22）

在 9ab0ef2d 之上的已有未提交 A2A 变更中实现已批准范围。测试先行证据：实现前 22 项定向 Python 和 8 项 UI 用例失败。评审解决迟到端点选择、可选 Card 安全投影、浏览器凭据覆盖以及读取认证/云权限错误区分，无范围内未解决发现。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| `uv run --extra dev pytest tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py tests/cli/test_frontend_runtime_proxy.py tests/test_mpa_collaborator_proxy_policy.py -q` | pass | 227 passed（6 warnings）；MockTransport 覆盖真实 Studio 挂载和共享 helper，包括成功模拟删除以及绑定认证拒绝后零云调用。 |
| `npm --prefix frontend test` | pass | 1389 项 Node 和 11 文件 183 项 Vitest，其中协作 Agent 36 项。 |
| `npm --prefix frontend run build` | pass | 已重建当前 WebUI 产物；保留既有大分块提示。 |
| `npm --prefix frontend run check:i18n`；`npm --prefix frontend run test:webui-assets` | pass | 2 语言 / 22 命名空间；114 产物文件 / 351 内部引用。 |
| `frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json` | pass | 无诊断。 |
| `uv run --extra dev pre-commit run ruff-check --files ...`；相同文件的 `ruff-format` | pass | a2a_center.py、test_a2a_center_actions.py、test_frontend_runtime_proxy.py、cli_frontend.py；格式化变更已在最终测试前对齐。 |
| 使用相邻仓库已有 Pyright，`--pythonpath .venv/bin/python frontend/server/a2a_center.py tests/cli/test_a2a_center_actions.py` | pass | 0 错误/警告；未安装依赖或改变全局配置。 |
| CLI / 代理测试整文件 Pyright | fail（基线） | CLI 37 项和代理测试既有 20 项诊断。仅移除本次 helper 块和代理测试后，对照诊断消息多重集完全一致（各 57 项），无新增诊断。临时对照文件已删除。 |
| 浏览器 | pass | 隔离模拟 fetch 的真实浏览器：端点描述和选中完整 URL、鼠标/键盘切换、取消/焦点返回、详情/技能、390px iframe 与内部滚动、可操作的前置认证提示。夹具和 Vite 进程已删除。 |
| 本机实时只读集成 | pass | 当前 localhost Studio 已提供新端点路由并服务匹配构建，两个真实来源 Runtime 的端点读取及两个注册详情读取均 HTTP 200。一条同时有公私网，另一条仅公网；生效地址和技能与控制台记录一致。未执行云写入。 |
| 仓库配置的范围内 gitleaks；文档链接/双语/编号；`git diff --check` | pass | 未发现秘密泄露；保留既有扫描排除项，未绕过。 |
| 全量 Python 回归、提交前全文件 pre-commit、真实云写入 | not_run | 变更限 A2A 路由和已有按路径过滤认证策略，已验证受影响代理/API 调用者。未授权提交/推送，因此未执行分支同步及提交门禁。模拟或只读检查不证明真实云删除/注册成功。 |

T-1/T-2/T-3、AC-1/AC-2/AC-3 完成。任务期间 Studio 由外部重启，本 Agent 未中断进程。新后端和构建已生效，浏览器刷新加载新界面。未提交、推送或部署 Runtime，保留全部无关用户修改。后续名称调查仅读取实时值，未改变 AgentCard 或注册名称。
