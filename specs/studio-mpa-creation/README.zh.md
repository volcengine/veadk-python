# Studio MPA 创建

[English](README.md)

- 组件 ID：`studio-mpa-creation`
- 状态：active
- 修订日期：2026-09-24
- 设计及证据：[Studio MPA 创建](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.zh.md)
- 所属代码：`veadk/integrations/mpa/managed/`、`frontend/server/mpa_creation.py`、`frontend/src/adk/mpaCreation.ts`、`frontend/src/ui/mpa-create/`；CLI 和目录接入。
- 测试：`tests/integrations/mpa_managed/`、`frontend/tests/mpaCreation.test.tsx`。
- 依赖：[旧部署](../mpa-runtime-provisioning/README.zh.md)、[Studio MPA 控制面](../studio-mpa-control-plane/README.zh.md)、现有 AgentKit/Volcengine SDK、SQLAlchemy/asyncpg、SQLite、MPA 镜像。
- 操作指南：[MPA 托管创建](../../veadk/integrations/mpa/managed/README.zh.md)。

## 职责与边界

VeADK 负责托管 YAML 解析、云服务/数据库编排、有权限约束的持久创建任务和 MPA 目录窗口。无需外部源码仓库。共享注册/初始化协议与 MPA 镜像互通。旧 `veadk mpa create` 独立保留且行为不变。不增加模型执行、渠道路由、PostgreSQL 实例创建或 IAM 策略管理。

## 契约

- **CON-15 — Studio 身份复用：**云上 Studio 部署在第二次发布中将 UserPool 名称、客户端名称、Identity 地域和公网 MPA 回调保存为四项 `VEADK_STUDIO_MPA_*` 函数环境变量。托管配置加载在 Studio 内置配置未指定身份值时使用这组完整的服务端配置，并在云写入前拒绝不完整配置与显式冲突（包括 `managed.runtime.env`）；固定子进程读取相同值。没有这组配置时，独立 CLI/YAML 行为不变。新 Runtime 获得 `MPA_USER_POOL_NAME`、`MPA_USER_POOL_CLIENT_NAME`、`IDENTITY_CALLBACK_URL`、`IDENTITY_REGION`；浏览器请求和任务持久化均不包含这些值。已有云上 Studio 需要重新部署，已有 MPA Runtime 不变。参见[身份复用设计](../../prd-spec/features/studio-mpa-identity-reuse/2026-09-23-deploy-identity-reuse.zh.md)。

