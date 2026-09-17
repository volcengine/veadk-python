# MPA Runtime 部署

- **Component ID：** `mpa-runtime-provisioning`
- **状态：** 草案；提议变更由关联 PRD 管理
<<<<<<< HEAD
- **修订日期：** 2026-09-20
=======
- **修订日期：** 2026-09-15
>>>>>>> dd7f974c (feat(studio): deliver MPA P0 control plane)
- **English version:** [README.md](README.md)
- **关联 PRD：** [MPA Runtime 集成加固](../../prd-spec/bugfixes/mpa-runtime-integration/2026-09-12-mpa-runtime-integration-hardening.zh.md)
- **关联 PRD：** [MPA Studio 工作负载身份创建](../../prd-spec/features/mpa-studio-workload-identity/2026-09-20-mpa-studio-workload-identity.zh.md)
- **负责代码：** `veadk/cli/cli_mpa.py`、`veadk/integrations/mpa/mpa_provision.py`、`veadk/integrations/mpa/mpa_runtime.py`

## 职责

本组件将 `veadk mpa create` 输入转换为一个可恢复的 AgentKit Runtime 或 VeFaaS 部署，绑定 Tool，预写/完成 `mpa_meta`，把公网 A2A Endpoint 和 Runtime 凭据发布到服务端环境，并验证 Endpoint 可访问。PostgreSQL、OpenViking、模型服务、ArkClaw 控制面资源和 Studio 展示仍由各自系统负责。

## 入口与依赖

- CLI：`veadk mpa create`。
- 控制面：默认使用 AgentKit Runtime；VeFaaS 为兼容选项。
- 数据：调用方提供的外部 PostgreSQL 和可选 OpenViking。
- Runtime 消费方：独立版本的 mpa-agent 镜像。

## 契约

- `CON-1`：VeADK 部署配置设置 `IDENTITY_STARTUP_ENABLED=false`、`MPA_LAZY_LOGIN=false`、`APPCENTER_RESOURCE_DISCOVERY_ENABLED=false`，并保留派生的 `CLAW_SPACE_ID` 兼容值。这会关闭 ArkClaw UserPool 启动，但不会禁用出站 workload token 使用。
- `CON-2`：默认开启 key-auth。Endpoint 和 Key 可用后，第二阶段发布同时包含 `A2A_PUBLIC_URL` 与 `CODEX_MCP_RUNTIME_API_KEY` 的环境。Key 不得打印，并在预览中按 Secret 处理。
- `CON-3`：AgentKit Runtime 创建及收敛更新设置 `ApmplusEnable=true`。除非操作方显式覆盖，`APMPLUS_TRACE_CONTENT=false` 保持内容追踪关闭。
- `CON-4`：第一阶段在启动前写入占位符；第二阶段只使用非空权威 Runtime 值覆盖。第二阶段部署失败必须报告失败，不得报告部分成功。
- `CON-5`：调用方显式提供的 `extra_env` 继续保持 last-wins，包括有意覆盖 VeADK 配置默认值。
- `CON-6`：AgentKit Runtime 创建及收敛更新必须持久化 `veadk:agent-type=mpa`，作为 Studio 稳定分类标签。未打标签 Runtime 在执行显式标签修复前不进入 MPA 筛选。
- `CON-7`：在其他创建副作用之前，CLI 创建或复用账号和地域范围内的 `agentkit-studio-workload` Pool 与 `{MPA_AGENT_ID}-studio` Identity，然后以 `MPA_WORKLOAD_POOL_NAME` 和 `MPA_WORKLOAD_IDENTITY_NAME` 注入 Runtime。
- `CON-8`：`veadk mpa create` 自动生成和显式接收的 ID 均匹配 `mi-[0-9a-z]{12}`。基础 ID 仍作为 Runtime 和元数据身份，只有 WorkloadIdentity 增加 `-studio` 后缀。
- `CON-9`：工作负载资源按精确名称幂等 get-or-create。并发创建冲突后重新读取；其他 Identity 错误在 Tool、数据库或 Runtime 修改前失败。已创建的身份资源保留供重试。

## 状态、安全与兼容

生命周期为 `prepared -> resource-created -> ready -> environment-finalized -> metadata-finalized -> verified`。按名称复用时通过 `UpdateRuntime(ReleaseEnable=True)` 收敛现有 Runtime，并等待更新版本 Ready。Secret 只属于进程/控制面数据，必须从 CLI 输出、文档、日志及测试夹具中脱敏。退出开关由本组件注入，不改变原生默认值，因此原生 mpa-agent 部署保持兼容。

## 失败与可观测性

缺少 Endpoint、Key、Runtime ID 或 APIG ID 会阻止 metadata 完成。Runtime 终态失败和 Ready 超时抛出 `MpaRuntimeError`。CLI 报告恢复所需的已创建资源标识，但不暴露凭据。APMPlus 是否开启通过 Runtime metadata 验证；链路读取授权属于独立的 Studio 责任。

## 验证

