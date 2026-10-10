# Studio MPA 创建

[English](README.md)

- 组件 ID：`studio-mpa-creation`
- 状态：active
- 修订日期： 2026-10-09
- 设计及证据：[Studio MPA 创建](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.zh.md)
- 所属代码：`veadk/integrations/mpa/managed/`、`frontend/server/mpa_creation.py`、`frontend/src/adk/mpaCreation.ts`、`frontend/src/ui/mpa-create/`；CLI 和目录接入。
- 测试：`tests/integrations/mpa_managed/`、`frontend/tests/mpaCreation.test.tsx`。
- 依赖：[旧部署](../mpa-runtime-provisioning/README.zh.md)、[Studio MPA 控制面](../studio-mpa-control-plane/README.zh.md)、现有 AgentKit/Volcengine SDK、SQLAlchemy/asyncpg、SQLite、MPA 镜像。
- 操作指南：[MPA 托管创建](../../veadk/integrations/mpa/managed/README.zh.md)。

## 职责与边界

VeADK 负责托管 YAML 解析、云服务/数据库编排、有权限约束的持久创建任务和 MPA 目录窗口。无需外部源码仓库。共享注册/初始化协议与 MPA 镜像互通。旧 `veadk mpa create` 独立保留且行为不变。模型执行与渠道路由仍由 Runtime 负责。托管运行角色 IAM 准备遵循下文契约。

## 契约

- **CON-15 — Studio 身份复用：**云上 Studio 部署在第二次发布中将 UserPool 名称、客户端名称、Identity 地域和公网 MPA 回调保存为四项 `VEADK_STUDIO_MPA_*` 函数环境变量。托管配置加载在 Studio 内置配置未指定身份值时使用这组完整的服务端配置，并在云写入前拒绝不完整配置与显式冲突（包括 `managed.runtime.env`）；固定子进程读取相同值。没有这组配置时，独立 CLI/YAML 行为不变。新 Runtime 获得 `MPA_USER_POOL_NAME`、`MPA_USER_POOL_CLIENT_NAME`、`IDENTITY_CALLBACK_URL`、`IDENTITY_REGION`；浏览器请求和任务持久化均不包含这些值。已有云上 Studio 需要重新部署，已有 MPA Runtime 不变。参见[身份复用设计](../../prd-spec/features/studio-mpa-identity-reuse/2026-09-23-deploy-identity-reuse.zh.md)。

- **CON-16 — Studio MPA 来源标签：**通用 Studio MPA 部署和托管式一键创建都写入 `veadk:agent-type=mpa`、`veadk:managed=true`、`veadk:provisioner=studio-mpa`、可信 `veadk:owner` 和其持有的 `veadk:mpa-instance-id`；可信 owner 缺失时必须在云变更前失败，且启动子进程前必须验证原始 owner 的哈希与任务 owner 一致。一键创建路由把 owner 哈希后用于本地任务和原生注册表归属，同时仅通过固定子进程把原始可信 owner 临时传递给 Runtime 标签，不把它持久化到任务状态。只有该路由显式提供可信 Runtime owner 时，共享 provisioning 服务才写入 Studio 来源，因此 `veadk mpa create` 不进入 Studio 发现范围。标签对账替换这些受管键、保留无关非系统标签，并且不重放 `sys:*` 标签。对于持久化了旧版无来源标签 request hash 的 pending create，先使用原始 create payload 与 client token 精确重放，再通过正常 Runtime update 写入当前来源标签后完成。共享常量位于内部 MPA 标签模块，不新增公共 Python API。标签是发现 metadata，不是授权凭据。缺少 `veadk:managed=true` 的历史托管式一键 Runtime 必须经过显式受支持的更新/重试或未来回填后，Studio 才会列出。已由 [Studio 创建的 MPA Runtime 过滤](../../prd-spec/features/studio-mpa-source-filter/2026-09-28-studio-mpa-source-filter.zh.md) 于 2026-09-29 实现并完成本地验证；真实浏览器发现仍是独立的本机验收步骤。

