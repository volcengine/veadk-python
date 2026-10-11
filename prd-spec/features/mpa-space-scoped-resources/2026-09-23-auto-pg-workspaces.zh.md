# 自动准备管理与业务 PG Workspace

[English](2026-09-23-auto-pg-workspaces.md)

日期：2026-09-23。状态：用户要求实施前述自动 PG 流程，已批准实施。归属：[Studio 创建契约](../../../specs/studio-mpa-creation/README.zh.md)。本方案将[两 Workspace 设计](2026-09-23-two-pg-workspaces.zh.md)的推荐路径改为自动准备，同时保留手动配置和显式迁移兼容性。

## 意图与证据

使用可刷新的 VeADK 部署凭据，经 STS 核验后，为每个账号/地域/项目准备一个 `mpa_admin_workspace/mpa_admin_db` 和一个业务 Workspace（默认 `mpa_business_workspace`）。每个 MPA 继续使用独立命名的业务库。已安装 `volcenginesdkaidap.AIDAPApi` 提供 CreateWorkspace、DescribeWorkspaces/WorkspaceDetail/Branches/Computes/WorkspaceEndpoint/DBAccounts/Databases/DBAccountConnection，与检查过的 ArkClaw 源码对应。SDK 创建请求没有 ClientToken，不能假设重复创建幂等。

## 需求与设计

1. `managed.postgres.mode: auto` 无需 PG URL/账号/密码；可选 Workspace ID 用于显式复用。旧/手动配置继续可用。引擎默认 PostgreSQL_17，项目默认 default，业务 Workspace 名称可配置。配置 API 无云调用、无凭据，只报告自动模式；创建弹窗 PG 步骤变为说明，不提供主机/端口编辑框，OpenViking 仍为第三步。自动模式拒绝提交 PG 字段；未提交草稿清空旧值，已提交任务保留原载荷，配置变化时安全失败。
2. AIDAP 适配器每次请求使用当前部署凭据进行 SDK 签名，核验账号一致性，脱敏服务错误。完整遍历分页并限制页数、检测重复页。等待明确就绪状态，支持取消和步骤超时；拒绝终态/未知状态、歧义分支/计算/账号/端点及不完整凭据。SQL 连接仅在服务端内存中处理并注入对应 Runtime。
3. PG 注册库创建前，在私有 SQLite（`.adk/mpa-pg-bootstrap.sqlite3`，路径可配置）保存无密钥的创建意图、范围/配置摘要和 Workspace ID。使用操作系统文件锁按账号/地域/项目串行化，覆盖共享路径的 Studio/CLI 多进程。调用创建前保存意图，等待就绪前保存 ID。创建响应丢失时按精确名称及范围/用途标签恢复；结果不确定、已登记资源丢失、归属或配置冲突时禁止再次创建。独立部署主机必须共享协调器/状态位置，本版不宣称提供分布式锁。
4. 在已核验账号/地域/项目中查找并复用唯一匹配的 Workspace，检查名称、引擎和范围，拒绝冲突用途标签。显式 ID 单独核验，新资源打稳定归属标签。先准备管理 Workspace，再准备业务 Workspace，推导管理库 URL 并调用现有安全 SQL 初始化器准备 `mpa_admin_db`。保留业务库命名和账号/地域 APIG 共享规则，不为每个 MPA 创建 Workspace。接管已有业务数据须指定业务 Workspace ID，切换前检查旧业务端点。
5. 不允许把旧注册库端点静默切到空管理库。自动创建默认拒绝仍配置的旧共享 URL。显式设置 `managed.postgres.legacy-urls: ignore` 后，新建流程从全新的管理与业务 Workspace 开始，不读取两个旧 PG URL；已有智能体和数据库保持原状，也不导入旧记录。另一种方案是通过 `init-admin-db --source-url-env ...` 按停写迁移契约复制旧记录。本编码任务不执行自动线上迁移、删除、公开访问设置变更、密码重置或计费云测试。
6. 新增安全阶段显示管理 Workspace、业务 Workspace 和管理库初始化进度。维护凭据不进入浏览器、任务数据库或日志。参考 Runtime 的 PG 设置由解析出的业务连接覆盖；智能体部署记录继续固定共享 Workspace ID。

## 任务与验收

- T1：配置、API 契约、弹窗；测试自动/手动模式、无需 PG 密钥、可选复用、草稿/提交兼容及国际化。
- T2：SDK 适配和连接解析；测试请求/凭据刷新、分页、就绪、选择及脱敏。
- T3：持久化初始化与 SQL 接入；测试两个智能体复用、并发、取消、不确定创建、ID 丢失、范围冲突、旧库迁移保护及业务身份不变。
- T4：服务/CLI 集成、双语文档、生成资源；执行 managed Python/CLI 测试、Ruff/Pyright、前端测试/构建/国际化/资源和浏览器检查。全量回归若仅重现已知依赖问题，可引用此前基线证据。没有隔离且授权的目标时，真实云/SQL 验证明确记为 not_run。

## 审查与风险

直接审查（review-spec 不可用）：保留用户批准的拓扑；显式启用自动模式，避免旧配置意外分配资源。SDK 凭据替代人工填写 PG 凭据，不取代数据库认证。服务权限、CREATEDB 或网络缺失仍明确失败。文件锁保护共享状态目录，不保护互不共享的部署主机。持久化意图支持进程终止后恢复。云调用具有请求超时，晚到响应不能触发盲目重试。离线实施无未决设计阻塞；服务实际就绪值、账号权限及端点可达性需真实验证。未授权提交/推送/部署。

