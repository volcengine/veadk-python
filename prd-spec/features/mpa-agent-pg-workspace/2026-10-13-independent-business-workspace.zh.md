# 新建 MPA 使用独立业务 PostgreSQL Workspace

[English](2026-10-13-independent-business-workspace.md)

- Change ID：`mpa-agent-pg-workspace`
- 创建/修订：2026-10-13
- 状态：implemented
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-19
- 前置设计：[共享 PG 准备](../mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.zh.md)

## 背景与证据

`managed/pg_bootstrap.py` 使用核验后的账号、地域和项目给两个 Workspace 划定范围。`service.py` 将它们的 ID 和业务连接端点固定到部署记录。独立业务库因此仍共享计算资源和维护凭据。`deletion.py` 从 Runtime 获取管理库连接，不要求业务 Workspace 共享。MPA 镜像使用注入的 PG 连接，不依赖编排布局。

## 目标与非目标

新 Studio MPA 请求每个智能体使用一个业务 Workspace，保留 `mpa_admin_workspace/mpa_admin_db` 和账号/地域级网络、APIG 复用。已有智能体和已提交任务保持数据库绑定。本次不迁移数据、不初始化业务表、不删除 PG、不重新设计凭据、不改通用智能体、不更换镜像、不执行云资源变更。

## 场景与需求

- FR-1：两个新智能体共享管理资源，但拥有不同业务 Workspace、端点和 `mpa_agent_<hash>` 数据库。两个提供商使用原有 AIDAP 适配器。
- FR-2：重试、取消、创建结果未知和重启复用智能体范围内的引导身份。未知结果不盲目重复购买，保留现有确定终态失败恢复机制。
- FR-3：缺少 `businessWorkspaceMode` 表示旧共享请求契约。新 Studio 请求显式持久化 `per-agent`。已提交草稿不自动升级。
- FR-4：购买独立业务 Workspace 前，读取已准备好的管理库中的部署绑定。已有共享智能体保留共享 Workspace，已有独立智能体复用原 Workspace。冲突明确失败，不迁移、覆盖或删除业务数据。
- FR-5：PG 设置注入该智能体自己的业务凭据，共享注册库注入保持不变。部署记录保留 Workspace ID 和布局，不记录密钥。
- FR-6：保留三步向导，更新数据库说明，兼容手动/共享配置及通用智能体流程。删除继续保留业务 PG 资源。

## 设计与契约影响

增加 `managed.postgres.business-workspace-mode: shared|per-agent`，默认 `shared`；公开输入仅允许自动准备使用独立布局，不接受该布局下显式配置业务 Workspace ID。请求/配置增加可选 `businessWorkspaceMode`。内置 Studio 配置声明 `per-agent` 能力，但不改变旧请求的执行默认值；新表单显式提交。CLI/YAML 可显式启用。

向 PG 准备传入稳定内部 `agent_id`。管理范围保持不变。独立业务范围由账号/地域/项目及智能体 ID 的哈希确定，名称为 `mpa_agent_<agent_suffix>`，满足 AIDAP 名称限制。复用引导存储、归属校验、锁和就绪超时。独立模式先准备管理库，在原有注册库锁下读取已有绑定；无布局标记的旧记录视为共享。登记身份必须与引导状态、范围、端点一致。不仅凭名称判断归属，不接受冲突标签。注册库/连接错误在购买业务 Workspace 前停止。管理和业务准备仍位于有超时限制的原账号引导锁中，不宣称新增跨主机锁保证。

现有业务库准备器接收新的维护连接，数据库名称、标记和表结构归属不变。`bind_postgres_workspaces` 固定实际布局和 ID。Runtime/会话/技能/飞书及兄弟仓库 `agentkit-mpa-agent` 不需要修改。`openviking_users` 缺表是独立镜像/初始化问题。

安全：使用刷新后的提供商凭据，不向引导文件、注册记录、请求或文档写入 PG 密码及模型/OV Key。现有 Runtime 注册库凭据保持不变，本次不重构。取消/删除后 PG 仍计费，需管理员单独释放。

## 任务与受影响文件

