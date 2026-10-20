# 技能下载与指令加载可观测

[English](2026-10-16-skill-observability.md)

- 变更 ID：`skill-observability`；创建/修订：2026-10-16；状态：implemented；受影响检查通过，全量回归存在既有/环境失败。
- 契约：[skill-observability](../../../specs/skill-observability/README.zh.md)。
- 来源：AgentKit Skills 运行时可观测方案，revision 2102（2026-10-16）。
- 范围批准：用户确认提出的 Runtime/Python 工具范围，并明确纳入 `actb-mono/sandboxes/agentkit-skill`。仅本地实现；未授权提交、发布或云端操作。

## 证据、目标与边界

`VeSkillRegistry.get_skill` 获取技能包，但转换成 ADK Skill 时丢失云端身份。ADK 2.7.1 按 invocation 缓存技能，因此 registry 调用不能计作指令加载。`SkillsTool` 有耗时 histogram，但没有方案要求的 counter。Sandbox Python 固定使用 VeADK 1.1.14 / ADK 1.34.0；Go 有独立的包存储和工具适配层。两种 Sandbox 遥测初始化目前都配置 trace，没有配置 metric 导出。

按照关联契约的准确来源身份和数据结构统计技能包获取与成功指令交付。保留 SDK 签名、缓存/安装策略、既有指标、工具结果、取消和清理行为。发现、资源读取、脚本、A2A 转发和任务成功均不计作指令加载。不实现问题主动汇报、看板、新增依赖或依赖升级。AIO 协议、守护进程生命周期和隔离机制不在本次变更范围。

## 需求与场景

- FR-1：已识别来源的远端技能包获取结束时记录一次 `gen_ai_skill_download`，覆盖验证成功的磁盘缓存恢复和失败。无效缓存后重新下载属于一次获取，`cache_hit=false`。
- FR-2：成功返回指令时记录一次 `gen_ai_skill_load`。同一 invocation 两次成功 `load_skill` 计两次，即使 ADK 只获取一次。未知技能、读取失败和取消不计成功加载。
- FR-3：云端身份在转换/缓存后保留。Sandbox Python 区分内置技能、SkillHub slug、显式 AgentKit ID 和两类空间；Go 保留既有四类来源支持。来源不明的本地技能不猜测成内置技能。
- FR-4：使用既有进程级 OTEL provider；Sandbox 仅在未配置 provider 时安装周期 OTLP metric exporter。trace 与 metric 禁用开关独立。导出失败不影响对话；退出 flush 有时间上限。
- FR-5：新增遥测不记录包 URL、凭据、指令正文、路径或原始异常消息。既有内容遥测策略保持不变。
- FR-6：Python 与 Go 对已支持的来源使用相同标签和来源语义；预取只产生下载数据。保留既有安装包和会话链接。

## 设计与受影响消费者

Runtime：增加小型 `veadk/skills/telemetry.py` 记录模块，在既有 materializer 采集；将云端身份保存在 ADK frontmatter 的保留 metadata 中；在既有 VeADK 工具 tracing 回调中处理原生 ADK `LoadSkillTool` 的成功响应。不替换 toolset、不增加全局缓存。Runtime 加载采集沿用既有 VeADK tracing hook 的启用方式；hook 启用后，计数不依赖 Span 采样。

Sandbox：使用已经安装的 OTEL 包实现本地记录模块，确保已发布 SDK 无需依赖尚未发布的 VeADK 改动。在 `playground_skills/packages.py`、SkillHub 安装和既有 `ObservedSkillsTool` 采集。随安装包保存 SkillHub slug，避免替换失败时把旧内置技能标记成新的 SkillHub 技能。Go 包存储负责下载记录；目录元数据把身份传递给既有 tracked tool。内置技能不产生下载事件。在现有遥测初始化中配置 metric 导出，并复用退出 flush。

