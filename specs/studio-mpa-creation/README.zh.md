# Studio MPA 创建

[English](README.md)

- 组件 ID：`studio-mpa-creation`
- 状态：active
- 修订日期：2026-09-20
- 设计及证据：[Studio MPA 创建](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.zh.md)
- 所属代码：`veadk/integrations/mpa/managed/`、`frontend/server/mpa_creation.py`、`frontend/src/adk/mpaCreation.ts`、`frontend/src/ui/mpa-create/`；CLI 和目录接入。
- 测试：`tests/integrations/mpa_managed/`、`frontend/tests/mpaCreation.test.tsx`。
- 依赖：[旧部署](../mpa-runtime-provisioning/README.zh.md)、[Studio MPA 控制面](../studio-mpa-control-plane/README.zh.md)、现有 AgentKit/Volcengine SDK、SQLAlchemy/asyncpg、SQLite、MPA 镜像。
- 操作指南：[MPA 托管创建](../../veadk/integrations/mpa/managed/README.zh.md)。

## 职责与边界

VeADK 负责托管 YAML 解析、云服务/数据库编排、有权限约束的持久创建任务和 MPA 目录窗口。无需外部源码仓库。共享注册/初始化协议与 MPA 镜像互通。旧 `veadk mpa create` 独立保留且行为不变。不增加模型执行、渠道路由、PostgreSQL 实例创建或 IAM 策略管理。

## 契约

- **CON-1 — 配置：** 服务端选择 `VEADK_MPA_CREATE_CONFIG`（默认 `mpa-create.config.yaml`）。`managed.version: 1` 接受短横线/下划线别名，拒绝未知 managed 字段。一个配置服务一个匹配的 `cn-*` 地域。`from-runtime` 与 `template-file` 互斥，否则通过平铺镜像/模型/PG 字段构建模板。`database-admin-url-env` 与 `shared-database-url-env` 在服务端解析 PostgreSQL URL。配置/模板文件最多 256 KiB。HTTP 客户端不能选择路径、命令、账号或凭据。配置检查仅限本地，不证明真实访问权限。
- **CON-2 — 准备：** 运维提供 PostgreSQL 实例/注册库/登录用户/属主、IAM 角色、镜像、模型权限和网络连通性。先核验云账号及数据库权限，再准备账号 VPC/子网、APIG/IM Gateway、worker、独立业务库、Skill Space 和 Runtime。显式接管 APIG 要求配置匹配 VPC。不得假设新 VPC 可访问私网 PostgreSQL。等待应用就绪前释放账号锁。
- **CON-3 — 身份：** 持久身份为已核验账号 + 地域 + 稳定智能体 ID。原生归属标记、哈希、client token 和会话 advisory lock 决定复用。拒绝无关同名资源及未完成配置冲突。在原生部署记录保存 `studio_owner`；其他所属用户或无该所属身份的已有记录不能被隐式接管。CLI 使用 `cli`，Studio 使用授权主体的哈希。
- **CON-4 — 初始化：** 使用真实 Runtime 元数据及共享 APIG 初始化，不进行旧占位 endpoint 回填。要求公私网、KeyAuth、MPA 标签、绑定 worker/Skill Space 及元数据/IM 启动初始化。参考 Runtime 模板移除来源身份、渠道凭据、Skill Space 和 worker 身份。成功要求平台 Ready 及应用 `/readiness`。
- **CON-5 — 鉴权：** 四个接口在读取配置/状态前均调用 Studio 智能体管理鉴权。认证普通用户不能创建；本地开发沿用现有 `local` 主体语义。查询/取消按所属用户隔离。同一用户/request ID 复用任务；修改输入返回 409。全局最多四个活动任务，每用户一个。
- **CON-6 — 生命周期：** 状态为 `running`、`cancelling`、`succeeded`、`failed`、`cancelled`。提交/恢复进入 `running`；显式取消进入 `cancelling`，再到 `cancelled`；超时/失败进入 `failed`。成功任务不重跑。阶段为 `queued`、`checking`、`network`、`gateway`、`worker`、`database`、`skills`、`deploying`、`verifying`；阶段表示最近观察进度，不是另一套状态机。查询/提交时核验已退出的监管进程。恢复保留原请求和智能体 ID。
- **CON-7 — 取消：** 使用当前 VeADK Python 执行固定子进程模块。取消、截止时间或服务端关闭时终止子进程，最多等待 3 秒，再强制终止/回收，随后报告终态。默认截止时间 1800 秒（60–7200）。保留持久云资源，包括结果未知的进行中请求。取消不是回滚，重试使用登记意图/token。本流程不创建需要删除的临时调试 Runtime。
- **CON-8 — 数据/安全：** `.adk/mpa-creation.sqlite3`（服务端可用 `VEADK_MPA_TASK_DB` 覆盖）持久化所属用户哈希、不含密钥的输入、状态/阶段、安全结果和监管进程 PID，权限为 0600。每次操作后关闭连接。无自动历史过期。原生 PostgreSQL 表保持 `mpa_account_network`、`mpa_account_apig`、`mpa_agent_deployment`；须使用直连/会话池。每次重读 STS 文件；Runtime/网络/APIG/worker 共用已核验账号的凭据。协议消息最多 16 KiB 并按白名单校验。不转发原始子进程输出、SDK 错误、环境转储、数据库 URL 或 Runtime 密钥。
- **CON-9 — UI：** 火山引擎的 MPA 筛选下，有智能体管理权限时展示创建卡片，含空列表。窗口显示固定地域、生成/可编辑 ID、描述和资源计划。POST 前保存请求身份，提交后锁定输入，确保响应丢失后安全重试。卸载时中止轮询并忽略迟到响应，保留服务端工作，重开时从会话存储恢复。成功后刷新原地域。复用本地化 BaseUI/Studio 组件、键盘/输入法行为及语义主题变量。`ModalLayout.footer` 是可选 React 节点：省略保留原操作，`null` 隐藏页脚；原调用者不变。

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

