# 为托管 MPA 创建确保 Workload Identity

- **变更 ID：** `mpa-managed-workload-identity`
- **创建 / 修订日期：** 2026-09-29
- **状态：** implemented
- **英文版：** [2026-09-29-ensure-managed-workload-identity.md](2026-09-29-ensure-managed-workload-identity.md)
- **组件：** [MPA Runtime 创建](../../../specs/mpa-runtime-provisioning/README.zh.md)
- **前序设计：** [MPA Studio Workload Identity 创建](../../features/mpa-studio-workload-identity/2026-09-20-mpa-studio-workload-identity.zh.md)

## 1. 背景与证据

`veadk mpa create` 会在创建前确保 Studio 共享 WorkloadPool 和每个 Agent 的
WorkloadIdentity。Studio 使用托管 `provision()` 链路，但该链路没有调用 ensure。
使用 `managed.from-runtime` 时可能继承参考 Runtime 的 Pool，同时 YAML 空值覆盖掉
Identity，mpa-agent 随后会因变量对不完整而拒绝启动。

## 2. 目标与非目标

### 目标

1. 在托管创建中复用现有幂等 Workload Identity ensure。
2. 对所有托管来源模式成对注入 ensure 后的 Pool 和 Identity。
3. 防止参考 Runtime 带入其 Agent 专属 Identity。
4. Identity 准备失败时，在 PostgreSQL、网关、Worker 或 Runtime 修改前停止。

### 非目标

- 修改命名、Identity 权限、UserPool 注入或 mpa-agent 消费逻辑。
- 后续创建失败时删除 Identity。
- 迁移已有 Runtime。

## 3. 场景与需求

- **FR-1：** 托管创建在账号校验后、其他创建副作用前确保
  `agentkit-studio-workload` 和 `{MPA_AGENT_ID}-studio`。
- **FR-2：** ensure 得到的变量对覆盖参考 Runtime、模板和 YAML 空值。
- **FR-3：** 托管 Runtime 显式提供的非空值若与规范名称不一致，必须在云资源修改前拒绝。
- **FR-4：** Identity API 失败保留现有脱敏、可执行错误，并阻止后续修改。
- **FR-5：** 从参考 Runtime 提取模板时排除两个 Workload Identity 变量。

## 4. 设计与契约影响

托管服务复用 `ensure_studio_workload_identity()`，并使用 Runtime 控制面已有的同一组
轮换部署凭据创建 `IdentityClient`。同步 SDK 调用在线程中执行。不新增依赖或公共 API。
显式空值表示“未配置”；冲突的非空值关闭式失败。已创建的 Identity 资源保留供幂等重试。

## 5. 实现任务

- **T-1：** 先增加托管服务失败回归，覆盖 ensure 顺序、注入和下游阻断。
- **T-2：** 在托管创建中接入现有 ensure helper，并排除继承的 Workload Identity 字段。
- **T-3：** 更新双语组件契约，执行针对性测试、覆盖率、pre-commit 和受影响回归。
- **T-4：** 从本地 Studio 创建一个真实 MPA，检查 Runtime、Worker 和 TOS 挂载状态。

## 6. 验证与验收

| 需求 | 任务 | 验收标准 | 命令 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1–FR-5 | T-1、T-2 | AC-1：所有托管来源模式收到 ensure 后的变量对，失败会阻止下游工作 | `uv run --extra dev pytest tests/integrations/mpa_managed` | pass；390 条测试 |
| FR-1–FR-5 | T-3 | AC-2：Python 增量行覆盖率至少 95%，仓库检查通过 | 针对性覆盖率、pre-commit 和受影响回归 | pass；增量可执行行 100%，全量回归 5259 passed、8 skipped、2 xfailed |
| FR-1、FR-2 | T-4 | AC-3：新 MPA 的 Runtime 与 Worker Ready，且具有 `/data/output` TOS 配置 | 本地 Studio 创建与云资源检查 | pass；`mi-6fc92ba155cc4bb28a733fb2`、Runtime `r-yew4qlw5c017agjttpcw`、Worker `t-yew4qkzu9smwrumgn11q` |

## 7. 风险与恢复

Studio 管理身份需要既有 Identity get/create action。ensure 失败会更早阻止创建，这是预期行为。
后续失败前已创建的 Identity 会保留并在重试时复用。回退只需撤销代码，不需要数据迁移。

## 8. 评审与交付记录

- 用户批准：2026-09-29，批准为托管创建增加 ensure，并要求真实重试。
- 设计评审：复用现有命名、helper、凭据和错误契约；接口、安全与兼容性不存在未解决阻塞项。
- 实现与验证：2026-09-29 完成。托管创建在下游修改前确保并注入规范变量对，且排除参考
  Runtime 的身份变量。真实 Studio 任务创建出 Ready Runtime 与 Worker；Tool 把
  `agentkit-demo` 以读写方式挂载到 `/data/output`。