- **CON-1 — 配置：** Studio 使用代码内置的北京地域配置并忽略 `VEADK_MPA_CREATE_CONFIG`；固定账号、网络、APIG、镜像及 Runtime 默认值与原私有文件一致。`VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY` 和部署凭据仍须由服务端提供，不写入源码。子进程收到内置配置标记并校验相同配置。CLI `--config` 继续接受私有 YAML；`managed.version: 1` 支持短横线/下划线别名并拒绝未知字段。CLI 的 `from-runtime` 与 `template-file` 互斥，否则通过平铺镜像/模型/PG 字段构建模板。CLI 的 `database-admin-url-env` 与 `shared-database-url-env` 在服务端解析 PostgreSQL URL；配置/模板文件最多 256 KiB。HTTP 客户端不能选择路径、命令、账号或部署/PG 凭据；CON-11 允许本次创建提供 OpenViking API Key。配置检查仅限本地，不证明真实访问权限。参见[内置配置设计](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-23-studio-builtin-mpa-profile.zh.md)。
- **CON-2 — 准备：** 运维提供 PostgreSQL 实例/注册库/登录用户/属主、IAM 角色、镜像、模型权限和网络连通性。先核验云账号及数据库权限，再准备账号 VPC/子网、APIG/IM Gateway、worker、独立业务库、Skill Space 和 Runtime。显式接管 APIG 要求配置匹配 VPC。不得假设新 VPC 可访问私网 PostgreSQL。等待应用就绪前释放账号锁。
- **CON-3 — 身份：** 持久身份为已核验账号 + 地域 + 稳定智能体 ID。原生归属标记、哈希、client token 和会话 advisory lock 决定复用。拒绝无关同名资源及未完成配置冲突。在原生部署记录保存 `studio_owner`；其他所属用户或无该所属身份的已有记录不能被隐式接管。CLI 使用 `cli`，Studio 使用授权主体的哈希。
- **CON-4 — 初始化：** 使用真实 Runtime 元数据及共享 APIG 初始化，不进行旧占位 endpoint 回填。要求公私网、KeyAuth、MPA 标签、绑定 worker/Skill Space 及元数据/IM 启动初始化。参考 Runtime 模板移除来源身份、渠道凭据、Skill Space 和 worker 身份。成功要求平台 Ready 及应用 `/readiness`。
- **CON-5 — 鉴权：** 四个接口在读取配置/状态前均调用 Studio 智能体管理鉴权。认证普通用户不能创建；本地开发沿用现有 `local` 主体语义。查询/取消按所属用户隔离。同一用户/request ID 复用任务；修改输入返回 409。全局最多四个活动任务，每用户一个。
- **CON-6 — 生命周期：** 状态为 `running`、`cancelling`、`succeeded`、`failed`、`cancelled`。提交/恢复进入 `running`；显式取消进入 `cancelling`，再到 `cancelled`；超时/失败进入 `failed`。成功任务不重跑。阶段为 `queued`、`checking`、`network`、`gateway`、`worker`、`database`、`skills`、`deploying`、`verifying`；阶段表示最近观察进度，不是另一套状态机。查询/提交时核验已退出的监管进程。恢复保留原请求和智能体 ID。
- **CON-7 — 取消：** 使用当前 VeADK Python 执行固定子进程模块。取消、截止时间或服务端关闭时终止子进程，最多等待 3 秒，再强制终止/回收，随后报告终态。默认截止时间 1800 秒（60–7200）。保留持久云资源，包括结果未知的进行中请求。取消不是回滚，重试使用登记意图/token。本流程不创建需要删除的临时调试 Runtime。
- **CON-8 — 数据/安全：**内置 Studio 使用 `/tmp/veadk-studio/mpa-creation.sqlite3`（服务端可用 `VEADK_MPA_TASK_DB` 覆盖）持久化所属用户哈希、不含密钥的输入、状态/阶段、安全结果和监管进程 PID，权限为 0600。这是针对云端代码目录只读问题而明确采用的临时、实例本地方案：重启可能丢失历史，多个实例不能依赖共享任务限制或锁。独立调用方显式构造服务时仍沿用 `.adk/mpa-creation.sqlite3` 约定。每次操作后关闭连接。无自动历史过期。原生 PostgreSQL 表保持 `mpa_account_network`、`mpa_account_apig`、`mpa_agent_deployment`；须使用直连/会话池。每次重读 STS 文件；Runtime/网络/APIG/worker 共用已核验账号的凭据。协议消息最多 16 KiB 并按白名单校验。不转发原始子进程输出、SDK 错误、环境转储、数据库 URL 或 Runtime 密钥。参见[临时可写状态修复](../../prd-spec/bugfixes/studio-mpa-writable-state/2026-09-23-use-temporary-state.zh.md)。
- **CON-9 — UI：** 火山引擎的 MPA 筛选下，有智能体管理权限时展示创建卡片，含空列表。窗口显示固定地域、原有生成的 `mi-[0-9a-f]{24}` 只读 ID、描述和资源计划。三步分别展示基础信息、PostgreSQL 自动准备和 OpenViking；仅第三步提交。POST 前保存请求身份，提交后锁定输入，确保响应丢失后安全重试。卸载时中止轮询并忽略迟到响应，保留服务端工作，重开时从会话存储恢复。明确失败或取消的任务同时提供同 ID 重试和独立的新建操作；后者仅以新请求/智能体 ID 及默认值替换浏览器草稿，不删除或修改原服务端任务与资源。运行中和提交结果不明时，弹窗不允许开始另一个身份。成功后刷新原地域。复用本地化 BaseUI/Studio 组件、键盘/输入法行为及语义主题变量。`ModalLayout.footer` 是可选 React 节点：省略保留原操作，`null` 隐藏页脚；原调用者不变。参见[终态任务新建修复](../../prd-spec/bugfixes/studio-mpa-creation/2026-09-24-start-another-agent-after-failure.zh.md)。

