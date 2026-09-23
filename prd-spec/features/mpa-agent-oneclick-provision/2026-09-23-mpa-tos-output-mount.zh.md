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
   同时覆盖 `mpa create` 与托管 `mpa provision`。
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

顶层 YAML 三个字段是唯一的密钥输入契约。托管配置加载时，把校验后的完整三元组
复制到内存中的 worker options。新 Tool 使用 access-key 类型的
`TosMountConfig`，基础路径固定为 `/sandbox-session/default/default`，本地路径
固定为 `/data/output`。VeADK 只向 Runtime 注入
`MPA_CODEX_WORKER_TOS_MOUNT_ENABLED=true` 和非敏感 bucket 名，不注入 TOS
AK/SK。

启用后，mpa-agent 复用 AgentKit SDK 的 `build_session_bucket_path` 生成会话
目录，并写入 `CreateSessionRequest`。TIP Session 客户端不支持 GetTool，因此这里不
读取 Tool；bucket 缺失时关闭式失败，不能静默创建未挂载 Session。已有 Session
不变，需要重建后才能获得挂载。

## 验收标准

- 完整 TOS YAML 在旧版和托管编排中都生成正确的 Tool 挂载配置及 Runtime 开关。
- 不完整的 TOS YAML 在本地失败，且错误信息不泄露密钥。
- 两个 Session ID 生成不同的 BucketPath，本地路径都为 `/data/output`。
- 未启用时不增加 GetTool 请求。
- 单测覆盖校验、请求构造、密钥脱敏与 Session 请求；增量可执行代码覆盖率高于 95%。

## 评审记录

仓库可选的 `review-spec` skill 当前不可用，因此按相同检查项直接评审。方案将凭证
限制在 Tool 边界，复用 SDK 标准会话路径 helper，且没有增加额外挂载参数；未发现
阻塞性不一致。
