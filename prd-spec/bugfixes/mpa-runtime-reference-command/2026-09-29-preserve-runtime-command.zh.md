# 保留参考 Runtime 的启动命令

[English](2026-09-29-preserve-runtime-command.md)

- **变更 ID：** `mpa-runtime-reference-command`
- **日期：** 2026-09-29
- **状态：** implemented
- **契约：** [MPA Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)

## 背景与证据

使用一个 Ready 参考 Runtime 进行真实托管创建时，新 Runtime 在版本 0 进入
`Error`。参考 Runtime 使用 `Command="bash run.sh"`，新 Runtime 的命令为空。
源码确认 `template_from_runtime()` 会复制镜像、资源、角色和项目，但遗漏 `Command`。

## 目标与非目标

- 在新 Runtime 创建请求中保留参考 Runtime 的 `Command`。
- 保持现有身份、凭据、endpoint、Tool、网络和环境清理逻辑不变。
- 参考 Runtime 未提供命令时不推断默认值，也不修改平铺或显式模板创建路径。

## 需求与设计

- **FR-1：** `managed.from-runtime` 必须在 `Command` 存在时复制该字段。
- **FR-2：** 必须继续移除参考 Runtime 所属的身份和密钥。
- **FR-3：** 参考 Runtime 未提供命令时必须保持缺失，不得猜测默认命令。

在 `template_from_runtime()` 现有白名单中加入 `Command`。这是针对根因的最小修复，
并保留白名单安全边界。不修改 API、schema、权限、并发或持久化。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| `FR-1` | `T-1` 先增加失败断言，再更新白名单 | `AC-1` 复制模板包含完全相同的命令 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_agent_deployment.py` |
| `FR-2`、`FR-3` | `T-2` 运行受影响托管回归 | `AC-2` 清理及命令缺失行为保持不变 | 同上，并运行 `tests/integrations/mpa_managed/test_service.py` |

## 风险、审查与交付

该命令是同一账号下参考 Runtime 的既有可信配置，并传入相同控制面字段。风险仅限于
保留此前被丢弃的值；回滚时删除该白名单项即可。`review-spec` 不可用，因此已直接
审查范围、安全、兼容性、失败行为、可测试性和双语一致性。没有阻塞项，用户本轮
指令批准该修复。

已于 2026-09-29 实施。实现前回归因缺少 `Command` 失败；加入一个白名单字段后，
两个受影响测试文件共 58 个测试全部通过。参考命令存在/缺失测试执行了
`template_from_runtime()` 的全部 12 个可执行行，覆盖率 100%。变更文件的
pre-commit Ruff、密钥检查及 `git diff --check` 均通过。必需的全文件 pre-commit
中 Ruff check 和两个密钥扫描通过，但 Ruff format 会重写范围外
`veadk/integrations/mpa/managed/tasks.py` 的存量排版；该无关改动已还原。本次代码
修复步骤未运行真实云端重建。