## HTTP 契约

| 方法与路径 | 响应 |
| --- | --- |
| `GET /web/mpa-creation/config?region=...` | 200 `{configured,region,error?}`；成功另含安全 `source`、资源名、`checks:["configuration"]`、`requiresLiveChecks:true` |
| `POST /web/mpa-creation/tasks` | 202 任务快照；启动或恢复 |
| `GET /web/mpa-creation/tasks/{id}` | 200 按所属用户隔离的任务快照 |
| `POST /web/mpa-creation/tasks/{id}/cancel` | 200 任务快照；终态不变 |

POST 请求体（最多 8192 字节，拒绝未知字段）：

```json
{"requestId":"11111111-1111-4111-8111-111111111111","agentId":"customer-service","description":"Customer service","region":"cn-beijing"}
```

`requestId` 为 UUID；`agentId` 匹配 `[a-z0-9][a-z0-9_-]{0,63}`；`description` 默认空，最多 512 字符；地域匹配 `cn-[a-z]+`，最多 32 字符。快照包含上述字段及 `taskId`、`state`、`stage`、`result`、`error`。成功结果恰好包含 `runtime_id`、`skill_space_id`、`gateway_id`、`agent_id`、`region`、`state:"ready"`，均为有长度限制的标识；不返回 endpoint 或凭据。安全错误码包括 `creationFailed`、`timeout`、`interrupted`、`cancelled`。HTTP 错误：400 配置，413 请求体大小，422 输入无效，409 冲突/容量，404 未知/其他用户任务；鉴权沿用 Studio 状态码。不支持的云厂商配置不可用。

## 兼容性、验证及变更记录

2026-09-20 批准的迁入由 VeADK 维护云部署代码及测试。不支持外部部署命令或依赖外部代码仓库。API/镜像/共享表兼容性变化须审查本契约。旧 CLI 和无关 SDK/harness 契约不变。平铺模式支持字段及重试说明见操作指南。

