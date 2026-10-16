# Runtime DeepSeek Harness 组件

[English](README.md)

## 元数据与范围

- **组件 ID：** `runtime-deepseek-harness`
- **状态：** active
- **修订日期：** 2026-10-15
- **所属代码：** `veadk/runtime/deepseek_harness/`、`veadk/runtime/__init__.py`、`veadk/agent.py` runtime 字段、runtime 支持矩阵条目。
- **主要测试：** `tests/runtime/deepseek_harness/`
- **相关 PRD：** [DSH Runtime](../../prd-spec/features/deepseek-harness-runtime/2026-10-15-deepseek-harness-runtime.zh.md)
- **依赖组件：** Agent execution、runtime compatibility、optional dependency metadata、用户 runtime 文档。

## 职责与非目标

本组件负责 `Agent(runtime="dsh")` 与本地 DeepSeek Harness SDK runtime 之间的 Python SDK 桥接。它解析 runtime 配置，管理长期 SDK 对象和显式 `DSH_HOME`，把 VeADK session 身份映射到 DSH session 身份，通过 DSH 原生工具插件桥接 ADK/MCP 工具，通过 DSH 原生 filesystem skill provider 桥接 skills，并输出 ADK 兼容的 partial、工具和最终回复 event。

它不负责 DSH profile 行为、DSH 内部 provider 鉴权语义、bundled binary 构建流水线、Studio 独立的 DeepSeek Harness sandbox 流程、在 DSH 原生 skill loader 内执行 ADK skill checklist，或 descendant session 的 UI 完整投影。

## 入口与依赖

- 公开 runtime 取值：`Agent(runtime="dsh")`。
- 公开配置导入：`from veadk.runtime.deepseek_harness import DeepSeekHarnessRuntimeConfig`。
- 可选依赖：`veadk-python[dsh]`，安装 `deepseek-harness-sdk==0.1.5rc1` 和匹配的传递依赖 `deepseek-harness-runtime-bin`。
- 外部 SDK import：`deepseek_harness`。
- Runtime 调度：`veadk.runtime.get_runtime("dsh")`。

## 契约

- **CON-1 — Runtime 取值。** `dsh` 是稳定公开 runtime 标识。未知拼写由 `Agent` 或 `get_runtime` 拒绝。
- **CON-2 — 可选依赖。** 未安装 DSH extra 时 import VeADK 成功。解析 DSH runtime 时如果缺少 SDK，会抛出包含 `pip install "veadk-python[dsh]"` 的 `ImportError`。
- **CON-3 — 配置来源。** `deepseek_harness_runtime_config` 接受 `DeepSeekHarnessRuntimeConfig` 实例或 dict。`VEADK_DEEPSEEK_HARNESS_*` 前缀环境变量覆盖对应字段。
- **CON-4 — 模型解析。** 若 config `model` 未设置，runtime 使用 `Agent.model_name` 的第一项。ADK before-model callbacks 可以修改 `llm_request.model`；runtime 会用修改后的模型选择 DSH manager 和 SDK config。
- **CON-4a — Provider 别名。** Config `provider` 是面向用户的 provider 名称，默认 `deepseek-official`；空值会归一到该默认值。`openai`、`volcengine`、`volcengine-ark`、`ark`、`openai-compatible` 和 `third-party` 会在构造 SDK 前映射到当前 DSH 的 `deepseek-official` adapter。未知 provider 名会原样透传，供未来 DSH 原生 adapter 使用。
- **CON-5 — 懒 sidecar。** 模块 import、runtime lookup 或 agent 构造期间不启动 DSH 子进程。SDK 对象从第一次实际 turn 开始启动。
- **CON-6 — 显式 home。** 未设置 `dsh_home` 时，runtime 创建并传入非空生成 DSH home。它不依赖隐式 `~/.dsh`。
- **CON-7 — Session 映射与短期上下文。** DSH `session_id` 对 `(app_name, user_id, session_id, agent name)` 元组稳定。Prompt 也会把可见 ADK session history 序列化进结构化 `<conversation_history>` block，保持 VeADK/ADK session state 是短期记忆的事实来源，而不是只依赖 DSH 内部 session state。
- **CON-8 — 工具桥接。** ADK function tools 和 ADK/MCP toolsets 会在 DSH run 前展开，通过生成的 `defineTool` plugin patch 注册为 DSH 原生工具，经带鉴权的 loopback bridge 在 Python 侧执行，并输出 ADK tool call/response events。
- **CON-9 — 子智能体转交。** 可转交的 `sub_agents` 通过注入式 `transfer_to_agent` 工具暴露。转交响应会运行目标 agent，并抑制该 turn 的 DSH 最终文本。
- **CON-10 — Skill 桥接。** ADK `SkillToolset` 与 legacy VeADK skills 会被物料化到隔离 skill root。Runtime 通过 DSH patch 注册 `@deepseek-ai/dsh-skill`、带 `includeDefaultRoots=false` 的 `@deepseek-ai/dsh-skill-filesystem`，以及 `@deepseek-ai/dsh-tool-skill`。已物料化 skill 内容 digest 会纳入 manager key。
- **CON-11 — Event 映射。** Root-session DSH assistant stream chunks 会输出为 ADK partial model events。DSH 原生 `tool/call` 和 `tool/result` events 会输出为 ADK function call/response events，并排除 VeADK 已桥接的 Python tool 名称以避免重复。
- **CON-12 — Event 输出。** 每次完成且非转交的 DSH run 会在 ADK after-model callbacks 后输出一个包含 `RunResult.final_response` 的 ADK model event。空 DSH 最终回复表示为空的最终模型响应。
- **CON-13 — 不支持表面。** ADK flow-only 能力继续由 `veadk.runtime.compat` 覆盖。ADK skill checklist enforcement 与完整 descendant-session projection 不属于本组件当前契约。

