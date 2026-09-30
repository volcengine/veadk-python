# Runtime 首次创建时挂载 Worker Tool

[English](2026-09-29-runtime-initial-tool-attachment.md)

- **变更 ID：** `mpa-runtime-initial-tool`
- **日期：** 2026-09-29
- **状态：** implemented
- **契约：** [MPA Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)

## 背景与证据

当前托管 MPA 部署会从首次 `CreateRuntime` 请求中删除 `ToolId`，再通过后续
`UpdateRuntime` 挂载。线上对比表明：这种 Runtime 可能在网络和 Worker 资源准备前
直接进入版本 0 `Error`；首次创建请求携带已 Ready Worker Tool 的 Runtime 则能进入
`Ready`。延迟挂载原本用于规避在一个已经失败的 Runtime 上替换 Tool 时出现的
`InvalidParameter.ToolId`，该现象不能证明首次创建会拒绝 Tool。

## 目标与非目标

- 当期望配置包含 `ToolId` 时，在 Runtime 首次创建请求中恢复该字段。
- 保留现有最终更新，用权威 endpoint/key 环境完成发布并收敛所有期望字段。
- 保留未完成请求哈希、ClientToken 重试、Worker 创建、TOS 配置以及已有 Runtime
  更新行为。
- 不修改 Tool 创建、TOS 凭据、会话挂载、Runtime 镜像，也不迁移已有失败 Runtime。

## 场景与需求

- **FR-1：** 已创建新的 Worker Tool 时，新建托管 Runtime 的 `CreateRuntime` 必须携带
  该 Tool 的 `ToolId`。
- **FR-2：** Runtime 达到平台 Ready 后，最终化仍必须发布 endpoint/key 环境并收敛
  期望 Tool。
- **FR-3：** 创建响应丢失后的重试必须保留相同期望请求和 `ClientToken` 行为。

## 设计与契约影响

删除调用 `cloud.create` 前复制并移除字段的特殊逻辑，直接传入已规范化的 `desired`
请求。收敛更新字段继续包含 `ToolId`，保证已有 Runtime 更新和最终化保持幂等。本次
修改托管 Runtime 生命周期契约，因此同步更新双语部署规范。Python 公共签名、持久化
schema、权限、凭据处理及兼容输入均不变。

## 任务、验证与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| `FR-1` | `T-1` 先修改回归断言，再修改 Runtime 创建请求 | `AC-1` 首次创建携带 Worker `ToolId` | `uv run --extra dev pytest tests/integrations/mpa_managed/test_agent_deployment.py tests/integrations/mpa_managed/test_service.py` |
| `FR-2` | `T-2` 保留收敛更新 | `AC-2` 最终 Runtime 保留相同 `ToolId` 与最终环境 | 同上 |
| `FR-3` | `T-3` 运行托管部署回归 | `AC-3` 重试和幂等测试继续通过 | `uv run --extra dev pytest tests/integrations/mpa_managed` |

## 风险、恢复与审查

剩余风险是部分控制面变体可能拒绝在 Runtime 创建时携带刚创建的 Tool。已观测线上
路径和成功参考 Runtime 均支持首次挂载；失败会显式暴露，不会被报告为部分成功。
恢复方式是回退本次聚焦修改。自动验证不包含密钥或外部写操作。

`review-spec` 不可用。已直接审查范围、生命周期顺序、重试/幂等、安全、兼容性、
可测试性和双语一致性，没有阻塞项。用户要求修复已诊断回归，视为批准本设计。

## 交付记录

已于 2026-09-29 实施。受影响路径的 `T-1` 至 `T-3`、`AC-1` 至 `AC-3`
已完成。

- `pass`：两个受影响测试文件共 58 个测试通过。实现前回归因缺少 `ToolId` 失败，
  实现后通过。
- `pass`：使用标准库行跟踪运行回归测试，本次两个生产代码变更行均被执行，增量
  可执行行覆盖率为 100%。
- `pass`：变更文件的 pre-commit Ruff 检查/格式化及硬编码密钥扫描通过；
  `git diff --check` 通过。
- `fail`（无关环境问题）：在 coverage 下运行完整 `mpa_managed` 套件时，AgentKit
  SDK/Pydantic 出现 `AliasChoices` 类身份不匹配。相同 coverage 插桩对单个回归也会在
  到达变更路径前失败；普通目标 pytest 通过。
- `fail`（无关存量格式）：全文件 pre-commit 会格式化本次范围外的
  `veadk/integrations/mpa/managed/tasks.py`。已还原该自动改动，并对受影响文件重新运行
  hooks，结果通过。
- `not_run`：真实云端创建；自动测试使用隔离的假控制面，不产生外部变更。
