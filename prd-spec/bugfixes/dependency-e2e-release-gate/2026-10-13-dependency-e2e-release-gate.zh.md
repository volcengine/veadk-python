# 依赖 E2E 发布门禁

[English](2026-10-13-dependency-e2e-release-gate.md)

| 字段 | 值 |
| --- | --- |
| 变更 ID | `dependency-e2e-release-gate` |
| 创建日期 | 2026-10-13 |
| 状态 | approved |
| 组件规格 | 无组件契约影响；本变更只增加发布期的包元数据和依赖解析校验。 |

## 背景

本次依赖问题说明：本地 `uv.lock` 可用不代表 PyPI 用户可用。VeADK 可能发布出允许 pip 解析到未适配上游版本的元数据，也可能把共享基础依赖 pin 得过死，导致原本兼容的上游依赖栈无法安装。

## 目标和非目标

| 类型 | 范围 |
| --- | --- |
| 目标 | 发布到 PyPI 前，如果构建出的 wheel 无法在干净环境安装，则阻塞发布。 |
| 目标 | 暴露高风险 direct dependency 升级后与当前 runtime pin 或其它包元数据冲突的问题。 |
| 目标 | 拒绝高风险无上限 runtime 依赖，以及 OpenTelemetry 共享依赖 exact pin。 |
| 非目标 | 不穷举所有 optional extra、Studio/docker/sandbox runtime，且不调用真实云服务。 |

## 需求

| ID | 需求 |
| --- | --- |
| FR-1 | tag 发布 workflow 必须在上传 PyPI 前，将构建出的 wheel 安装到干净 venv，执行 `pip check` 和最小 import smoke。 |
| FR-2 | tag 发布 workflow 必须验证选定高风险 base runtime direct dependency 在 VeADK 声明范围内当前可用最高版本，能否和构建出的 wheel 当前 runtime pin 一起解析。 |
| FR-3 | 策略检查必须拦截无上限 `google-adk` 和 exact pin 的 `opentelemetry-*` runtime 依赖。 |
| FR-4 | 检查必须基于发布产物，而不是开发者的 `uv.lock` 环境。 |

## 设计

| 部分 | 决策 |
| --- | --- |
| 脚本 | 新增 `scripts/check_dependency_e2e.py`，提供 `policy`、`clean-install`、`declared-range` 命令。 |
| Workflow | 在 PR 和 push 上暴露独立的 `dependency-policy-gate`；clean install 和 declared-range 重检查只在 tag 发布或手动 workflow dispatch 时运行。 |
| 依赖范围 | 只检查选定高风险 base 依赖：`google-adk`、`agentkit-sdk-python`、OpenTelemetry packages、`litellm`、`mcp`、`fastmcp`、`tos` 和 `jsonschema`；每个候选升级都会和完整 wheel metadata 一起解析，包括精确 runtime pin。optional extras 后续再扩展。 |
| 开发规范 | 增加仓库级 dependency metadata 规范，要求开发者和 coding agent 在重 E2E 发布门禁前先规避高风险依赖无上限、无理由 shared base pin、只依赖 `uv.lock` 验证等问题。 |
| Runtime smoke | 只 import `veadk`、`google.adk`、`opentelemetry`；不需要凭据，也不访问外部服务。 |

## 任务

| ID | 工作 | 需求 |
| --- | --- | --- |
| T-1 | 新增依赖 E2E 脚本。 | FR-1, FR-2, FR-3, FR-4 |
| T-2 | 增加依赖策略和最高版本选择的单测。 | FR-2, FR-3 |
| T-3 | 将脚本接入 tag 发布 workflow 和 PR 可见的 dependency policy gate。 | FR-1, FR-2, FR-4 |
| T-5 | 在 pre-commit 中对依赖元数据改动执行 policy 检查。 | FR-3 |
| T-6 | 为开发者和 coding agent 记录仓库级 dependency metadata 规范。 | FR-2, FR-3 |
| T-4 | 如果新检查暴露已有依赖冲突，则修正 runtime dependency metadata。 | FR-2, FR-3 |

## 验收

