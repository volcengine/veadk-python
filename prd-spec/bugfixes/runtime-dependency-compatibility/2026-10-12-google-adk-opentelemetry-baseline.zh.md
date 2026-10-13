# 对齐 Google ADK 与 OpenTelemetry 的包依赖元数据

[English](2026-10-12-google-adk-opentelemetry-baseline.md)

- 变更 ID：`runtime-dependency-compatibility`
- 创建/修订日期：2026-10-13
- 状态：implemented
- 相关组件规格：[Runtime dependency compatibility](../../../specs/runtime-dependency-compatibility/README.zh.md)
- 范围：主包依赖元数据、主开发 lock、元数据回归测试，以及最小 ADK 2.7 build-graph/Studio 兼容覆盖。Studio、sandbox、生成项目、托管 sidecar 和 Docker 依赖声明有意不在本次范围内。

## 背景与证据

两个上游 Google ADK commit 修复了 session event 时间戳确定性以及 UTC 存储/过滤问题：

- `4ca975eb9acd30a64b2c8615a93d31dada63052c`：`fix(sessions): make event reads deterministic and timezone-correct`
- `1b8ed3d9c0b125852df1902dd32b65bcab63ce1d`：`fix(sessions): store and filter event timestamps in UTC`

这些修复从 Google ADK `2.7.0` 开始可用。VeADK 本地 lock 此前解析到 Google ADK `2.2.0`。

已确认的 resolver 阻塞点是：

- AgentKit SDK 旧的 OpenTelemetry 上限；该问题已通过发布 `agentkit-sdk-python==0.8.9` 修复。
- VeADK 直接声明的 `opentelemetry-exporter-otlp==1.37.0` 精确 pin。

2026-10-13 的全新 resolver 证据显示，不加上限的 `google-adk>=2.7.0` 会选择 `google-adk==2.11.0`。目标兼容测试在该版本线上失败，因为 ADK 2.11 移除或改变了 VeADK 仍在 patch 的内部入口，包括 `google.adk.flows.llm_flows.functions.__call_tool_async`；piagent 工具执行还会在测试 invocation context 上遇到缺失 `run_config` 的问题。因此本 PR 将当前支持窗口定义为 `google-adk>=2.7.0,<2.8.0`。

## 目标

- 将 VeADK 的 Google ADK 需求提升到 `google-adk>=2.7.0,<2.8.0`，确保包含 UTC session 时间戳修复，同时避开已知 ADK 2.8+ 兼容风险。
- 保持 VeADK 的 AgentKit 需求为灵活的 `agentkit-sdk-python>=0.8.5`，使全新安装可以解析到 `0.8.9`，但不做精确 pin。
- 保持 VeADK 直接的 OpenTelemetry exporter 依赖为灵活的 `opentelemetry-exporter-otlp>=1.37.0`。
- 将主开发 `uv.lock` 更新到当前兼容解析。
- 保持回归测试覆盖的 ADK 2.7 build-graph 与 Studio lazy GenAI 行为。

## 非目标

- 不在本次变更中修改 Studio、sandbox、生成项目、托管 sidecar 或 Docker 依赖声明。
- 不把 VeADK pin 到 `agentkit-sdk-python==0.8.9`。
- 不在本 PR 支持 ADK `2.8.0` 或更高版本；这需要单独适配已变化的 ADK 内部 API。
- 不发布包、Docker 镜像、sandbox 镜像或 Studio 资产。

## 需求

- `FR-1`：基础依赖必须使用 `google-adk>=2.7.0,<2.8.0`，eval extra 必须使用 `google-adk[eval]>=2.7.0,<2.8.0`。
- `FR-2`：包元数据必须保持 `agentkit-sdk-python>=0.8.5`。
- `FR-3`：包元数据必须使用 `opentelemetry-exporter-otlp>=1.37.0`，而不是精确 pin。
- `FR-4`：主 `uv.lock` 元数据必须反映更新后的包元数据，并将 Google ADK 解析到兼容的 2.7.x 版本。
- `FR-5`：回归测试必须覆盖包元数据和 lock 元数据。
- `FR-6`：ADK build-graph 序列化在 ADK 2.7.x 下必须继续暴露 VeADK 嵌套 `sub_agents`。
- `FR-7`：Studio 启动测试必须继续验证 ADK 2.7.x telemetry API 下的 lazy GenAI model 加载。

## 设计与契约影响

更新发布包依赖元数据和主开发 lock：

- `google-adk>=2.7.0,<2.8.0`
- `agentkit-sdk-python>=0.8.5`
- `opentelemetry-exporter-otlp>=1.37.0`

`google-adk[eval]` 使用同样的 `>=2.7.0,<2.8.0` 窗口。`harness-sidecar` optional dependency 保持相同的 AgentKit 下限。

`google-adk<2.8.0` 上限是有意设置的。目标测试已复现 ADK 2.11 不兼容，因此该上限避免全新安装选择当前未验证的 ADK 2.8+ 版本。

ADK 2.7 的 graph serializer 会跳过 Pydantic 中标记 `exclude=True` 的字段；VeADK 的 `Agent.sub_agents` 使用了该标记。因此 build-graph 兼容 patch 只在 ADK 原生序列化结果缺失 `sub_agents` 时，从运行中的 VeADK agent 补回子 Agent。

