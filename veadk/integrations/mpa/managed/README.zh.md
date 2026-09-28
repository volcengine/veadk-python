# MPA 托管创建

[English](README.md)

VeADK 可准备 MPA 前置资源并部署智能体，无需检出 `agentkit-mpa-agent` 源码。Studio 和 `veadk mpa provision` 共用同一实现。部署的 MPA 镜像须支持账号共享 APIG 注册和元数据初始化。

## 自动准备 PG（新部署推荐）

Studio 内置的北京地域配置采用 PostgreSQL 自动准备；CLI 用户在私有 YAML 中设置 `managed.postgres.mode: auto`。不需要 PG 地址/用户名/密码或 PG URL 环境变量。部署账号的轮转 STS 凭据除已有 AgentKit/VPC/APIG 权限及模型/角色配置外，还需 `GetCallerIdentity`、AIDAP `CreateWorkspace`、`DescribeWorkspaces`、`DescribeWorkspaceDetail`、`DescribeBranches`、`DescribeComputes`、`DescribeWorkspaceEndpoint`、`DescribeDBAccounts`、`DescribeDatabases` 和 `DescribeDBAccountConnection` 权限。账号须已开通 AIDAP，且 Studio、Runtime 能连接返回的 PostgreSQL 端点。该流程使用服务商公网端点，不修改数据库网络/白名单设置。

```yaml
managed:
  version: 1
  postgres:
    mode: auto
    admin-workspace-name: mpa_admin_workspace
    business-workspace-name: mpa_business_workspace
    project-name: default
    bootstrap-path: .adk/mpa-pg-bootstrap.sqlite3
    timeout-seconds: 600
  # 保留已有 runtime、worker 和 network 配置。
```

提交创建后，准备/复用 `mpa_admin_workspace/mpa_admin_db`，再准备一个业务 Workspace，每个 MPA 使用独立 `mpa_agent_<hash>` 业务库。创建页 PG 步骤展示说明，不再提供连接信息输入框。连接信息在服务端获取；自动模式忽略或覆盖平铺/模板/参考 Runtime 中的 PG 设置。可用 `admin-workspace-id` / `business-workspace-id` 接管已有资源，范围/名称/引擎须一致。默认引擎为 PostgreSQL_17。配置检查和 dry-run 不分配云资源。

同一范围的所有 Studio/CLI 进程必须使用**同一协调主机上的同一持久引导文件路径**，重启和重新部署时须保留。私有 SQLite 文件仅保存意图和 ID，不保存密码。任务取消/失败保留资源。创建响应丢失后，重试会发现带标签的 Workspace；结果仍不明确时，应检查 AIDAP 并配置匹配的 ID。不要通过删除状态强制再次创建。确定的 IAM/参数拒绝可修正后重试。不自动删除任何 Workspace。

### 已有部署切换

旧共享注册库 URL 仍配置时，自动模式默认拒绝创建。如果新建任务可以舍弃旧 MPA 的资源关系，CLI 用户在私有 YAML 中设置 `managed.postgres.legacy-urls: ignore`；Studio 内置配置已采用该设置。即使 Studio 进程环境仍有 `SHARED_APIG_DATABASE_URL` 和 `DEPLOYMENT_DATABASE_ADMIN_URL`，该配置也不读取它们。新智能体从全新的管理与业务 Workspace 开始；旧智能体、数据库、Runtime 连接和记录都不修改或删除。不要用该设置以相同智能体 ID 继续未完成的旧创建任务。

如果要保留并迁移旧资源关系，则保持默认的 `legacy-urls: reject` 并按以下步骤切换。已有部署不要直接删除旧 URL，否则会失去对已有资源关系的识别。