- **CON-1 — 配置：** Studio 使用代码内置的北京地域配置并忽略 `VEADK_MPA_CREATE_CONFIG`；非账号 Runtime 设置保留原私有默认值；Studio 镜像默认值为 CON-9 中的两个 latest 地址；部署账号来自核验的 STS 身份；不固定 VPC/子网/APIG ID。自动准备 PG 后，Studio 按核验后的账号和地域读取 `mpa_admin_workspace/mpa_admin_db` 中的共享资源：校验并复用已登记资源，或通过现有带锁 provisioner 创建并保存缺失的 VPC/子网及 APIG/IM Gateway。不重置已有记录来绕过配额。CLI 显式接管仍受支持。参见[注册库驱动网络修复](../../prd-spec/bugfixes/mpa-shared-network-bootstrap/2026-09-28-registry-owned-network.zh.md)。部署凭据仍须由服务端提供；模型 Key 按 CON-16 自动发现，不写入源码。子进程收到内置配置标记并校验相同配置。CLI `--config` 继续接受私有 YAML；`managed.version: 1` 支持短横线/下划线别名并拒绝未知字段。CLI 的 `from-runtime` 与 `template-file` 互斥，否则通过平铺镜像/模型/PG 字段构建模板。CLI 的 `database-admin-url-env` 与 `shared-database-url-env` 在服务端解析 PostgreSQL URL；配置/模板文件最多 256 KiB。HTTP 客户端不能选择路径、命令、账号或部署/PG 凭据；CON-11 允许本次创建提供 OpenViking API Key。配置检查仅限本地，不证明真实访问权限。参见[内置配置设计](../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-23-studio-builtin-mpa-profile.zh.md)。
- **CON-2 — 准备：** 运维提供 PostgreSQL 实例/注册库/登录用户/属主、IAM 角色（内置配置自动准备）、镜像、模型权限和网络连通性。先核验云账号及数据库权限，再准备账号 VPC/子网、APIG/IM Gateway、worker、独立业务库、Skill Space 和 Runtime。显式接管 APIG 要求配置匹配 VPC。不得假设新 VPC 可访问私网 PostgreSQL。等待应用就绪前释放账号锁。
- **CON-3 — 身份：** 持久身份为已核验账号 + 地域 + 稳定智能体 ID。原生归属标记、哈希、client token 和会话 advisory lock 决定复用。拒绝无关同名资源及未完成配置冲突。在原生部署记录保存 `studio_owner`；其他所属用户或无该所属身份的已有记录不能被隐式接管。CLI 使用 `cli`，Studio 使用授权主体的哈希。
- **CON-4 — 初始化：** 使用真实 Runtime 元数据及共享 APIG 初始化，不进行旧占位 endpoint 回填。要求公私网、KeyAuth、MPA 标签、绑定 worker/Skill Space 及元数据/IM 启动初始化。参考 Runtime 模板移除来源身份、渠道凭据、Skill Space 和 worker 身份。成功要求平台 Ready 及应用 `/readiness`。
- **CON-5 — 鉴权：** 四个接口在读取配置/状态前均调用 Studio 智能体管理鉴权。认证普通用户不能创建；本地开发沿用现有 `local` 主体语义。查询/取消按所属用户隔离。同一用户/request ID 复用任务；修改输入返回 409。全局最多四个活动任务，每用户一个。
- **CON-6 — 生命周期：** 状态为 `running`、`cancelling`、`succeeded`、`failed`、`cancelled`。提交/恢复进入 `running`；显式取消进入 `cancelling`，再到 `cancelled`；超时/失败进入 `failed`。成功任务不重跑。阶段为 `queued`、`checking`、`network`、`gateway`、`worker`、`database`、`skills`、`deploying`、`verifying`；阶段表示最近观察进度，不是另一套状态机。查询/提交时核验已退出的监管进程。恢复保留原请求和智能体 ID。
- **CON-7 — 取消：** 使用当前 VeADK Python 执行固定子进程模块。取消、截止时间或服务端关闭时终止子进程，最多等待 3 秒，再强制终止/回收，随后报告终态。默认截止时间 1800 秒（60–7200）。保留持久云资源，包括结果未知的进行中请求。取消不是回滚，重试使用登记意图/token。本流程不创建需要删除的临时调试 Runtime。
- **CON-8 — 数据/安全：**内置 Studio 使用 `/tmp/veadk-studio/mpa-creation.sqlite3`（服务端可用 `VEADK_MPA_TASK_DB` 覆盖）持久化所属用户哈希、不含密钥的输入、状态/阶段、安全结果和监管进程 PID，权限为 0600。这是针对云端代码目录只读问题而明确采用的临时、实例本地方案：重启可能丢失历史，多个实例不能依赖共享任务限制或锁。独立调用方显式构造服务时仍沿用 `.adk/mpa-creation.sqlite3` 约定。每次操作后关闭连接。无自动历史过期。原生 PostgreSQL 表保持 `mpa_account_network`、`mpa_account_apig`、`mpa_agent_deployment`；须使用直连/会话池。每次重读 STS 文件；Runtime/网络/APIG/worker 共用已核验账号的凭据。协议消息最多 16 KiB 并按白名单校验。不转发原始子进程输出、SDK 错误、环境转储、数据库 URL 或 Runtime 密钥。参见[临时可写状态修复](../../prd-spec/bugfixes/studio-mpa-writable-state/2026-09-23-use-temporary-state.zh.md)。
- **CON-9 — UI：** 火山引擎的 MPA 筛选下，有智能体管理权限时展示创建卡片，含空列表。窗口显示固定地域、必填 Runtime 名称、描述和资源计划，智能体 ID 由服务端生成；与 main 一致，不显示 MPA/Worker 镜像输入框；服务端使用 main 的本地 latest 默认值。三步分别展示基础信息、PostgreSQL 自动准备和 OpenViking；仅第三步提交。POST 前保存请求身份，提交后锁定输入，确保响应丢失后安全重试。卸载时中止轮询并忽略迟到响应，保留服务端工作，重开时从会话存储恢复。明确失败或取消的任务同时提供同 ID 重试和独立的新建操作；后者仅以新请求 UUID、空白名称及默认值替换浏览器草稿，服务端在提交时派生智能体 ID，不删除或修改原服务端任务与资源。运行中和提交结果不明时，弹窗不允许开始另一个身份。成功后刷新原地域。复用本地化 BaseUI/Studio 组件、键盘/输入法行为及语义主题变量。`ModalLayout.footer` 是可选 React 节点：省略保留原操作，`null` 隐藏页脚；原调用者不变。参见[终态任务新建修复](../../prd-spec/bugfixes/studio-mpa-creation/2026-09-24-start-another-agent-after-failure.zh.md)。


