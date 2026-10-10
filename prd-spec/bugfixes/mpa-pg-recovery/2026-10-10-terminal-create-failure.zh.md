# 恢复 PG Workspace 的终态创建失败

[English](2026-10-10-terminal-create-failure.md)

- 变更 ID：`mpa-pg-terminal-create-failure`
- 日期：2026-10-10
- 状态：已实现
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-13

## 背景与证据

自动 PG 初始化按账号、地域和项目共享。CreateWorkspace 可能报错，同时在云端留下 `CreateFailed` 的 Workspace，SQLite 则保留没有资源 ID 的意图。发现逻辑在检查状态前校验归属标签，且位于就绪等待循环外，因此标签缺失会让所有后续智能体请求立即失败。服务商外层 InternalError 可能包含购买权限拒绝；仅凭外层错误码无法确定资源是否存在。

## 目标、非目标与场景

明确终态创建失败后恢复创建，不删除云资源，不改变正常复用。国内和 BytePlus 使用相同恢复规则。不修改手动模式或显式接管、数据库、VPC、APIG、Runtime、镜像、前端或聊天。实现验证无需真实云端写操作。

场景：首次失败有或没有 ID；修正权限后重试；旧失败资源与正常替代资源同时存在；替代请求超时；多个智能体并发；元数据不完整；归属冲突；显式 ID，以及删除、未知状态或运行故障的资源。

## 需求与设计

- **FR-1：** 仅精确的 `CreateFailed` 属于可恢复的终态创建失败。`Failed`、删除或删除中、未知状态和服务错误继续快速失败。本次刚发出的创建若进入 `CreateFailed`，当前任务失败，不在同一次尝试内重复购买。
- **FR-2：** 将失败候选记录退出前，必须完整匹配账号、地域、项目、名称、引擎及非空 ID；已存在但冲突的归属标签必须拒绝。仅在分类 `CreateFailed` 时允许标签缺失，接管正常资源不放宽标签检查。显式配置的 ID 不自动变更。
- **FR-3：** SQLite 增加非敏感 `failed_workspaces` 表，以范围、用途和 ID 为键。原子地将已确认失败的托管绑定及活动意图退出，保留原云资源。仅当退出的 ID 仍为 `CreateFailed` 时忽略它，状态变化则拒绝。原有表保留，采用增量升级。
- **FR-4：** 对无 ID 的未知意图，只有一个新发现的已确认失败候选且没有正常候选时，允许退出；多个未退出失败候选仍视为歧义。之前已退出的失败资源不能用于解释更新请求的未知结果。无候选仍表示结果未知，不盲目重发 CreateWorkspace。正常或创建中候选继续执行现有身份、标签与防重复校验。
- **FR-5：** 发现托管资源元数据暂不完整时，进入现有有界就绪循环，而非在循环外失败。已存在的冲突仍立即失败。沿用范围级 OS 锁和 PG/任务截止时间；取消保留持久化身份或意图。
- **FR-6：** 正常首次创建、共享复用、创建响应丢失后的成功恢复和后续步骤失败保持兼容。通用 API/UI 错误分类与脱敏诊断不变。已记录的 Workspace 缺失或发生运行故障时绝不替换。

影响文件：`managed/pg_bootstrap.py`、`tests/integrations/mpa_managed/test_auto_pg.py`、双语组件规范、托管模块 README 和本设计。不增加依赖、浏览器字段、服务商请求格式或云端删除接口。

## 任务、测试与验收

- **T-1 / AC-1：** 先编写回归测试：两种服务商、管理/业务用途、标签缺失、已存 ID、显式接管、并发恢复和正常复用。
- **T-2 / AC-2：** 实现增量持久化退出记录和先判断状态的恢复，每次请求每种用途最多创建一个新资源，不改动失败云资源。
- **T-3 / AC-3：** 验证未知结果、退出资源历史、歧义、退出资源状态变化、外部范围/标签、API 错误、详情缺失、超时与取消不会引起重复或破坏操作。
- **T-4 / AC-4：** 执行针对性及托管流程集成回归、两进程默认 Python 回归、改动文件 Ruff/Pyright、双语文档和空白检查。无前端变更，前端构建/浏览器门禁不适用。未经授权不提交、推送或进行真实云创建。

## 风险与评审

CreateFailed 分类依赖云端终态创建状态和已验证范围。失败资源标签缺失不代表允许接管或删除。持久化保留失败 ID，防止旧失败授权重发更新的超时请求。独立主机仍需共享初始化状态，本修复不引入分布式锁。保留的失败云资源可能需管理员清理。旧状态结果未知且存在多个候选时，有意保留人工恢复要求。

