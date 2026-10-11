# 分离管理与业务 PostgreSQL Workspace

[English](2026-09-23-two-pg-workspaces.md)

- 变更 ID：`mpa-two-pg-workspaces`；日期：2026-09-23；状态：已实现，真实数据库切换待操作员配置。
- 用户决定：共享记录迁入 `mpa_admin_workspace/mpa_admin_db`；所有智能体业务库共同放在另一 Workspace，继续按数据库隔离。本方案取代之前的[每智能体一个 Workspace 提案](2026-09-23-space-scoped-manual-pg.zh.md)。沿用此前要求，Workspace 由操作员预先创建。
- 归属：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 证据、目标与边界

`Profile.admin_url` 已用于业务库管理，`Profile.shared_url` 用于网络/APIG/部署注册库和 Runtime 启动配置。当前配置可能让两者指向同一 Workspace。只把连接切到空注册库会丢失复用和归属记录。已有业务库及 Runtime PG 身份必须保持稳定。

目标包含一个名为 `mpa_admin_workspace` 的管理 Workspace，其中 `mpa_admin_db` 存现有三张共享注册表；另一个业务 Workspace 存所有 `mpa_agent_<hash>` 库。保留按账号/地域共享网络和 APIG 的规则。通用智能体、每智能体创建 Workspace、Space 列表/选择、自动创建云 Workspace、业务数据迁移、去除现有 Runtime 启动契约中的注册库凭据，以及自动执行线上切换/删除，均不在本次范围。

## 需求与设计

- FR-1：可选 `managed.postgres` 启用两 Workspace 结构。必须提供不同且非空的 `admin-workspace-id` 和 `business-workspace-id`；`admin-workspace-name` 固定为 `mpa_admin_workspace`。`SHARED_APIG_DATABASE_URL` 必须指向 `mpa_admin_db`，且主机与业务库管理员连接不同。ID 和主机归属由操作员在 AIDAP 控制台核验，本地校验不代表已调用云 API 核验；不同主机名本身不能证明 Workspace 不同。没有该节的旧配置保持兼容。
- FR-2：该节中的 `admin-database-url-env` 指向准备管理库所需的独立维护连接，主机/端口必须与共享注册库连接一致。正常创建流程不会自动建立空管理库。显式执行 `veadk mpa init-admin-db --config ...` 才会创建/复用 `mpa_admin_db`、校验配置的注册库属主并初始化已知注册表。已有数据库必须属于该用户，且只能含已知的 public 表。SQL 标识符正确引用；输出不含 URL 或密码。维护凭据不会进入 Runtime 或浏览器载荷。
- FR-3：命令可加 `--source-url-env OLD_SHARED_APIG_DATABASE_URL` 复制现有三张共享表并保留源库。操作员必须在迁移及切换期间停止创建流程和注册库写入者。源库只读；表锁限制并发写入；目标事务保证整批复制或整批回滚；重跑接受相同记录，但拒绝冲突或多余的目标记录。复制保留 JSON、属主哈希、智能体 ID、网络/APIG ID、业务库身份。锁、语句和总体执行时间均有上限；取消时关闭连接。云变更和 Runtime 发布是后续显式运维步骤。
- FR-4：新创建流程只使用业务连接准备 `mpa_agent_<hash>`，只使用管理连接准备注册库/启动配置。为新记录或核验过的旧部署记录保存两套配置的 Workspace ID。已登记 Workspace 绑定变化必须在云资源变更前失败；旧记录的业务主机变化同样失败。首次创建及同 ID 重试沿用现有数据库命名、归属和清理规则。
- FR-5：Studio 配置接口返回安全的布局/名称信息。PG 步骤说明此处配置共用的业务 Workspace，并为本 MPA 创建独立数据库；管理 Workspace 由服务端配置。保留旧客户端及草稿/任务恢复。双语与 YAML 示例保持一致。

## 任务、验收与验证

审查补充：迁移拒绝源部署记录中的 `pending=true`。其持久化 Runtime 请求哈希包含旧注册库地址，操作员必须先在原配置下完成或核对这些部署再复制，以保持幂等恢复，不静默改写哈希。

| 任务 | 需求 | 验收 |
| --- | --- | --- |
| T-1 | FR-1 | AC-1：拒绝相同 ID/主机、错误管理库名和维护连接目标；旧配置仍可加载。 |
| T-2 | FR-2–3 | AC-2：离线测试覆盖初始化、缺表/异类表、复制/重试/冲突/回滚/超时；不修改源库。 |
| T-3 | FR-4 | AC-3：两个智能体在同一业务主机上使用不同库名并接收同一管理连接；绑定变化提前失败。 |
| T-4 | FR-5 | AC-4：本地化弹窗/API 测试、浏览器检查、前端构建及资源；双语运维说明包含迁移与恢复。 |