counter 从身份解析后的技能包获取开始计数。尚无技能 ID 的元数据列表失败无法产生按技能归属的下载。获取成功表示技能包通过验证且可用，不只是 HTTP 成功。Python 工作线程可能在等待任务取消后完成下载；按实际获取结果计数，但不计取消的加载。Go context 取消计入错误结果。metric 仅含契约规定的维度；`consumer`、`cache_hit` 和错误放在 Span。Span 耗时覆盖获取、验证和安装。通过 Span 计算的缓存命中率受 trace 采样影响。

## 任务、测试与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1, FR-3 | T-1：Runtime materializer、registry 与记录模块 | AC-1：网络、缓存、无效包和未知来源的身份/次数准确 | `uv run --extra dev pytest tests/skills/` |
| FR-2, FR-5 | T-2：原生 ADK 加载 hook 与回归测试 | AC-2：缓存后的重复加载计数；失败/资源/脚本不计；不泄露敏感信息 | `uv run --extra dev pytest tests/test_portal_metrics.py tests/test_tracing_content.py tests/skills/` |
| FR-1, FR-2, FR-3, FR-6 | T-3：Sandbox Python 包、安装与工具适配 | AC-3：五种来源、安装失败/缓存、slug 保留、不重复计数 | 使用隔离状态运行 Sandbox Python 定向/全模块测试 |
| FR-1, FR-2, FR-3, FR-6 | T-4：Sandbox Go 包、目录与 tracked tool | AC-4：Go 次数一致，取消/清理正确 | Sandbox `go/` 中运行 `go run ./cmd/skill-go test ./...` |
| FR-4, FR-5 | T-5：Sandbox OTLP metric 与导出测试 | AC-5：本地 HTTP collector 收到 counter；开关/provider 复用/退出有效 | Python 本地 collector 测试；Go metric exporter 测试 |
| 全部 | T-6：同步双语文档、示例与验证 | AC-6：契约成对，验证有实际证据 | SDK 回归；Sandbox `make verify`；`git diff --check` |

SDK 最终回归：`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`（两个 worker）。不运行真实云端/provider 测试。后续若获提交授权，须先同步目标基线并执行仓库 pre-commit 门禁。前端/浏览器门禁不适用：未改变 Studio 代码或 API。

## 评审、风险与交付记录

2026-10-16 直接设计评审（review-spec 不可用）：检查来源归属、缓存/加载区分、标签一致、API 兼容、错误脱敏、取消、provider 所有权与双语等价。Runtime 转发不采集、Sandbox 在适配层计数，消除重复计数；Sandbox 独立埋点，消除对未发布依赖的耦合。用户在源码访问澄清后确认 Sandbox 业务代码范围。用户还明确批准保留 Go 不支持 `sp-*` 的限制：本次只增加观测，不升级 SDK、不扩展来源支持。不对 AIO 协议作结论。

风险：原生 ADK 响应 metadata 是版本相关接入点，须用实际安装的 ADK 测试；“从未使用”仍需关联完整技能清单。新增 Sandbox exporter 增加周期后台工作，不在工具执行时同步请求网络。既有 Span 采样限制基于 trace 的缓存统计。测试基线：VeADK `d55fe8fa`；ACTB `7354ed5`。执行日期：2026-10-16。


### 实现评审

T-1 至 T-6 已实现。真实 ADK 加载响应保留 Registry 提供的身份，invocation 缓存命中后仍保留。Sandbox 分别记录安装和指令交付；Go 与 Python 读取同一份已安装 SkillHub 来源记录。技能包不能覆盖安装器写入的来源记录。无法解析来源时不猜测标签。既有公开签名、安装/回滚规则和工具结果不变。Go 仅把已经锁定的间接 metric 模块提升为直接依赖，版本和 `go.sum` 不变。

直接实现评审检查了取消、安装失败、缓存复用、provider 记录失败、成功指令边界、来源一致性、endpoint 配置及 provider 所有权。回归测试在实现前因缺少记录函数失败；实现切换来源测试在修复前复现了误标为内置技能的问题。受影响范围无遗留阻断发现。不声明已部署或容器已就绪。

