# DeepSeek Harness 运行时

[English](2026-10-15-deepseek-harness-runtime.md)

## 元数据

- **变更 ID：** `deepseek-harness-runtime`
- **创建 / 修订日期：** 2026-10-15 / 2026-10-15
- **生命周期状态：** implemented
- **相关组件规格：** [Runtime DeepSeek Harness](../../../specs/runtime-deepseek-harness/README.zh.md)
- **所属区域：** `veadk.agent`、`veadk.runtime`、可选依赖、运行时文档、运行时测试。

## 背景与证据

VeADK 当前公开三个 `Agent.runtime` 取值：`adk`、`codex` 和 `piagent`。`codex` 通过 `codex` extra 安装：Python SDK 包会精确绑定匹配的二进制 wheel。`piagent` 则在首次运行时解析或下载二进制。

DeepSeek Harness 已经发布 Python SDK 包 `deepseek-harness-sdk==0.1.5rc1`。它的导入包名是 `deepseek_harness`；SDK 依赖 `deepseek-harness-runtime-bin==0.1.5rc1`，该包在支持的平台上包含 bundled `dsh` 可执行文件。SDK 要求显式 `dsh_home` 或非空 `DSH_HOME`，不会回退到 `~/.dsh`。`DeepSeekHarness` 会懒启动子进程，并在多次 `run()` 调用之间复用它。

2026-10-15 的真实 SDK 检查显示，当前 wheel 中可启动的 DSH 原生 provider 名称是 `deepseek-official`；`volcengine`、`ark`、`volcengine-ark`、`openai`、`openai-compatible`、`third-party`、`doubao` 和 `deepseek` 不是当前已注册的 DSH adapter 名。VeADK 因此负责提供面向用户的火山与第三方 OpenAI-compatible provider 别名，再把它们映射到当前接受显式 `base_url` 和 `api_key` 的 DSH adapter。

本变更刻意收窄的假设：

- DSH 原生工具插件通过已文档化的 Cordis `ctx.tools.register(defineTool(...))` 扩展路径注册。
- DSH skills 通过已文档化的原生 `@deepseek-ai/dsh-skill`、`@deepseek-ai/dsh-skill-filesystem` 和 `@deepseek-ai/dsh-tool-skill` 插件注册。
- DSH notifications 会映射 root session 的 assistant stream chunks 和原生 tool call/result events；descendant session notifications 保留给后续扩展，但不替代 root final response。

## 目标

- 增加 `runtime="dsh"` 作为公开 Python SDK runtime 取值。
- 通过 VeADK optional extra 安装 DSH SDK 及其传递依赖的 runtime binary 包。
- 在第一轮真正执行时懒启动 DSH，而不是 import 或 `Agent(...)` 构造时启动。
- 按有效运行时配置复用长期 DSH SDK 对象，并基于 VeADK app/user/session/agent 身份生成稳定 DSH session ID。
- 通过生成的 DSH 插件和本地带鉴权的 Python callback server，把 ADK function tools 和 ADK/MCP toolsets 桥接为 DSH 原生工具。
- 通过其他外部 runtime 使用的同一个注入式 `transfer_to_agent` 工具桥接 ADK 子智能体转交。
- 通过 DSH 原生 filesystem skill provider 和 `skill` loader tool 桥接 ADK `SkillToolset` 与 legacy VeADK skills。
- 把 DSH assistant deltas 和原生 tool call/result events 流式转换为 ADK events，同时保留最终回复上的 after-model callback 语义。
- 通过把可见 session history 序列化进 DSH prompt，保持 VeADK/ADK session history 是短期记忆的事实来源，与 Codex runtime 契约一致。
- Before-model callback 修改模型后，DSH 会用修改后的模型选择 SDK config 和已缓存 manager。
- 默认使用显式隔离的 `DSH_HOME`，并允许部署方配置持久目录。
- 支持不填 provider，以及面向用户的 `openai`、`volcengine`、`volcengine-ark`、`ark`、`openai-compatible` 和 `third-party` provider 别名，不要求调用方知道当前 DSH adapter 名称。
- 缺少 optional extra 时给出明确错误。
- 文档说明它与 Codex、PiAgent 生命周期的差异。

## 非目标

- 不为 `dsh` 二进制实现 VeADK 自有的首次运行下载器。
- 不声称在 DSH 原生 skill loader 内执行 ADK `enable_skills_checklist` 校验。
- 本变更不实现 descendant DSH subagent session notifications 的完整 UI 投影。
- 不修改 Studio 前端 DeepSeek Harness 行为；Studio 已有独立的 DeepSeek Harness sandbox 路径。
- 普通单元测试不执行真实 provider 调用。

