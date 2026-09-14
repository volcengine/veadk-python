# MPA Runtime 部署

- **Component ID：** `mpa-runtime-provisioning`
- **状态：** 草案；提议变更由关联 PRD 管理
- **修订日期：** 2026-09-12
- **English version:** [README.md](README.md)
- **关联 PRD：** [MPA Runtime 集成加固](../../prd-spec/bugfixes/mpa-runtime-integration/2026-09-12-mpa-runtime-integration-hardening.zh.md)
- **负责代码：** `veadk/cli/cli_mpa.py`、`veadk/integrations/mpa/mpa_provision.py`、`veadk/integrations/mpa/mpa_runtime.py`

## 职责

本组件将 `veadk mpa create` 输入转换为一个可恢复的 AgentKit Runtime 或 VeFaaS 部署，绑定 Tool，预写/完成 `mpa_meta`，把公网 A2A Endpoint 和 Runtime 凭据发布到服务端环境，并验证 Endpoint 可访问。PostgreSQL、OpenViking、模型服务、ArkClaw 控制面资源和 Studio 展示仍由各自系统负责。

## 入口与依赖

- CLI：`veadk mpa create`。
- 控制面：默认使用 AgentKit Runtime；VeFaaS 为兼容选项。
- 数据：调用方提供的外部 PostgreSQL 和可选 OpenViking。
- Runtime 消费方：独立版本的 mpa-agent 镜像。

## 契约

- `CON-1`：VeADK 部署配置设置 `IDENTITY_STARTUP_ENABLED=false`、`MPA_LAZY_LOGIN=false`、`APPCENTER_RESOURCE_DISCOVERY_ENABLED=false`，并保留派生的 `CLAW_SPACE_ID` 兼容值。
- `CON-2`：默认开启 key-auth。Endpoint 和 Key 可用后，第二阶段发布同时包含 `A2A_PUBLIC_URL` 与 `CODEX_MCP_RUNTIME_API_KEY` 的环境。Key 不得打印，并在预览中按 Secret 处理。
- `CON-3`：AgentKit Runtime 创建及收敛更新设置 `ApmplusEnable=true`。除非操作方显式覆盖，`APMPLUS_TRACE_CONTENT=false` 保持内容追踪关闭。
- `CON-4`：第一阶段在启动前写入占位符；第二阶段只使用非空权威 Runtime 值覆盖。第二阶段部署失败必须报告失败，不得报告部分成功。
- `CON-5`：调用方显式提供的 `extra_env` 继续保持 last-wins，包括有意覆盖 VeADK 配置默认值。
- `CON-6`：AgentKit Runtime 创建及收敛更新必须持久化 `veadk:agent-type=mpa`，作为 Studio 稳定分类标签。未打标签 Runtime 在执行显式标签修复前不进入 MPA 筛选。

## 状态、安全与兼容

生命周期为 `prepared -> resource-created -> ready -> environment-finalized -> metadata-finalized -> verified`。按名称复用时通过 `UpdateRuntime(ReleaseEnable=True)` 收敛现有 Runtime，并等待更新版本 Ready。Secret 只属于进程/控制面数据，必须从 CLI 输出、文档、日志及测试夹具中脱敏。退出开关由本组件注入，不改变原生默认值，因此原生 mpa-agent 部署保持兼容。

## 失败与可观测性

缺少 Endpoint、Key、Runtime ID 或 APIG ID 会阻止 metadata 完成。Runtime 终态失败和 Ready 超时抛出 `MpaRuntimeError`。CLI 报告恢复所需的已创建资源标识，但不暴露凭据。APMPlus 是否开启通过 Runtime metadata 验证；链路读取授权属于独立的 Studio 责任。

## 验证

| 契约 | 验证 |
| --- | --- |
| `CON-1`、`CON-2`、`CON-5` | `uv run --extra dev pytest tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py` |
| `CON-2`、`CON-3`、`CON-4`、`CON-6` | `uv run --extra dev pytest tests/integrations/test_mpa_runtime.py` |
| 端到端 | 创建/复用隔离 Runtime，不打印 Key 地检查 metadata，调用 A2A 和内置 MCP，并观察两个 MCP 缓存周期 |
