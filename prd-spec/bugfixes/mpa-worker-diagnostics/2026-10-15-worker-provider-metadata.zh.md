# MPA Worker 服务商元数据诊断

[English](2026-10-15-worker-provider-metadata.md)

## 元数据

- 变更 ID：`mpa-worker-diagnostics`
- 创建日期：2026-10-15
- 修订日期：2026-10-15
- 状态：approved
- 相关组件规格：[Studio MPA creation](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与证据

BytePlus Studio MPA 创建任务 `84f8dfe6-e7fa-4063-9803-912ff12fbc3a` 在 `worker` 阶段失败，诊断为 `create_worker/provider_error`，随后在 `network` 阶段展示为 `creationFailed`。私有任务数据库没有记录 Worker 失败的 `error_code` 或 `request_id`。只读检查显示：

- `/web/ui-config` 为 `provider:"byteplus"`，`/web/runtime-config` 返回 `credentials:true`。
- BytePlus PG 引导库已有 `mpa_agent_wlc-ap-test` 的管理 Workspace 和独立业务 Workspace 记录。
- BytePlus AgentKit Tools 列表中没有名为 `wlc-ap-test` 的 Tool，也没有带目标 `mpa_agent_key` 的 Tool。
- 当前子进程丢弃原始 stderr，只持久化白名单 `MPA_EVENT` 诊断，因此历史服务商响应无法恢复。
- Runtime 和 OpenViking 路径已经会从 SDK 包装 body 中安全提取服务商 `Error.Code` 与 `RequestId`，但 Worker 重试诊断只分类异常并丢弃这些标识。

假设：与 Runtime/OpenViking 测试中的形态一致，服务商响应可能在 SDK 包装 body 或 response 对象中包含结构化错误码。本变更不假设具体的云侧错误类型。

## 目标与非目标

目标：

- Worker API 失败时，如服务商提供安全的 `errorCode` 和 `requestId`，则保留到诊断中。
- 复用现有 `task_diagnostics.error_code` 和 `request_id` 字段。
- 原始服务商文案、请求体、凭据、带 token 的镜像 URL 以及异常文本不得进入任务状态或日志。
- 不改变 Worker 创建载荷、资源生命周期、重试次数、UI 行为或云权限。

非目标：

- 直接修复 BytePlus `CreateTool` 的底层拒绝原因。
- 新增 UI 字段或向浏览器暴露原始服务商文案。
- 自动重试历史失败任务。
- 除抽取逻辑共用化外，不改变 Runtime/OpenViking 行为。

## 场景与需求

- `FR-1`：给定 `WorkerCloud.create` 抛出的 SDK 错误包装 body 含 `ResponseMetadata.Error.Code` 和 `RequestId`，当 `retry_worker` 记录失败尝试时，`task_diagnostics` 应保存白名单内的 `error_code` 和 `request_id`。
- `FR-2`：给定 SDK 错误 body 格式错误、过大、为自由文本或疑似 token，当诊断运行时，不得保存原始文本或不安全标识。
- `FR-3`：给定已抽取到安全服务商错误码，当现有分类是通用 `provider_error` 或 `unknown` 时，诊断可通过现有安全错误码分类表细化分类。
- `FR-4`：给定 Runtime 创建/更新失败已记录元数据，当 helper 移入 diagnostics 后，现有 Runtime 行为和测试应保持等价。

## 设计与契约影响

实现会在 `veadk.integrations.mpa.managed.diagnostics` 中新增共享安全 helper，检查有界异常链中的：

- 直接 `error_code` / `request_id` 属性；
- 现有 OpenViking helper 可处理的结构化 `response.json()` 或 `body` 元数据；
- 单个字符串/字节 SDK 参数中的有界 JSON 或 bytes 字面量。

`retry_worker` 在记录诊断前使用该 helper，并将安全标识传入现有 `report()` 路径；`report()` 已经对白名单字段做校验。helper 会拒绝格式错误、过大、自由文本和疑似 token 的值。

组件规格影响：无契约变更。`task_diagnostics` 已支持可选 `error_code` 和 `request_id`，脱敏边界保持不变。本修复只是补齐现有可观测性契约在 Worker 路径上的覆盖。

安全影响：正向。变更增加结构化诊断，但不扩大持久化数据范围。原始服务商文案和载荷仍被排除。

兼容影响：只增加诊断元数据。已有记录仍有效，忽略这些字段的调用方不受影响。

## 实现任务

- `T-1`：将安全 SDK 元数据抽取移动到 `diagnostics.py`。
- `T-2`：更新 Runtime 创建/更新诊断以使用共享 helper，并保持行为不漂移。
- `T-3`：更新 Worker 重试诊断以记录安全 `errorCode` 和 `requestId`。
- `T-4`：补充 Worker SDK 包装元数据与不安全 body 拒绝的回归测试。

## 验证与验收

| 需求 | 任务 | 验收标准 | 测试或验证命令 | 结果/证据 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-3`, `T-4` | `AC-1`：Worker 诊断保留安全服务商错误码/request ID | `uv run --extra dev pytest tests/integrations/mpa_managed/test_runtime_diagnostics.py tests/integrations/mpa_managed/test_worker_recovery.py -q` | `pass`，2026-10-15 共 57 个测试通过 |
| `FR-2` | `T-1`, `T-4` | `AC-2`：格式错误或不安全 body 不持久化文本或 token | 同一定向 pytest 命令 | `pass`，2026-10-15 共 57 个测试通过 |
| `FR-3` | `T-3`, `T-4` | `AC-3`：安全错误码可细化通用 Worker 分类 | 同一定向 pytest 命令 | `pass`，2026-10-15 共 57 个测试通过 |
| `FR-4` | `T-2` | `AC-4`：现有 Runtime 诊断测试仍通过 | 同一定向 pytest 命令 | `pass`，2026-10-15 共 57 个测试通过 |

必需的定向命令：

```bash
uv run --extra dev pytest tests/integrations/mpa_managed/test_runtime_diagnostics.py tests/integrations/mpa_managed/test_worker_recovery.py -q
```

真实 BytePlus 确认需要使用更新后的后端重启 Studio，并对同一或新的 MPA 创建请求执行重试。该云端重试与自动化单测验证分开记录。

## 风险与待确认问题

- 服务商仍可能不提供结构化元数据；这种情况下诊断会保持通用分类，且不会使用原始文本兜底。
- 在新的重试记录错误码或查询云侧控制面日志前，BytePlus 的具体原因仍未最终确认。
- 当前 `.zshrc` 在导出 BytePlus 凭据后会直接启动 Studio；交互式 shell 启动可能意外尝试在 8000 端口启动第二个 Studio 进程。

## 评审与交付记录

设计评审结论：这是一个很窄的可观测性 bugfix，复用既有脱敏模式，不改变云端载荷或用户可见 API 形态。

用户批准：当前调试请求要求持续关注创建流程并定位根因；该诊断增强是避免基于通用 `provider_error` 猜测的必要步骤。

实现已于 2026-10-15 完成。定向 pytest 通过 57 个测试；`uv run ruff check veadk/integrations/mpa/managed/diagnostics.py veadk/integrations/mpa/managed/runtime.py tests/integrations/mpa_managed/test_worker_recovery.py` 和 `git diff --check` 也已通过。
