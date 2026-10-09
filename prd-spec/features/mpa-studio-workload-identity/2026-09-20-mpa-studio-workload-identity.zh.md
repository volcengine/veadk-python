# MPA Studio 工作负载身份创建

- **变更 ID：** `mpa-studio-workload-identity`
- **创建 / 修订日期：** 2026-09-20
- **状态：** implemented
- **英文版：** [2026-09-20-mpa-studio-workload-identity.md](2026-09-20-mpa-studio-workload-identity.md)
- **组件：** [MPA Runtime 创建](../../../specs/mpa-runtime-provisioning/README.zh.md)
- **前序设计：** [MPA Agent 一键创建](../mpa-agent-oneclick-provision/2026-09-10-mpa-agent-oneclick-provision-design.zh.md)

## 1. 背景与证据

`veadk mpa create` 当前把 `MPA_AGENT_ID` 生成为 `mi-` 加十二位小写字母数字，并关闭 ArkClaw 身份启动。已部署的 mpa-agent 仍把出站工作负载身份推导为 `arkclaw-{CLAW_SPACE_ID}-workload` 和 `MPA_AGENT_ID`。Studio 拓扑中不存在该 Pool，因此即使 Runtime 健康，出站 TIP 交换仍会失败。

已批准的 Studio 约定是：账号和地域内共享一个名为 `agentkit-studio-workload` 的 Pool，每个 MPA 实例使用 `{MPA_AGENT_ID}-studio` 作为 Identity。基础 MPA ID 仍然用于数据库、Runtime、Tool、渠道和可观测性。

## 2. 目标与非目标

### 目标

1. 生成并校验 `mi-[0-9a-z]{12}` 形式的规范 MPA ID。
2. 在其他创建副作用之前，幂等创建或复用 `agentkit-studio-workload` 和 `{MPA_AGENT_ID}-studio`。
3. 向 Runtime 注入明确的 WorkloadPool 和 WorkloadIdentity 名称。
4. 通过配套消费者改动，为非 Studio mpa-agent 部署保留现有 ArkClaw 推导行为。
5. 对 Identity 权限缺失给出可执行且脱敏的错误。

### 非目标

- 创建 Identity UserPool、client、group 或 ArkClaw 控制面记录。
- 开启入站 A2A TIP 校验；Studio 边界继续使用 APIG key 鉴权。
- 自动迁移已运行的 Runtime 或删除未使用的工作负载身份。
- 移植 ArkClaw Go `ubw/id` 生成器的内部位布局。VeADK 按已批准方案保留现有安全随机源和十二位后缀。

## 3. 场景与需求

### 场景 A：创建新的 Studio MPA

在云凭据有效且 Studio WorkloadPool 不存在时，运维执行 `veadk mpa create`，VeADK 创建共享 Pool、创建 `{MPA_AGENT_ID}-studio`、注入两个名称，然后继续既有 Skill Space、Tool、元数据和 Runtime 流程。

### 场景 B：重试或创建第二个 MPA

Pool 或 Identity 已存在时，命令按精确名称复用。并发创建冲突后重新读取并校验，而不是直接失败。

### 场景 C：权限不足

凭据缺少 Identity get/create 动作时，流程在创建 Tool、写数据库或创建 Runtime 前停止，只报告失败资源和所需动作，不输出凭据。

### 功能需求

- **FR-1：** `generate_mpa_agent_id()` 返回 `mi-` 加十二位小写 base36 字符；显式 `--mpa-agent-id` 必须符合相同规范。
- **FR-2：** WorkloadPool 固定为 `agentkit-studio-workload`；Identity 为 `{MPA_AGENT_ID}-studio`。
- **FR-3：** 工作负载资源采用 get-or-create 和精确名称幂等；`AlreadyExists` 后重新读取，其他错误关闭式失败。
- **FR-4：** 在本地输入校验后、Skill Space、Tool、PostgreSQL、VeFaaS 或 Runtime 修改前创建身份资源。
- **FR-5：** `--dry-run` 展示 MPA ID、Pool、Identity 和脱敏 Runtime 环境，不调用云或数据库。
- **FR-6：** Runtime 环境包含 `MPA_WORKLOAD_POOL_NAME` 和 `MPA_WORKLOAD_IDENTITY_NAME`；保持 `IDENTITY_STARTUP_ENABLED=false` 和 `A2A_TIP_VERIFY_ENABLED=false`。
- **FR-7：** 管理身份需要 `id:GetWorkloadPool`、`id:CreateWorkloadPool`、`id:GetWorkloadIdentity`、`id:CreateWorkloadIdentity`；鉴权失败时标明所需 action。
- **FR-8：** 配套 mpa-agent 在两个显式名称都存在时使用它们；都不存在时使用 ArkClaw 旧推导；只配置一个时拒绝启动。

## 4. 设计与契约影响

### 4.1 VeADK 职责

新增聚焦 MPA 的 `veadk.integrations.mpa.mpa_identity` 模块，负责名称和 get-or-create 编排。它复用现有 `veadk.integrations.ve_identity.IdentityClient` 上新增的兼容式、支持 Pool 的方法、已有火山引擎 Identity SDK，以及 `veadk mpa create` 已使用的管理凭据。现有 IdentityClient 方法签名保持兼容。

