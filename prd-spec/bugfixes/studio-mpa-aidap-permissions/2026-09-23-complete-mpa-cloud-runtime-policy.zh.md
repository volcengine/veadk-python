# 补齐 Studio MPA 云端运行策略

[English](2026-09-23-complete-mpa-cloud-runtime-policy.md)

- 变更 ID：`studio-mpa-cloud-runtime-permissions`
- 创建/修订日期：2026-09-23
- 状态：approved
- 相关组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)
- 前序设计：[仅 AIDAP 权限修复](2026-09-23-complete-aidap-runtime-policy.zh.md)
- 用户批准：2026-09-23，授予 MPA 创建所有阶段使用的全部权限，包括 VPC 和 APIG。

## 背景与证据

云端 Studio 使用 `VeADKFrontendServiceRole` 的 STS 凭据，本地部署通常使用权限更广的运维 AK/SK。初次审计发现 4 项 AIDAP 权限缺失。本次扩展代码审计覆盖 `provision()` 可达的每个直接云端适配器：

| 阶段 | 直接操作 | 本次修订前的覆盖情况 |
| --- | --- | --- |
| 账号检查 | `sts:GetCallerIdentity` | 缺失 |
| 自动 PG | 9 项明确的 `aidap:` Action | 前序修复后完整 |
| 网络 | `ecs:DescribeZones`；VPC 查询/列表/创建操作 | 缺少 `ecs:DescribeZones`、`vpc:DescribeSubnetAttributes`、`vpc:CreateVpc`、`vpc:CreateSubnet` |
| 网关 | APIG 列表/创建/详情及 IM Gateway 创建/状态操作 | 5 项全部缺失 |
| Worker、Skill Space、Runtime | AgentKit 查询/列表/创建/更新操作 | 已由现有 `agentkit:*` 覆盖 |
| 数据库/OpenViking | PostgreSQL 协议及 Runtime 环境变量注入 | 无额外云 IAM Action |

该策略缺口会使云端流程在连续阶段失败，即使本地创建能够成功。

## 目标与非目标

目标：

- 覆盖当前 MPA 创建路径直接执行的每项云 IAM Action。
- 保持默认角色对已有部署的幂等刷新。
- 用一个回归测试记录完整的跨服务权限集合。
- 保持客户自有角色所有权和凭据处理不变。

非目标：

- 授予 `aidap:*`、`vpc:*`、`ecs:*` 或 `apig:*`。
- 增加当前实现不可达的猜测性 Action。
- 在本修复中替换现有 `agentkit:*` 策略。
- 修改编排、API 请求、重试/状态行为或执行部署。

## 场景与需求

- **FR-1：**默认 Studio 策略包含 `sts:GetCallerIdentity`。
- **FR-2：**策略包含 `NetworkCloud` 使用的全部 7 项网络权限：`ecs:DescribeZones`、`vpc:DescribeVpcs`、`vpc:DescribeVpcAttributes`、`vpc:DescribeSubnets`、`vpc:DescribeSubnetAttributes`、`vpc:CreateVpc` 和 `vpc:CreateSubnet`。
- **FR-3：**策略包含 `GatewayCloud` 使用的全部 5 项 APIG 权限：`apig:ListGateways`、`apig:CreateGateway`、`apig:GetGateway`、`apig:CreateIMChannelGateway` 和 `apig:GetIMChannelGatewayStatus`。
- **FR-4：**策略保留自动 PG、Worker、Skill Space 和 Runtime 操作所需的 `aidap:DescribeWorkspaces`、`aidap:CreateWorkspace`、`aidap:DescribeWorkspaceDetail`、`aidap:DescribeBranches`、`aidap:DescribeComputes`、`aidap:DescribeWorkspaceEndpoint`、`aidap:DescribeDBAccounts`、`aidap:DescribeDatabases`、`aidap:DescribeDBAccountConnection` 及 `agentkit:*` 覆盖。
- **FR-5：**`studio update` 刷新默认角色策略；客户自有角色保持不变。
- **FR-6：**不为 STS、ECS、VPC、APIG 或 AIDAP 引入新的服务通配符。

## 设计与契约影响

在 `FRONTEND_DEPLOY_POLICY` 中增加 10 项缺失的明确 Action：STS 1 项、ECS 1 项、VPC 3 项、APIG 5 项。现有 Action 不变。策略已经包含流程需要的 4 项 VPC 读取权限、全部 9 项 AIDAP 权限及 `agentkit:*`。