CON-1–4 对应配置/service/network/gateway/worker/database/Runtime 测试。CON-5–8 对应 route/task 测试（所属关系、重复提交、响应丢失、已退出监管进程、超时/回收、脱敏）。CON-9 对应弹窗测试、已有目录测试和真实浏览器检查。执行 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`、前端测试/构建/产物检查、改动文件 Ruff/Pyright 及隔离浏览器检查。实际结果和剩余基线/环境限制记录在设计中。模拟测试及使用模拟接口的浏览器不能证明真实云部署；云冒烟单独授权。

配置错误区分文件缺失/不可读、YAML 格式错误及 Runtime JSON 模板缺失/格式错误。响应指出相关配置项（`VEADK_MPA_CREATE_CONFIG` 或 `managed.template-file`），不返回私有路径、文件内容或解析器异常细节。保持 CON-1/CON-8 及已有 HTTP 结构不变。

Worker 查询按云端返回的 `NextToken` 游标翻页，使用 `MaxResults=100`，不能根据当前页数量判断查询结束。重复游标或超过 1,000 页必须明确失败。重叠页中匹配的 ToolId 应去重，不同 ID 的同名资源仍构成归属冲突。查询失败或不完整时不得视为资源不存在（CON-2/CON-3）。

CON-3 命名：新建托管 Runtime 的 `Name` 等于 `MPA_AGENT_ID`。已有登记 Runtime 保留其名称。旧版待完成创建尚未返回 Runtime ID 时，仅在完整旧请求与持久化请求哈希匹配的情况下沿用哈希名称，保持 ClientToken 重试语义。其他输入变化仍构成冲突。Runtime ID 和数据库/worker/技能空间的标识不变。当前 UpdateRuntime API 未提供 Name，因此本调整不会重命名已有云实例。

CON-1 镜像优先级：可选 `managed.runtime.image` 显式指定 MPA 自定义镜像（ArtifactType 为 `image`），优先于所选参考 Runtime/模板/平铺来源。省略/null 保持原来源行为。空字符串、含空白字符、占位符的值和未知 runtime 配置项在本地校验失败。平铺模式可用它提供必需的镜像，不替代其他前置配置。`managed.worker.image` 仍独立生效。不会自动更新已有智能体，也不会放宽未完成请求哈希检查。

CON-1 显式基础设施：`managed.runtime` 可选字段包括 `role-name`、正数 `cpu-milli`/`memory-mb`/`max-concurrency`、非负 `min-instance`、正数 `max-instance`、`apmplus-enable`、`project-name` 和 `env`（字符串环境值，完整 `${ENV_NAME}` 引用由服务端解析）。显式值覆盖参考 Runtime/模板/平铺设置，省略字段保留默认值。合并来源后验证 min<=max。平铺 `model-*`、`pg-*` 与 `managed.network.vpc-id/subnet-ids` 支持不依赖参考 Runtime 的配置。Runtime env 键须为大写环境变量标识；禁止设置创建流程拥有的智能体/Runtime/工具/技能 ID、派生数据库名、Runtime 端点/鉴权/加密、数据库管理员/共享注册库 URL、请求/遥测标识。CON-3/CON-8 的生成、秘密脱敏和未完成请求一致性仍为准。Worker 参考配置独立于 MPA Runtime 来源。

CON-9 创建镜像：弹窗包含可编辑的 MPA/Worker 镜像输入框，使用鉴权配置返回的 `runtimeImage`/`workerImage` 初始化。留空沿用服务端来源，显式镜像仅作用于本次创建。提交后锁定输入，并保留原请求值以支持重试/恢复。POST 接受可选镜像引用（去除首尾空白，最多 1024 字符），拒绝 URL/凭据/查询片段/非法 SHA256 digest，绝不作为 shell 命令执行。配置接口仅返回本地可确定的默认镜像，纯参考配置可为空。CON-6/CON-8 任务存储新增 `images` JSON 列，旧记录为 `{}`。首次提交保存本地可确定的实际镜像，重试沿用该列并拒绝修改显式输入。任务响应包含该非秘密快照，固定 runner 将其应用于配置副本。显式 worker 镜像会在本次新任务中取消配置的已有 worker 选择。权限和其他资源设置仍由服务端管理。


CON-10 — Worker 恢复/诊断：暂时性 Worker 操作最多尝试 4 次，间隔 1/2/4 秒，受默认 600 秒阶段预算和总任务期限限制。创建重试保持同一载荷/ClientToken；仅已登记的托管 Worker 可恢复已识别的不存在错误。永久/未知错误和归属冲突立即失败。只含安全枚举的诊断记录到日志和 `task_diagnostics`（每任务最新 100 条，跨重试保留），绝不持久化原始异常数据。任务 HTTP 字段和错误码不变。见[已批准设计](../../prd-spec/bugfixes/mpa-worker-retry/2026-09-20-worker-retry.zh.md)。

CON-10 元数据可见性：区分初始化元数据缺失和显式冲突。具有持久化 ID/令牌/哈希的托管 Worker 仅在 Creating/Pending/Starting/Initializing/Provisioning 或无状态时可等待缺失 ID/项目/归属标签，最多 4 次不完整观测，等待 5/10/20 秒。Ready 缺失字段、已有值冲突、终态/未知状态以及无托管创建意图的 Worker 立即失败。固定字段诊断不包含值。见[可见性修复](../../prd-spec/bugfixes/mpa-worker-retry/2026-09-20-worker-metadata-visibility.zh.md)。