| 需求 | 任务 | 标准 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1 | T-1, T-3 | PyPI 上传前存在 clean wheel install 门禁。 | `uv run --extra dev pytest tests/test_dependency_e2e.py` | pass |
| FR-2 | T-1, T-2, T-3 | 已实现并单测覆盖选定高风险 direct dependency 最高声明版本与当前 runtime pin 的兼容检查。 | `uv run --extra dev pytest tests/test_dependency_e2e.py`；`uv run python scripts/check_dependency_e2e.py --dist-dir <tmp-dist> declared-range` | pass |
| FR-3 | T-1, T-2, T-4 | `google-adk` 必须有上限，`opentelemetry-*` 不允许 exact pin。 | `uv run python scripts/check_dependency_e2e.py policy` | pass |
| FR-4 | T-3 | Workflow 检查 `dist/*.whl`，不依赖 `uv.lock`。 | workflow diff review | pass |
| FR-3 | T-5 | 修改 `pyproject.toml` 时，本地 pre-commit 会执行同一 runtime dependency policy 检查。 | `uv run --extra dev pre-commit run --all-files` | pass |
| FR-2, FR-3 | T-6 | `AGENTS.md` 已记录高风险依赖上限、shared base pin、直接依赖声明和重 E2E 延后执行等 dependency metadata 规则。 | guideline diff review | pass |

## 风险

| 风险 | 缓解 |
| --- | --- |
| PyPI 状态在发布后仍可能变化。 | tag 发布时运行门禁，必要时也可手动预检。 |
| 最高版本安装检查比普通单测慢。 | 只检查选定高风险依赖，且重检查只在 tag 发布或手动 workflow dispatch 时运行。 |

## 评审记录

用户在会话中审阅 E2E 方案后批准开始实现。直接评审结论：本变更不改变公开 SDK 行为和运行时契约，因此无需更新组件 spec。

## 验证记录

| 日期 | 命令 | 结果 | 说明 |
| --- | --- | --- | --- |
| 2026-10-13 | `uv lock` | pass | 依赖边界调整后刷新 lock metadata。 |
| 2026-10-13 | `uv run --extra dev pytest tests/test_dependency_e2e.py` | pass | 11 个测试通过。 |
| 2026-10-13 | `uv run python scripts/check_dependency_e2e.py policy` | pass | Runtime dependency policy 通过。 |
| 2026-10-13 | `uv run python scripts/check_dependency_e2e.py --dist-dir <tmp-dist> declared-range` | pass | 已验证选定高风险依赖的声明范围最高版本，包括 `google-adk==2.7.1`、`opentelemetry-exporter-otlp==1.42.1`、`opentelemetry-instrumentation-logging==0.63b1`、`fastmcp==3.4.8`、`tos==2.8.7` 和 `jsonschema==4.23.0`。 |
| 2026-10-13 | `uv run python scripts/check_dependency_e2e.py --dist-dir <tmp-dist> clean-install` | blocked | 本地下载 `google-adk` 过慢后中断；workflow 已接入该门禁，会在 GitHub Actions 上传前执行。 |

## E2E 暴露出的依赖元数据调整

| 依赖 | 调整前 | 调整后 | 原因 |
| --- | --- | --- | --- |
| `opentelemetry-exporter-otlp` | `>=1.37.0` | `>=1.37.0,<1.43` | `google-adk 2.7.x` 将 OpenTelemetry SDK/API 限制在 1.42 线。 |
| `opentelemetry-instrumentation-logging` | `>=0.56b0` | `>=0.56b0,<0.64` | 0.64+ instrumentation 会解析到 `google-adk 2.7.x` 不允许的新版 OpenTelemetry 包。 |
| `fastmcp` | `>=2.12.3` | `>=2.12.3,<4` | `fastmcp 4.x` 要求 `mcp>=2`，但 VeADK 当前声明 `mcp==1.26.0`。 |
| `tos` | `>=2.8.4` | `>=2.8.4,<2.9` | `tos 2.9.x` pin 了 `wrapt==1.16.0`，与 VeADK 的 `wrapt==1.17.2` 冲突。 |
| `jsonschema` | `>=4.23,<5` | `>=4.23,<4.24` | `litellm 1.83.x` pin 了 `jsonschema==4.23.0`；原范围夸大了可安装版本。 |
