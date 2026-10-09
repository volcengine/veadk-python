# Worker 初始化元数据可见性

[English](2026-09-20-worker-metadata-visibility.md)

- ID：mpa-worker-metadata-visibility；日期：2026-09-20；状态：implemented。
- 前序：[Worker API 恢复](2026-09-20-worker-retry.zh.md)。
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 背景与证据

跟踪到一次创建在 Worker 刚创建的同一秒以安全类别 `ownership` 失败。11 秒后 Worker 为 Ready，只读检查确认 ID、项目、归属标签和智能体环境均匹配；手动重试复用了同一 Worker 并通过。首次具体缺失/冲突字段未记录，因此元数据延迟是有较强证据的推断，不是完整历史响应还原。现有代码在考虑初始化状态前将缺失标签/ID 或空项目视为永久冲突。SDK GetTool 字段均可选。

## 范围与需求

- FR-1：区分归属元数据缺失和已有值冲突。对于持久化 worker_id、worker_token、worker_hash 的托管 Worker，在已识别的初始化状态（Creating、Pending、Starting、Initializing、Provisioning，或未返回/空状态）下，可等待缺失的 ToolId、ProjectName、managed_by、mpa_agent_key。最多 4 次不完整观测，等待 5/10/20 秒；中途完整响应不重置预算。现有 600 秒阶段/任务期限和取消仍优先。
- FR-2：已有且冲突的 ID/项目/标签/MPA_AGENT_ID 立即失败，即使其他字段缺失。Failed/Error/Deleted/Deleting 和非空未知状态不享受元数据宽限。Ready 缺少必需字段立即失败。非托管/既有 Worker 或创建意图不完整时不享受宽限。保留非托管 Worker 省略默认项目以及可选智能体环境缺失的兼容性；托管 Worker 的 ID/项目/标签未验证绝不接受。
- FR-3：安全诊断区分固定字段 `worker_id`、`worker_project`、`worker_managed_by`、`worker_agent_key`、`worker_agent_binding`、`worker_state`；类别为 `metadata_pending`、`metadata_missing`、`ownership`、`resource_failed`，复用有界尝试次数/结果字段。不记录真实值。每次有界观测报告所有缺失字段，但先检查所有冲突。元数据完整后仍必须等待 Ready。
- FR-4：查询重试/幂等和资源绑定保持不变。等待元数据期间不创建新 Worker。不修改 UI/API/数据库结构，不为测试创建真实云资源。

## 设计与影响文件

在 `worker.py` 增加局部校验函数，以固定字段操作记录、返回缺失字段并保持冲突快速失败。就绪循环管理有界缺失计数和等待；终态校验优先于等待。扩展诊断白名单及固定内部异常类别映射。原始 SDK 值保持私有。更新双语组件/运维文档。`test_worker_metadata.py` 覆盖元数据变化、每个冲突字段、Ready/终态/未知状态、持久化意图边界、耗尽、取消/期限、稳定创建次数和脱敏。保留 Worker/任务/CLI 测试门禁。

## 任务与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1/2 | T-1：回归测试与 Worker 状态处理 | AC-1：初始化不完整响应无需手动重试即可到 Ready；冲突/不支持场景立即失败；耗尽/取消/期限有界 |
| FR-3 | T-2：安全字段诊断及测试 | AC-2：可识别待同步/缺失/冲突字段，不泄露值，日志/存储无密钥 |
| FR-4 | T-3：完整受影响测试及双语文档 | AC-3：原幂等/归属/任务契约通过，无云写入、不打断运行任务 |

## 审查、风险与批准

用户批准：“帮我修复这个问题把”批准上文提出的仅等待初始化元数据缺失、拒绝显式冲突的方案。直接审查（review-spec 不可用）覆盖安全、有界等待、取消、结构兼容、测试及双语等价，无阻塞项。元数据超过累计 35 秒宽限仍安全失败，可重试。若初始值冲突，将明确识别，不静默接受。不重跑整个部署，不改 UI。仅在所有活动创建完成后重启本地 Studio。

## 验证

2026-09-20 工作区差异：not_run（待实现）。前端/浏览器/构建：not_applicable（无 UI/HTTP 变化）。真实云创建：not_run（未授权创建测试资源）；只读跟踪用户已有任务。提交/pre-commit：not_applicable（未请求提交）。


## 交付审查与验证（2026-09-21）

范围：当前 worker/diagnostics 实现、Worker 元数据/恢复测试以及双语文档。T-1/T-2/T-3 和 AC-1/AC-2/AC-3 完成。直接实现审查确认：任何宽限之前先检查显式冲突，托管身份必需字段缺失绝不成功，计数不重置，取消及阶段期限限制所有等待，元数据等待期间不新增创建调用。固定诊断通过已有父进程白名单校验，不保留服务端字段值。无数据库结构或 HTTP/UI 改动。

- pass：测试先行，实现前出现 21 failed、4 passed，覆盖初始化元数据不完整和字段诊断。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` — 272 passed，一条上游 Starlette 弃用警告。包含 28 项元数据用例及原恢复、归属、持久化任务和 CLI 覆盖，无外部云写入。
- pass：对 worker.py、diagnostics.py、test_worker_metadata.py、test_worker_recovery.py 执行 `uv run --extra dev --with ruff==0.11.12 ruff check` 和 `uv run --extra dev --with pyright pyright`，已执行 Ruff format。Pyright 初次发现测试字典推断过窄，已标注 `dict[str, object]`，复查零错误。
- pass：按仓库规则对 10 个受影响代码/测试/文档文件执行 Gitleaks，检查 PRD 相对链接、双语/标识符一致性，`git diff --check` 通过。
- pass：只读跟踪确认用户已有重试任务到达 succeeded，计划重载本地服务前没有活动创建。
- not_run：真实首次云创建复现（未授权）、全仓回归（完整受影响组件/CLI 测试已通过）、pre-commit（未请求提交）。UI/构建/浏览器：not_applicable，无 UI/HTTP 契约改动。
- 剩余限制：原始首次响应字段未保留。已修复新增的元数据缺失回归，字段诊断可区分未来的显式冲突；不声称完成真实首次创建验证。

- pass：确认零活动创建后，本地 Studio 已重载；配置接口返回 HTTP 200 且 configured=true。未触发云创建。