启动权衡：SkillHub 同步是短生命周期进程，观测必须在退出前尽力 flush。只有实际配置 SkillHub 才初始化 exporter；空配置和仅禁用内置技能不增加遥测初始化。启动 exporter 超时为 200 ms；常规 Python metric 导出为 3 s，Go 退出共用 5 s context。本地慢 collector 实验中，两种信号均超时时，导入/初始化为 575 ms、退出为 533 ms。这只是本地样本，不代表镜像启动时间保证；开销只发生在 Python 启动安装器，不发生在每次工具调用。本地 collector 测试也验证该启动初始化的 metric 发送和 provider 复用。

### 验证记录（2026-10-16）

测试范围为 VeADK `d55fe8fa` 与 ACTB `7354ed5` 之上的未提交 diff。SDK 使用 Python 3.12.15 / ADK 2.7.1；Sandbox 使用自身 Python 环境 / ADK 1.34.0 及既有固定 Go SDK。

| 检查 | 状态 | 实际结果 |
| --- | --- | --- |
| `uv run --extra dev pytest tests/skills tests/test_portal_metrics.py tests/test_tracing_content.py -q` | pass | 120 项；覆盖真实 ADK 重复加载、缓存/错误/取消、身份、脱敏和记录失败不影响结果。 |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail | 6971 passed、16 failed、59 skipped、4 xfailed、2 项收集错误。失败需要当前未安装的可选 `llama_index`、`openai_codex` 和 `anthropic` 包；本功能未纳入无关依赖安装。使用两个 worker。 |
| Sandbox 定向 Python：`TMPDIR=/private/tmp PYTHONPATH=src MODEL_AGENT_API_KEY=local-test-placeholder OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none .venv/bin/python -m pytest tests/test_skill_observability.py tests/test_skill_reconciler.py tests/test_playground_skills.py tests/test_sandbox_agent.py tests/test_a2a_telemetry.py -q` | pass | 42 项、7 个 subtest。collector 测试在干净子进程中显式开启 metrics。 |
| Sandbox 全模块 Python：同上环境，`.venv/bin/python -m pytest tests -q` | fail | 182 passed、9 failed、20 skipped、13 个 subtest。余下九项 cleanup/迁移契约失败均在复制的 ACTB `7354ed5` 已跟踪源码上复现；新增观测测试无失败。 |
| `TMPDIR=/private/tmp go run ./cmd/skill-go test ./...`（Sandbox `go/`） | pass | 所有 Go package 通过；使用 macOS 规范临时目录，避开既有路径别名 cleanup 断言。 |
| `TMPDIR=/private/tmp go run ./cmd/skill-go test -race -run 'TestSkill|TestInstalledSkillHub' .` | pass | 受影响 Go 获取/加载/来源及 exporter 测试，开启 race 检查。 |
| `make verify PYTHON=/Users/bytedance/actb-mono/sandboxes/agentkit-skill/.venv/bin/python` | pass | 28 项根目录 smoke、shell 语法和 diff 检查；不代表容器就绪。 |
| 变更 Python 文件的 Ruff 0.11.12 检查 | pass | 使用隔离的 `uvx --from ruff==0.11.12 ruff check <changed-files>`；项目环境没有 Ruff 可执行文件。 |
| 双语配对、schema 标识符、相对链接及 `git diff --check` | pass | PRD/spec 成对同步；更新 Sandbox README 和 Unreleased 变更记录。 |
| 真实云端/镜像就绪、线上 collector 和 grpc 传输 | not_run | 未授权云端/镜像操作；本地 collector 发送采用 HTTP/protobuf。 |
| 仓库 pre-commit 与远端同步 | not_run | 未请求提交；后续获提交授权时仍必须执行。 |
| Studio/浏览器门禁 | not_applicable | 未改变 Studio 前后端契约。 |

Sandbox 初次全模块收集需要测试模型 API 值；最终命令使用占位值、禁用外部 exporter，并设置 `PYTHONPATH=src` 供子进程导入。创建内存 SDK provider 的测试局部移除 `OTEL_SDK_DISABLED`。未使用真实凭据、真实模型请求或修改全局机器配置。用户同意在此记录这些环境/工具限制。临时基线副本在对比后删除。受影响检查验证了本地实现行为，全仓验收尚未全绿。