## 场景与需求

- **FR-1 — Runtime 选择。** 给定使用 `runtime="dsh"` 构造的 agent，当它运行时，VeADK 调度到 DSH runtime，而不是 ADK LLM flow。
- **FR-2 — 可选依赖边界。** 给定默认 VeADK 安装中没有 DSH，当代码解析该 runtime 时，错误信息说明缺少 extra 和安装命令。
- **FR-3 — 二进制获取。** 给定安装了 `veadk-python[dsh]`，匹配的 `dsh` 二进制通过 `deepseek-harness-runtime-bin` 获得；VeADK 不做运行时下载。
- **FR-4 — 懒启动。** 给定进程 import VeADK 或构造 agent，直到 turn 到达 `DeepSeekHarnessRuntime.run_async` 前 DSH 都不会启动。
- **FR-5 — Session 身份。** 给定相同 `app_name`、`user_id`、`session_id` 和 agent 名称的重复 turn，VeADK 传入相同 DSH `session_id`。
- **FR-6 — 隔离 home。** 给定未配置 `dsh_home`，VeADK 在临时 root 下创建显式、进程所有的 `DSH_HOME` 并传给 SDK。
- **FR-7 — Callback 兼容。** 给定配置了 model callback，before/after/error model callback 在与其他外部 runtime 相同的粗粒度 per-turn 边界执行。
- **FR-8 — 工具桥接。** 给定配置了 ADK function tools 或 ADK/MCP toolsets，VeADK 通过 `defineTool` 暴露为 DSH 原生工具，在 Python 侧执行，并输出对应 ADK tool events。
- **FR-9 — 子智能体转交。** 给定配置了可转交的 `sub_agents`，VeADK 暴露 `transfer_to_agent`；当 DSH 调用它时，VeADK 运行目标 agent，并抑制该 turn 的 DSH 最终文本。
- **FR-10 — Skill 桥接。** 给定配置了 ADK `SkillToolset` 或 legacy VeADK skills，VeADK 会把它们物料化到隔离 skill root，通过 `includeDefaultRoots=false` 注册 DSH 原生 skill 插件，并把 skill 内容 digest 纳入 manager key。
- **FR-11 — Event 映射。** 给定 DSH 输出 root-session assistant stream chunks 或原生 tool call/result events，VeADK 会映射为 ADK partial model events 和 function call/response events，并避免重复输出 VeADK 桥接的 Python tool events。
- **FR-12 — Codex 对齐的短期上下文与模型 callback。** 给定存在 ADK session history，DSH 会在 prompt 中收到结构化 conversation data。给定 before-model callback 修改 `llm_request.model`，DSH 会用修改后的模型选择 manager 和 SDK config。
- **FR-13 — 如实表达限制。** 给定不支持的 ADK flow 能力，VeADK 通过现有 runtime 支持矩阵和文档告警或报错，而不是默默宣称等价。
- **FR-14 — Provider 别名。** 给定 config `provider` 未填写、为空、为 `openai`、`volcengine`、`volcengine-ark`、`ark`、`openai-compatible` 或 `third-party`，VeADK 会解析成有效的用户侧配置，并传给 DSH 当前已注册的 OpenAI-compatible adapter provider。

## 设计与契约影响

选定设计与 Codex 的依赖获取模式一致：新增 `dsh` optional extra，固定依赖 `deepseek-harness-sdk==0.1.5rc1`，由该包带入匹配的 runtime binary wheel。它优于 PiAgent 风格的首次运行下载器，因为 DSH 已经发布 SDK/runtime-bin 配对，VeADK 不应重复实现平台选择、缓存管理和版本耦合。

runtime 包路径为 `veadk.runtime.deepseek_harness`。公开配置类为 `DeepSeekHarnessRuntimeConfig`。`Agent` 增加 `deepseek_harness_runtime_config`，接受该配置或 dict。

有效 DSH 配置按以下顺序解析：

1. Agent 的 `deepseek_harness_runtime_config`。
2. `VEADK_DEEPSEEK_HARNESS_*` 前缀的窄环境变量覆盖。
3. 未设置 DSH 专用覆盖时，使用 agent 的 model name、API base 和 API key。
4. 保守默认值（`provider="deepseek-official"`、`profile="sdk-minimal"`）。`sdk-minimal` 让 VeADK 注入它自己负责的 DSH tool 和 skill 插件；调用方仍可显式选择 DSH 更完整的 `sdk` profile。

