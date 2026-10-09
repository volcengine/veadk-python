# MPA 网络由共享注册库驱动创建

[English](2026-09-28-registry-owned-network.md)

- 变更 ID：`mpa-shared-network-bootstrap`
- 创建/修订日期：2026-09-28
- 状态：implemented
- 契约：[Studio 创建 CON-1/2/8/13](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与范围

`studio_profile.py` 固定了已有 VPC、子网和 APIG。虽然
`AccountNetworkProvisioner` 与 `SharedAPIGService` 已支持共享资源持久化，
Studio 在管理注册库为空时仍会接管这些固定资源。用户要求创建流程从
`mpa_admin_workspace/mpa_admin_db` 复用已登记资源，缺失时创建并保存。

目标：让 Studio 内置入口使用已有的自动准备流程。
非目标：网络迁移、删除/重置已有记录或资源、提高配额、改变共享范围、修复
Runtime 重试、重新设计数据库权限，以及修改通用智能体聊天或 UI。

## 需求与设计

- FR-1：移除内置 VPC/子网/APIG ID。保留现有账号、地域、镜像、模型及凭据要求。
  CLI 显式接管保持不变。
- FR-2：自动准备 PG 后，以解析出的管理库连接保存 `mpa_account_network`、
  `mpa_account_apig` 和部署记录。按核验后的账号和地域共享。空注册库时先创建
  VPC/子网，再创建 APIG 和 IM Gateway、持久化资源 ID，再创建智能体相关资源。
- FR-3：有记录时校验并复用已登记的网络和网关。部分完成时依据持久化意图和资源
  ID 恢复。权限错误、资源不可用、配额不足及创建结果未知不能当作记录缺失或成功。
- FR-4：保留账号锁和调用前持久化。并发不能重复创建；取消/超时保留已记录资源。
  本次不删除云资源、不改写现网注册记录。

复用已有 provisioner、表结构和锁，不增加另一套资源注册库或选择器。
不改变 HTTP/表结构/前端产物。已有记录（包括配额耗尽的 VPC）仍复用；修改这些
记录需要另行明确迁移范围。自动创建 APIG 保持已有 Serverless 请求；APIG 配额和
私网数据库连通性仍是部署前提。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1 | T-1 移除固定资源默认值 | AC-1 内置配置不含接管 ID | 配置回归在修复前失败 |
| FR-2/3 | T-2 使用模拟 PG/云端执行 Studio 配置的 service 流程 | AC-2 共享记录使用管理库；首次创建、后续复用 | service 回归 |
| FR-3/4 | T-3 执行恢复/并发测试 | AC-3 不确定创建和失败不会重复创建资源 | 网络/网关/PG 测试集 |
| FR-1–4 | T-4 同步文档并审查 | AC-4 双语契约与操作说明一致 | 链接、空白、Ruff/Pyright、托管创建回归 |

影响文件：`studio_profile.py`、托管配置/service 测试、Studio 创建规范双语文件、
托管 README 双语文件，以及 `frontend/README.md` 的操作说明。

## 审查与批准

用户在 2026-09-28 明确要求按注册库复用、创建缺失的共享 VPC/APIG，已批准该范围。
这取代此前将所有新智能体迁往另一套网络的建议，不意味着批准修改现网记录或
删除资源。`review-spec` 不可用；已直接审查范围、数据来源、兼容性、错误、并发、
安全、可测试性和双语一致性。无设计阻塞：已有 provisioner 实现 FR-2–4，缺陷在
内置配置的资源选择。

## 验证记录

范围：基于 `79acf209` 的工作区 diff，2026-09-28。

- `pass`：先写测试复现；修复前，新的配置断言和四个 service 场景均因固定资源 ID 失败。
- `pass`：`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py -q --tb=short`
  — 414 项通过，五条依赖弃用警告。
- `pass`：测试 lint 收尾后，执行
  `uv run --extra dev pytest tests/integrations/mpa_managed/test_studio_shared_resources.py -q`
  — 四项通过。
- `pass`：改动 Python 文件的 Ruff 和 Pyright。直接 `uv run ruff`/`uv run pyright`
  不可用，使用 `uv run --with ruff --with pyright <tool> <changed-python-files>`
  的隔离工具环境。Pyright 零错误/警告。首次 uv 缓存访问受沙箱限制，获准提权后运行。
  未修改全局设置或项目依赖；按用户要求仅在此记录。
- `pass`：`uv run --with pre-commit pre-commit run --files <changed-files>`：
  仓库固定版本 Ruff 检查/格式通过。gitleaks 暂存区钩子通过，但不覆盖未暂存文件；
  另以脱敏目录扫描覆盖全部改动/新增文件。YAML 钩子：`not_applicable`，无 YAML 变更。
- `pass`：`git diff --check`、新增相对链接及双语需求/任务/验收 ID 核对。
  最终直接审查未发现代码或双语一致性阻塞问题。
- `not_run`：真实云端冒烟及真实 PostgreSQL 集成。新增场景模拟云/PG 边界，不能证明
  现网权限、配额或连通性。本次未修改现网注册记录或资源。
- `not_applicable`：浏览器/前端构建，无 UI 或 HTTP 结构变化。采用受影响的 414 项测试，
  未执行全仓回归：生产代码仅移除内置资源选择默认值。

本地代码变更的 T-1–4 与 AC-1–4 已完成。已有注册记录仍为准；重启本地 Studio
或重新部署云端 Studio 后加载新默认配置。本次未提交、推送或部署。

## PR #17 rebase 协调 — 2026-10-07

用户批准解决与 `origin/main`（`e0448a4d`）的冲突。直接评审保留 main 的 Workload Identity 初始化、Worker 元数据等待、MPA 优先 A2A 发现及 `DISABLE_JWT_AUTH=true`，同时保留本分支的注册库资源选择、Worker 命名及带类型的事件去重。不引入新的生产契约。文档保留双方内容，Worker 测试导入保留 `_missing_worker_metadata`。移除无关的 512 行锁文件删除，保留 main 的依赖记录。

首次离线组合回归得到 686 项通过、四项失败：共享资源测试的模拟云对象不返回凭据，而 main 现在会调用 `ensure_workload_identity`。在该测试边界使用 `AsyncMock` 返回按智能体区分的 workload identity，并断言初始化调用及 Runtime 环境传递。保持生产身份初始化逻辑和所有网络/PG 断言。这属于已批准 rebase 范围内的测试夹具适配，不进行真实云操作。重跑后补充验证结果。

### 协调结果

范围：2026-10-07，PR #17 在 `e0448a4d` 上的 rebase 差异。
- `pass`：`uv run --extra dev pytest -n 2 tests/integrations/mpa_managed tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py tests/cli/test_cli_mpa.py tests/cli/test_cli_mpa_control.py tests/cli/test_mpa_a2a_url.py tests/integrations/test_mpa_provision_env.py -q` — 690 项，14 条依赖弃用警告，使用两个 worker。适配 Identity 边界后，先前失败的四项夹具场景通过。
- `pass`：`node --test frontend/tests/mpaResponseGrouping.test.mjs frontend/tests/mpaContentPreservation.test.mjs frontend/tests/mpaSessionProtocol.test.mjs frontend/tests/runSseAbort.test.mjs` — 71 项。
- `pass`：`uv run --extra dev pre-commit run --all-files`；修改的 Python 文件经 Pyright 检查零错误/警告；适配后的夹具额外通过 Ruff/Pyright。
- `pass`：双方所有 Worker 测试函数均保留（合并后 13 个）；三个原生产补丁相对各自基线不变；main 的发现/鉴权和锁文件完全保留。已检查双语文档/相对链接及 diff 空白。
- `not_run`：全仓回归、真实云端/浏览器冒烟及部署。本次为冲突协调及仅测试依赖适配，目标创建/代理/协议测试验证受影响兼容性。未修改前端源码/生成资源或云资源。