文件：managed 配置/服务及新管理库模块；CLI 注册/模块；Studio 弹窗/类型/本地化；managed 测试、双语组件契约/操作指南/YAML 示例。执行定向 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`、变更文件 Ruff/Pyright、前端测试/构建/国际化/资源检查，再在环境允许时执行两个 worker 的非冒烟 Python 回归。这些测试不变更真实资源或私有配置。

## 审查、风险及交付记录

### 实现审查与验证，2026-09-23

范围：基线 `821f0f36`、分支 `feat/from-main-20260922` 的未提交工作区差异，包含已有的三步创建修改。未执行提交、推送、私有配置变更、云 Workspace 创建、真实数据复制或 Runtime 发布。T-1–T-4 已实现；AC-1–AC-3 有离线回归覆盖，AC-4 有前端/浏览器/构建覆盖。数据库事务和锁使用隔离模拟测试，未连接真实 PostgreSQL 服务。

| 检查 | 状态 | 证据 |
| --- | --- | --- |
| 定向 Python | pass | `UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q`，317 项通过。覆盖主机分离、复制冲突回滚、取消/错误清理、CLI 脱敏、两个智能体同业务主机不同数据库及安全配置 API。 |
| 前端 | pass | `npm --prefix frontend test`：1305 项 Node 测试、33 项 Vitest；单独 `npm --prefix frontend exec -- vitest run frontend/tests/mpaCreation.test.tsx`：16 项通过。 |
| 构建/国际化/资源 | pass | `npm --prefix frontend run build`、`check:i18n`、`test:webui-assets`；检查 2 个语言/21 个命名空间、104 个打包文件/248 个内部引用。 |
| 浏览器 | pass | 实际弹窗配合模拟配置 API：检查中英文管理/业务说明、AIDAP 链接、正常步骤导航及 390 px iframe 窄窗口。未提交云创建。加载/错误/取消/重试由自动化测试覆盖，本次未新增真实资源运行。临时预览文件/服务已清理。 |
| Ruff | pass | 使用缓存的 pre-commit Ruff 检查并格式化变更 Python 文件；项目 dev extra 没有安装独立 `ruff` 命令。 |
| Pyright，本功能代码/测试 | pass | 缓存 Pyright 配合 `--pythonpath .venv/bin/python` 检查配置/服务/新增数据库及 CLI 模块、变更 managed 测试，无错误。 |
| Pyright，CLI 注册文件 | fail（既有） | `cli_mpa.py` 旧 VeFaaS 部署存在返回 3 或 5 元组与解包不匹配；对 `git show HEAD:veadk/cli/cli_mpa.py` 复现相同问题，新增注册未引入类型错误。 |
| 双 worker 全量 Python | fail（环境） | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：4980 通过、76 失败、11 跳过、2 xfailed、5 错误。允许本地端口后重跑失败节点：73 通过、6 失败、2 收集错误。余下 Harness/self-host 测试缺少 `llama_index`/`anthropic`，相关文件未修改；不宣称全量回归全绿。 |
| 真实 SQL/云切换 | not_run | 尚未配置新管理 Workspace/凭据及停止写入的迁移窗口。不宣称已验证真实锁、属主、连通性或已有 Runtime。 |
| 全仓库 pre-commit | not_run | 未要求提交；后续提交前需同步分支并执行。 |

直接审查确认：表键及业务库推导不变，管理维护凭据不注入 Runtime，迁移不覆盖/删除，目标三表事务整体回滚，超时有界、取消向上传递，正常输出不含连接 URL/密码。操作员必须协调所有使用方统一注册库端点。保留已有数据库授权；Workspace 分离本身不会增强业务库之间的权限隔离。

缺少 `review-spec`，采用直接审查：用户已批准两 Workspace 拓扑；之前每智能体 Workspace 和 Space 选择的未答问题被新方案取代。保留现有 MPA 镜像的协议/表兼容性，保留源注册库以供恢复，只在显式初始化命令中要求维护凭据。已有 Runtime 发布前仍使用旧共享 URL，因此恢复注册库写入前须协调迁移。新库开始写入后不得直接切回旧库，应先对账。不从端点名称推断云账号或 Workspace 归属。设计建立时实现/测试/真实云验证状态均为 `not_run`，后续补充实际结果。
