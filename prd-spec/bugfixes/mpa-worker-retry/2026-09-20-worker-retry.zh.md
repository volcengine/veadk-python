# MPA Worker 自动恢复与安全诊断

[English](2026-09-20-worker-retry.md)

- ID：mpa-worker-retry；创建/修订：2026-09-20；状态：implemented。
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 证据、目标与边界

`runner.py` 丢弃异常；`tasks.py` 丢弃 stderr，并在手动重试时重置最近的失败；`worker.py` 立即传播暂时性 API 失败。用户遇到首次在准备 Worker 时失败、手动重试后继续的情况。由于异常已被丢弃，历史故障的根因未知。本次修复已确认的恢复和诊断缺口，不声称还原历史原因。

有限自动恢复 Worker 暂时性故障，跨手动重试保留安全的任务诊断。不重跑整个部署、不修改镜像/配置或归属规则、不创建云资源用于测试、不暴露原始错误、不重做弹窗。其他云阶段补最终诊断但不加自动重试。

## 需求与场景

- FR-1：Worker 参考查询、发现、幂等创建和就绪查询最多尝试 4 次，在可恢复失败之间分别等待 1、2、4 秒。重试超时/连接故障、已知限流/服务错误码和 HTTP 408/429/500/502/503/504。未知、鉴权、校验、归属和资源终态错误立即停止。不通过任意错误文本的子串匹配分类。
- FR-2：仅在读取具有已持久化托管创建意图和 ID 的 Worker 时重试已识别的不存在错误。参考/既有 Worker 缺失立即失败。阶段默认 600 秒，包括发现和重试；总任务期限和取消仍优先。重试保持同一持久化 ClientToken 和载荷，发现失败绝不能当成不存在。
- FR-3：在私有任务 SQLite 中保存白名单诊断事件（阶段、操作、类别、尝试次数、retrying/failed、时间戳、任务 ID）；跨手动重试保留每任务最新 100 条。不保存异常消息、堆栈、URL、请求头、载荷、凭据、任意服务端错误码或环境值。服务端日志记录相同安全字段。API 响应结构/错误码保持兼容。
- FR-4：Runner 为所有阶段报告已分类的最终失败。即使子进程没有诊断，父进程也记录异常退出、超时和取消。在日志/存储之前校验子进程诊断字段。诊断不得把失败变成成功或掩盖清理。

## 设计与影响

新增小型诊断分类器和 Worker 重试函数。识别已安装 AgentKit 的类型化异常/error_code 与链式 requests 传输异常（含 HTTP 状态）；仅将固定已知码映射为固定类别。创建重试保持原幂等令牌。托管就绪查询的 404 容忍有界，不放宽归属校验。增加任务诊断表，不修改旧任务记录或 HTTP 契约；事务内限制保留数量。Runner 使用有作用域的诊断回调，父进程再次验证事件。CLI 可记录安全事件，但不写 Studio 任务库。UI 和构建产物无需修改。

## 任务、测试与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1/2 | T-1：测试、诊断模块及 Worker 集成 | AC-1：暂时性恢复、耗尽重试、稳定令牌/载荷、参考 404/权限快速失败、归属校验、取消/期限 | Worker 与诊断目标测试 |
| FR-3/4 | T-2：runner/任务集成与迁移测试 | AC-2：历史跨重试/重开保留、上限 100、拒绝畸形/注入事件、保持终态 | 真实子进程任务测试及 runner 测试 |
| 全部 | T-3：双语契约/运维文档及审查 | AC-3：文档与实现一致、记录检查 | Python 回归、Ruff、Pyright、空白/密钥检查 |

影响路径：`veadk/integrations/mpa/managed/{diagnostics,worker,runner,tasks}.py`、对应测试、双语组件/运维文档。不改前端代码，不加依赖。

## 风险与审查

未知服务端错误码故意快速失败，白名单外的暂时性故障仍可能需要手动重试。云请求可在取消后完成，持久化意图仍是恢复依据。SDK 内部重试可能使实际网络请求次数超过四次编排调用。诊断使用类别，在细节与凭据安全之间取舍。就绪轮询保持原频率。

直接设计审查（review-spec 不可用）：已检查一致性、有界重试、写操作幂等、取消、输入校验、保密、迁移和双语等价，无阻塞项。用户批准：“帮我补”明确批准上文提出的安全错误记录与暂时性自动重试方案。本设计不授权提交/推送/部署。历史错误缺少证据，无法真实复现；必须使用隔离模拟。

## 验证记录

2026-09-20 工作区差异：not_run（待实现）。前端/浏览器：not_applicable（无 UI/HTTP 契约变化）。真实云写入：not_run（未请求创建新云资源）。提交/pre-commit：not_applicable（未请求提交）。


### 实现验证（2026-09-20，当前工作区差异）

- pass：实现前新增 19 个回归用例失败（缺少恢复/诊断），未调用真实云服务。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` — 244 passed；一条上游 Starlette 弃用警告。
- pass：修正超时类型标注后最终受影响测试：`uv run --extra dev pytest tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_tasks.py -q` — 39 passed。
- pass：对 diagnostics/worker/runner/tasks 和 test_worker_recovery/test_worker 执行 `uv run --extra dev --with ruff==0.11.12 ruff check` 与 `uv run --extra dev --with pyright pyright`，无错误；已执行 Ruff format。初次裸命令 `uv run ruff` 不可用，使用临时工具依赖解决，未修改项目/全局配置。Pyright 在小数期限测试中发现 timeout 被推断为仅 int；已标注为 float 并复查。
- pass：按仓库规则对 25 个实现/测试/文档文件执行 Gitleaks，检查双语 PRD 链接/需求 ID，人工复核双语语义，`git diff --check` 通过。
- pass：审查确认固定安全枚举、有界操作重试、保持持久化创建令牌/载荷、归属快速失败、API 不变、历史数量上限以及真实子进程清理测试覆盖。T-1/T-2/T-3 与 AC-1/AC-2/AC-3 完成。
- not_run：全仓 Python 回归（改动限定于托管 MPA，完整受影响组件和 CLI 测试已通过）。UI 构建/浏览器和产物：not_applicable，无 UI/HTTP 结构变化。真实云创建：not_run；模拟恢复不能证明已丢弃的历史原因。提交/pre-commit：not_applicable，未请求提交。

- pass：仅在活动创建数为零后重载本地 Studio；配置 GET 返回 HTTP 200/configured=true。首次任务访问初始化 `task_diagnostics`，保留已有任务。本地未登录身份查询任务返回 404，不声称完成已登录 UI/真实云创建冒烟。用户此前任务在重启前已经 succeeded。