1. 备份源注册库，并在整个切换期间停止**所有注册库写入方**，包括 Runtime 启动注册写入。
2. 配置自动模式，显式指定当前业务 Workspace ID 及其实际 `business-workspace-name`，保持业务端点不变。要求 PostgreSQL_17。用 `OLD_SHARED_APIG_DATABASE_URL` 等私有环境变量提供旧注册库 URL。
3. 执行 `veadk mpa init-admin-db --config mpa-create.config.yaml --source-url-env OLD_SHARED_APIG_DATABASE_URL`。它准备 Workspace/管理库，并按下文迁移规则原子复制注册记录，不搬迁业务库、不修改运行中 Runtime 的环境变量。
4. 核对复制后的资源绑定。按现有安全部署流程协调运行中 Runtime 的 `SHARED_APIG_DATABASE_URL` 切至新管理库；切换完成后才移除 Studio/CLI 环境中的旧注册库 URL。保留旧业务凭据，或在删除废弃配置前显式核验接管后的连接。验证后才恢复写入；保留源备份以便回滚。

仓库测试不执行线上迁移或云资源分配。限制和验证情况参见[自动 PG 设计](../../../../prd-spec/features/mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.zh.md)。


## CLI YAML 与手动 / 旧模式服务端配置

1. 复制[示例 YAML](../../../../prd-spec/features/mpa-agent-oneclick-provision/mpa-create.config.example.yaml) 到私有的 `mpa-create.config.yaml`。填写后的配置不要进入 Git。
2. 提供已有的 PostgreSQL 实例、共享注册数据库、数据库登录/属主角色、Runtime/worker IAM 角色、镜像和模型访问权限。部署管理员须有 `CREATEDB` 和指定业务库属主的权限。注册库须允许建表，并使用直连或会话级连接池；事务级连接池与 advisory lock 不兼容。
3. 手动 CLI 配置须在 CLI 环境中设置 `DEPLOYMENT_DATABASE_ADMIN_URL` 和 `SHARED_APIG_DATABASE_URL`。它们是 PostgreSQL 连接 URL；YAML 只保存环境变量名。平铺字段/模板中的密钥支持完整 `${ENV_NAME}` 引用。不要将这些变量暴露到浏览器配置。
4. 使用轮换的 `managed.credential-file`，或 `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY` 与可选 `VOLCENGINE_SESSION_TOKEN` 配置部署凭据。没有显式文件和环境密钥对时，使用挂载的 `/var/run/secrets/iam/credential`。每次云调用刷新凭据；Runtime、VPC、worker、APIG 使用同一经核验账号。
5. 选择一个模板来源：`managed.from-runtime`、私有 JSON `managed.template-file`，或平铺的镜像/模型/PostgreSQL 字段。参考实例模式会移除智能体专属渠道凭据和 Skill Space 身份。通过 `managed.worker.image` 创建专属 worker（可选 `reference-id` 复用 worker 环境配置），或在核验兼容性后显式使用 `existing-id`。
6. PostgreSQL 使用私网地址时，设置可访问它的 `managed.network.vpc-id` 和 `subnet-ids`。自动创建网络**不会**配置数据库白名单、对等连接或跨 VPC 路由。显式 `managed.apig.adopt-id` 要求提供该 VPC ID 且网关兼容；否则复用或创建账号登记的网关。
7. CLI 通过 `--config` 显式传入私有 YAML。Studio 不读取该文件或 `VEADK_MPA_CREATE_CONFIG`；它使用代码内置的北京地域配置，服务端环境仍须提供 `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY` 与部署 STS 凭据。Studio 选择其他地域时返回配置错误。

部署身份需要 AgentKit Runtime、Skill Space、Tool、VPC/子网、APIG/IM Gateway 及 `GetCallerIdentity` 操作权限。Runtime/worker 角色还须单独拥有对应镜像所需权限和挂载凭据。IAM 策略、PostgreSQL 云实例、模型服务和网络连通性由运维准备，不会自动创建。

## 在 Studio 使用

新执行 `veadk studio deploy` 后，托管创建会从服务端 VeFaaS 环境自动复用该 Studio 的 UserPool、客户端、Identity 地域和 `/oauth/callback`。Studio 无需创建 YAML，直接使用代码内置的北京地域账号、VPC/子网、APIG、Runtime/worker 镜像及模型默认值；模型 API Key 仍从 `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY` 读取。独立 CLI YAML 若显式填写不同的 `user-pool-name`、`user-pool-client-name`、`identity-callback-url`、`identity-region` 或对应的 `managed.runtime.env` 值，配置检查会在云写入前失败。此前部署的 Studio 须重新部署才能获得这些值。没有 Studio 环境值的独立 `veadk mpa provision` 仍使用显式 YAML。共享 PostgreSQL Workspace 在后续创建 MPA 时才准备，并非部署时的 Identity 存储。