编排顺序变为：

`校验 ID/输入 -> ensure Pool -> ensure Identity -> ensure Skill Space -> ensure Tool -> 预写 mpa_meta -> 创建 Runtime -> 回写元数据 -> 验证`。

后续步骤失败后保留已创建的身份资源，使同 ID 重试可以收敛。该命令不会删除固定共享 Pool。

### 4.2 Runtime 消费契约

VeADK 注入：

```text
MPA_WORKLOAD_POOL_NAME=agentkit-studio-workload
MPA_WORKLOAD_IDENTITY_NAME=mi-xxxxxxxxxxxx-studio
```

独立版本的 mpa-agent 必须消费这组变量。在部署镜像包含配套提交前，真实 TIP 交换不能视为完成。

### 4.3 权限与安全

管理 AK/SK 只作为本地控制面输入，绝不注入 Runtime 环境。Identity API 错误只暴露 action 和资源名称。Pool 和 Identity 名称不是秘密。Runtime 获取 workload token 的权限仍由执行角色负责，本次管理面创建不扩大该权限。

### 4.4 兼容性

自动生成 ID 保持现有十二位后缀。新执行的 `veadk mpa create` 会拒绝显式非规范 ID；已有部署在重新创建前不受影响。非 Studio mpa-agent 在两个新变量都不存在时继续使用旧名称推导。

不修改 HTTP、SSE、数据库 schema、前端、session 或 event 契约，也不新增依赖。

## 5. 实现任务

- **T-1：** 在 `mpa_provision.py` 中增加规范 ID 校验和工作负载名称 helper。
- **T-2：** 增加最小 Identity SDK get-or-create 模块和错误映射。
- **T-3：** 在 `cli_mpa.py` 接入身份创建和 dry-run 输出；鉴权失败时报告所需 action。
- **T-4：** 更新 Runtime 环境组装和双语组件 spec。
- **T-5：** 增加 mpa-agent 配套配置和解析改动。
- **T-6：** 测试先行，执行针对性回归、pre-commit 和要求的更广 Python 门禁。

## 6. 验证与验收

| 需求 | 任务 | 验收标准 | 命令 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1、FR-2 | T-1 | AC-1：自动生成、显式 ID 和派生 Identity 名称符合规范 | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py` | pass；已包含在 39 条针对性用例中 |
| FR-3、FR-4、FR-7 | T-2、T-3 | AC-2：创建、复用、并发冲突和鉴权失败路径确定，副作用顺序正确 | `uv run --extra dev pytest tests/integrations/test_mpa_identity.py tests/cli/test_cli_mpa.py` | pass；已包含在 39 条针对性用例中 |
| FR-5、FR-6 | T-3、T-4 | AC-3：dry-run 无副作用，Runtime 收到显式变量对 | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py` | pass；已包含在 39 条针对性用例中 |
| FR-8 | T-5 | AC-4：mpa-agent 覆盖显式、旧推导和变量缺一场景 | 配套仓库针对性 pytest | pass；47 条用例，diff 覆盖率 100% |
| 全部 | T-6 | AC-5：仓库 pre-commit 和受影响回归通过 | `uv run --extra dev pre-commit run --all-files`；`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | 针对性测试和增量覆盖率通过（39 条、100%）；广泛回归先执行到 4563 passed、12 skipped、2 xfailed，另有 8 个可选依赖缺失失败；安装声明的 `extensions`、`sandbox` extras 后，受影响的 13 条用例全部通过 |
| 全部 | T-6 | AC-6：授权隔离账号可用新名称获取 workload token | 脱敏输出的手工云 smoke | not_run；需要明确提供真实凭据并部署配套镜像 |

## 7. 风险与恢复

- 创建固定 Pool 需要账号级 Identity 权限；权限缺失会在其他创建副作用前停止。
- 后续失败可能留下未使用 Identity；使用同一 ID 重试会复用，清理由运维手工执行。
- 新环境变量搭配旧 mpa-agent 镜像时，旧镜像仍使用旧名称。发布记录和真实验证必须标明配套镜像版本。
- 共享 Pool 把身份集中在同一命名空间；规范 MPA ID 避免误别名，Pool 容量监控属于本次变更外的运维职责。

## 8. 评审与交付记录

- 用户批准：2026-09-20，批准双仓方案并保留十二位后缀。
- 设计评审：2026-09-20 按仓库要求直接评审；身份副作用、权限集合、幂等、失败顺序、兼容性和配套消费者契约均已明确，无阻塞歧义。
- 实现评审：两轮检查覆盖命名和 API 契约、副作用顺序、幂等和错误处理、Secret 边界、兼容性与测试质量；无未关闭 finding。
- 验证：VeADK 针对性用例 39 条通过，增量覆盖率 100%；初次缺少可选依赖的用例在安装声明的 `extensions`、`sandbox` extras 后 13 条全部通过。配套 mpa-agent 针对性用例 47 条通过，全量覆盖率门禁为 2818 passed、21 skipped、总覆盖率 95.05%，增量覆盖率 100%。
- 剩余验证缺口：AC-6 仍为 `not_run`，因为需要有权限的真实账号和部署配套镜像后的 Runtime。