ADK 2.7 在 Studio 测试路径中不再暴露 `_experimental_semconv.transformers`。测试现在 fallback 到 `google.genai.models.t`，同时保留“Studio 在首次真正使用前延迟加载真实 GenAI models 模块”的断言。

本次变更不引入持久化状态、安全边界或公开 Python API 变化。

## 实施任务

| 任务 | 需求 | 影响文件 |
| --- | --- | --- |
| `T-1` | `FR-1`, `FR-2`, `FR-3` | `pyproject.toml` |
| `T-2` | `FR-4` | `uv.lock` |
| `T-3` | `FR-5` | `tests/test_runtime_dependency_compatibility.py` |
| `T-4` | `FR-6` | `veadk/utils/patches.py`, `tests/cli/test_frontend_trace.py` |
| `T-5` | `FR-7` | `tests/cli/test_studio_startup_imports.py` |
| `T-6` | all | PRD/spec 对齐和验证记录 |

## 验证与验收

| 需求 | 验收标准 | 结果/证据 |
| --- | --- | --- |
| `FR-1` | 包元数据使用 `google-adk>=2.7.0,<2.8.0` 和 `google-adk[eval]>=2.7.0,<2.8.0` | pass |
| `FR-2` | 包元数据保留 `agentkit-sdk-python>=0.8.5` | pass |
| `FR-3` | `opentelemetry-exporter-otlp>=1.37.0` 保持灵活 | pass |
| `FR-4` | `uv.lock` 元数据反映更新后的包元数据并解析 ADK 2.7.x | pass：lock 解析为 `google-adk==2.7.1` |
| `FR-5` | 目标依赖元数据测试通过 | pass |
| `FR-6` | 嵌套 VeADK agents 出现在 ADK build-graph JSON 中 | pass |
| `FR-7` | Studio lazy GenAI 启动测试在 ADK 2.7.x 下通过 | pass |

## 风险与开放问题

- 已有 lock 文件或 constraints 的用户仍可能停留在旧依赖选择，直到他们更新这些文件。
- ADK `2.8.0` 及更高版本被有意排除，直到 VeADK 适配上游内部 API 变化。
- Studio、sandbox、生成项目、托管 sidecar 和 Docker 路径仍保留现有依赖声明；如果产品负责人决定更新这些表面，应另行处理。

## 评审与批准

- 用户在 2026-10-13 明确批准在此 PR 中直接升级 ADK，并要求如果更高 ADK 版本存在不兼容就设置上限。
- 直接设计评审（`review-spec` 不可用）：已评审范围、依赖边界、lock 行为、ADK 2.7 兼容性、ADK 2.11 失败证据和中英文等价性。

## 交付记录

### 验证（2026-10-13，working diff）

| 检查 | 结果 |
| --- | --- |
| `google-adk` PyPI 版本检查 | pass：观察到最新稳定版为 `2.11.0`；不设上限的 `>=2.7.0` 会选择更新版本线 |
| 在无限制 `>=2.7.0` 下运行 `uv lock --upgrade-package google-adk` | fail（针对兼容范围）：解析为 `google-adk==2.11.0`；目标测试因 ADK 内部变化失败 |
| 在 `>=2.7.0,<2.8.0` 下运行 `uv lock --upgrade-package google-adk` | pass：解析为 `google-adk==2.7.1` |
| `uv run --extra dev pytest -q tests/test_runtime_dependency_compatibility.py tests/extensions/harness/test_sidecar_wheel.py::test_wheel_metadata_keeps_sidecar_optional_and_sdk_constraints_aligned tests/cli/test_frontend_sandbox.py::test_snapshot_metadata_survives_older_sdk_and_scopes_cards tests/runtime/piagent/test_piagent_runtime.py::test_piagent_runtime_emits_canonical_bridge_tool_events tests/runtime/piagent/test_piagent_runtime.py::test_piagent_runtime_exposes_before_model_added_tools tests/test_adk_sync_tool_thread_pool_patch.py::test_run_code_uses_agent_thread_pool_when_configured tests/tools/builtin_tools/create_agent/test_create_agent_toolset.py::test_runner_transfers_from_create_agents_to_dynamic_sub_agent tests/cli/test_frontend_trace.py::test_build_graph_serializes_nested_veadk_agent_models tests/cli/test_studio_startup_imports.py::test_studio_fast_api_defers_genai_models_until_first_request tests/cli/test_studio_startup_imports.py::test_studio_deferred_genai_models_support_openapi_first_use` | pass：11 passed |
| `uv run --extra dev pre-commit run --all-files` | pass |
| `git diff --check` | pass |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail：6913 passed，55 skipped，4 xfailed，16 failed。该失败运行包含已在本变更中修复的旧断言，以及在 `--extra dev` 下缺少 optional `openai_codex` 包的 Codex runtime 测试。Codex 失败子集在 `--extra codex` 下通过。 |
| 对 10 个失败的 Codex runtime 测试运行 `uv run --extra dev --extra codex pytest -q` | pass：10 passed |

本次变更已完成主包依赖和 ADK 2.7 兼容范围。Studio、sandbox、生成项目、托管 sidecar 和 Docker 依赖声明延后处理。