Runtime 名称无效时，输入框边框和错误文字使用 danger 状态色，并保留无障碍 alert；输入框提供本地化合法名称示例。共享 Button 基础组件为原生禁用按钮统一置灰并显示禁止光标，保留加载态样式。修改为合法名称后恢复向后导航。

## HTTP 契约

### 名称创建（2026-10-09）

[名称创建设计](../../prd-spec/features/mpa-agent-oneclick-provision/2026-10-09-named-studio-creation.zh.md) 已实现 CON-1、CON-3、CON-5、CON-6 和 CON-9 的修订。

新的 Studio 表单提交 `name`、`requestId`、`description`、`region` 及既有资源字段，省略 `agentId`、`runtimeImage`、`workerImage`。名称去除首尾空白后须为 4–64 个 ASCII 字母、数字、下划线或连字符。服务端根据可信 owner 和请求 UUID 派生稳定的 `mi-[0-9a-f]{24}` 智能体 ID，随任务请求保存并在重试时复用。名称参与请求相等比较和 Runtime 创建哈希，成为新 Runtime 的 `Name`，不替代 `MPA_AGENT_ID` 或其他资源身份键。已注册 Runtime 名称保持不变。

Studio 内置默认镜像改为 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa/mpa_agent:latest` 和 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa/mpa_codex_worker:latest`。新草稿不恢复隐藏的旧镜像覆盖项；已提交草稿/任务保留原输入和镜像选择。继续支持显式 `agentId` 和可选镜像字段的旧 API 请求，没有名称的旧请求保留按 ID 命名 Runtime 的行为。CLI/YAML 覆盖不变。弹窗显示名称和描述，不显示 ID/镜像输入框；无效名称阻止向后导航及提交。既有任务授权、取消、并发、密钥处理和错误状态语义继续有效。

验证映射至所链接设计中的路由/任务/runner/service/runtime/profile 测试和弹窗/浏览器检查。真实云端创建单独验证；新的镜像默认值不会更新运行中的智能体。

CON-9 导航修复（2026-09-30）：步骤标题是支持键盘操作的按钮。
恢复已提交草稿后，前面的步骤和“上一步”仍可查看；已提交字段保持锁定，
重试保留原请求身份。向前导航校验镜像和 PG 配置，忙碌操作禁用导航。
参见[导航修复](../../prd-spec/bugfixes/mpa-create-navigation/2026-09-30-recover-step-navigation.zh.md)。

CON-9 显式新请求修订（2026-09-30，已实现）：任何已提交草稿均提供新建入口，
包括运行中、结果未知或查询不可用的任务。显式以新身份和可编辑默认配置替换
浏览器恢复草稿，不取消或修改旧云端任务。UI 操作未结束及配置加载时禁用；
服务端提交限制不变。本修订替代上文仅终态可新建的限制。
参见[设计](../../prd-spec/bugfixes/mpa-create-navigation/2026-09-30-explicit-new-request.zh.md)。

| 方法与路径 | 响应 |
| --- | --- |
| `GET /web/mpa-creation/config?region=...` | 200 `{configured,region,error?}`；成功另含安全 `source`、资源名、`checks:["configuration"]`、`requiresLiveChecks:true` |
| `POST /web/mpa-creation/tasks` | 202 任务快照；启动或恢复 |
| `GET /web/mpa-creation/tasks/{id}` | 200 按所属用户隔离的任务快照 |
| `POST /web/mpa-creation/tasks/{id}/cancel` | 200 任务快照；终态不变 |