`ensure_default_frontend_role_policy` 已负责更新并回读核验 `VeADKFrontendPolicy`，因此已有默认部署会在 `studio update` 时取得扩展后的策略文档。客户角色不被自动修改，须由运维自行授予同一组必需权限。

不修改密钥、状态、API、并发、网络拓扑或云资源生命周期。新增权限仅授权已批准流程当前正在尝试的操作。Runtime 绑定的角色属于独立信任边界；本次修改的是 Studio 执行角色，不是 Runtime 工作负载权限。

## 实现任务

- **T-1（FR-1–FR-6）：**将仅 AIDAP 回归扩展为完整 MPA 云端策略测试，并确认修改策略前测试失败。
- **T-2（FR-1–FR-3、FR-6）：**增加 10 项缺失的明确 Action。
- **T-3（FR-4、FR-5）：**运行策略刷新和 MPA 集成回归。
- **T-4：**运行 Ruff、Pyright、双语一致性、空白检查及默认并行 Python 回归。
- **T-5：**另行授权后部署，并执行一次覆盖全部阶段的真实 MPA 创建重试。

涉及文件：`veadk/cli/frontend_deploy_policy.py`、`tests/cli/test_frontend_deploy_iam.py`、本双语 PRD、前序 PRD、双语组件规范及当前调试记录。

## 验证与验收

| 需求 | 任务 | 验收标准 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1`–`FR-4`、`FR-6` | `T-1`、`T-2` | `AC-1`：默认策略包含完整明确的 MPA 权限集合且不引入新服务通配符 | `uv run --extra dev pytest tests/cli/test_frontend_deploy_iam.py tests/cli/test_studio_update_permissions.py -q` | `pass`，22 项测试，2026-09-23 |
| `FR-5` | `T-3` | `AC-2`：默认角色刷新及客户角色保留测试通过 | 同一目标命令 | `pass`，2026-09-23 |
| `FR-1`–`FR-6` | `T-3`、`T-4` | `AC-3`：受影响及默认回归门禁通过 | 受影响测试、Ruff、Pyright、双语/空白检查及默认并行回归 | 受影响/静态检查 `pass`；默认回归因无关基线/环境问题 `fail`，2026-09-23 |
| `FR-1`–`FR-5` | `T-5` | `AC-4`：已部署创建通过 PG、网络、网关、Worker、Skill Space、Runtime 和就绪阶段 | 经授权部署及真实冒烟 | `not_run`；未获部署授权 |

由于不修改 UI 或 HTTP 结构，前端测试/构建不适用。静态策略检查不能证明 IAM 传播、服务开通、配额、资源兼容性或真实网络访问。

## 风险与恢复

- 服务端可能强制要求无法从直接客户端调用观察到的依赖权限；仍须真实冒烟验证。
- 更新后 IAM 策略传播可能延迟。
- 已有显式拒绝、服务未开通、配额限制或资源冲突仍优先生效。
- 回滚会恢复已知不完整策略。

## 审查与交付记录

2026-09-23 直接审查沿 `provision()` 跟踪了 `RuntimeCloud`、`PGCloud`、`NetworkCloud`、`GatewayCloud`、`WorkerCloud` 以及 Skill Space/Runtime 操作，并检查最小权限、服务/Action 拼写、默认角色刷新、客户角色所有权、安全边界、兼容性、可测试性和双语一致性。用户已批准扩展后的全阶段范围。

完整策略测试在修改前按预期失败，并恰好列出审计所得的 10 项缺失 Action。修改后，22 项 IAM/更新测试及 418 项受影响 MPA/CLI 测试通过。`uv run --with ruff ruff check veadk/cli/frontend_deploy_policy.py tests/cli/test_frontend_deploy_iam.py`、等效 Pyright 命令、策略唯一性、双语标识及 `git diff --check` 均通过。

规定的默认回归命令 `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` 执行结果为 5,216 通过、11 跳过、2 xfailed、8 失败、2 个收集错误。6 个 Harness 失败和 2 个 Sandbox 收集错误需要当前未声明的可选依赖 `llama_index`/`anthropic`；2 个优化 Skill 测试因并行地域状态串扰失败，串行复跑为 2 项通过。以上均不涉及本次策略或测试文件。部署和真实 MPA 创建仍等待授权，为 `not_run`，因此生命周期状态保持 `approved`。
