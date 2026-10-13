# 运行时依赖兼容性

[English](README.md)

- **Component ID:** `runtime-dependency-compatibility`
- **状态：** draft；已实现变更由相关 PRD 管理
- **修订日期：** 2026-10-13
- **相关 PRD：** [Align package dependency metadata for Google ADK and OpenTelemetry](../../prd-spec/bugfixes/runtime-dependency-compatibility/2026-10-12-google-adk-opentelemetry-baseline.zh.md)
- **拥有代码：** `pyproject.toml`、`uv.lock`、包元数据回归测试，以及相关 PRD 覆盖的窄范围 ADK 兼容 patch。
- **依赖上游：** `google-adk`、`agentkit-sdk-python` 和 OpenTelemetry Python 包。

## 职责和非目标

本组件负责维护 VeADK 发布 Python 包依赖元数据，以及 Google ADK、AgentKit SDK 和 OpenTelemetry 兼容线对应的主开发 lock。

本次收窄变更不负责 Studio、sandbox、生成项目、managed sidecar 或 Docker 的依赖声明。这些入口可能有各自的发布和回滚约束，如需更新应单独处理。

## 入口点和依赖

- 包元数据：`pyproject.toml`。
- 开发 lock：`uv.lock`。
- 回归覆盖：断言包元数据、lock 元数据以及相关 PRD 指定的 ADK 2.7 兼容路径的测试。
- 外部依赖所有者：Google ADK、AgentKit SDK 和 OpenTelemetry Python。

## 契约

- `CON-1`：VeADK 包元数据必须使用已验证的 Google ADK 兼容窗口。对于 2026-10-13 基线，该范围是 `google-adk>=2.7.0,<2.8.0`。
- `CON-2`：VeADK 包元数据不得把 OpenTelemetry exporter 精确 pin 到 `1.37.0`。对于 2026-10-13 基线，该范围是 `opentelemetry-exporter-otlp>=1.37.0`。
- `CON-3`：VeADK 包元数据必须保持 AgentKit 足够灵活，使全新安装可以解析到最新兼容 AgentKit SDK。对于 2026-10-13 基线，该范围是 `agentkit-sdk-python>=0.8.5`。
- `CON-4`：主 `uv.lock` 是开发 resolver 输出。包元数据变更后，若引用的包版本可获取，应重新生成。
- `CON-5`：回归测试必须检查包元数据、lock 元数据以及本次变更影响的 ADK 2.7 兼容路径。

## 数据和配置

VeADK 包依赖的事实来源是 `pyproject.toml`。`uv.lock` 记录一个具体开发解析结果，不会直接约束普通 `pip install veadk-python` 用户。

## 安全和隔离

本组件不得在依赖证据中包含凭据、签名 URL、生产日志或个人数据。验证时依赖解析可以访问公开包索引；真实云/服务商操作不在本契约范围内。

## 兼容性和演进

修改依赖下限、上限或精确 pin 需要 bugfix 或 feature PRD、resolver 证据和受影响包元数据测试。ADK `2.8.0` 及更高版本不在当前已验证窗口内，因为目标测试已在 ADK `2.11.0` 复现不兼容。生成项目、Studio、sandbox、managed sidecar 和 Docker 的依赖变更不在本次收窄契约内，应由其所属入口单独处理。

## 可观测性和失败

失败表现为 resolver 错误、包元数据回退或 lock 元数据回退。报告时应明确冲突的包和约束。

## 验证

| 契约 | 验证 |
| --- | --- |
| `CON-1`, `CON-2`, `CON-3` | 包元数据回归测试 |
| `CON-4` | `uv lock` |
| `CON-5` | lock 元数据回归测试和目标 ADK 兼容测试 |

## 变更记录

- 2026-10-13：将组件范围收窄到主包元数据、主开发 lock 和最小 ADK 2.7 兼容覆盖。包元数据使用 `google-adk>=2.7.0,<2.8.0`，保持 `agentkit-sdk-python>=0.8.5`，并保持 `opentelemetry-exporter-otlp>=1.37.0`。