POST 请求体（最多 8192 字节，拒绝未知字段）：

```json
{"requestId":"11111111-1111-4111-8111-111111111111","name":"customer-service","description":"Customer service","region":"cn-beijing"}
```

`requestId` 为 UUID；新请求必填 `name`，规则见上文；旧请求的 `agentId` 匹配 `[a-z0-9][a-z0-9_-]{0,63}`；`description` 默认空，最多 512 字符；地域匹配 `cn-[a-z]+`，最多 32 字符。快照包含上述字段及 `taskId`、`state`、`stage`、`result`、`error`。成功结果恰好包含 `runtime_id`、`skill_space_id`、`gateway_id`、`agent_id`、`region`、`state:"ready"`，均为有长度限制的标识；不返回 endpoint 或凭据。安全错误码包括 `creationFailed`、`timeout`、`interrupted`、`cancelled`。HTTP 错误：400 配置，413 请求体大小，422 输入无效，409 冲突/容量，404 未知/其他用户任务；鉴权沿用 Studio 状态码。不支持的云厂商配置不可用。

## 兼容性、验证及变更记录

2026-09-20 批准的迁入由 VeADK 维护云部署代码及测试。不支持外部部署命令或依赖外部代码仓库。API/镜像/共享表兼容性变化须审查本契约。旧 CLI 和无关 SDK/harness 契约不变。平铺模式支持字段及重试说明见操作指南。

