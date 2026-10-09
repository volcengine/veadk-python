# 补齐 Studio AIDAP 运行权限

[English](2026-09-23-complete-aidap-runtime-policy.md)

- 变更 ID：`studio-mpa-aidap-permissions`
- 创建/修订日期：2026-09-23
- 状态：superseded
- 相关组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)
- 后继设计：[补齐 MPA 云端运行策略](2026-09-23-complete-mpa-cloud-runtime-policy.zh.md)
- 用户批准：2026-09-23，加入自动 PostgreSQL Workspace 流程需要的全部权限。

## 背景与证据

云端 Studio MPA 创建现已通过可写状态初始化，但在 `admin_workspace` 阶段失败。本地部署可成功，是因为本地使用运维 AK/SK；VeFaaS 部署通常使用 `VeADKFrontendServiceRole` 的 STS 凭据。

`PGCloud` 调用 9 项 AIDAP 操作：`DescribeWorkspaces`、`CreateWorkspace`、`DescribeWorkspaceDetail`、`DescribeBranches`、`DescribeComputes`、`DescribeWorkspaceEndpoint`、`DescribeDBAccounts`、`DescribeDatabases` 和 `DescribeDBAccountConnection`。默认 Studio 策略目前只授予 5 项集合查询权限，缺少同一流程所需的创建、详情、端点和账号连接操作。代码与策略不一致已确认；由于当前 shell 没有云凭据或日志访问能力，尚未取得服务商的确切错误码。

预期行为是默认云端 Studio 部署可使用其执行角色完成受支持的自动 PostgreSQL 准备。实际行为是该角色缺少失败阶段及后续流程实际调用的 4 项权限。

## 目标与非目标

目标：

- 授予 `PGCloud` 当前实际调用的全部 9 项 AIDAP Action。
- 在正常 `studio update` 角色策略刷新中更新已有 `VeADKFrontendPolicy`。
- 增加回归测试，将默认策略与自动 PG 调用面绑定。
- 保持凭据脱敏、HTTP 行为、幂等性和自定义角色所有权不变。

非目标：

- 授予 `aidap:*` 或无关的 AIDAP 管理操作。
- 自动改写客户自有 Studio 角色。
- 修改 AIDAP 编排、重试行为、Workspace 生命周期或执行部署。

## 场景与需求

- **FR-1：**使用默认 Studio 执行角色时，其自定义策略包含 `PGCloud` 所需的全部 9 项 AIDAP Action。
- **FR-2：**已有默认 Studio 角色执行 `studio update` 时，应替换自定义策略文档并核验刷新后的 Action 集合。
- **FR-3：**使用客户自有 Studio 角色时，更新流程不得自动替换其策略；运维须自行授予同一组必需权限。
- **FR-4：**策略只授予明确 Action，不增加 `aidap:*`。

## 设计与契约影响

在 `FRONTEND_DEPLOY_POLICY` 中增加以下缺失 Action：

- `aidap:CreateWorkspace`
- `aidap:DescribeWorkspaceDetail`
- `aidap:DescribeWorkspaceEndpoint`
- `aidap:DescribeDBAccountConnection`

它们与现有 5 项 Action 共同精确覆盖 `PGCloud` 调用的方法。`ensure_default_frontend_role_policy` 已负责更新并核验 `VeADKFrontendPolicy`，无需修改 IAM 更新算法。为保持所有权边界，客户自有角色仍不自动修改。

云端凭据来源保持不变：本地执行可使用 AK/SK，VeFaaS 读取角色 STS 凭据。不持久化或返回任何凭据、服务商响应或连接串。新增创建权限用于已有且经用户批准的自动 Workspace 操作，不引入新的云端副作用。API、配置、状态、并发及兼容性契约均不作其他修改。

## 实现任务

- **T-1（FR-1、FR-4）：**为精确的 9 项权限集合增加先失败的策略完整性测试。
- **T-2（FR-1）：**在 `veadk/cli/frontend_deploy_policy.py` 中增加 4 项缺失 Action。
- **T-3（FR-2、FR-3）：**运行已有默认角色刷新及自定义角色保留测试。
- **T-4：**运行受影响的 MPA/CLI 测试及改动文件静态检查。
- **T-5：**另行获得部署授权后更新 Studio，并执行真实云端创建冒烟测试。

涉及文件：`veadk/cli/frontend_deploy_policy.py`、`tests/cli/test_frontend_deploy_iam.py`、本双语 PRD 及 Studio MPA 创建双语组件规范。

## 验证与验收

| 需求 | 任务 | 验收标准 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1`、`FR-4` | `T-1`、`T-2` | `AC-1`：策略包含精确的必需 AIDAP 子集且不含 `aidap:*` | `uv run --extra dev pytest tests/cli/test_frontend_deploy_iam.py tests/cli/test_studio_update_permissions.py -q` | `pass`，21 项测试，2026-09-23 |
| `FR-2`、`FR-3` | `T-3` | `AC-2`：默认策略刷新及自定义角色保留测试通过 | 同一目标测试命令 | `pass`，2026-09-23 |
| `FR-1` | `T-4` | `AC-3`：受影响的 MPA/CLI 回归及 Ruff/Pyright 通过 | `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py tests/cli/test_studio_update_permissions.py -q`；`uv run --with ruff ruff check veadk/cli/frontend_deploy_policy.py tests/cli/test_frontend_deploy_iam.py`；`uv run --with pyright pyright veadk/cli/frontend_deploy_policy.py tests/cli/test_frontend_deploy_iam.py` | `pass`，417 项测试、Ruff 及 Pyright，2026-09-23 |
| `FR-1`、`FR-2` | `T-5` | `AC-4`：已部署 Studio 通过 `admin_workspace`，并完成创建或进入下一个合理阶段 | 经授权的 `studio update` 及真实创建 | `not_run`；未获部署授权 |

由于不修改 UI、浏览器行为或 HTTP 结构，前端测试/构建不适用。本地策略测试只能证明文档完整，不能证明 IAM 传播或真实 AIDAP 访问成功。

## 风险与恢复

- 更新后 IAM 策略传播可能延迟；仅在策略可见后重试。
- 服务端权限名称不匹配或无关的账号/项目冲突仍可能导致云端冒烟失败；须保留脱敏诊断。
- 回滚会移除 4 项 Action，并恢复已知的策略缺口。

## 审查与交付记录

2026-09-23 直接设计审查已检查策略范围、最小权限、已有角色刷新、客户角色所有权、凭据处理、兼容性、可测试性及双语一致性，无阻塞问题。用户已明确批准加入该流程使用的全部权限。

策略修改前，回归测试按预期失败并列出 4 项缺失 Action。修改后，21 项权限目标测试及 417 项受影响 MPA/CLI 测试通过；Ruff、Pyright、双语标识检查和 `git diff --check` 均通过。仓库规定的裸 `uv run --extra dev ruff ...` 命令因当前 dev 环境未声明 Ruff 而为 `blocked`，等效的隔离命令 `uv run --with ruff ...` 已通过。部署和真实 AIDAP 验证仍等待单独授权，为 `not_run`，因此生命周期状态保持 `approved`。