## 状态与并发

有效 runtime 配置在解析 model、provider、DSH profile、home、路径、timeout、显式环境覆盖、已桥接 DSH tool schema digest 和已物料化 skill 内容 digest 后形成 key。每个 key 拥有一个 `DeepSeekHarness` 实例、适用时生成的 `dsh_home`、存在工具时的长期 tool bridge/plugin patch，以及存在 skills 时的 DSH 原生 skill patch/root。Manager 在进程退出时关闭。

共享同一 manager 的 turn 使用 async lock 串行执行。这避免对同一个 SDK stdio client 做未文档化的并发访问。不同 manager key 可以独立运行。

当前同步 SDK 无法可靠地从外层 task 取消一个进行中的 DSH `run()`。组件会在可行时于取消时关闭 manager，但不承诺优雅的 per-turn cancellation。

Tool bridge 只在 manager lock 拥有活跃 turn 时接受调用。缺少 per-manager bearer token 或缺少活跃 ADK tool bundle 的请求会被拒绝。

## 数据与配置

配置字段：

- `provider`、`model`、`reasoning_effort`、`max_tokens`
- `cwd`、`runtime_cwd`、`dsh_bin`、`profile`、`patches`、`dsh_home`
- `env`、`initialize_timeout_seconds`、`request_timeout_seconds`、`shutdown_timeout_seconds`
- `base_url`、`api_key`

环境变量覆盖：

- `VEADK_DEEPSEEK_HARNESS_PROVIDER`
- `VEADK_DEEPSEEK_HARNESS_MODEL`
- `VEADK_DEEPSEEK_HARNESS_REASONING_EFFORT`
- `VEADK_DEEPSEEK_HARNESS_MAX_TOKENS`
- `VEADK_DEEPSEEK_HARNESS_CWD`
- `VEADK_DEEPSEEK_HARNESS_RUNTIME_CWD`
- `VEADK_DEEPSEEK_HARNESS_DSH_BIN`
- `VEADK_DEEPSEEK_HARNESS_PROFILE`
- `VEADK_DEEPSEEK_HARNESS_DSH_HOME`
- `VEADK_DEEPSEEK_HARNESS_INITIALIZE_TIMEOUT_SECONDS`
- `VEADK_DEEPSEEK_HARNESS_REQUEST_TIMEOUT_SECONDS`
- `VEADK_DEEPSEEK_HARNESS_SHUTDOWN_TIMEOUT_SECONDS`
- `VEADK_DEEPSEEK_HARNESS_BASE_URL`
- `VEADK_DEEPSEEK_HARNESS_API_KEY`

默认 `profile` 是 `sdk-minimal`，因此 VeADK 可以注入自己负责的精确 DSH tool 和 skill 插件。调用方可以选择 DSH 更完整的 `sdk` profile；此时 VeADK 会 patch 已存在的 skill filesystem plugin 配置，而不是插入重复插件组。

## 安全与隔离

生成的 `DSH_HOME` 路径是进程拥有的临时目录。配置的 `dsh_home`、`cwd` 和 `runtime_cwd` 在使用前会 expand 并 resolve。Runtime 只通过 SDK 配置传入 `api_key` 和 `base_url`；DSH 内部脱敏由 DSH 拥有。

用户 prompt 和 session ID 都是不可信输入。Session ID 会 hash 后再嵌入 DSH 标识，不直接使用原始值。

## 兼容性与演进

本组件是新增能力。现有 runtime 取值和配置保持不变。未来只有在 PRD/spec 契约更新并通过测试覆盖后，才会增加 checklist enforcement、descendant-session projection 和更细粒度 cancellation。

## 可观测性与失败

Runtime 以不含密钥的方式记录选中的 model/provider 和 session 身份。SDK import 错误、初始化错误和运行错误会继续抛出，除非 ADK on-model-error callback 返回 fallback `LlmResponse`。

## 验证

| 契约 | 保证 | 测试或验证 | 证据 |
| --- | --- | --- | --- |
| `CON-1` 至 `CON-4a` | Runtime 调度和配置解析。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD 验证记录 |
| `CON-5` 至 `CON-7` | 懒 manager、显式 home、稳定 session ID。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD 验证记录 |
| `CON-8` | ADK tools 通过生成式 DSH plugin 和 loopback callback 桥接。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD 验证记录 |
| `CON-9` | 子智能体转交使用注入式 transfer tool 路径。 | 源码审查和桥接路径测试 | PRD 验证记录 |
| `CON-10` | Skills 通过 DSH 原生 skill 插件和隔离物料化 root 桥接。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD 验证记录 |
| `CON-11` | DSH partial 与原生 tool events 会成为 ADK events。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD 验证记录 |
| `CON-12` | 最终回复成为 ADK event。 | `uv run --extra dev pytest tests/runtime/deepseek_harness` | PRD 验证记录 |
| `CON-13` | 不支持表面已文档化并进入 gate。 | 源码/文档审查和 runtime compatibility 测试 | PRD 验证记录 |

## 变更记录

- 2026-10-15：由 `deepseek-harness-runtime` 引入 `runtime="dsh"` 的初始 active 契约。
- 2026-10-15：新增面向省略 provider、OpenAI、火山和第三方 OpenAI-compatible endpoint 的 VeADK provider 别名，并映射到当前 DSH adapter。