| 契约 | 验证 |
| --- | --- |
| `CON-1`、`CON-2`、`CON-5`、`CON-7`、`CON-8` | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py` |
| `CON-2`、`CON-3`、`CON-4`、`CON-6` | `uv run --extra dev pytest tests/integrations/test_mpa_runtime.py` |
| `CON-7`、`CON-9` | `uv run --extra dev pytest tests/integrations/test_mpa_identity.py tests/cli/test_cli_mpa.py` |
| 端到端 | 创建/复用隔离 Runtime，不打印 Key 地检查 metadata，调用 A2A 和内置 MCP，并观察两个 MCP 缓存周期 |

VeADK MPA 部署默认设置 DISABLE_JWT_AUTH=true。extra_env 显式配置优先，包括 false。网关鉴权及其他部署路径不变。

MPA 部署默认注入 `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=sqlalchemy,asyncpg,psycopg,psycopg2,dbapi`，关闭数据库自动埋点并保留业务链路。显式 `extra_env` 优先，包括传空字符串重新启用埋点。适用于新部署或显式重新部署的资源，不自动修改已有运行实例。

## 托管创建边界

Studio MPA 创建和 `veadk mpa provision` 由 [Studio MPA 创建](../studio-mpa-creation/README.zh.md)负责。该路径准备账号资源并通过真实 Runtime 元数据初始化。本文原有职责和旧入口保持不变。

## 拟议 AgentKit P0 profile

由 [P0 功能迁移](../../prd-spec/features/mpa-p0-productionization/2026-09-15-mpa-p0-productionization-design.zh.md) 管理。基线 `CON-1` 至 `CON-6` 保留为历史/当前集成契约；以下拟议 profile 加强 readiness 和安全，不表示已实现。原生/VeFaaS 兼容路径独立保留，不导入 ArkClaw 用户、元数据或旧标识。

- `CON-7`：AgentKit 模式使用版本化 bootstrap manifest，包含 account/workspace/MPA-instance/Runtime 身份、endpoint、resource 和服务端 credential 引用。由 `agentkit-mpa-agent` 消费，P0 必需功能不得调用 ArkClaw configuration/identity/AppCenter fallback。缺失配置返回分类 not-ready 状态和可恢复 finalization 步骤。`CLAW_SPACE_ID` 等内部兼容名仅可作为派生值保留，不查询旧服务。Runtime 持有 MPA Profile revision，bootstrap 只记录绑定和已应用 revision。
- `CON-8`：保留 prepare/create/finalize 阶段，区分 transport-ready 与 execution-ready。未 finalization 的 Runtime 可响应 bootstrap health，但拒绝用户执行，避免平台 transport-ready 前必须已有最终 endpoint 凭据的循环依赖。Endpoint/key/Tool/manifest 完成后，execution readiness 与 A2A/worker smoke 均通过才报告成功。重复 create/finalize 使用稳定 operation ID 并检查资源所有权；部分失败返回安全资源 ID 和下一恢复步骤。
- `CON-9`：按 [runtime 身份契约](../mpa-runtime-control/README.zh.md) `CON-1` 配置 AgentKit custom JWT issuer discovery、allowed client/audience，并由 BFF 转发已验证 bearer；API key-auth 与用户身份独立。新 AgentKit profile 在 caller override 合并后验证最终配置，拒绝 JWT bypass 或开启旧 fallback。这仅在 opt-in profile 中有意约束基线 `extra_env` last-wins，必须作为公共 CLI/config 边界验证。
- `CON-10`：Key 轮换更新服务端引用/配置，并对齐 runtime、内置 MCP、worker client。CLI/UI 普通结果不包含原值。Reconciliation 失败保持失败，允许相同 operation ID 重试；消费者未就绪前不声称旧 key 已撤销。实际 key release/rotation operation 由 PRD `T-1` 对照平台 API 验证。
- `CON-11`：发布 metadata 固定 runtime image digest、已应用 MPA Profile revision、session execution-config schema、worker protocol 兼容。复用 AgentKit SDK 的 Runtime create/get/list/update/release/delete/listVersions/listInstances/getLogs；Managed Agent API 不在 P0。实施时仍需验证 Runtime 写操作的权限、幂等、错误和回滚行为。兼容回滚等待 execution-ready 和 smoke；新平台 schema 增量演进，不兼容降级在写操作前拒绝。历史 ArkClaw 迁移不属于此生命周期。
- `CON-12`：删除要求授权影响预览、活动 Session/job 与资源引用检查、显式确认、持久化清理进度。共享 Tool/Skill/storage 保留，除非属于该操作独占且另行授权。清理失败返回 retryable/blocked 状态和安全 ID；仍有所属 runtime 资源时不报告全部删除完成。

Studio/CLI 通过共享编排遵循相同保证。平台 operation 清单与 bootstrap field/config 名称是阻塞性 `T-1` 交付物，不是现有 API 声明。

`CON-7` 至 `CON-12` 验证映射 PRD `AC-1`、`AC-2`、`AC-9`、`AC-10`：阻断旧端点的全新启动、缺失配置/finalization 失败/重启、不安全 override、轮换/重试、兼容回滚、活动/共享资源删除。复用上述 provisioning 回归并为新 profile 增加失败测试。拟议 runtime/live 结果均为 `not_run`。

2026-09-15：新增无历史导入的功能迁移 profile 草案，实现与真实证据待补。
