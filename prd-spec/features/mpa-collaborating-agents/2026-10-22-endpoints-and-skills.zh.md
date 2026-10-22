# A2A Runtime 端点和 Agent 详情

[English](2026-10-22-endpoints-and-skills.md)

ID：mpa-a2a-endpoints-and-skills。创建/修订：2026-10-22。状态：implemented。
关联：[组件](../../../specs/mpa-collaborating-agents/README.zh.md)、[成员操作](2026-10-22-member-actions.zh.md)、[认证修复](../../bugfixes/mpa-a2a-space-deletion/2026-10-22-runtime-auth.zh.md)。

## 背景与证据

注册当前固定提供 public/private，未读取实际 Runtime 地址；详情投影省略 AgentCard 服务地址和技能。用户要求选项与控制台对齐、显示具体地址、查看时显示技能，并以“按此实现”批准。官方[注册](https://docs.volcengine.com/docs/86681/2229304)、[服务地址](https://docs.volcengine.com/docs/86681/2248691)和 [GetA2aAgent](https://docs.volcengine.com/docs/86681/2249666) 描述了 Runtime 实际公私网地址与 AgentCard 元数据。已部署 MPA 注册中心将 AgentCard 解析为 JSON 字符串/对象，但公开 Get 文档示例不一致，因此缺失/不可解析元数据必须明确提示，不能编造。

## 目标、场景与需求

FR-1：选择或输入来源 Runtime 后，在目标地域读取其已授权网络配置。仅列已配置的公私网端点，显示本地化“公网地址/私网地址”和具体地址。原类型仍可用时保留，否则选择首个可用类型。切换 Runtime 立即使旧选项失效；区分加载、空和读取错误。支持重试；切换 Runtime/地域/来源及卸载时中止旧请求。没有当前匹配端点时禁止提交。注册 Payload 仍为 RuntimeId 加 NetworkType，不把浏览器提供的 URL 作为注册目的地。
FR-2：查看显示生效 AgentCard 的服务地址，以及技能名称、描述、标签、示例，均为纯文本。服务 URL 与 AgentCard 文件 URL 分开。区分已知无技能与元数据缺失/无效。可选 Card 元数据不可用时保留基本详情。保留有界投影、身份检查和读取重试。
FR-3：URL 移除 query/fragment，拒绝带凭据、非 HTTP(S)、无效端口、控制字符和超长地址。不返回原始 Card、安全方案、请求头、Key、提供商原因或环境变量，不抓取 Card URL。Card 输入限制 128 KiB；技能最多 100 项并明确提示截断；ID/名称/描述分别最多 256/512/4096 字符；标签/示例各最多 20 项，每项最多 128/1024 字符。技能元数据无效表示不可用，不能伪装为空。复用表单控件、ModalButton、字体和滚动；窄屏长地址/文本可换行。

## 设计、合同与兼容

GET /web/a2a-runtime-endpoints/{sourceRuntimeId}?targetRuntimeId=...&region=... 要求 Studio 管理员及两个 Runtime ID 的授权。返回 {runtimeId, endpoints:[{networkType:public|private,url}]}，最多两项，每种已配置类型一项；没有安全可用端点时明确返回空。不暴露 Key。增加专用客户端/读取，不扩大共享 Runtime 列表/详情 DTO。注册资格和并发竞态仍由提供商负责。

GET /web/a2a-agents/{agentId} 增加 serviceAddress:string|null、skills:Array<{id,name,description,tags:string[],examples:string[]}>|null、skillsTruncated:boolean。增量字段兼容旧调用者。null 为不可用，[] 为已确认无技能。仅查看时读取元数据，DELETE 校验不解析，避免无效可选 Card 改变注销资格。不改变 schema/数据、不新增依赖、不改 SDK 公共签名、Runtime 部署、派发、Harness 或 IAM。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1 | T-1：端点路由/客户端/解析，再实现注册状态与选择 | AC-1：仅公网/仅私网/两者/无端点、重试、迟到响应、无效手输 ID 和提交门禁正确；凭据不泄露 | Python 端点授权/投影；frontend/tests/collaboratingAgents.test.tsx |
| FR-2 | T-2：有界 Card 投影与详情展示 | AC-2：Runtime/Standard 详情显示地址与技能；空/不可用不同；保留纯文本及身份检查 | Python 元数据测试；UI 弹窗测试；浏览器 |
| FR-3 | T-3：安全/兼容、文档及发布产物 | AC-3：排除不安全 URL 和原始凭据，无效/超限元数据明确；保留键盘/窄屏/加载/错误/取消行为 | 受影响 Python、Ruff/Pyright；npm test/build/check:i18n/test:webui-assets；tsc；浏览器；密钥扫描；git diff --check |

## 评审、批准、风险和验证

没有 review-spec 技能，已直接评审双语等价、API 归属、授权、安全、失败、兼容、取消和测试，无阻塞。用户在生产/测试修改前确认范围方案。复用 UI 控件和提示满足布局/反馈基准，不换风格、不加依赖。Runtime 端点读取可能独立于列表失败，须明确显示并可重试。安全地址有意省略 query/fragment 中的秘密。验证期间不自动写入或真实云注册/删除，模拟测试不能证明真实端到端云成功。

日期：2026-10-22。范围：HEAD 9ab0ef2d 之上的当前未提交 A2A 差异。最终检查记录于交付证据。提交、推送和云部署未获本次授权。


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