## 验证与交付记录 — 2026-09-23

范围：分支 `feat/from-main-20260922`、基线 `821f0f36` 上的工作区改动，包含原有未提交的三步弹窗和手动双 Workspace 工作。T1–T4 已实现。已备份本机私有配置并切到自动模式，已重启本机 Studio。部署凭据仅用于只读 STS/AIDAP 核验。未创建线上 Workspace、迁移线上 SQL、切换 Runtime、提交或推送。

| 检查 | 状态 | 证据 |
| --- | --- | --- |
| 托管 Python 与部署集成 | pass | `UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py -q`：344 通过。覆盖 SDK 请求结构、凭据刷新、发现、标签/归属、幂等重试、显式忽略旧 URL、默认迁移保护及服务/CLI 集成。 |
| CLI 回归 | pass | `UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/cli/test_cli_mpa.py tests/cli/test_cli_mpa_control.py -q`：允许本地模拟服务端口后 41 通过。 |
| 静态和类型检查 | blocked | Python 编译及 `git diff --check` 通过。新增配置字段/测试之前的 Ruff、Pyright 检查通过；本次重跑因本机缺少可执行文件且离线缓存无 Ruff 而受阻。 |
| 前端测试和发布资源 | pass | `npm --prefix frontend test`：1305 项 Node 和 36 项 Vitest 通过。`npm --prefix frontend run build`、`check:i18n`、`test:webui-assets` 通过；核对 104 个打包文件和 248 个内部引用。 |
| 浏览器 | pass | 本地模拟：观察到自动 PG 说明和链接、三步/键盘跳转、进度阶段、取消/重试、配置错误、加载及 390px 窄屏布局。没有服务商调用。 |
| 本机配置和 Studio 接口 | pass | 私有 YAML 已切到自动模式并显式设置 `legacy-urls: ignore`。重启 Studio 后，`/web/mpa-creation/config` 返回 `postgresMode=auto`、空 PG 主机、`configured=true`、无迁移标志。旧注册库记录保持原状。 |
| 真实 AIDAP/PG 与迁移 | not_run | 只读 STS/AIDAP 发现通过；部署账号下尚无配置的管理员和业务 Workspace 名称。Workspace 分配与注册库/Runtime 切换需另行协调，尚未执行。 |
| 全量 Python 非 smoke 回归 | not_run | 此前相关未提交范围存在可选依赖缺失及本地端口沙箱的基线失败；以上受影响的托管与 CLI 测试已通过。未改动共享 SDK 依赖或核心运行时契约。 |

后续操作：通过受控的新智能体创建，核验 AIDAP 权限、端点连通性和 Workspace 创建。本机配置明确选择从新库开始，因此旧注册记录及旧业务库不会出现在新建任务中；已有智能体仍使用原连接。引导状态文件须保存在同一协调主机的持久目录。需要保留旧数据的部署仍可选手动模式或显式迁移。

## main 历史对齐及 PR 前验证 — 2026-09-23

用户已批准将当前功能修改完整保留在基于重写后 `origin/main` 的干净分支。已在 `c7b23a9b` 创建 `feat/mpa-pg-workspaces`，并显式执行 `git pull --ff-only origin main`；旧分支 `feat/from-main-20260922` 仍保留在 `821f0f36`。没有将旧提交合并回重写后的历史。本操作不改变组件契约。

切换前的本地私有归档保存了 125 个现存文件及 62 项删除，包括被忽略的本地配置；切换后全部逐字节一致。重新构建后，源码及本地配置仍与备份一致；额外编辑仅包括本双语验证记录，以及两份就绪等待设计中的契约相对链接修正。被忽略的配置和备份不进入 PR。分支操作没有修改云资源或运行中的服务。

验证范围：对齐后基于 `c7b23a9b` 保留的本次功能差异。

| 检查 | 状态 | 证据 |
| --- | --- | --- |
| 定向 Python | pass | `uv run --offline --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/cli/test_mpa_a2a_url.py tests/cli/test_frontend_runtime_proxy.py tests/scripts/test_scan_yaml_secrets.py -q`：470 通过，5 条警告。 |
| 前端 | pass | `npm --prefix frontend test`：1305 项 Node 测试及 36 项 Vitest 测试通过。生产构建、`check:i18n`、`test:webui-assets` 通过；验证 104 个打包文件及 248 个引用。 |
| 提交钩子 | pass | `uv run --offline --extra dev pre-commit run --all-files` 和 `pre-commit run --files <全部现存改动路径>` 的 Ruff、格式化、Gitleaks、YAML 密钥扫描通过。后者覆盖未跟踪的新文件。钩子没有修改 Python 源码。 |
| 类型检查 | 部分通过 | 23 个重点改动 Python 文件的 Pyright 通过。另外三个既有 CLI/代理文件的全文件检查仍报告此前记录的 57 项诊断；本次对齐逐字节保留这些文件，不宣称全文件类型检查通过。 |
| 完整性 | pass | 对照私有归档核验文件哈希及删除记录；`git diff --check` 通过。分支基线为重写后的 main 历史。 |
| 浏览器/云端重跑 | not_run | 分支对齐不改变 UI 或运行时行为；此前浏览器/云端验证仍作为历史证据。本轮没有新增真实部署或聊天操作。 |
| 全量非 smoke Python 回归 | fail（环境） | `uv run --offline --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：5137 通过、6 失败、11 跳过、2 xfailed、2 项收集错误。六项失败均缺少 `llama_index`，两项收集错误缺少 `anthropic`；与此前依赖限制一致，不宣称全量全绿。 |
