# APMPlus 流式与 TTFT 遥测

[English](2026-11-02-apmplus-ttft.md)

变更 ID：`apmplus-ttft`；创建/修订日期：2026-11-02；状态：approved。
组件：[model-timing](../../../specs/model-timing/README.zh.md)。
前序设计：[first-token-timestamps](../../features/first-token-timestamps/2026-10-28-first-token-timestamps.zh.md)。
检查版本：`feat/first-token-timestamps` 的 `d9ef697b82fde94373737aae518148df348e60b0`（PR #1190）。

当前契约：本文末尾的仅标准字段修订取代前文保留自定义字段的决定。前文保留历史证据。

## 背景与证据

[PR 评论](https://github.com/volcengine/veadk-python/pull/1190#issuecomment-6514480806) 要求补齐标准流式标记、以秒为单位的 TTFT Span 属性及真正的 TTFT Histogram 记录。2026-11-02 读取的指定 APMPlus Trace 规范（revision 261）和 Metrics 规范（revision 17）与这些要求一致。

`ModelTiming` 当前记录自定义时间戳和实际 SDK 流式模式。`PortalMetricRecorder` 已创建名称正确、单位为 `s` 的 TTFT Histogram，但记录逻辑仍为 TODO。`record_call_llm()` 在响应回调中执行，现有观测还受 usage 检查限制，无法保证每次 SDK 请求恰好记录一次 TTFT。原设计明确排除了 Histogram；本后续设计提出这一有限扩展。

## 目标与非目标

为每次可观测 SDK 请求的 Span 添加 `gen_ai.request.stream` 和 `gen_ai.chat_completions.streaming_time_to_first_token`，并在现有 Histogram 中记录同一个 TTFT 值一次。保留自定义时间戳和模型行为。

不包含 TPOT、无关指标改名、token 计数变更、客户端渲染耗时、供应商内部不可观测重试、新 exporter/配置/依赖、前端变更和云部署。历史云端证据不证明本次新变更。

## 要求与场景

- FR-1：已埋点的 `model_request` Span 使用实际 SDK 请求的布尔值设置 `gen_ai.request.stream`，不依赖 Runner 流式配置。保留 `veadk.model.streaming` 和旧属性。
- FR-2：首个非空文本、推理或工具调用 delta 产生浮点秒数 `(first_token_time_unix_ns - model_start_time_unix_ns) / 1e9`，写入 `gen_ai.chat_completions.streaming_time_to_first_token`。复用自定义属性所用的同一请求开始时间戳。请求入口时间和外层 Span 开始时间不参与计算。
- FR-3：首次观测时，在现有同名、单位为 `s` 的 Histogram 中记录同一个值一次，即使没有 usage 或可记录的 Trace Span。后续 chunk 和最终响应回调不能重复记录。每次可观测重试/降级 SDK 请求独立持有首次观测状态和样本。
- FR-4：非流式、无输出和不支持埋点的请求没有 TTFT 属性/样本。实际 SDK 模式未知时，不从 Runner 配置推造。时钟回退时保留原始时间戳，省略负耗时并产生有限诊断；真正测得的零耗时有效，不是缺失值占位。
- FR-5：失败、取消或关闭前已观测的样本应保留。保持原始输出、异常传播和资源清理。指标记录失败时产生有限诊断，不记录请求内容，也不替换模型结果/异常。
- FR-6：新指标维度使用规范中的点分名称，且仅填写已知稳定值。包含实际请求模型；未知供应商/响应模型省略。不得加入提示词/输出正文、用户/会话/Trace ID 或响应 ID。继续使用现有全局 MeterProvider，不安装导出链路。

当元数据后出现生成 delta 时，只由生成 delta 记录 TTFT。当两个请求共用一个外层模型 Span 时，各 SDK 子 Span 独立保存属性和观测。关闭 tracing 但已配置指标 reader 时，已观测流式请求仍记录 Histogram。没有生成 delta 时，完成响应不能伪造样本。

## 设计、方案取舍与契约影响

由 `ModelTiming.observe()` 唯一负责观测。在本地保存请求开始时间和模型，使计算和指标记录不依赖读取 Span 属性。为 `PortalMetricRecorder` 添加职责单一、带类型注解的记录方法；仅移除被替代的 TTFT TODO。复用现有 instrument、单位和桶边界。

每次 SDK 请求的 `model_request` 子 Span 是标准 LLM Span 的权威位置，并标记 `gen_ai.span.kind=llm`，避免将聚合/重试所属 Span 的生命周期当成单次 SDK 请求。继续兼容现有向 `call_llm` 镜像自定义时间戳的行为；不向聚合 Span 复制标准 TTFT，避免后续无输出尝试遗留旧观测。文档明确该 Span 边界。现有 `gen_ai.is_streaming` 保留兼容。

替代方案：在 `record_call_llm()` 记录。不采用，因为回调次数、usage 缺失和重试需要额外共享状态，可能重复或遗漏样本。替代方案：重命名/删除自定义时间戳。不采用，因为时间戳仍有价值，删除既破坏消费者兼容，也不能满足耗时要求。

实现前更新 model-timing 双语契约：扩展 CON-2/4/6，新增覆盖 FR-3/5/6 的逐请求 Histogram 契约。在原设计添加后续设计说明，保留历史验收事实。同步更新两份 tracing MDX。无需修改持久化、权限、HTTP/事件载荷、公开模型调用签名或数据库。回滚删除新增标准遥测即可，原自定义时间戳仍可使用。

## 任务与验收

| 要求 | 任务 | 验收 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1..6 | T-1：同步双语设计/契约并评审 | AC-1：范围一致且设计获批 | 双语标识符、链接、直接设计评审 | pass：2026-11-02 获批 |
| FR-1/2/4 | T-2：先添加失败的 Span 契约测试，再实现 | AC-2：实际布尔模式；精确秒数；正确省略 | `tests/test_model_ttft.py`、`tests/test_model_timing.py`、`tests/models/test_model_timing_adapters.py` | pass：已实现并完成本地验证 |
| FR-3/5/6 | T-3：先添加 reader 指标测试，再接入记录 | AC-3：真实 Histogram 名称/单位/count/sum/维度；无重复或遗漏 | `tests/test_portal_metrics.py`、timing 与适配器测试 | pass：已实现并完成本地验证 |
| FR-1..6 | T-4：受影响/回归/静态/文档检查及评审 | AC-4：输出、清理、导出兼容；双语文档一致；变更生产行覆盖率 >=95% | 下列命令及相对检查版本的覆盖率 | 本地检查通过；默认回归 fail：一项已复现的基线 MIME 不匹配 |

测试包含文本/推理/工具输出、纯元数据 chunk、重复 chunk、无 usage、实际 SDK 模式与 Runner 模式不同、非流式、无输出、重试/降级、并发请求、输出前后取消/关闭、禁用 tracing、已配置/未配置 MeterProvider、时钟回退、真正零耗时、指标记录失败。使用受控时钟与供应商边界，断言 Histogram 类型、单位 `s`、count、sum、维度及导出的 Span 属性。

根据仓库指南和清单确认的计划命令：

- `uv run --extra dev pytest tests/test_model_ttft.py tests/test_model_timing.py tests/models/test_model_timing_adapters.py tests/test_portal_metrics.py -q`
- `uv run --extra dev pytest tests/models tests/test_model_ttft.py tests/test_model_timing.py tests/test_portal_metrics.py tests/test_tracing.py tests/test_tracing_content.py tests/test_inmemory_exporter.py -q --cov=veadk --cov-branch --cov-report=json`
- `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`
- `uv run --extra dev pre-commit run --all-files`（另对未跟踪新增文件显式执行变更文件检查）
- `npm --prefix docs run types:check`；`npm --prefix docs run build`；`git diff --check`

使用仓库本地环境；记录环境阻碍，不修改机器全局配置。两个回归 worker 遵循仓库要求。真实供应商/云调用不属于本次本地变更验收；分别报告本地适配器/reader 证据和前序设计的真实测试。提交/推送仍需单独授权。

## 评审、风险与交付记录

`review-spec` 不可用，因此执行直接评审。已检查计算归属、回调重复、重试边界、缺失观测、指标维度/隐私、故障隔离、兼容性及双语等价性。设计澄清：标准字段位于可观测 SDK 请求子 Span，不放在聚合 Span。主要风险是重复样本、错误时间边界/单位、聚合字段残留，以及意外依赖 Trace 采样或 usage；验收场景直接覆盖这些风险。

用户于 2026-11-02 明确批准“创建新分支，立即修改”。已创建 `fix/apmplus-ttft`，并通过 `git pull --ff-only origin feat/first-token-timestamps` 同步 PR 基线。实现、组件契约及 MDX 同步已完成。因仓库级 AC-4 检查存在下方记录的既有失败，生命周期保留 approved。运行验证记录见下方。2026-11-02 已完成源码读取和规范核对；分支切换及 `git pull --ff-only` 成功。本设计下方及英文版本已记录实现证据、八个验证 Gate、Change Impact 和 Test Portfolio 表。

## 实现验证（2026-11-02）

范围：`fix/apmplus-ttft` 相对 `d9ef697b82fde94373737aae518148df348e60b0` 的工作区差异，包含新增测试和设计文件。生产代码仅修改 `timing.py` 和 `portal_metrics.py`。没有无关用户改动。逐请求标准属性和 Histogram 记录已实现；最终仓库级验证存在一项已复现的基线失败，详见下方。

### Gate 状态

| Gate | 状态 | 证据或阻碍原因 |
| --- | --- | --- |
| Change Basis | PASS | 已检查相对 PR head 的全部已跟踪/未跟踪差异；新分支已从该 head 同步。 |
| Contract | PASS | FR-1..6 与 CON-7..9 保留旧字段，并定义标准 SDK 请求字段、单位、省略规则及指标归属。 |
| Impact | PASS | 下方 R-1..4 覆盖 Span、指标、生命周期和维护文档。无依赖清单、UI、载荷或部署变更。 |
| Portfolio | PASS | 受控时钟、真实 OTel reader/exporter、受控供应商边界下的真实模型适配器、故障注入及既有回归。 |
| Baseline | PASS | 实现前新增测试 13 项失败、5 项通过；缺少属性和指标观测导致预期失败。 |
| Execution | BLOCKED | 默认回归 7950 项通过、1 项已复现基线 MIME 失败。定向/受影响、静态及文档检查通过；不声明仓库级检查通过。 |
| Evaluation | PASS | 覆盖全部变更生产可执行行和变更分支；断言能识别错误单位、重复/缺失样本和错误 Span 范围。 |
| Handoff | PASS | 交付范围内实现及证据，并明确基线回归限制；未提交或推送。 |

### Change Impact

| Change ID | 变更契约 | 受影响面 | 仓库证据 | 失败模式 | 风险 |
| --- | --- | --- | --- | --- | --- |
| FR-1/2/4 | CON-7 逐请求标准属性 | LiteLLM/Ark 请求 Span 及导出 | `ModelTiming`、真实适配器测试 | 模式/类型/单位/起点错误；伪造或聚合 Span 残留 TTFT | R-1 Medium |
| FR-3/6 | CON-8/9 逐请求 Histogram | 全局指标链路 | `record_model_ttft`、真实 `InMemoryMetricReader` | 重复/遗漏样本、依赖 usage/trace、维度错误 | R-2 Medium |
| FR-4/5 | CON-8 生命周期和失败 | 流式、重试、取消、关闭 | 计时/适配器测试及指标故障注入 | 遥测替换模型异常/输出；请求混淆或泄漏 | R-3 High |
| FR-1..6 | 增量兼容及文档 | 旧属性、tracing 页面、组件契约 | 既有回归、双语检查、文档构建 | 消费者获得冲突定义或丢失旧属性 | R-4 Medium |

R-1/2/4 跨可观测契约，定为 Medium。R-3 可能影响常用路径的模型完成行为（影响和暴露均为 High），验证前定为 High。没有已知但未追踪的重要消费者。残余风险以本地受控供应商验证为界，不声明新增云端真实导出验证。

### Test Portfolio

| Risk ID | 边界 | 方法 | 场景 | 判定依据 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| R-1 | SDK 计时及 Span exporter | 时钟控制、契约测试 | 文本/推理/工具输出、模式、空/不支持、负/零间隔、重试范围 | 精确浮点秒数、布尔模式、仅子 Span 标准字段、正确缺失 | 新增 TTFT 测试及既有 LiteLLM/Ark 适配器断言 | VERIFIED |
| R-2 | 真实 OTel metrics reader | 集成/状态转换 | 无 usage、无录制 Span、无 exporter、重复 chunk/最终回调、重试/并发 | Histogram 类型/名称/单位、精确 count/sum、模型隔离、安全维度全集 | 新增 TTFT 测试；既有 Portal provider/延迟 provider 测试 | VERIFIED |
| R-3 | SDK 流及 recorder 边界 | 故障注入、生命周期测试 | 首输出前后异常/取消/关闭；指标失败 | 保留原异常与清理；已观测样本保留；有限诊断不含错误详情 | 新增 TTFT 测试及既有计时、适配器生命周期测试 | VERIFIED |
| R-4 | 消费者与文档 | 回归、类型/构建、静态评审 | 旧属性、导出、双语标识符/链接 | 既有断言通过；定义等价且文档构建有效 | 受影响套件、pre-commit、文档检查 | VERIFIED |

### 已执行证据

- 生产修改前，`uv run --extra dev pytest tests/test_model_ttft.py -q`：**13 failed、5 passed**（收集/执行 18 项）。这是预期 RED 结果。
- 增加最终回调及无 exporter 场景后，`uv run --extra dev pytest tests/test_model_ttft.py -q`：**20 passed**，零失败/跳过。已断言负时钟诊断。
- `uv run --no-sync --extra dev pytest tests/models tests/test_model_ttft.py tests/test_model_timing.py tests/test_portal_metrics.py tests/test_tracing.py tests/test_tracing_content.py tests/test_inmemory_exporter.py -q --cov=veadk --cov-branch --cov-report=json:/tmp/veadk-ttft-coverage-final.json`：**156 passed**，零失败/跳过（收集/执行 156 项）。
- 生产变更行覆盖率取工作区新增行与 coverage.py 可执行行的交集：**21/21（100%）**，变更分支 **4/4** 已覆盖。没有新增覆盖率排除。Portal metrics 既有无关分支缺口不在本次差异中。
- `uv run --extra dev pre-commit run --all-files` 及新增文件显式检查：**pass**。Ruff 首次格式化测试改动后，后续检查通过。不适用的 hook 标为跳过，不算已执行。
- `npm --prefix docs run types:check` 与 `npm --prefix docs run build`：**pass**。双语代码标识符/命令、相对链接、新增测试函数长度以及 `git diff --check`：**pass**。
- 既有 `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes` 在未修改的 `d9ef697b` 快照同样失败：预期 `text/markdown`，实际 `application/octet-stream`。快照加载了自身未修改的 `writer.py`、`service.py`、`timing.py`；定向运行结果为 **1 failed**。没有修改断言或无关生产代码来隐藏该失败。
- `uv run --extra dev --extra sandbox --extra extensions --extra codex pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q`：**fail：7950 passed、1 failed、53 skipped、4 xfailed**，另有 **6 项子测试通过**，耗时 412.98s。选中 8008 项；执行 7955 项（含预期失败）；跳过 53 项。唯一失败为上述未修改的基线 MIME 测试。两个 worker 遵循仓库要求；跳过/预期失败不证明相关行为。真实云/供应商测试：**not_run**，不在批准的本地范围内。外部执行引擎 smoke：**not_applicable**，这些引擎未变更。

最终评审确认：指标由既有首次输出状态唯一触发；耗时从保存的 SDK 起点计算，不使用父 Span 计时；指标记录不受 `span.is_recording()` 限制。仅捕获并诊断 instrument 记录异常，不拦截模型异常。保留现有时间戳。已知基线 MIME 不匹配是仓库级检查限制，不属于 TTFT 验收证据。

## 提交与推送验证（2026-11-02）

用户已明确授权提交和推送。PR #1190 已通过 squash 合并为 `c1d4096d`；修复分支已 rebase 到 fetch 后的 `origin/main`：`65f30f2881b5d09aca94ea0c5e3450852866748f`，没有重复应用原 PR 提交。生产修复差异保持不变。

同步后，`uv run --no-sync --extra dev pytest tests/models tests/test_model_ttft.py tests/test_model_timing.py tests/test_portal_metrics.py tests/test_tracing.py tests/test_tracing_content.py tests/test_inmemory_exporter.py -q` 的 **156 项测试全部通过**。`uv run --no-sync --extra dev pre-commit run --all-files` 通过。

`uv run --no-sync --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q` 结果为 **8044 passed、1 failed、55 skipped、4 xfailed**，另有 **6 项子测试通过**，耗时 407.20s。唯一失败仍为此前已复现的基线 Markdown MIME 不匹配；其生产/测试文件在原 PR head 与同步后基线之间没有变化。仓库级检查仍为 `fail`，没有放宽断言。本次授权包含推送 `fix/apmplus-ttft`，不包含新建另一个 PR。

## 已批准的仅标准字段修订（2026-11-02）

用户明确不考虑已有消费者，并授权立即实施。本修订替代 FR-1/2/4/5/6 中保留自定义遥测的决定：移除全部 `veadk.request.*` / `veadk.model.*` 计时属性及自定义首 Token 事件。原生 HTTP/Runner Span 负责请求起止时间；SDK Span 将精确 SDK 开始时间设为原生 `start_time`。只保留标准流式与 TTFT 属性/Histogram。失败请求使用 Status `ERROR` 和有限类别的 `error.type`；区分超时、取消，主动关闭生成器不算错误。不采集异常正文。

同步请求上下文传递、最终遥测/导出器钩子、计时/适配器测试及双语文档。保留生成器 yield 隔离、流清理、独立重试、无 usage 指标及无输出省略行为。验证无自定义属性/事件、精确原生起点、请求/模型父子关系、错误状态/隐私及原响应行为。原生请求 Span 替代请求开始属性，不删除请求计时能力。用户已批准该契约变化，无需旧别名或兼容桥接。上方历史测试结果仅适用于前一修订。

### 仅标准字段实现与证据（2026-11-02）

比较基线：`95fd4c63`；工作区差异按用户明确要求替代自定义遥测，不保留兼容别名。生产修改仅包含 `timing.py`、移除 `telemetry.py` 中最终响应注解、移除 `inmemory_exporter.py` 中导出器注解。原生请求 Span 保留请求边界计时，并在生产者推进/关闭时绑定上下文，不跨 yield 泄漏。应用工厂和 Runner 复用既有安装点。本修订不包含凭证、依赖清单、部署、提交或推送变更。

| Gate | 状态 | 证据或限制 |
| --- | --- | --- |
| Change Basis | PASS | 已检查相对 `95fd4c63` 的全部工作区差异；无无关修改。 |
| Contract | PASS | 用户批准删除；更新的 CON-1..9 使用原生区间及标准属性/状态。 |
| Impact | PASS | S-1..4 覆盖请求/模型 Span、回调/导出器、生命周期和文档。 |
| Portfolio | PASS | 原生 Span 与 Histogram 断言、供应商边界测试、HTTP/Runner 测试、故障注入及回归。 |
| Baseline | PASS | 四个新增回归场景在实现前失败，实现后通过。 |
| Execution | BLOCKED | 范围内检查通过；默认回归保留此前已复现的无关 MIME 失败。 |
| Evaluation | PASS | 覆盖 56/56 个变更生产可执行行；无缺失变更分支。 |
| Handoff | PASS | 本地实现与限制已记录；无兼容别名或未经验证的云端声明。 |

#### Change Impact

| Change ID | 变更契约 | 受影响面 | 仓库证据 | 失败模式 | 风险 |
| --- | --- | --- | --- | --- | --- |
| Standard-only | CON-1/2/6/7 | 请求/模型 Span 及导出 | `timing.py`、注解移除 | 自定义字段残留；原生区间或父子关系错误 | S-1 Medium |
| Standard-only | CON-3/4/8/9 | TTFT 和 Histogram | 既有 recorder 与计时/适配器测试 | 样本遗漏/重复或单位改变 | S-2 Medium |
| Standard-only | CON-5 | 请求上下文、重试、失败/关闭 | 中间件、Runner 包装、真实 SDK 适配器 | 上下文泄漏、状态错误、原异常或清理丢失 | S-3 High |
| Standard-only | CON-1..9 | 双语契约与用户文档 | 更新的 tracing MDX 和组件文档对 | 把旧自定义字段契约表述为现状 | S-4 Medium |

#### Test Portfolio

| Risk ID | 边界 | 方法 | 场景 | 判定依据 | 证据 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| S-1 | OTel exporter 和 ASGI/Runner | 契约/集成 | 精确模型起点、读取 body 前请求范围、父子关系、未知模式 | 原生时间/父子关系；零自定义属性/事件 | 84 项定向与 294 项受影响测试 | VERIFIED |
| S-2 | 真实 OTel reader 和适配器 | 受控时钟/状态转换 | 所有输出类型、无输出/usage、重试、不采样 Trace、指标失败 | 精确秒数/count/sum 及省略规则 | 定向/受影响测试保留先前 Histogram 断言 | VERIFIED |
| S-3 | 异步生产者和请求 Span | 故障注入/并发 | 超时、取消、主动关闭、关闭异常、HTTP 5xx、继承范围 | 原始异常/输出；正确 ERROR/error.type；无异常正文；上下文恢复 | 定向/受影响测试及默认回归 | VERIFIED |
| S-4 | 双语文档 | 标识符/链接评审及站点构建 | 现行仅标准字段契约和前序历史标记 | 标识符等价，类型/构建检查成功 | 文档/静态检查 | VERIFIED |

已执行检查：

- `uv run --no-sync --extra dev pytest tests/test_model_ttft.py -q -k 'only_standard or model_failure'`：实现前 **4 failed、20 deselected**；实现后 **4 passed、20 deselected**。
- `uv run --no-sync --extra dev pytest tests/test_model_timing.py tests/test_model_ttft.py tests/models/test_model_timing_adapters.py -q`：**84 passed**，零失败/跳过，包含加强的读取 HTTP body 前断言。
- `MODEL_AGENT_API_KEY=offline-test-placeholder uv run --no-sync --extra dev pytest tests/models tests/test_model_timing.py tests/test_model_ttft.py tests/test_portal_metrics.py tests/test_tracing.py tests/test_tracing_content.py tests/test_inmemory_exporter.py tests/test_runner.py tests/runner/test_runner_contract.py tests/integrations/agentkit/test_app.py tests/cloud/test_harness_app_contract.py tests/cloud/test_harness_app_http.py -q --cov=veadk --cov-branch --cov-report=json:/tmp/veadk-standard-coverage.json`：**294 passed**，零失败/跳过。该值为合成占位值，供应商调用受控。生产变更可执行行覆盖率：**56/56（100%）**；没有添加覆盖率排除。
- `uv run --no-sync --extra dev pytest -n 2 -m 'not codex_smoke and not piagent_smoke' -q`：**8053 passed、1 failed、55 skipped、4 xfailed**，另有 **6 项子测试通过**，耗时 422.58s。唯一失败为此前已复现的 `test_success_uses_trusted_scope_and_hashes_utf8_bytes` 基线不匹配。该失败涉及的生产/测试文件未修改。没有隐藏失败或放宽断言。
- `uv run --no-sync --extra dev pre-commit run --all-files`：格式化后 **pass**，包含 Ruff 与密钥扫描。`npm --prefix docs run types:check`、`npm --prefix docs run build`、双语标识符、相对链接、函数长度及 diff 空白检查：**pass**。
- 真实云/供应商验证：**not_run**，超出本次授权的本地范围。原功能的云端证据不能证明新的 Span 拓扑。剩余兼容性影响是有意删除自定义字段，以及增加原生请求父 Span。

发布授权（2026-11-02）：用户明确要求提交并推送仅标准字段修订。Fetch 确认远端基线 `65f30f28` 和分支 head `95fd4c63` 未变化；rebase 到 `origin/main` 已是最新。同步后 294 项受影响测试及所有适用 pre-commit 检查通过。此前记录的全量回归基线限制未变化。
