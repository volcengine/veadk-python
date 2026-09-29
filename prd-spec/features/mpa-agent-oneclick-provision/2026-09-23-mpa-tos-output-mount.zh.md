# MPA 会话级 TOS 输出挂载

- 状态：已批准
- 日期：2026-09-23
- 负责人：VeADK MPA provisioning
- 批准记录：需求方于 2026-09-23 确认进入开发

## 问题

VeADK 创建 MPA Runtime 及专属 Codex worker Tool 时，目前没有为 Tool 和
Session 配置 TOS 输出挂载，因此 `/data/output` 没有按会话隔离的 TOS 目录。

## 目标

1. 现有私有 MPA YAML 接受 `tos-access-key`、`tos-secret-key`、`tos-bucket`，
   同时覆盖 `mpa create` 与托管 `mpa provision`；Studio 创建页也可为单次创建
   传入完整三元组并覆盖 YAML 默认值。
2. AK/SK 只进入 Tool 的 `TosMountConfig`，不得进入 Runtime 环境变量、dry-run
   输出、日志或部署注册表。
3. TOS 以读写方式挂载到 `/data/output`，Endpoint 根据 Tool 地域推导。
4. Runtime 在每次新建 Session 时生成 `CreateSessionRequest.TosMountPoints`；
   使用 SDK 标准路径 `/sandbox-session/tool-{tool_id}/session-{session_id}/`。
5. 三个字段都不传时保持原行为；只传一部分时必须在任何云端或数据库副作用前失败。

## 非目标

- 更新已存在的 Tool，或给已经运行的 Session 重新挂载。
- 将 bucket 前缀、Endpoint、本地路径或只读模式开放成配置项。
- 替换 Worker 现有的输出镜像逻辑。

## 设计

顶层 YAML 三个字段提供服务端默认值。Studio 创建页可选输入完整三元组，提交后从
可恢复请求 payload 中剥离 AK/SK，仅通过创建子进程 stdin 在内存中覆盖本次 worker
options；浏览器 sessionStorage、任务 SQLite 和任务查询响应均不得保存或返回 AK/SK。
新 Tool 使用 access-key 类型的
`TosMountConfig`，基础路径固定为 `/sandbox-session/default/default`，本地路径
固定为 `/data/output`。VeADK 只向 Runtime 注入
`MPA_CODEX_WORKER_TOS_MOUNT_ENABLED=true` 和非敏感 bucket 名，不注入 TOS
AK/SK。

VeADK 要求 `agentkit-sdk-python>=0.8.5`；这是 Studio 支持的首个会序列化
access-key `CredentialType` 的 SDK 契约。Studio 的轻量增量更新必须升级更旧的
已安装 SDK，不能把旧版本视为已满足依赖。

启用后，mpa-agent 复用 AgentKit SDK 的 `build_session_bucket_path` 生成会话
目录，并写入 `CreateSessionRequest`。TIP Session 客户端不支持 GetTool，因此这里不
读取 Tool；bucket 缺失时关闭式失败，不能静默创建未挂载 Session。已有 Session
不变，需要重建后才能获得挂载。

## 验收标准

- 完整 TOS YAML 在旧版和托管编排中都生成正确的 Tool 挂载配置及 Runtime 开关。
- Studio 完整 TOS 输入覆盖本次新建 Worker，部分输入被拒绝，AK/SK 不进入浏览器
  恢复数据、任务 SQLite 或任务响应。
- 不完整的 TOS YAML 在本地失败，且错误信息不泄露密钥。
- 两个 Session ID 生成不同的 BucketPath，本地路径都为 `/data/output`。
- 未启用时不增加 GetTool 请求。
- Studio 更新后不能继续保留低于 0.8.5 的 AgentKit SDK。
- 单测覆盖校验、请求构造、密钥脱敏与 Session 请求；增量可执行代码覆盖率高于 95%。

## 评审记录

仓库可选的 `review-spec` skill 当前不可用，因此按相同检查项直接评审。方案将凭证
限制在 Tool 边界，复用 SDK 标准会话路径 helper，且没有增加额外挂载参数；未发现
阻塞性不一致。
