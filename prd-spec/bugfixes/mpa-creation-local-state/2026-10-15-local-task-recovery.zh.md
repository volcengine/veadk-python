# MPA 创建本地任务恢复

[English](2026-10-15-local-task-recovery.md)

## 元数据

- 变更 ID：`mpa-creation-local-state`
- 创建日期：2026-10-15
- 修订日期：2026-10-15
- 状态：approved
- 相关组件规格：[Studio MPA creation](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与证据

Studio MPA 创建已经将 owner 维度的任务状态持久化到本地 SQLite 数据库。但前端主要依赖浏览器 `sessionStorage` 恢复进度。刷新、缓存丢失或草稿被替换后，弹窗无法按当前 owner 和地域从服务端发现最近任务。本地未配置 Studio TOS 存储时，MPA operation service 也可能不可用。

`wlc-ap-test` 的 BytePlus 创建暴露了另一个问题：操作者在重试之间修改了 TOS 配置。服务端把 `tosBucket` 从存储的任务 payload 中移除，只单独传给子进程；而 Worker 哈希包含最终 TOS mount 配置。结果是任务层认为请求未变化，但 Worker intent 已变化，最后在 Worker 阶段才报 `configuration_changed`。

AIDAP 重试修复后，同一任务已能多次推进到 Worker 阶段，但 BytePlus `create_worker` 持续返回 `InvalidParameter.TosEndpoint`。使用旧的 `https://tos-ap-southeast-1.bytepluses.com`、后续改成的 `tos-ap-southeast-1.bytepluses.com`、省略 endpoint，以及 AgentKit 风格的 `http://tos-ap-southeast-1.bytepluses.com` 都被拒绝，对应 request ID 包括 `2026101511483686035D67AE3B4A1C41A8`、`20261015115339C02052F0ED43FE23806D`、`2026101512015520E30384A95D0B0B510C` 和 `202610151214245AE8256781CAFD0F5F45`。这说明 BytePlus Tool 创建当前不接受 Tool 级 TOS mount 配置。Agent 创建应降级为不带 Tool TOS mount 创建 Worker，同时保留其余 MPA 资源。

## 目标与非目标

目标：

- 增加按 owner 隔离的本地任务列表接口，用于刷新恢复。
- 当前端没有或丢失 `sessionStorage` 时，可从服务端恢复当前 owner 和地域下最近的已提交任务。
- 将非密的 `tosBucket` 纳入任务身份，TOS 配置变化在提交阶段尽早拒绝。
- 在恢复的任务载荷中包含最新安全诊断摘要。
- 对暂时性的 AIDAP 读/查询失败做有界退避重试，同时保持创建 Workspace 的幂等安全边界。
- BytePlus IAM role 模式的 Worker TOS mount 先尝试 AgentKit Tool mount endpoint 形态 `http://tos-ap-southeast-1.bytepluses.com`；当 BytePlus 拒绝 `TosEndpoint` 时，自动降级为不带 Tool 级 TOS mount 创建 Worker。
- 降级后的重试保持幂等，并清理 Runtime TOS mount 环境变量，避免 Runtime 误认为 Worker 已挂载。

非目标：

- 不改变国内火山 Worker TOS mount 序列化。
- 不持久化 TOS access key、secret 等密钥。
- 不替代生产环境需要的持久化 MPA operation service。
- 本次不建设完整恢复控制台。
- 不自动重试缺少幂等 token 的 `CreateWorkspace`。

## 需求

- `FR-1`：给定本地 SQLite 中已有提交任务，当弹窗刷新后没有浏览器恢复状态时，应能按当前 owner 和地域恢复并继续轮询最近任务。
- `FR-2`：给定同一 `requestId` 使用不同 `tosBucket` 再次提交，服务端应在任务接收阶段拒绝，而不是进入 Worker 哈希校验后失败。
- `FR-3`：给定任务已有诊断，恢复任务应返回最新的安全结构化诊断，不包含原始服务商文案或凭据。
- `FR-4`：给定任务进入子进程，非密 `tosBucket` 仍应进入 TOS 配置路径，且 TOS 密钥不得持久化。
- `FR-5`：给定 branch、compute、endpoint、account、database、connection、list 或 detail 等只读 AIDAP 调用遇到暂时性服务商错误，创建流程应有界退避重试，并记录具体安全 AIDAP 操作名。
- `FR-6`：给定 `CreateWorkspace` 失败，不得自动重试，因为云 API 没有客户端幂等 token。
- `FR-7`：给定 BytePlus Worker 创建使用 IAM role TOS mount，首次创建 payload 应使用 `MountPoints[].Endpoint=http://tos-ap-southeast-1.bytepluses.com`；已用省略 endpoint、`tos-ap-southeast-1.bytepluses.com` 或 `https://tos-ap-southeast-1.bytepluses.com` 计算 hash 的未完成旧 intent 应被升级，而不是被拒绝为输入变化。
- `FR-8`：给定 BytePlus 以 `InvalidParameter.TosEndpoint` 拒绝 Worker 创建，同一创建流程应记录安全诊断，并使用新的客户端 token 以不带 `TosMountConfig` 的请求重试 Worker 创建，同时持久化降级标记。
- `FR-9`：给定 Worker TOS mount 已降级，Runtime 部署不应设置 `MPA_CODEX_WORKER_TOS_MOUNT_ENABLED` 或 `MPA_CODEX_WORKER_TOS_BUCKET`。

## 设计与契约影响

`CreationTasks` 增加按 owner 查询最近任务的 `list()` 方法。`GET /web/mpa-creation/tasks?region=...` 调用它并返回 `{tasks:[...]}`。每个任务保持现有任务形状，并可新增 `latestDiagnostic`。

任务 payload 会在存在 `tosBucket` 时保留该字段。子进程输入仍单独包含 `tos` 对象，`_run()` 不会将 `tosBucket` 作为无关资源字段传递。这样现有重复请求比较会在子进程启动前捕获 TOS 变化。

前端 `MpaCreateDialog` 在没有从 session storage 恢复到提交任务时调用列表接口，并挂接当前地域最近的已提交任务。浏览器存储继续作为快速恢复缓存，而不是唯一状态源。

组件规格影响：新增一个 HTTP 查询端点，并收紧请求身份一致性。现有单任务查询端点不变。

AIDAP 读调用最多执行八次尝试，使用有界指数退避。可重试类别为 `connection`、`timeout`、`throttled` 和 `unavailable`。权限、认证、参数非法、归属/配置冲突、资源缺失和协议形态错误均快速失败。`create_workspace` 保持单次调用，避免重复资源。

BytePlus Worker TOS mount 序列化会先将 AgentKit 生成的国内默认 `MountPoints[].Endpoint` 改写为 `http://tos-ap-southeast-1.bytepluses.com`，再计算 hash 并提交云端。Worker 重试路径识别省略 endpoint、原始 HTTPS BytePlus endpoint 或后续 host-only endpoint 的未完成旧 hash，并将存储 hash 升级为 HTTP endpoint 请求。

如果服务商仍返回 `InvalidParameter.TosEndpoint`，Worker provisioner 会记录 `worker_tos_mount_disabled=true` 和安全原因，切换到不带 `TosMountConfig` 的请求，轮换客户端 token 以避免变更 payload 的幂等冲突，并重试 `create_worker`。`provision()` 在 Worker 创建后重新读取 registry record，并按实际 Worker 状态重新应用 Runtime TOS env，避免降级后的 Worker 暴露不可用挂载。

## 任务

- `T-1`：新增带最新诊断摘要的 `CreationTasks.list()`。
- `T-2`：新增 `GET /web/mpa-creation/tasks`。
- `T-3`：任务 payload 保留 `tosBucket`，同时继续将 `tos` 传给子进程。
- `T-4`：新增前端客户端与弹窗恢复逻辑。
- `T-5`：补充后端与聚焦前端测试。
- `T-6`：增加 AIDAP 读重试诊断与测试，同时保持 Workspace 创建单次执行。
- `T-7`：调整 BytePlus Worker TOS mount 序列化和旧 hash 恢复。
- `T-8`：增加 BytePlus Worker TOS mount 降级与 Runtime env 对齐。

## 验证与验收

| 需求 | 任务 | 验收标准 | 测试或验证命令 | 结果/证据 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-2`, `T-4`, `T-5` | 无 session storage 时可从本地服务端恢复已提交任务 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_tasks.py tests/integrations/mpa_managed/test_routes.py -q`；`npm --prefix frontend test -- mpaCreation.test.tsx --runInBand` | `pass`，2026-10-15 后端 34 个测试通过，前端 1389 个 Node 测试和 117 个 Vitest 测试通过 |
| `FR-2` | `T-3`, `T-5` | 同一请求修改 `tosBucket` 会在任务接收阶段拒绝 | 同一后端 pytest 命令 | `pass`，2026-10-15 后端 34 个测试通过 |
| `FR-3` | `T-1`, `T-5` | 最新诊断为安全结构化数据 | 同一后端 pytest 命令 | `pass`，2026-10-15 后端 34 个测试通过 |
| `FR-4` | `T-3`, `T-5` | 子进程收到 TOS 选择且密钥不持久化 | 同一后端 pytest 命令 | `pass`，2026-10-15 后端 34 个测试通过 |
| `FR-5` | `T-6` | 暂时性 AIDAP 读失败会重试并记录具体 AIDAP 操作 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_auto_pg.py tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_tasks.py tests/integrations/mpa_managed/test_routes.py -q`；`uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_auto_pg.py::test_sdk_read_calls_tolerate_repeated_cross_region_failures -q` | `pass`，2026-10-15 共 129 个测试通过，并补充重复失败聚焦覆盖 |
| `FR-6` | `T-6` | `CreateWorkspace` 失败不会自动重试 | 同一 AIDAP/PG pytest 命令 | `pass`，2026-10-15 共 129 个测试通过 |
| `FR-7` | `T-7` | BytePlus Worker 创建使用 HTTP TOS Endpoint，且旧 endpoint hash 可恢复 | `uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_byteplus.py::test_byteplus_worker_mount_and_environment_are_overseas tests/integrations/mpa_managed/test_byteplus.py::test_byteplus_worker_recovers_legacy_tos_endpoint -q` | `pass`，2026-10-15 聚焦 6 个测试覆盖 |
| `FR-8` | `T-8` | BytePlus `InvalidParameter.TosEndpoint` 会降级为不带 Tool TOS mount 创建 Worker | `uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_byteplus.py::test_byteplus_worker_tos_endpoint_failure_falls_back_without_mount -q` | `pass`，2026-10-15 聚焦 6 个测试覆盖 |
| `FR-9` | `T-8` | Worker mount 降级时清理 Runtime TOS env | `uv run --python 3.13 --extra dev pytest tests/integrations/mpa_managed/test_service.py::test_tos_runtime_env_is_owned_and_contains_no_credentials -q` | `pass`，2026-10-15 聚焦 6 个测试覆盖 |

## 风险

- 本地 SQLite 仍是实例本地状态，适合本地 Studio 和单实例部署，不等价于跨实例生产恢复。
- 最近任务列表必须按 owner 隔离，避免暴露其他用户的草稿或云资源名称。

## 评审与交付记录

设计评审结论：这是基于已有本地任务存储的窄范围可靠性修复，不增加新的云侧副作用，并让 TOS 变化更早失败。

实现已于 2026-10-15 完成。定向后端测试、聚焦前端测试、AIDAP/PG 重试测试、BytePlus Worker TOS endpoint/降级回归测试、Ruff、i18n 检查、前端构建和 `git diff --check` 均通过。前端构建仍输出既有的大 chunk 与动态/静态混合导入警告。