2026-10-10 用户在了解正常、失败及未知状态行为后，以“改下”批准恢复规则。`review-spec` 不可用，直接评审覆盖可行性、增量表结构、状态转换、取消、锁、显式 ID 边界、敏感信息、国内兼容和双语一致性。没有阻塞项，可以修改生产代码和测试。

## 验证记录

验证日期：2026-10-10。测试版本：基于 `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91` 的工作区，包含此前已批准的 BytePlus 适配。本次恢复修复修改一个生产模块、一个测试模块及双语设计/规范/模块说明，保留已有适配改动。正常、失败及并发测试使用临时 SQLite 文件和模拟云适配器，不使用用户状态或真实云资源。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| 实现前失败回归 | pass | 首批 16 个恢复用例中 14 个因缺失标签恢复、退出历史不存在及失败状态处理而失败，两个归属防护原本通过；另补的现有冲突用例也在修正前失败。 |
| `uv run --extra dev pytest tests/integrations/mpa_managed -q --tb=short` | pass | 782 个测试，5 条已有警告；新增 30 个恢复/兼容用例。覆盖两种服务商、两种 Workspace 用途、交错并发请求、正常复用不变、未知/取消结果、迁移和显式 ID 防护。 |
| `uv run --with ruff==0.11.12 ruff check <changed-python-files>` 及 `ruff format --check` | pass | `pg_bootstrap.py` 和 `test_auto_pg.py`；临时工具环境，没有全局安装。 |
| `uv run --with pyright pyright <changed-python-files>` | pass | 同上两个文件，0 个错误、警告或信息诊断。 |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" --tb=short` | fail | 6,985 项通过，1 项失败，53 项跳过，4 项 xfailed，耗时 411.61 秒。已有 `test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes` 预期 `text/markdown`，本地 MIME 检测返回 `application/octet-stream`。此前 BytePlus 验证已在未修改 HEAD 上复现同一失败。本次全量运行期间恢复生产代码未变化，最后两个兼容用例另在最终 782 项托管流程测试中验证。 |
| 双语文档、标识符、相对链接与 `git diff --check` | pass | 评审两种语言及维护的 CON-13，改动不包含凭据或生产日志。 |
| 前端/浏览器/构建、harness 覆盖率、Codex smoke | not_applicable | 没有 UI/生成发布产物、聊天、sidecar 或 Codex 运行时变更。 |
| Pre-commit、分支同步、提交/推送 | not_run | 未授权提交或推送；后续提交前执行对应门禁。 |
| 真实创建/替换 | not_run | 本代码修复采用离线验证，未授权为验证执行新的云端写操作；此前明确授权的清理是独立操作。 |

最终直接评审：每次请求每种用途最多购买一个新资源，失败身份重启后仍保留，解除状态在现有锁下原子执行，显式 ID 与其他范围/用途记录保留，运行故障终态不会被替换，缺失元数据无法遮盖已存在冲突。失败资源清理及分布式/多主机协调仍由管理员负责。


## 提交前验证（2026-10-10）

用户已授权提交并推送本地修改。获取 `origin` 和 `upstream` 后，在 `feat/mpa-account-fixes-upstream-clean-20261010` 执行 `git rebase --autostash upstream/main`。分支已经同步；同步后原有 159 个改动文件状态全部一致。基础版本仍为 `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91`。随后唯一的生产代码调整是 Ruff 格式化 CLI 中的创建路由注册调用。

- **pass：** `uv run --extra dev pre-commit run --all-files`：Ruff 检查/格式化及两项敏感信息扫描。首次运行格式化了 CLI 调用，再次运行全部通过。
- **pass：** 同步后 `uv run --extra dev pytest tests/integrations/mpa_managed -q --tb=short`：782 项通过，5 条已有警告。
- **pass：** 同步后 `npm --prefix frontend test`：1,377 项 Node 测试和 67 项 Vitest 测试。
- **pass：** 同步后 `npm --prefix frontend run check:i18n` 及 `npm --prefix frontend run test:webui-assets`：2 种语言 / 21 个命名空间，113 个文件 / 350 个引用。
- **not_run：** 重复执行完整 Python 回归、前端构建/浏览器及 Pyright。同步保留了此前已验证的源码，CLI 调整仅改变格式。完整回归的 MIME 及 CLI Pyright 基线失败仍按上文记录。本次提交请求不涉及新的云端创建、发布或部署；海外全流程就绪仍未验证。

提交包含 BytePlus 适配、PG 创建失败终态恢复、双语文档、测试及配套前端构建产物，不包含凭据、本地状态数据库或生产日志。