CON-1–4 对应配置/service/network/gateway/worker/database/Runtime 测试。CON-5–8 对应 route/task 测试（所属关系、重复提交、响应丢失、已退出监管进程、超时/回收、脱敏）。CON-9 对应弹窗测试、已有目录测试和真实浏览器检查。CON-13 执行角色权限对应 `tests/cli/test_frontend_deploy_iam.py`，并仍须真实云端冒烟验证。执行 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`、前端测试/构建/产物检查、改动文件 Ruff/Pyright 及隔离浏览器检查。实际结果和剩余基线/环境限制记录在设计中。模拟测试及使用模拟接口的浏览器不能证明真实云部署；云冒烟单独授权。

Studio 配置错误指出缺少服务端环境凭据或不支持的地域，不泄露实际值。CLI YAML 配置仍区分文件缺失/不可读、YAML 格式错误及 Runtime JSON 模板缺失/格式错误；错误指出相关配置项，不返回私有路径、文件内容或解析器异常细节。保持 CON-1/CON-8 及已有 HTTP 结构不变。

Worker 查询按云端返回的 `NextToken` 游标翻页，使用 `MaxResults=100`，不能根据当前页数量判断查询结束。重复游标或超过 1,000 页必须明确失败。重叠页中匹配的 ToolId 应去重，不同 ID 的同名资源仍构成归属冲突。查询失败或不完整时不得视为资源不存在（CON-2/CON-3）。

CON-3 命名：新建托管 Runtime 的 `Name` 等于 `MPA_AGENT_ID`。已有登记 Runtime 保留其名称。旧版待完成创建尚未返回 Runtime ID 时，仅在完整旧请求与持久化请求哈希匹配的情况下沿用哈希名称，保持 ClientToken 重试语义。其他输入变化仍构成冲突。Runtime ID 和数据库/worker/技能空间的标识不变。当前 UpdateRuntime API 未提供 Name，因此本调整不会重命名已有云实例。

CON-1 镜像优先级：可选 `managed.runtime.image` 显式指定 MPA 自定义镜像（ArtifactType 为 `image`），优先于所选参考 Runtime/模板/平铺来源。省略/null 保持原来源行为。空字符串、含空白字符、占位符的值和未知 runtime 配置项在本地校验失败。平铺模式可用它提供必需的镜像，不替代其他前置配置。`managed.worker.image` 仍独立生效。不会自动更新已有智能体，也不会放宽未完成请求哈希检查。

CON-1 显式基础设施：`managed.runtime` 可选字段包括 `role-name`、正数 `cpu-milli`/`memory-mb`/`max-concurrency`、非负 `min-instance`、正数 `max-instance`、`apmplus-enable`、`project-name` 和 `env`（字符串环境值，完整 `${ENV_NAME}` 引用由服务端解析）。显式值覆盖参考 Runtime/模板/平铺设置，省略字段保留默认值。合并来源后验证 min<=max。平铺 `model-*`、`pg-*` 与 `managed.network.vpc-id/subnet-ids` 支持不依赖参考 Runtime 的配置。Runtime env 键须为大写环境变量标识；禁止设置创建流程拥有的智能体/Runtime/工具/技能 ID、派生数据库名、Runtime 端点/鉴权/加密、数据库管理员/共享注册库 URL、请求/遥测标识。CON-3/CON-8 的生成、秘密脱敏和未完成请求一致性仍为准。Worker 参考配置独立于 MPA Runtime 来源。

CON-9 创建镜像：新表单没有镜像输入框，使用内置 latest 默认值。仅旧请求和已提交草稿保留显式镜像；提交后锁定输入。POST 接受可选镜像引用（去除首尾空白，最多 1024 字符），拒绝 URL/凭据/查询片段/非法 SHA256 digest，绝不作为 shell 命令执行。配置接口仅返回本地可确定的默认镜像，纯参考配置可为空。CON-6/CON-8 任务存储新增 `images` JSON 列，旧记录为 `{}`。首次提交保存本地可确定的实际镜像，重试沿用该列并拒绝修改显式输入。任务响应包含该非秘密快照，固定 runner 将其应用于配置副本。显式 worker 镜像会在本次新任务中取消配置的已有 worker 选择。权限和其他资源设置仍由服务端管理。


CON-10 — Worker 恢复/诊断：暂时性 Worker 操作最多尝试 4 次，间隔 1/2/4 秒，受默认 600 秒阶段预算和总任务期限限制。创建重试保持同一载荷/ClientToken；仅已登记的托管 Worker 可恢复已识别的不存在错误。永久/未知错误和归属冲突立即失败。只含安全枚举的诊断记录到日志和 `task_diagnostics`（每任务最新 100 条，跨重试保留），绝不持久化原始异常数据。任务 HTTP 字段和错误码不变。见[已批准设计](../../prd-spec/bugfixes/mpa-worker-retry/2026-09-20-worker-retry.zh.md)。

CON-10 元数据可见性：区分初始化元数据缺失和显式冲突。具有持久化 ID/令牌/哈希的托管 Worker 仅在 Creating/Pending/Starting/Initializing/Provisioning 或无状态时可等待缺失 ID/项目/归属标签，每 5 秒检查，受现有 Worker/任务期限限制，不设置独立观察次数上限。Ready 缺失字段、已有值冲突、终态/未知状态以及无托管创建意图的 Worker 立即失败。固定字段诊断不包含值；元数据 attempt 最大保持 4，兼容已有诊断协议。Worker API 错误重试限制不变。见[期限修复及验证限制](../../prd-spec/bugfixes/mpa-worker-retry/2026-09-30-worker-metadata-deadline.zh.md)。

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

对引导状态已记录且由本流程创建的 Workspace，详情字段、预期归属标签暂时缺失或服务商返回 not-found，均在现有超时范围内视为等待就绪。发现自有资源时，元数据不完整也进入同一就绪循环。已出现但冲突的身份或归属值立即失败，即使其他元数据尚未出现。显式接管的 Workspace 保持严格校验。重试正常或仍在创建中的自有 Workspace 不再次调用 CreateWorkspace。

[终态创建失败恢复](../../prd-spec/bugfixes/mpa-pg-recovery/2026-10-10-terminal-create-failure.zh.md) 对两种服务商及管理/业务用途应用相同规则。仅经确认的 `CreateFailed`，且账号/地域/项目/名称/引擎/ID 完整匹配、现有标签没有冲突时，允许将自动绑定退出。失败资源缺失标签不代表允许接管或删除。SQLite 增量表 `failed_workspaces(scope,purpose,workspace_id)` 保存失败云资源 ID；在现有范围锁下，退出记录与解除意图原子执行。没有正常候选时，唯一新发现的失败候选可解释无 ID 意图；没有正常候选且存在多个未退出失败候选时仍视为歧义。旧退出失败不能解释更新请求的未知结果，退出资源状态变化则报错。本次刚发出的创建失败时结束当前任务，不重复购买；另一个请求可创建替代资源。显式 ID、运行状态 `Failed`、删除/未知状态和服务错误绝不触发替换。保留失败云资源，API、凭据、超时和取消规则不变。

仍配置旧注册库 URL 时默认禁止自动创建。显式设置 `managed.postgres.legacy-urls: ignore` 后，新建任务使用全新的管理和业务 Workspace，本配置不读取两个旧 PG 环境 URL；已有智能体和数据库不迁移、不修改、不删除。另一种方案是通过 `init-admin-db --source-url-env ...` 准备新管理库，并原子复制已停止写入的源注册库。已有业务数据须指定业务 Workspace ID 且保持端点不变。协调写入方和 Runtime 切换后，管理员才可清除旧注册库 URL 并启用迁移后的创建。本操作不搬迁现有业务库，不修改运行中 Runtime 的环境变量。参见[设计与验证](../../prd-spec/features/mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.zh.md)。

## CON-14：Runtime 注册库 URL 兼容性

托管创建将 Runtime 的 `SHARED_APIG_DATABASE_URL` 中 `sslmode` 查询参数转换为 asyncpg 使用的 `ssl`，保留配置的 TLS 模式及所有其他连接字段。已兼容 URL 保持不变；冲突或重复 TLS 参数报错且不暴露凭据。初次创建和最终配置均使用此表示。进行中哈希仅因该转换而不同时允许恢复；Runtime ID 未知时仍须用原创建请求和客户端令牌精确重放，然后进行规范化的最终配置。其他输入变化仍被拒绝。参见[修复与验证](../../prd-spec/bugfixes/2026-09-23-mpa-registry-tls-url.zh.md)。

### 托管沙箱模板命名 (CON-3)

新的 Studio 名称请求直接使用经过校验的手填 Runtime 名称作为沙箱模板 Name（4–64 个 ASCII 字母、数字、连字符或下划线）。未提供名称的旧 CLI 请求仍使用去除首尾空白、将 `-` 替换为 `_` 的智能体 ID。内部智能体 ID、数据库/技能空间/渠道标识、作用域归属标签及 Runtime ToolId 绑定不变。已有 worker ID 为权威绑定，不重命名。新的未完成意图在部署 JSON 中保存 `worker_name`，拒绝后续名称变化。没有该字段的旧意图，仅在完整候选请求与已存 worker_hash 匹配时重放标准化 ID 名称或哈希名称，保留 ClientToken。其他请求变化及无关同名资源仍报错。 参见[名称 Worker 设计](../../prd-spec/bugfixes/mpa-worker-naming/2026-10-09-runtime-named-worker.zh.md)。

## 托管 MCP 签名密钥

每个托管 MPA Runtime 均配置 `MCP_TOKEN_SECRET`。显式模板环境变量非空值优先于目标 Runtime 值，后者优先于 Agent 专属 PostgreSQL `mpa_deployment_settings` 表中的 `mcp_token_secret`。全部缺失时生成 32 随机字节、编码为 64 位十六进制字符串，并在云创建前持久化。原子插入或保留已有值确保不确定创建结果的重试稳定。仅在校验未完成请求摘要后同步显式值/当前值，避免被拒绝的变更重试破坏原请求。数据库失败终止创建并释放连接。参考 Runtime 模板排除源 Agent 密钥；显式 JSON 模板可配置密钥。回填沿用密钥，正常返回值及共享非敏感部署登记记录不包含密钥。不新增前端字段或自动迁移存量部署。参见[双语设计](../../prd-spec/bugfixes/mpa-runtime-mcp-secret/2026-10-07-persistent-mcp-secret.zh.md)。

## 自动准备 Runtime IAM 角色

内置 Studio 使用 `managed.iam.mode: auto`，显式配置默认 `existing`。自动准备在 STS 账号核验后、工作负载身份和其他资源变更前执行。仅支持全新来源的默认 `IDRoleForArkClawShareAgent` 配置。IAM 为账号级。查询/创建角色及 `VeADKMPARuntimeAccessV1`，核验账号/名称及无条件信任 `vefaas`、`apig`，补齐已批准的 12 个系统策略和 14 个自定义动作的 Global 绑定，随后回读核验。保留额外绑定，不覆盖信任或已有策略。仅明确不存在错误允许创建，竞态和最终一致性采用最多 120 秒的恢复。取消保留资源。权限/信任/策略/属主/回读失败在 `iam_role` 阶段停止，输出白名单本地化错误，不输出原始云端文本和密钥。Studio 执行凭据须允许 GetRole、CreateRole、GetPolicy、CreatePolicy、ListAttachedRolePolicies、AttachRolePolicy。existing CLI 及通用智能体不受影响。完整权限及验收见[设计](../../prd-spec/features/mpa-runtime-iam/2026-10-09-managed-runtime-role.zh.md)。

## Studio 部署账号

内置配置不再固定预期账号。使用非空部署 STS 身份确定账号级 IAM、PG、VPC、APIG 和 Runtime 归属。新建 Runtime 的 `CLAW_SPACE_ID` 和 `RUNTIME_IAM_ROLE_TRN` 由该账号和所选角色派生；显式调用方环境变量覆盖保持优先。显式 YAML 预期账号检查和凭据账号变化检查继续生效。镜像仓库地址及 Worker 参考 ID 仍是源资源，具有独立访问要求。见[设计](../../prd-spec/bugfixes/mpa-studio-account/2026-10-09-sts-account.zh.md)。

## 网络归属描述与恢复

新 VPC/子网描述使用 `mpa-account-network-v1-<scope hash>`。恢复/校验托管资源仅接受当前范围精确的旧 `mpa-account-network:v1:<scope hash>` 或新标记，不改写已有资源。旧意图仅描述不同，派发标记明确为 false、无资源 ID、按名称查询无资源时，才修正描述并生成新 ClientToken；其他字段必须完全一致。结果不确定时，没有成功查询到资源就不得再次 Create。继续遵守现有锁及先保存后派发规则。见[设计](../../prd-spec/bugfixes/mpa-network-description/2026-10-09-valid-network-marker.zh.md)。

## 空网络查询

[已批准修复](../../prd-spec/bugfixes/mpa-network-discovery/2026-10-09-empty-network-results.zh.md)明确：DescribeVpcs/DescribeSubnets 第一页集合为 null/缺失且整数 `total_count=0` 时为空结果。其他非列表集合、null 集合且数量缺失/非整数/非零，以及后续页面的 null 集合仍为无效响应。SDK/提供方错误不得成为空查询。已记录的托管 VPC 可继续准备第一个子网，无需替换 VPC。分页、归属、持久化意图及未知结果防重复保护不变。

## 标准型共享网关准备

[已实施标准型网关修复](../../prd-spec/bugfixes/mpa-standard-gateway/2026-10-09-standard-shared-gateway.zh.md)规定：新托管 APIG 使用 standard、两个 1c2g 节点、small_1 CLB、公私网和 traffic 计费。新网关创建前，在共享锁内准备同 VPC、不同 APIG 支持可用区的两个子网。可选 gateway_subnet_intents 持久化每个伴随请求/token/发送状态，未知创建必须查询恢复。保留已有网关接管/复用和已有 Runtime 网络载荷。ExceededQuota 明确允许修正后重新发送；旧未知标记仍需审计恢复。部署凭据额外需要 apig:GetGatewayAvailableZones。不新增前端字段，不修改 Runtime 角色。

## 独立 Worker 配置

内置 Studio 使用镜像默认值创建 Worker，不引用 Tool，也不重复注入启动环境。CreateTool.Port 仍为 8000，默认 Envs 仅包含生成的 MPA_AGENT_ID。见[镜像默认值修订](../../prd-spec/bugfixes/mpa-worker-template/2026-10-09-worker-image-defaults.zh.md)。可选 `managed.worker.env` 是字符串映射；完整 `${ENV_NAME}` 在服务端解析。键必须使用大写。智能体/Runtime/Tool/技能空间绑定、继承的渠道/Runtime 密钥和控制库地址为保留字段。existing-id 不允许非空 env。显式 env 覆盖已过滤的可选模板环境，最后编排器生成 MPA_AGENT_ID。显式模板不存在仍报错。环境值不进入配置摘要/repr 或部署记录。已有归属、时限、取消及请求哈希/ClientToken 保护不变；修改未完成请求参数仍冲突。见[已批准设计与验证](../../prd-spec/bugfixes/mpa-worker-template/2026-10-09-independent-worker.zh.md)。

## Runtime 子网顺序与恢复

SubnetIds 按非空、唯一成员判断相同，不受平台返回顺序影响。VpcId、EnableSharedInternetAccess 仍不可变且精确比较。成员变化、重复及格式错误列表仍校验失败。恢复保留请求顺序，或在注册记录与当前 Runtime 成员相同时保留注册顺序，使已有请求哈希及 ClientToken 继续可用。成员不同的共享默认值不得替换当前智能体选择。无需结构或哈希格式迁移。设计与验证：[子网顺序修复](../../prd-spec/bugfixes/mpa-subnet-order/2026-10-09-subnet-order.zh.md)。



镜像回退（2026-10-09）：已撤回公开仓库查询及自动 digest 转换。配置接口和新任务使用内置本地 latest 默认值；已有任务快照保持不变。见[回退设计](../../prd-spec/bugfixes/mpa-create-images/2026-10-09-restore-main-images.zh.md)。

### 托管技能空间描述（CON-3/CON-4）

新的名称部署创建 `Description: Skills for MPA agent <runtime_name>`，使用经过校验、去除首尾空白的手填名称。不提供名称的调用保留内部 ID 描述。空间 `Name`、`display_name`、归属标签、ID 及绑定仍由内部标识派生。已有/显式配置空间直接复用，不更新描述。升级前待完成请求仅在完整旧描述候选与持久化 `skill_space_request` 匹配时保留原描述；其他待完成输入变化仍报错。结果未知时通过发现恢复，不盲目重复 CreateSkillSpace。见[描述设计](../../prd-spec/bugfixes/mpa-skill-space-description/2026-10-09-entered-name-description.zh.md)。

## CON-16：部署账号方舟模型 Key

[账号 Key 设计](../../prd-spec/features/mpa-model-key-discovery/2026-10-10-account-ark-key.zh.md)定义：内置 Studio 使用 `managed.model-key.mode: ark`，可选精确 ID/名称选择器（`VEADK_MPA_ARK_API_KEY_ID` / `VEADK_MPA_ARK_API_KEY_NAME`）。本地检查不需要模型明文 Key 或云访问。创建在资源变更前，使用刷新且经 STS 账号核验的部署凭据调用 ListApiKeys/GetRawApiKey。读取所有页面并去重 ID。精确选择器要求唯一匹配；否则多个候选按创建时刻选最新，同时间选择字符串 ID 字典序最大者。接受 CreateTime（兼容 CreatedAt/CreationTime）、正的 Unix 秒/毫秒或带时区 ISO 8601；任何候选时间缺失/异常时，在读取明文前失败。唯一候选无需时间字段。拒绝明确非 Active 状态，兼容缺少 Status 的旧响应。参见[最新 Key 后续设计](../../prd-spec/features/mpa-model-key-discovery/2026-10-10-latest-created-key.zh.md)。不使用掩码、不创建 Key。复制的 Profile 只向 Runtime 注入明文；原始云错误和凭据不进入事件、日志或任务/bootstrap 存储。调用超时有界，暂时错误最多三次尝试；取消后不继续变更。原请求哈希检查拒绝已提交的变更输入。CLI 默认显式 Key，通用智能体鉴权不变。默认部署角色已具备两个方舟动作；客户自管角色须授权。模型开通/访问及 Key IP 规则仍由操作者准备。

## CON-17：BytePlus 托管创建

Studio 服务端选择的云平台允许 BytePlus `ap-southeast-1` 托管创建 MPA，并保留现有火山引擎流程。浏览器不能指定云平台、账号或云接口地址；平台与地域不匹配时，在资源变更前失败。国内配置值保持不变。BytePlus 使用自己的 AK/SK/会话令牌，或显式指定的轮转 IAM 凭据文件，每次刷新凭据通过 `open.byteplusapi.com` STS 核验账号；不读取火山引擎环境凭据。Runtime、Skills、Tools SDK 客户端在线程内按平台上下文构造。Identity 及签名 VPC/ECS/APIG/AIDAP/Ark/IAM 请求选择对应平台接口。不支持的 API 或必要 IAM 策略显式失败，不回退国内服务，也不省略权限。

BytePlus 默认使用现有海外 Studio 模型及地址，将平台/地域传入 Runtime 和 Worker，并使用 Runtime 的 `APIG_TOP_ENDPOINT` 覆盖项。可选 TOS 挂载使用海外地址。默认仍使用现有公开镜像；可信服务端覆盖项为 `VEADK_MPA_BYTEPLUS_RUNTIME_IMAGE` / `VEADK_MPA_BYTEPLUS_WORKER_IMAGE`。服务端可通过 `VEADK_MPA_BYTEPLUS_AIDAP_HOST` 覆盖 AIDAP 主机名；URL、路径及用户信息等无效输入在本地检查时失败。`VEADK_MPA_BYTEPLUS_CREDENTIAL_FILE` 显式指定轮转 IAM 文件；没有 BytePlus 环境凭据时，不会隐式读取国内挂载文件。可用区校验接受 `ap-southeast-1a` 和 `ap-southeast-1-a`，不改写资源 ID，并保留国内校验。浏览器及任务响应不包含凭据。BytePlus 任务在持久化指纹和子进程 stdin 中增加可信平台标记；默认任务及 PG 引导文件增加 `-byteplus` 后缀，保留国内恢复状态。共享 Workspace/数据库布局、锁/重试/取消/就绪检查及可选 OpenViking 语义不变。控制台链接跟随平台。镜像拉取、海外 API/策略可用性及真实就绪/聊天行为须单独实测；本地配置就绪不能证明云资源可用。参见[设计及验证](../../prd-spec/features/mpa-byteplus/2026-10-10-byteplus-creation.zh.md)。

BytePlus 托管 IAM 默认通过 `open.byteplusapi.com` 调用，保留可信服务端 `IAM_OPENAPI_HOST` 覆盖；共享 IAM 工具与国内创建行为不变。

BytePlus 托管 AIDAP 默认使用 `open.byteplusapi.com`，仍支持已校验的 `VEADK_MPA_BYTEPLUS_AIDAP_HOST` 覆盖。API 可访问不代表 Workspace 创建成功；继续保留失败状态及属主校验，不自动删除或接管失败的同名资源。