选择**智能体 → MPA 智能体 → 创建 MPA 智能体**。三步依次填写基础信息、PostgreSQL 自动准备说明，以及可选的 OpenViking 服务地址/资源 ID/API Key。生成的智能体 ID 为只读。PG 步骤提供[火山引擎 AIDAP 控制台](https://console.volcengine.com/aidap/region:aidap+cn-beijing/)入口；服务端在提交后取得 Workspace 连接。OpenViking 步骤提供[上下文管理控制台](https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing/ov-6689fabdf032294/context-management?accountId=default&userId=default&projectName=default)入口；该页面地址不是要填写的服务地址。PG 凭据仍由服务端配置。同时填写 OpenViking 地址、资源 ID 和遮罩的 API Key 时，注入 `OPENVIKING_URL`、`OPENVIKING_RESOURCE_ID`、`OPENVIKING_API_KEY` 和 `OPENVIKING_USER=default`。三项全空时不注入这些变量，模板或参考 Runtime 中的旧值也不会继承。密钥不保存到浏览器草稿或任务 SQLite，浏览器重启后须重新填写。查看资源计划后在第三步提交。流程依次准备账号网络/APIG/IM Gateway、worker、独立业务库和 Skill Space，然后部署并检查 Runtime 和应用就绪状态。成功后刷新列表。

最初的配置检查是本地校验，**不代表**真实权限或连通性已通过。提交后、创建资源前会检查云账号和数据库权限；后续各云步骤检查自身响应。关闭窗口可让创建继续，显式取消才停止编排。在同一浏览器会话重新打开可恢复进度。窗口支持键盘、多行中文输入、两种主题和窄窗口。

## 手动配置两个 PostgreSQL Workspace

先在 [AIDAP 控制台](https://console.volcengine.com/aidap/region:aidap+cn-beijing/)手动创建两个 Workspace：

```text
mpa_admin_workspace
└── mpa_admin_db
    ├── mpa_account_network
    ├── mpa_account_apig
    └── mpa_agent_deployment
业务 Workspace（复用当前 Workspace）
├── mpa_agent_<agent-A-hash>
└── mpa_agent_<agent-B-hash>
```

手动模式请参考示例 YAML，并将 `managed.postgres.mode` 改为 `manual`。设置 `admin-workspace-name: mpa_admin_workspace`、真实的 `admin-workspace-id` 和 `business-workspace-id`，以及 `admin-database-url-env: MPA_ADMIN_DATABASE_ADMIN_URL`。两个 ID 和主机必须不同；管理连接必须使用 `mpa_admin_db`。请在控制台核实 ID 和端点归属：本地校验不会查询 AIDAP，也不能证明云资源归属。不配置 `managed.postgres` 则兼容旧行为。

| 服务端环境变量 | 目标与用途 |
| --- | --- |
| `DEPLOYMENT_DATABASE_ADMIN_URL` | 业务 Workspace 的已有维护库，用于创建各智能体业务库。 |
| `SHARED_APIG_DATABASE_URL` | 管理 Workspace 的 `mpa_admin_db`；注册库登录用户/owner，具备建表权限并使用会话池。 |
| `MPA_ADMIN_DATABASE_ADMIN_URL` | 管理 Workspace 的已有维护库，例如 `aidb`；仅 `init-admin-db` 使用，需要 `CREATEDB` 和分配注册库 owner 的权限。 |

平铺 `pg-host`、`pg-user`、`pg-password` 和模板/Runtime PG 配置继续指向**业务** Workspace。管理维护凭据不会注入 Runtime。现有 MPA 镜像仍接收 `SHARED_APIG_DATABASE_URL` 用于注册库启动；本次不重设计其权限，也不新增每智能体数据库用户。不会自动创建或删除 Workspace。普通创建要求管理库已存在，不会静默创建空库替代旧注册库。

全新环境执行：

```bash
veadk mpa init-admin-db --config /secure/mpa-create.config.yaml
```

已有环境应**先复制原共享注册库，再切换**：

1. 备份旧注册库。先用原配置完成或核对未完成的 Runtime 部署：复制会拒绝 `pending` 记录，因为其幂等请求哈希包含旧共享地址。停止 Studio 创建任务及所有可能写注册记录的 Runtime/渠道进程，直到完成端点切换。保留业务 PG 地址、库名、凭据和数据。
2. 配置新的私有配置文件及上述环境变量。将旧共享连接放入 `OLD_SHARED_APIG_DATABASE_URL`。源凭据需要三张表的 SELECT 及 SHARE 表锁权限。不要把连接 URL 当作命令行参数传入。
3. 执行：

   ```bash
   veadk mpa init-admin-db --config /secure/mpa-create.config.yaml --source-url-env OLD_SHARED_APIG_DATABASE_URL
   ```

4. 命令校验目标 owner 并拒绝无关 public 对象，仅复制三张表，保留完整 JSON 记录和身份。相同记录可重复执行；目标存在冲突或多余记录则整批复制事务回滚。不会写入源库。失败后目标数据库可能保留，解决原因后重试。锁/语句超时为 5/30 秒，整体上限为 120 秒。
5. 核对返回的各表数量及资源身份。切换 Studio/CLI 共享连接，并显式发布已有 MPA Runtime 的新 `SHARED_APIG_DATABASE_URL`，再恢复写入。新建部署自动注入新地址；该命令不更新已有 Runtime。保持其业务 PG 配置不变，验证 Runtime、渠道和创建流程就绪。
6. 保留源库用于恢复。新注册库尚无新写入时，可将**全部**使用方切回旧地址；产生新写入后必须先对账再回退，不可让使用方分别连接新旧注册库，也不要删除共享资源来重试。

VPC/APIG 仍按账号和地域共享。部署 JSON 记录保存两个 Workspace ID；重试时绑定或已有业务端点改变，会在云资源写入前拒绝。业务库命名及 owner 校验保持不变。复制三张表不会迁移业务数据或更新 Runtime 镜像。

## CLI

```bash
veadk mpa provision --config /secure/mpa-create.config.yaml --agent-id customer-service --dry-run
veadk mpa provision --config /secure/mpa-create.config.yaml --agent-id customer-service --description "Customer service"
```

`--dry-run` 校验本地配置并输出安全计划，不调用云服务/数据库。实际创建可能分配计费云资源。旧 `veadk mpa create` 行为不变，不准备这些托管前置资源。

托管平铺模式读取镜像、镜像仓库名、模型 provider/base/key/name、PostgreSQL host/port/user/password/SSL 设置、Runtime 角色和项目。每个智能体使用独立推导的业务库；旧 `pg-database`、Tool 选择、渠道、OpenViking 配置不会隐式应用到此模式。额外应用环境配置使用私有 Runtime 模板；worker 选择使用 `managed.worker`。创建后通过 Studio 的 MPA 消息渠道页面绑定渠道。可选平铺 `account-id` 仅用于断言认证账号一致。

## 恢复与资源保留

重试时保持相同智能体 ID、请求身份和原配置。共享 PostgreSQL 表 `mpa_account_network`、`mpa_account_apig`、`mpa_agent_deployment` 保存资源身份、所属关系、创建意图和 client token。其他 Studio 用户不能接管同一部署。没有 Studio 所属用户的原生部署不会隐式接管，应使用新的智能体 ID。CLI 创建的部署使用独立 CLI 所属身份。

Studio 在 `.adk/mpa-creation.sqlite3` 保存不含密钥的任务状态（可通过服务端 `VEADK_MPA_TASK_DB` 覆盖）。重启时保留该文件。每个用户最多一个活动任务，全局最多四个。查询/提交时核验已退出的监管进程；失败/取消的任务沿用原请求 ID 恢复。任务历史没有自动过期机制。浏览器会话存储只含请求和任务身份。服务端关闭、超时（默认 1800 秒，可配置 60–7200）或取消时会终止并回收子进程。

取消不是云资源回滚。已创建的 APIG/VPC、业务库、Skill Space、worker 和 Runtime 会保留以便恢复；进行中的云请求可能在取消后完成。不要通过删除共享资源来重试。创建结果未知时使用持久化意图和 client token；未完成配置发生冲突时停止并报错。成功要求平台 Ready **且**应用 `/readiness` 通过。任务响应只含安全阶段/错误码和资源 ID，不包含原始部署日志或凭据。

参见[组件契约](../../../../specs/studio-mpa-creation/README.zh.md)和[验证记录](../../../../prd-spec/features/mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.zh.md)。测试模拟云操作；真实部署需要另行提供凭据和隔离目标。

### Runtime 显示名称

新建托管 Runtime 的名称等于 Studio 中输入或通过 `--agent-id` 指定的智能体 ID，例如 `mi-example`。AgentKit 仍会分配独立的 `r-...` Runtime ID。已有 Runtime 保留原名；当前更新接口没有 Name 参数。重试旧版未完成的创建时，在原始输入匹配的情况下保留原哈希名称和请求 token。数据库、worker 和技能空间的命名仍按账号、地域和智能体标识隔离。

### 显式配置 MPA 和 worker 镜像

使用 `managed.runtime.image` 独立固定 MPA 镜像，与 `managed.worker.image` 分开配置：

```yaml
managed:
  version: 1
  from-runtime: r-reference
  runtime:
    image: registry.example/agentkit/mpa_agent:release-tag
  worker:
    image: registry.example/agentkit/mpa_codex_worker:release-tag
```

这只是配置片段，需保留其他必需设置。`from-runtime` 除默认镜像外，还提供角色、计算/扩缩容/并发、APM/项目、VPC，以及经身份清理的模型/数据库连接等环境设置。显式 Runtime 镜像会作为自定义镜像覆盖默认值。对 `template-file` 和平铺模式也同样生效；平铺模式设置本字段后可省略顶层 `image`。省略/null 保持原行为；空字符串、含空白字符或占位符的镜像校验失败。模板来源选择规则不变。修改该配置不会自动更新已有智能体；重试未完成创建时须保留原实际镜像。

### 不依赖参考 Runtime 的显式基础配置

移除 `managed.from-runtime` 和 `managed.template-file`，即可使用平铺模型/数据库字段及以下覆盖配置：

```yaml
managed:
  version: 1
  runtime:
    image: registry.example/agentkit/mpa_agent:release-tag
    role-name: IDRoleForArkClawShareAgent
    cpu-milli: 2000       # 2 核 CPU
    memory-mb: 4096      # 4 GiB
    min-instance: 1
    max-instance: 1
    max-concurrency: 100
    apmplus-enable: true
    project-name: default
    env:
      CLOUD_PROVIDER: volcengine
  network:
    vpc-id: vpc-existing
    subnet-ids: [subnet-existing]
  worker:
    image: registry.example/agentkit/mpa_codex_worker:release-tag
model-provider: openai
model-name: your-model
model-api-base: https://model.example/api/v3
model-api-key: "${MPA_MODEL_API_KEY}"
pg-host: database.example
pg-port: "5432"
pg-user: app
pg-password: "${MPA_PG_PASSWORD}"
pg-sslmode: require
pg-channel-binding: require
```

需保留完整示例中的地域、共享/管理员数据库秘密引用，以及 worker 专用设置。`runtime.env` 支持其他字符串应用配置与完整环境变量引用，不能指定创建流程拥有的标识、生成的数据库名、Runtime 密钥或部署数据库 URL。任意来源模式下，显式 runtime 字段优先，省略则保留原默认值。最少实例可为零，但不能超过合并后的最多实例。网络创建仍要求公网/私网连通，不会创建数据库白名单。固定配置后，参考 Runtime 的后续变化不再影响该配置。如果保留 worker 的 `reference-id`，它仍会独立提供 worker 环境变量。这些设置用于后续创建/部署，不会自动重新部署已有实例。

### 在 Studio 创建时填写镜像

创建弹窗新增 **MPA 镜像**和 **Worker 镜像**文本框，默认填入当前服务端配置。可为本次创建修改任一镜像，或清空以使用配置默认值。填写 `registry.example/mpa:v2` 或 `registry.example/worker@sha256:<64 位十六进制>` 这样的容器镜像引用，不接受下载网址或镜像仓库登录凭据。输入不会修改 Studio 内置配置或重新部署已有智能体。提交后锁定两个输入；失败、取消、关闭后重开均保留原请求及已知实际镜像，以安全重试。仅引用 Runtime/已有 worker 的配置可能没有本地可展示的默认镜像，留空仍沿用该来源。镜像访问权限和兼容性由管理员负责。显式填写 Worker 镜像会创建独立 worker，即使原配置选择复用已有 worker。

### Worker 重试与失败诊断

Worker 参考查询、发现、创建和读取遇到已识别的超时、连接失败、限流或暂时性服务错误时，最多**尝试 4 次**，依次等待 **1、2、4 秒**。创建调用复用持久化载荷和 ClientToken。仅已登记的托管 Worker 会重试已识别的不存在错误；参考/既有 Worker 缺失、权限错误、参数错误和归属冲突立即失败。准备 Worker 默认预算 600 秒（包含重试），并遵循总任务期限和取消。SDK 内部重试可能增加网络请求次数。未知错误仍需排查，并使用相同身份手动重试；这不保证所有服务端故障都能恢复。

Studio 将安全诊断类别写入服务端日志和私有任务数据库的 `task_diagnostics` 表。每任务最新 100 条事件跨手动重试和重启保留。事件包含任务 ID、时间戳、阶段、操作、尝试次数、类别和结果（`retrying`、`failed`、`cancelled`），不包含原始消息、凭据或请求载荷。已有 HTTP 错误码和弹窗行为不变。本地查看方式：

```bash
sqlite3 -readonly .adk/mpa-creation.sqlite3 "SELECT task_id,datetime(created,'unixepoch'),stage,operation,category,attempt,outcome FROM task_diagnostics ORDER BY id DESC LIMIT 30;"
```

若设置了 `VEADK_MPA_TASK_DB`，请使用该路径。示例时间为 UTC。`permission` 需检查部署凭据/权限；`invalid_request` 需检查配置；`ownership` 和 `configuration_changed` 需核对原始资源身份/输入。`timeout`、`connection`、`throttled`、`unavailable` 区分暂时性故障；`not_found` 根据操作表示可见性延迟或资源缺失。`unknown`/`provider_error` 表示未能安全识别服务端错误，不代表成功。子进程异常退出、服务中断、超时和取消也会记录。旧版本已丢弃的历史错误无法恢复。

### 初始化元数据延迟

对于已持久化创建 ID/令牌/哈希的托管 Worker，初始化期间缺失 ID/项目/归属标签时，最多观察四次不完整响应，依次等待 5、10、20 秒，处理 CreateTool 返回后元数据稍晚可见的情况。已有值明确冲突仍立即失败；Ready 后缺失字段及终态/未知状态不享受宽限。等待遵循原阶段期限和取消，不会创建另一个 Worker。安全诊断操作标明具体字段（`worker_id`、`worker_project`、`worker_managed_by`、`worker_agent_key`、`worker_agent_binding`、`worker_state`）；`metadata_pending` 表示正在等待，`metadata_missing` 表示有界检查未通过。实际字段值仍保持私有。

托管部署接受带 `sslmode` 的 PostgreSQL 注册库 URL，并将该查询参数转换为 MPA Runtime 的 asyncpg 驱动使用的 `ssl`，保留原 TLS 模式。自动准备和手动配置的管理库均适用，无需重新构建镜像。已有未完成部署可以在保持资源身份不变的情况下恢复并应用此转换。

## Studio A2A 发现默认配置

Flat 创建默认设置 `ENABLE_A2A=true` 和 `DISABLE_JWT_AUTH=false`。使用兼容的 MPA 镜像时，Studio 的 Runtime-key `/list-apps` 探测收到 404，随后通过 A2A agent card 发现 `a2a-default`。`A2A_TIP_VERIFY_ENABLED=false` 保留现有外层网关 key-auth 集成，不绕过 REST JWT 鉴权。仍支持显式 `managed.runtime.env` 覆盖；引用 Runtime / 模板的环境保持不变。已有 Runtime 需要显式更新配置并发布；在 Studio 重新连接以刷新发现结果。本次默认值修改不需要重建前端。