CON-1–4 对应配置/service/network/gateway/worker/database/Runtime 测试。CON-5–8 对应 route/task 测试（所属关系、重复提交、响应丢失、已退出监管进程、超时/回收、脱敏）。CON-9 对应弹窗测试、已有目录测试和真实浏览器检查。CON-13 执行角色权限对应 `tests/cli/test_frontend_deploy_iam.py`，并仍须真实云端冒烟验证。执行 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`、前端测试/构建/产物检查、改动文件 Ruff/Pyright 及隔离浏览器检查。实际结果和剩余基线/环境限制记录在设计中。模拟测试及使用模拟接口的浏览器不能证明真实云部署；云冒烟单独授权。

Studio 配置错误指出缺少服务端环境凭据或不支持的地域，不泄露实际值。CLI YAML 配置仍区分文件缺失/不可读、YAML 格式错误及 Runtime JSON 模板缺失/格式错误；错误指出相关配置项，不返回私有路径、文件内容或解析器异常细节。保持 CON-1/CON-8 及已有 HTTP 结构不变。

Worker 查询按云端返回的 `NextToken` 游标翻页，使用 `MaxResults=100`，不能根据当前页数量判断查询结束。重复游标或超过 1,000 页必须明确失败。重叠页中匹配的 ToolId 应去重，不同 ID 的同名资源仍构成归属冲突。查询失败或不完整时不得视为资源不存在（CON-2/CON-3）。

CON-3 命名：新建托管 Runtime 的 `Name` 等于 `MPA_AGENT_ID`。已有登记 Runtime 保留其名称。旧版待完成创建尚未返回 Runtime ID 时，仅在完整旧请求与持久化请求哈希匹配的情况下沿用哈希名称，保持 ClientToken 重试语义。其他输入变化仍构成冲突。Runtime ID 和数据库/worker/技能空间的标识不变。当前 UpdateRuntime API 未提供 Name，因此本调整不会重命名已有云实例。

CON-1 镜像优先级：可选 `managed.runtime.image` 显式指定 MPA 自定义镜像（ArtifactType 为 `image`），优先于所选参考 Runtime/模板/平铺来源。省略/null 保持原来源行为。空字符串、含空白字符、占位符的值和未知 runtime 配置项在本地校验失败。平铺模式可用它提供必需的镜像，不替代其他前置配置。`managed.worker.image` 仍独立生效。不会自动更新已有智能体，也不会放宽未完成请求哈希检查。

CON-1 显式基础设施：`managed.runtime` 可选字段包括 `role-name`、正数 `cpu-milli`/`memory-mb`/`max-concurrency`、非负 `min-instance`、正数 `max-instance`、`apmplus-enable`、`project-name` 和 `env`（字符串环境值，完整 `${ENV_NAME}` 引用由服务端解析）。显式值覆盖参考 Runtime/模板/平铺设置，省略字段保留默认值。合并来源后验证 min<=max。平铺 `model-*`、`pg-*` 与 `managed.network.vpc-id/subnet-ids` 支持不依赖参考 Runtime 的配置。Runtime env 键须为大写环境变量标识；禁止设置创建流程拥有的智能体/Runtime/工具/技能 ID、派生数据库名、Runtime 端点/鉴权/加密、数据库管理员/共享注册库 URL、请求/遥测标识。CON-3/CON-8 的生成、秘密脱敏和未完成请求一致性仍为准。Worker 参考配置独立于 MPA Runtime 来源。

CON-9 创建镜像：弹窗包含可编辑的 MPA/Worker 镜像输入框，使用鉴权配置返回的 `runtimeImage`/`workerImage` 初始化。留空沿用服务端来源，显式镜像仅作用于本次创建。提交后锁定输入，并保留原请求值以支持重试/恢复。POST 接受可选镜像引用（去除首尾空白，最多 1024 字符），拒绝 URL/凭据/查询片段/非法 SHA256 digest，绝不作为 shell 命令执行。配置接口仅返回本地可确定的默认镜像，纯参考配置可为空。CON-6/CON-8 任务存储新增 `images` JSON 列，旧记录为 `{}`。首次提交保存本地可确定的实际镜像，重试沿用该列并拒绝修改显式输入。任务响应包含该非秘密快照，固定 runner 将其应用于配置副本。显式 worker 镜像会在本次新任务中取消配置的已有 worker 选择。权限和其他资源设置仍由服务端管理。


CON-10 — Worker 恢复/诊断：暂时性 Worker 操作最多尝试 4 次，间隔 1/2/4 秒，受默认 600 秒阶段预算和总任务期限限制。创建重试保持同一载荷/ClientToken；仅已登记的托管 Worker 可恢复已识别的不存在错误。永久/未知错误和归属冲突立即失败。只含安全枚举的诊断记录到日志和 `task_diagnostics`（每任务最新 100 条，跨重试保留），绝不持久化原始异常数据。任务 HTTP 字段和错误码不变。见[已批准设计](../../prd-spec/bugfixes/mpa-worker-retry/2026-09-20-worker-retry.zh.md)。

CON-10 元数据可见性：区分初始化元数据缺失和显式冲突。具有持久化 ID/令牌/哈希的托管 Worker 仅在 Creating/Pending/Starting/Initializing/Provisioning 或无状态时可等待缺失 ID/项目/归属标签，最多 4 次不完整观测，等待 5/10/20 秒。Ready 缺失字段、已有值冲突、终态/未知状态以及无托管创建意图的 Worker 立即失败。固定字段诊断不包含值。见[可见性修复](../../prd-spec/bugfixes/mpa-worker-retry/2026-09-20-worker-metadata-visibility.zh.md)。

## 自动 PG 粒度提案（尚未实现）

当前流程已由下文 **CON-12 / CON-13** 替代该历史提案：共享管理/业务 Workspace，业务保持库级隔离，并可选自动准备。

[部署账号 PG 设计](../../prd-spec/features/mpa-serverless-pg/2026-09-21-deployment-account-pg.zh.md) 采用 ArkClaw 每个智能体独立业务 Workspace 的粒度。身份为部署账号 + 地域 + 稳定智能体 ID；同智能体重试复用其 Workspace，另一个智能体使用另一个 Workspace。所有 PG 调用使用 VeADK 部署凭据，不采用 ArkClaw 资源账号委托。已有 PG 模式和上文现行契约保持不变。独立共享注册库的初始化/资源数量和详细设计需要在实施前确认；业务 Workspace 绝不能隐式变成共享管理注册库。

## 三步创建输入

**CON-11 — 前置资源：**参见[三步创建设计](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-23-studio-mpa-three-step-creation.zh.md)和[OpenViking 密钥扩展](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-23-studio-mpa-openviking-key.zh.md)。鉴权后的配置检查额外返回管理员连接的非密钥 `pgHost` 和 `pgPort` 默认值。POST 可选接收 `pgHost`、`pgPort`、`openvikingUrl` 和 `openvikingResourceId`，长度上限依次为 255、5、1024、128 字符，均不含密钥。PG 主机和端口必须同时提供，并在部署前与配置的管理员连接目标一致。OpenViking 地址必须为 HTTPS，不能包含嵌入凭据、端口、查询串或片段；OpenViking 地址、资源 ID 和 API Key 三项必须同时填写；资源 ID 匹配 `ov-[a-zA-Z0-9_-]+`。非空的非密钥选项随任务保留。OpenViking 三项全空时，即使模板或参考 Runtime 含有旧值，新 Runtime 也不含 `OPENVIKING_*` 变量。POST 还可选接收最多 512 字符的 `openvikingApiKey`。遮罩后的密钥只存在浏览器内存中，经鉴权 POST 与子进程标准输入传递，仅在本次创建时连同地址、资源 ID 和 `OPENVIKING_USER=default` 一起注入；任务接口不返回，浏览器会话存储及 SQLite 均不保存。浏览器或服务端重启后重试失败任务时需重新输入密钥。PG 密码仍由服务端管理。Studio 创建流程仅在启用 OpenViking 时注入 `OPENVIKING_USER=default`。旧 CLI 保持自己的配置行为。控制台链接仅用于导航，不是服务端点，也不会创建资源。旧 CLI 不受影响；Studio 请求的 OpenViking 字段全空时，新 Runtime 不含相关环境变量。

## 两套 PostgreSQL Workspace

配置响应新增可选 `postgresLayout: "split-workspaces"`、`adminWorkspaceName: "mpa_admin_workspace"` 和 `adminDatabaseName: "mpa_admin_db"`，不返回 Workspace ID 或维护连接。复制命令拒绝 `pending=true` 的 Runtime 部署，必须先在原配置下核对；迁移绝不改写持久化请求哈希。

**CON-12 — 注册库分离：** 可选 `managed.postgres` 启用[两 Workspace 契约](../../prd-spec/features/mpa-space-scoped-resources/2026-09-23-two-pg-workspaces.zh.md)。手动预建的管理 Workspace 名称为 `mpa_admin_workspace`，共享表位于 `mpa_admin_db`。另一业务 Workspace 继续为每个智能体保留一个 `mpa_agent_<hash>` 数据库。本地校验配置的 Workspace ID 和连接目标不同，云端归属由操作员核验。保留现有按账号/地域共享 APIG/网络的键和 Runtime 启动协议。独立管理维护凭据仅供 `veadk mpa init-admin-db` 使用；正常创建使用已有管理数据库。可选 `--source-url-env` 迁移仅复制三张注册表、保留源库、拒绝目标冲突/多余记录，要求协调停止写入并切换 Runtime URL。部署记录固定 Workspace ID，不自动迁移业务数据或删除 Workspace。旧配置保持兼容。实现及验证状态见关联设计。 自动模式另见 CON-13，本条描述手动模式。

## CON-13：自动准备共享 PostgreSQL Workspace

`managed.postgres.mode: auto` 显式启用基于部署账号 STS 的 AIDAP 准备流程。配置检查只读，无需 PG 凭据；返回 `postgresMode: "auto"` 以及空的 `pgHost`/`pgPort`。创建向导 PG 步骤展示准备说明；POST 拒绝非空 PG 地址/端口。未提交草稿清空旧 PG 目标；已提交请求保持不变，不兼容的重试被拦截。OpenViking 仍为第三步。Studio 执行角色必须覆盖调用方身份、`NetworkCloud` 执行的全部 VPC/子网查询与创建、`GatewayCloud` 执行的全部 APIG/IM Gateway 操作、`PGCloud` 执行的 9 项明确 AIDAP 操作，以及 AgentKit Worker、Skill Space 和 Runtime 操作。默认角色授予[经审计的明确云端权限集合](../../prd-spec/bugfixes/studio-mpa-aidap-permissions/2026-09-23-complete-mpa-cloud-runtime-policy.zh.md)及现有 `agentkit:*` 覆盖，并在 `studio update` 时刷新；客户自有角色仍由运维管理。

每个已核验账号/地域/项目准备 `mpa_admin_workspace/mpa_admin_db` 及一个 `mpa_business_workspace`（业务名称可配置）。每个 MPA 保持独立业务库。AIDAP Workspace ID 必须与账号、地域、项目、名称、引擎和归属标签一致。可用显式 ID 接管已有 Workspace。旧配置/手动模式保持兼容。新增任务阶段为 `admin_workspace`、`business_workspace`、`admin_database`。

在私有 SQLite 引导文件中保存无密钥的意图与资源身份。内置 Studio 配置临时使用 `/tmp/veadk-studio/mpa-pg-bootstrap.sqlite3`，避免云端创建写入只读代码目录；独立 YAML 未显式配置时仍使用 `.adk/mpa-pg-bootstrap.sqlite3`。同一实例上的所有创建进程必须共享该路径及操作系统锁。Studio 的 `/tmp` 路径在实例替换后不持久，也不被独立主机共享；状态丢失后，必须先检查云资源再重试结果不确定的创建。调用 CreateWorkspace 前保存意图，等待就绪前保存 ID。创建结果不确定时禁止盲目重试，按范围/标签发现或通过 ID 接管。确定的权限/参数拒绝允许修正后重试。取消、超时及后续失败保留资源，不替换已登记但删除的 Workspace。服务商错误脱敏；每次 SDK 请求刷新凭据并核验账号，凭据只在服务端使用，不进入配置/任务响应或引导状态文件。

对引导状态已记录且由本流程创建的 Workspace，详情字段、预期归属标签暂时缺失或服务商返回 not-found，均在现有超时范围内视为等待就绪。已出现但冲突的身份或归属值立即失败。显式接管的 Workspace 保持严格校验。重试自有 Workspace 不再次调用 CreateWorkspace。

仍配置旧注册库 URL 时默认禁止自动创建。显式设置 `managed.postgres.legacy-urls: ignore` 后，新建任务使用全新的管理和业务 Workspace，本配置不读取两个旧 PG 环境 URL；已有智能体和数据库不迁移、不修改、不删除。另一种方案是通过 `init-admin-db --source-url-env ...` 准备新管理库，并原子复制已停止写入的源注册库。已有业务数据须指定业务 Workspace ID 且保持端点不变。协调写入方和 Runtime 切换后，管理员才可清除旧注册库 URL 并启用迁移后的创建。本操作不搬迁现有业务库，不修改运行中 Runtime 的环境变量。参见[设计与验证](../../prd-spec/features/mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.zh.md)。

## CON-14：Runtime 注册库 URL 兼容性

托管创建将 Runtime 的 `SHARED_APIG_DATABASE_URL` 中 `sslmode` 查询参数转换为 asyncpg 使用的 `ssl`，保留配置的 TLS 模式及所有其他连接字段。已兼容 URL 保持不变；冲突或重复 TLS 参数报错且不暴露凭据。初次创建和最终配置均使用此表示。进行中哈希仅因该转换而不同时允许恢复；Runtime ID 未知时仍须用原创建请求和客户端令牌精确重放，然后进行规范化的最终配置。其他输入变化仍被拒绝。参见[修复与验证](../../prd-spec/bugfixes/2026-09-23-mpa-registry-tls-url.zh.md)。