Provider 处理刻意分成两层。`DeepSeekHarnessRuntimeConfig.provider` 保持用户可见 provider 名称。空 provider 值会归一成 `deepseek-official`。Runtime 在构造 `DeepSeekHarnessConfig` 前，把 `openai`、`volcengine`、`volcengine-ark`、`ark`、`openai-compatible` 和 `third-party` 映射到当前 DSH 的 `deepseek-official` adapter。未知 provider 名会原样透传，让未来 DSH 原生 provider 不需要等待 VeADK 发版也能工作。

状态与生命周期：

- 每个有效进程配置缓存一个 `DeepSeekHarness` manager。
- manager 懒启动，并在解释器退出时关闭。
- 除非配置 `dsh_home`，生成的 `DSH_HOME` 位于进程拥有的临时 root 下。
- Manager key 包含已桥接 DSH tool schema 的 digest。存在工具时，每个 manager 拥有长期本地 tool bridge 和生成的 DSH plugin patch。
- Manager key 包含已物料化 skill 内容的 digest。存在 skills 时，每个 manager 拥有 DSH skill patch 和 skill root。
- 同一 manager 内的 turn 串行执行。每个活跃 turn 会把当前 ADK tool bundle 绑定到该 bridge，SDK 调用返回后清理绑定。
- DSH session id 是基于 VeADK app/user/session/agent 身份计算的 SHA-256 稳定 ID。
- DSH prompt 会把 callback 可见的 `LlmRequest.contents` 序列化为结构化的历史 conversation 和 current-message blocks。这让 ADK session history，而不是只靠 DSH 私有 session state，成为与 Codex 共享的可移植短期记忆契约。

安全：

- SDK 子进程默认继承进程环境，保持 DSH SDK 行为。配置的 `env`、`base_url` 和 `api_key` 是显式覆盖。
- runtime 不发明沙箱策略。DSH profile 行为由 DSH 拥有。
- Tool bridge 只接受 loopback 调用，并要求生成的 DSH 插件携带 per-manager bearer token。
- 生成的 `DSH_HOME` 避免隐式写入 `~/.dsh`。

兼容性：

- 现有 `adk`、`codex` 和 `piagent` 行为不变。
- 新 runtime 需要 runtime 取值和 extra 依赖双重显式选择。
- 缺少 extra 的失败发生在解析 runtime 时，不影响包 import。

组件契约影响：本变更改变公开 runtime 取值、optional dependency 行为、session 状态、sidecar 生命周期和配置语义，因此需要新增组件规格。

## 实施任务

- **T-1：** 新增双语 PRD/spec，定义 runtime 契约。覆盖 `FR-1` 至 `FR-8`。
- **T-2：** 新增 optional dependency extra 并同步 lock 元数据。覆盖 `FR-2`、`FR-3`。
- **T-3：** 扩展 `Agent.runtime`、新增 `deepseek_harness_runtime_config`，并从 `veadk.runtime.get_runtime` 调度。覆盖 `FR-1`、`FR-2`。
- **T-4：** 实现 `veadk.runtime.deepseek_harness` 的 config、manager、prompt 转换、生成式 DSH 工具插件、本地工具桥、原生 skill patch、event translator 和 runtime。覆盖 `FR-4` 至 `FR-12`。
- **T-5：** 扩展 runtime 兼容性警告/错误。覆盖 `FR-13`。
- **T-6：** 使用 fake `deepseek_harness` module 增加单元测试，不要求真实 binary。覆盖 `FR-1` 至 `FR-12`。
- **T-7：** 更新中英文 runtime 文档。覆盖 `FR-2`、`FR-3`、`FR-8`、`FR-10` 至 `FR-14`。

## 验证与验收