- T-1 / FR-1,2,4：先写失败的模拟云测试，再改 `config.py`、`pg_bootstrap.py`、`service.py` 及 PG 测试。
- T-2 / FR-3,5：请求校验、任务透传、配置能力、前端类型/表单测试；保留请求指纹。
- T-3 / FR-6：国际化文案、双语组件契约/模块说明、构建产物；核对删除，不扩展删除范围。
- T-4：定向/更广 Python、Ruff/Pyright、前端测试/构建/国际化/资源检查、隔离浏览器验证和双语审查。

## 验收与验证

| 需求 | 任务 | 验收 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1,2,4,5 | T-1 | AC-1：新业务 Workspace 不同；同智能体重试稳定；旧绑定保留；未知结果不重复创建 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_auto_pg.py tests/integrations/mpa_managed/test_service.py` | pass |
| FR-3 | T-2 | AC-2：模式经 BFF/任务/runner 持久化；旧请求缺省为共享；恢复表单不升级 | 定向配置/路由/任务与前端测试 | pass |
| FR-6 | T-3,4 | AC-3：三步 UI 兼容、通用智能体/删除回归、文档/资源同步 | 更广 managed Python，`npm --prefix frontend test`、构建、国际化/资源及浏览器 | pass |

验证范围：`71175c68` 上的当前工作区差异，包含先前未提交 OV 改动；日期 2026-10-13。真实云创建：not_run（未授权隔离云创建）。Codex 进程 smoke 和 harness 覆盖：not_applicable（契约未变）。提交/推送/提交前同步：not_run（未请求）。

## 风险与恢复

更多 Workspace 增加云资源数量和可能的最低计算费用。不迁移数据。共享管理 PG 仍是控制面故障域。引导文件/锁位于本地，跨主机未知创建仍遵循现有明确失败的恢复限制。独立 Workspace 不能代替 MPA 业务表初始化。API 限制和权限沿用现有 PG 适配器。

## 审查与批准

`review-spec` 不可用，已直接审查边界、重试/取消、已有绑定、归属、密钥、兼容性、可测试性和双语一致性，无设计阻塞。用户于 2026-10-13 通过“那帮我改吧”批准新 MPA 独立 Workspace，随后要求确认仓库其他影响。批准包括创建/请求/绑定/UI 适配，不包括迁移或 PG 删除。未授权提交、推送或部署。

## 最终实现审查与验证（2026-10-13）

隔离实现范围内 T-1 至 T-4、AC-1 至 AC-3 已完成。已审查请求到 runner 的透传、旧登记绑定保留、智能体范围名称/归属、元数据未知状态、超时、注册库关闭及 PG 保留删除行为，无阻塞代码/契约问题。

- 先写回归：11 项新 Python 用例和新前端布局用例在对应实现前失败；最终新 PG 测试集 15 项通过。
- pass：`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_skill_space.py tests/integrations/test_ve_faas_deploy_image_key_auth.py -q --no-cov`，951 项通过，两个 worker。无关完整 SDK 测试集为 not_run，改动限定受管 MPA 创建。
- pass：`npm --prefix frontend test`，1,379 项 Node 测试和 81 项 React 测试；`npm --prefix frontend run build`、`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`（113 文件、350 引用）。
- pass：固定 Ruff 0.11.12 及 Pyright 检查所有 14 个改动/新增 Python 文件，包括前置 OV 改动。本地环境缺少 Ruff/Pyright 可执行文件，使用 `uvx --from ruff==0.11.12 ruff check <files>` 和 `uvx pyright --pythonpath .venv/bin/python <files>`，未修改机器全局配置。
- pass：实际 React 弹窗配隔离模拟 API 的真实浏览器验证，包括新/旧请求模式、失败重试、取消确认、加载/错误/空输入状态、键盘下一步、390×844 窗口及截图检查。已移除临时页面/服务/浏览器标签，没有创建云资源。原有 IME/通用智能体自动测试保持通过，未改输入处理器。
- pass：双语及相对链接审查、`git diff --check`，按仓库 Gitleaks 配置检查 94 个改动/新增文件。额外默认规则扫描构建包命中一段压缩编辑器表达式（`p.anchor.key`），已确认为供应商代码误报；仓库策略原本排除生成的供应商包。未弱化扫描策略或 hook。
- not_run：实际 AIDAP 分配/Runtime 部署、数据迁移、提交/推送和提交前同步，未授权/未请求。Runtime PG 部署参数及两个提供商分支已离线验证。共享控制 PG 和保留 Workspace 的费用仍是明确的运行限制。
