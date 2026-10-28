# 首 Token 时间戳

[English](2026-10-28-first-token-timestamps.md)

变更 ID：`first-token-timestamps`；创建/修订：2026-10-28；状态：approved（实现与本地验证已完成；当前发布检查由 PR #1190 记录）。
组件：[model-timing](../../../specs/model-timing/README.zh.md)。基线：`23014771`。

## 背景、范围和授权

A360 需要时间戳分析模型和 Agent 等待时间。现有 `portal_metrics.py` 定义了 TTFT/TPOT 仪表，但实际记录仍为 TODO；单靠响应 Trace 无法保留首输出接收时间。用户明确将范围收敛为首 Token 时间戳、计时定义/范围、区分非流式，并授权新建分支实现、变更行覆盖率 >=95% 和真实云端 E2E。授权覆盖隔离测试部署。用户随后授权提交并推送本功能分支，未要求创建 PR。

目标：在请求/模型 Span 上新增计时属性，不依赖 usage 采集接收时间，记录范围定义，提供真实云端证据。非目标：TTFT/TPOT 直方图、客户端渲染计时、服务端推理时间、Provider 隐藏重试采集、外部执行引擎模型拦截、前端修改、依赖升级。

## 需求和场景

- FR-1：HTTP 请求和直接 Runner 调用在预处理前建立隔离请求计时（CON-1/5）。
- FR-2：SDK 请求记录模型开始及正文/推理/工具调用流的首个生成增量；忽略空包、元数据和最终聚合事件（CON-2/3/6）。
- FR-3：非流式、不支持和无输出路径明确标记状态且不提供首 Token 时间；重试和取消保留准确尝试证据（CON-4/5）。
- FR-4：现有云端导出器和 JSON dump 保留计时属性，不泄露内容，不改变响应（CON-6）。

流以角色元数据开始时，正文到达后只锁存一次接收时间。推理或工具参数先于正文时，首个生成增量按类型标记。没有 usage 时仍有计时。非流式响应完成不能作为首 Token。两个并发请求或恢复生成器迭代时，时间戳仍属于正确调用。首输出前失败并重试时，各尝试子 Span 独立。取消生成器时，尝试 Span 结束且原取消异常继续传播。

## 设计与影响

使用小型公共计时模块，包含请求 ContextVar、ASGI 中间件、不会跨 yield 泄漏的 Runner 传播、生成增量识别和每次 SDK 请求的 Span 记录器。计时 LiteLLM 客户端子类在 ADK 聚合之前拦截实际 SDK 调用；Ark 在原始事件循环采集。避免从最终遥测估计首输出，也避免全局修改第三方客户端。支持的 HTTP 工厂仅安装一次中间件。现有标注处理器将请求计时复制到 invocation/agent Span。最终遥测为不支持的路径标记状态，不伪造模型开始。

影响代码：计时模块、LiteLLM 客户端/RetryingLiteLlm、ArkLlm、Runner、telemetry、内存标注处理器、AgentKit/Harness 工厂。生成的 AgentKit 项目已使用共享工厂。鉴权和数据库契约不变。现有工具、内容脱敏、重试/fallback 和导出行为保持一致。回滚移除新增字段与代码，无需迁移。

## 任务与验收