| 需求 | 任务 | 验收标准 | 测试或验证命令 | 结果/证据 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-3`, `T-6` | `runtime="dsh"` 可以构造并调度。 | `uv run --extra dev pytest tests/runtime/deepseek_harness tests/runtime/differential/test_runtime_parity.py::test_model_fallbacks_warn_for_external_runtime` | pass，2026-10-15 |
| `FR-2` | `T-2`, `T-3`, `T-6` | 缺少 SDK 时错误提示 extra 安装命令。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-3` | `T-2` | extra 声明 `deepseek-harness-sdk==0.1.5rc1`，未新增下载器。 | `uv lock --check`；源码审查 | pass，2026-10-15 |
| `FR-4` | `T-4`, `T-6` | fake SDK 在 runtime 执行前不会实例化。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-5` | `T-4`, `T-6` | 相同 VeADK session 映射到相同 DSH session id。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-6` | `T-4`, `T-6` | runtime 默认传入非空显式 `dsh_home`。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-7` | `T-4`, `T-6` | DSH 最终回复成为 ADK final event，callback 可短路。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-8` | `T-4`, `T-6` | Fake DSH 加载生成的 plugin patch，并通过 localhost bridge 调用 ADK FunctionTool。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-9` | `T-4`, `T-6` | 子智能体转交使用与其他外部 runtime 相同的注入式 transfer tool 路径。 | 源码审查；由桥接路径测试覆盖 | pass，2026-10-15 |
| `FR-10` | `T-4`, `T-6` | Fake DSH config 包含 DSH 原生 skill 插件和已物料化的隔离 skill root。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-11` | `T-4`, `T-6` | Fake DSH notifications/events 映射为 ADK partial model events 与原生 function call/response events。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-12` | `T-4`, `T-6`, `T-7` | Fake DSH 收到结构化 ADK session history，并使用 before-model callbacks 选择的模型。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |
| `FR-13` | `T-5`, `T-7` | 支持矩阵和文档表达限制。 | 源码/文档审查 | pass，2026-10-15 |
| `FR-14` | `T-4`, `T-6`, `T-7` | Provider 别名映射到当前 DSH adapter，同时保留显式 model/base/key 配置。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | pass，2026-10-15 |

发布前还需补充验证：

- 在 DSH 支持的各发布 wheel 平台做依赖安装 smoke。
- 只有在显式授权并使用隔离 API key 时运行真实 DSH live smoke。

2026-10-15 追加验证：

- `uv run --extra dev ruff check veadk/runtime/deepseek_harness tests/runtime/deepseek_harness/test_deepseek_harness_runtime.py examples/deepseek_harness_runtime/main.py` — blocked，当前 checkout 的活动环境未安装 `ruff` 可执行文件。更宽泛的 dev dependency 清理不保留，因为它超出本次 runtime 变更范围。
- `uv run --extra dev pytest tests/runtime/deepseek_harness -q` — pass，15 passed，1 warning。
- `uv run --extra dev --extra dsh pytest tests/runtime/deepseek_harness -q` — pass，15 passed，1 warning。
- `uv run --extra dev pytest tests/runtime/deepseek_harness tests/runtime/differential/test_runtime_parity.py::test_model_fallbacks_warn_for_external_runtime -q` — pass，16 passed，1 warning。
- `uv run --extra dev --extra dsh python examples/deepseek_harness_runtime/main.py --sqlite-path /tmp/veadk_dsh_runtime_acceptance_final_check.sqlite` — pass，使用已准备环境真实运行。该 live run 使用拆分后的 skill 与 memory runners，证明了示例五项检查全部通过：`streaming` 记录 2 个 partial chunks，`skill` 返回 `DSH-SKILL-OK`，`short_term_memory_sqlite` 持久化 6 条 session events 并召回 session secret，`long_term_memory_auto_save` 在切换 session 后直接检索到 1 条长期记忆，`observability` 记录 15 个匹配 spans，其中包含 5 个 `call_llm` spans。
- `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` — pass，7065 passed，50 skipped，4 xfailed，82 warnings。pytest 结果输出后，本地 metrics exporter 记录了临时 `localhost:8000` unavailable 信息，但 pytest 已成功完成。
- `npm --prefix docs run lint` — 不作为本变更的发布信号保留。临时 docs toolchain 与格式化修复已撤回，因为它们触及 DSH runtime 范围外的全站 docs 文件。
- `npm --prefix docs run types:check` — 同样因范围原因不作为本变更的发布信号保留。

## 风险与开放问题

- DSH SDK 当前为 `0.1.5rc1`；VeADK 稳定发布前应重新评估该 release-candidate pin。
- `enable_skills_checklist` 暂不在 DSH 原生 skill loading 中执行，因为该 checklist 是 ADK before-tool callback。
- Descendant DSH subagent session notifications 尚未投影成一等 ADK child-session events。
- 持久化 `dsh_home` 可能包含 DSH session 数据；部署方配置后负责保留与清理策略。

## 评审与交付记录

- 用户在 2026-10-15 认可 extra-based SDK/runtime-bin 方向并要求开始实现。
- 本会话中没有可用的仓库 `review-spec` skill，因此执行直接设计评审。结论：
  - 依赖获取不应重复 DSH 的 runtime-bin wheel 机制。
  - `DSH_HOME` 必须显式传入，因为 SDK 要求如此，也能避免全局状态。
  - ADK/MCP tools 必须使用已文档化的 DSH tool plugin 路径；skills 必须使用已文档化的 DSH 原生 skill 插件，而不是普通 tool 展开。
  - runtime 支持矩阵必须覆盖新的非 ADK runtime。
- 阻塞问题：上述限制显式写入后无阻塞。
