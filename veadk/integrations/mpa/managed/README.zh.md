# MPA 托管创建

[English](README.md)

VeADK 可准备 MPA 前置资源并部署智能体，无需检出 `agentkit-mpa-agent` 源码。Studio 和 `veadk mpa provision` 共用同一实现。部署的 MPA 镜像须支持账号共享 APIG 注册和元数据初始化。

## 服务端配置

1. 复制[示例 YAML](../../../../prd-spec/features/mpa-agent-oneclick-provision/mpa-create.config.example.yaml) 到私有的 `mpa-create.config.yaml`。填写后的配置不要进入 Git。
2. 提供已有的 PostgreSQL 实例、共享注册数据库、数据库登录/属主角色、Runtime/worker IAM 角色、镜像和模型访问权限。部署管理员须有 `CREATEDB` 和指定业务库属主的权限。注册库须允许建表，并使用直连或会话级连接池；事务级连接池与 advisory lock 不兼容。
3. 在 CLI/Studio 环境中设置 `DEPLOYMENT_DATABASE_ADMIN_URL` 和 `SHARED_APIG_DATABASE_URL`。它们是 PostgreSQL 连接 URL；YAML 只保存环境变量名。平铺字段/模板中的密钥支持完整 `${ENV_NAME}` 引用。不要将这些变量暴露到浏览器配置。
4. 使用轮换的 `managed.credential-file`，或 `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY` 与可选 `VOLCENGINE_SESSION_TOKEN` 配置部署凭据。没有显式文件和环境密钥对时，使用挂载的 `/var/run/secrets/iam/credential`。每次云调用刷新凭据；Runtime、VPC、worker、APIG 使用同一经核验账号。
5. 选择一个模板来源：`managed.from-runtime`、私有 JSON `managed.template-file`，或平铺的镜像/模型/PostgreSQL 字段。参考实例模式会移除智能体专属渠道凭据和 Skill Space 身份。通过 `managed.worker.image` 创建专属 worker（可选 `reference-id` 复用 worker 环境配置），或在核验兼容性后显式使用 `existing-id`。
6. PostgreSQL 使用私网地址时，设置可访问它的 `managed.network.vpc-id` 和 `subnet-ids`。自动创建网络**不会**配置数据库白名单、对等连接或跨 VPC 路由。显式 `managed.apig.adopt-id` 要求提供该 VPC ID 且网关兼容；否则复用或创建账号登记的网关。
7. 在 Studio 进程环境中将 `VEADK_MPA_CREATE_CONFIG` 设为私有 YAML 的绝对路径，正常启动 Studio。一个配置服务其指定地域；其他地域显示配置错误。此创建路径支持火山引擎。

部署身份需要 AgentKit Runtime、Skill Space、Tool、VPC/子网、APIG/IM Gateway 及 `GetCallerIdentity` 操作权限。Runtime/worker 角色还须单独拥有对应镜像所需权限和挂载凭据。IAM 策略、PostgreSQL 云实例、模型服务和网络连通性由运维准备，不会自动创建。

## 在 Studio 使用

选择**智能体 → MPA 智能体 → 创建 MPA 智能体**。具有智能体管理权限的管理员可填写稳定的智能体 ID 和描述，查看资源计划并提交。流程依次准备账号网络/APIG/IM Gateway、worker、独立业务库和 Skill Space，然后部署并检查 Runtime 和应用就绪状态。成功后刷新列表。

最初的配置检查是本地校验，**不代表**真实权限或连通性已通过。提交后、创建资源前会检查云账号和数据库权限；后续各云步骤检查自身响应。关闭窗口可让创建继续，显式取消才停止编排。在同一浏览器会话重新打开可恢复进度。窗口支持键盘、多行中文输入、两种主题和窄窗口。

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