| 需求 | 任务 | 验收 | 测试/命令 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1 | T-1：请求入口/上下文 | AC-1：起点和来源准确；上下文不泄漏 | `uv run --extra dev pytest tests/test_model_timing.py -q` | pass：请求/上下文契约 |
| FR-2/3 | T-2：适配器采集 | AC-2：锁存首增量；非流式缺省；尝试结束 | 计时与适配器回归测试 | pass：55 项计时/适配器用例 |
| FR-4 | T-3：Span/导出接入 | AC-3：导出和 dump 保留属性 | tracing/integration 回归测试 | pass：真实云端 exporter/dump |
| FR-1/2/3/4 | T-4：验证 | AC-4：变更可执行行覆盖率 >=95%；必需检查通过 | 相对 `23014771` 的 coverage JSON；`uv run --extra dev pre-commit run --all-files`；`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | pass：100% 覆盖率、静态/文档检查；fail：一项既有默认回归 |
| FR-1/2/3/4 | T-5：隔离真实云端 E2E | AC-5：部署分支代码、真实流式/非流式模型调用、核对导出时间戳 | 隔离 AgentKit Runtime；受保护的环境凭证；HTTP 调用与导出 Span 断言 | pass：6 项真实云端用例、源码指纹一致、Runtime 已删除 |

## 评审、风险和交付

因 `review-spec` 不可用，已直接完成设计评审。PRD/spec 职责、双语标识、无 usage/空包/非流式语义、生成器上下文和资源清理、请求来源、隐私、兼容性、可测试性及部署授权已对齐，无设计阻塞。用户授权来自确认范围后的实现请求。实现评审核对了原始 SDK 拦截、yield 安全的请求上下文、流清理、兼容的 client 注入、不采集内容的计时，以及工厂/导出消费者。需求自身验收证据完整。AC-4 的仓库默认回归条件仍为 fail：一项既有 Sidecar 测试已在对比基线复现，因此 PRD 保持 approved，不宣称全部交付门禁通过。SDK 边界无法暴露 Provider 内部重试开始。HTTP 计时起于 ASGI 入口，不代表浏览器可见等待。

## 验证结论（2026-10-28）

对比基线：`2301477104f6f77e76c8182529545950e2d8ae6e`；分支：`feat/first-token-timestamps`。检查范围包含所有已修改的受版本管理文件，以及尚未跟踪的新增生产代码、测试和设计文件。独立 worktree 保留了用户原工作区的未提交改动。验证环境为 Python 3.12.13、google-adk 2.7.1、LiteLLM 1.83.14，安装仓库全部 extras；测试命令通过 `--no-sync` 保留该环境。依赖元数据未修改。

旧行为不保留首个生成增量的接收时间。CON-1..6 现在定义增量添加的 UTC Unix 纳秒属性、来源/模式/类型/状态、每次 SDK 请求的尝试 Span，以及保持原有响应和异常传播。受影响的消费者包括 HTTP 工厂、Runner、适配器原始事件循环、最终遥测、现有 exporter/dump 和双语用户文档。生成的 AgentKit 项目已调用共享工厂。前端 UI、数据迁移、认证和指标直方图契约均无变更。

### Gate 状态

| Gate | Status | 证据或阻断原因 |
| --- | --- | --- |
| Change Basis | PASS | 对 `23014771` 检查完整的已跟踪/未跟踪 diff；保留原工作区。 |
| Contract | PASS | FR-1..4、CON-1..6 与代码和两种语言的文档一致。 |
| Impact | PASS | R-1..7 映射请求、模型、生命周期、导出、工厂、兼容性和文档消费者。 |
| Portfolio | PASS | 受控时钟、原始 SDK 边界、故障注入、ASGI 契约、云端 E2E 和既有回归。 |
| Baseline | PASS | 计时模块缺失时为 RED；迭代前关闭用例 RED 后转为 GREEN。既有 Harness HTTP 测试补齐前置条件，断言未变；完整收集上下文中的两项用例为 GREEN。 |
| Execution | PASS | 已执行变更行为验证，最终精确数量见下文。一项无关的默认回归失败在对比基线上复现，其检查状态仍为 `fail`。 |
| Evaluation | PASS | 变更可执行生产行 208/208，变更分支弧 53/54；所有实质性需求风险均已验证，下文说明 Ark 可选关闭保护分支。 |
| Handoff | PASS | 双语契约/文档对齐，保存不含内容/凭证的真实证据，删除独立云端 Runtime；用户随后授权提交/推送。 |

### Change Impact

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
| --- | --- | --- | --- | --- | --- |
| FR-1 | CON-1/5 请求来源与传播 | Runner、ASGI 请求/invocation Span | `timing.py`、`runner.py`、应用工厂 | 时间在 yield/并发请求间串用，或晚于预处理开始 | R-1 High |
| FR-2 | CON-2/3 首个增量 | LiteLLM 与 Ark 原始 SDK 响应 | `timed_lite_llm.py`、`ark_llm.py` | 把元数据/聚合响应算成首 Token，漏掉推理/工具增量，依赖 usage | R-2 High |
| FR-3 | CON-4 模式/状态 | 模型 Span 与不支持的引擎 | `ModelTiming`、`mark_uninstrumented_model` | 把非流式完成或 invocation 起点伪装成首 Token/模型起点 | R-3 High |
| FR-3 | CON-2/5 尝试与终止 | 重试、异常、取消、流关闭 | `RetryingLiteLlm`、`_TimedStream`、Ark 响应循环 | Span/资源泄漏、输出重放、首输出证据丢失 | R-4 High |
| FR-4 | CON-6 导出 | OTel processor/exporter 与 Trace dump | `inmemory_exporter.py`、`telemetry.py`、真实 `/e2e/evidence` | 导出丢失时间属性，或添加敏感内容 | R-5 Medium |
| FR-1/4 | 兼容的增量接入 | AgentKit/Harness 工厂、生成应用、既有调用方 | 既有 AgentKit/Harness/Runner/模型测试契约和生成器工厂调用点 | 请求事件、路由/会话行为或公共 client 注入回归 | R-6 High |
| FR-1..4 | 持续维护的定义 | 两种语言的 PRD/spec 和 Tracing 页面 | 成对 `.md`/`.zh.md`、`.mdx`/`.en.mdx` | 范围/标识符不一致，或 MDX 破坏文档构建 | R-7 Medium |

High 对应常用公共路径与计时/生命周期变更风险；Medium 对应跨模块的导出/文档边界。未引入新的授权或持久化风险。覆盖率降低执行范围的不确定性，不降低故障影响严重度。

### Test Portfolio

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | ASGI/异步生成器 | 时钟控制、并发、上下文/关闭契约 | HTTP 与 Runner、继承起点、并行 yield、异常/关闭、非 HTTP scope | 来源/起点正确，恢复调用方上下文，请求相互隔离 | `tests/test_model_timing.py`；2 次并发真实云端调用 | VERIFIED |
| R-2 | 真实自有适配器；受控 Provider 边界 | 等价类与适配器集成 | 文本/推理/工具增量，空值/元数据/聚合，缺少 usage | ADK 聚合前首个生成增量锁定时间，且只记录一次 | 两个新增测试模块；4 个真实云端适配器/模式用例 | VERIFIED |
| R-3 | 计时状态/遥测 | 模式/状态契约 | 非流式、无输出、不支持（`unsupported`）、无 recording tracer | 状态明确，不伪造模型/首 Token 时间 | 单元/Tracing 测试及两个真实云端非流式用例 | VERIFIED |
| R-4 | SDK 请求/迭代器生命周期 | 故障注入与真实 VeADK 重试集成 | 输出前 429 重试，异常/取消，迭代前后关闭，关闭异常 | 独立子 Span，保留输出/异常，原始流只关闭一次，终态正确 | `tests/models/test_model_timing_adapters.py` 及既有重试/fallback 测试 | VERIFIED |
| R-5 | 实际 exporter/dump | 集成与隐私检查 | 云端导出的请求/模型字段，源码指纹 | 真实 dump 保留属性/父子关系/时间顺序；计时不添加内容 | 6 份脱敏真实证据，凭证内容检查，pre-commit 扫描 | VERIFIED |
| R-6 | 工厂和既有 SDK 调用方 | 契约/受影响/默认回归 | 路由、会话创建/配置、Runner 事件、适配器/重试/fallback | 保留既有断言；计时中间件和字段为增量变更 | 244 项受影响测试；下文最终默认回归和基线结论 | VERIFIED |
| R-7 | 文档构建和成对文件 | 类型/构建、标识符和相对链接 | 中英文定义与有效 MDX | 字段/ID/范围等价；文档编译及类型检查通过 | 文档命令、双语/链接检查、`git diff --check` | VERIFIED |

### 已执行检查

- `uv run --no-sync --extra dev pytest tests/models/test_model_timing_adapters.py tests/test_model_timing.py -q`：**55 项通过**，无失败/跳过。Provider 调用在 SDK 边界受控，这是本地适配器测试。
- `COVERAGE_FILE=/tmp/veadk-first-token-delivery.coverage uv run --no-sync --extra dev pytest tests/test_tracing_content.py tests/test_tracing.py tests/test_inmemory_exporter.py tests/test_runner.py tests/runner/test_runner_contract.py tests/integrations/agentkit/test_app.py tests/cloud/test_harness_app_contract.py tests/cloud/test_harness_app_http.py tests/models tests/test_model_timing.py --cov=veadk --cov-branch --cov-report=json:/tmp/veadk-first-token-coverage-delivery.json --cov-report= -q`：**244 项选中/执行/通过**，无失败/跳过。
- `uv run --no-sync --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q`：**选中 7,987 项；执行 7,945 项（含 4 项预期失败）；7,940 项通过、1 项失败、42 项跳过、4 项 xfailed；另有 6 个子测试通过；472.86s；状态：fail（对比基线的既有失败）**。两个 worker 符合仓库要求。仓库默认回归排除 Codex/Pi smoke 标记；外部引擎模型拦截不在本需求范围。跳过和预期失败的用例不作为真实验证证据。
- 对比基线以完整测试收集上下文执行 `-n 2 -k test_run_wraps_child_with_sidecar_environment -q`：**1 项失败**。剩余默认回归失败为相同的既有 Sidecar 子进程模型 URL 断言（固定端口与 relay URL），本需求未修改或屏蔽该用例。
- `uv run --no-sync --extra dev pre-commit run --all-files` 及对新增 Python/设计/spec 文件显式执行 `--files`：Ruff、格式及适用的凭证/依赖检查均 **pass**。无匹配文件的 hook 标记为跳过，不算执行通过。
- `npm --prefix docs run types:check` 和 `npm --prefix docs run build`：均 **pass**。文档依赖来自既有 pnpm lock，package/lock 未修改。
- 双语标识符、相对链接、全部生产文件 SHA256 与云端构建一致性、凭证内容检查以及 `git diff --check`：均 **pass**。

变更行覆盖率按完整 Git diff 加新增未跟踪生产 Python 模块的全部行，再与 coverage.py 可执行行求交集计算。测试与 Markdown 不属于生产可执行行。未添加任何覆盖率排除项。结果：**100%（208/208）**。两个新增生产模块的行和分支覆盖率均为 100%。整体变更分支弧为 **53/54**；未执行分支是 Ark 可选的缺少 `close` 保护分支，而经验证的真实 Ark SDK Stream 具备异步 `close`。正常/提前关闭/异常路径使用该真实接口。

时间值、状态/字段缺失、事件只锁定一次、请求隔离、父子关系、原始输出和终态资源关闭断言，能够区分相应缺陷；累计覆盖率本身不是测试判据。

### 真实云端 E2E

地域：`cn-beijing`；独立 Runtime：`r-yey87ec8hs2hv32antzi`；真实模型：`doubao-seed-2-1-pro-260628`；结果：**6/6 通过**。云端 Runtime 部署本分支 wheel，全部 9 个生产变更文件的 SHA256 一致。通过实际 VeADK 应用工厂/中间件及 Runner，调用真实 LiteLLM Chat、Ark Responses 适配器和模型服务；证据来自内置 Trace exporter/dump。它与本地受控 SDK 边界测试分别记录。

Chat 流式/非流式、Responses 流式/非流式及并发 Chat/Responses 流式调用，均返回非空真实输出并完成。流式 Span 的来源为 `http`，父 Span 为 `call_llm`，范围为 `sdk_request`，状态/类型为 `observed`，且请求开始 <= 模型开始 <= 首 Token <= Span 结束。非流式 Span 的实际 SDK `streaming=false`、状态为 `non_streaming`，无首 Token 时间/类型。并发请求保留不同的请求起点与会话证据。导出的父 Span 字段与子尝试一致。采集证据后已删除独立 Runtime。

脱敏证据保留在 Git 之外的 `veadk-first-token-20261028` 目录；结论：`cloud-verification.json`；各场景：`chat-stream.json`、`chat-nonstream.json`、`responses-stream.json`、`responses-nonstream.json`、`concurrent-chat.json`、`concurrent-responses.json`；变更覆盖率：`changed-coverage.json`。本文仅保留验证结论，不包含凭证和排障历史。

### 交付边界

请求起点是服务端 ASGI 入口或直接 Runner 执行，不是浏览器提交/渲染。模型起点是适配器 SDK 请求，不是 Provider 推理。不可见的 LiteLLM/Provider 内部重试计入一次 SDK 请求；外部/自定义引擎明确标记不可用。未新增 TTFT/TPOT 直方图或跨主机耗时保证。云端证据覆盖北京一个 Runtime、两个支持的适配器及模型调用模式，不宣称完整 Provider 矩阵或负载基准。上述既有 Sidecar 回归在本次变更范围之外。用户随后授权 commit 和 push，未要求创建 PR。发布记录见 Git 历史和远端功能分支。

发布前验证（2026-10-28）：已 fetch 并相对 `origin/main`（`23014771`，未变化）执行 rebase；全部适用的 pre-commit hook 通过，244 项受影响测试再次全部通过。生产文件 SHA256 仍与真实云端 E2E 构建一致。

CI 后续修复（2026-10-28）：[测试稳定性修复](../../bugfixes/pr1190-ci/2026-10-28-stabilize-concurrent-tests.zh.md)修正 Sandbox 并发测试断言，并隔离既有 Sidecar 测试环境。原基线失败已解决。最新本地默认全量回归：**7,942 passed、0 failed、42 skipped、4 xfailed；6 subtests passed**。上文失败属于原始运行历史。九个生产源码哈希、100%（208/208）生产变更行覆盖率及真实云端 E2E 6/6 证据均不变。用户现已明确授权创建 PR 和修复 CI。推送后的检查结果见 [PR #1190](https://github.com/volcengine/veadk-python/pull/1190/checks)。
