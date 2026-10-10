# 在 Python 3.10 保持 IAM 超时语义

[English](2026-10-09-python310-timeout.md)

## 元数据

- 变更 ID：`mpa-iam-timeout-compat`
- 创建日期：2026-10-09
- 修订日期：2026-10-09
- 状态：implemented
- 相关组件规格：无；保持现有 IAM 失败契约

## 背景与证据

PR #23 的 Python 3.10 单元测试任务在
`test_readback_timeout_and_cancellation_keep_resources` 失败。托管 MPA IAM
协调器使用 `except TimeoutError` 包裹 `asyncio.wait_for()`。在 Python 3.10
中，`asyncio.wait_for()` 抛出 `asyncio.TimeoutError`，不会被内置
`TimeoutError` 处理器捕获。Python 3.11 及更高版本将这两个异常类型设为别名，
因此较新的本地环境掩盖了这个兼容性缺陷。

CI 结果为 6,497 项通过、1 项失败。未捕获的超时直接逸出，而没有转换为现有的
`IamError` 和 `iamVerificationFailed`。

## 目标与非目标

### 目标

- 在 Python 3.10 保持现有 IAM 校验失败行为。
- 保持取消传播和资源保留行为不变。
- 使现有回归测试在 Python 3.10 和当前 Python 上通过。

### 非目标

- 修改 IAM 资源、权限、重试时间或协调顺序。
- 修改公开错误契约或增加新回退行为。
- 修改无关 MPA 行为。

## 需求与设计

- `FR-1`：`asyncio.wait_for()` 的超时必须转换为现有 `IamError`。
- `FR-2`：调用方取消必须继续以 `asyncio.CancelledError` 传播。
- `FR-3`：修复必须同时适用于 Python 3.10 和 Python 3.12，且不改变 IAM 功能逻辑。

在现有转换边界使用 `except asyncio.TimeoutError`。这是 Python 3.10 中
`asyncio.wait_for()` 抛出的异常，并且与较新 Python 版本兼容。

组件契约影响：无。实现被修正为满足已有测试覆盖的超时和取消契约。接口、配置、
权限、持久化、安全边界和用户文档均不变化。

## 任务与验收

| 需求 | 任务 | 验收标准 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`：修复前复现 | Python 3.10 暴露未捕获超时 | Python 3.10 目标 pytest | pass：复现未捕获的 `asyncio.TimeoutError` |
| `FR-1`、`FR-3` | `T-2`：使用 `asyncio.TimeoutError` | 现有超时转换测试通过 | Python 3.10 和 3.12 目标 pytest | pass：两个版本各 13 项 |
| `FR-2` | `T-2` | 现有取消断言通过 | 同一目标 pytest | pass |
| `FR-3` | `T-3`：静态验证 | 修改的 Python 文件检查通过 | Ruff 和 Pyright | pass |

## 风险与待决问题

- 风险仅限于现有超时边界的异常选择器。
- 没有待决问题。

## 审查与交付记录

- 2026-10-09：CI traceback 确认 Python 3.10 异常类型不匹配。
- 2026-10-09：设计审查未发现契约、安全或兼容性阻塞项。
- 2026-10-09：用户批准仅做兼容性修复，并明确要求不改变功能行为。
- 2026-10-09：修复前在 Python 3.10 复现失败。完成一行异常类型限定后，
  IAM 测试在 Python 3.10.20 和 Python 3.12.13 各通过 13 项，Python 3.12
  托管 MPA 测试通过 664 项，Ruff 0.11.12 和 Pyright 均通过。
- 提交和推送需要单独授权。
