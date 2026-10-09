# 基于预构建镜像一键创建 mpa-agent 设计文档

## 元信息

- **Change ID：** `mpa-agent-oneclick-provision`
- **创建 / 修订：** 2026-09-10 / 2026-09-10
- **生命周期状态：** `approved`
- **对应语言版本：** [2026-09-10-mpa-agent-oneclick-provision-design.md](2026-09-10-mpa-agent-oneclick-provision-design.md)
- **相关组件 spec：** 暂未创建；本次变更引入一个新的 CLI 契约面（见 §6），未修改 `specs/` 下任何现有组件契约。
- **前序 / 后继版本：** 无。

## 1. 概述

### 1.1 问题 / 背景

`mpa-agent`（`~/workspace/bytedance/mpa/mpa-agent`）是基于 FastAPI + veadk 的企业 Agent，以 AgentKit 镜像形式交付（`Dockerfile` `CMD ["python", "main.py"]`，`agentkit.yaml`）。当前拉起一个可运行实例依赖一条外部控制面记录：启动时 `app/services/mpa_meta.py` 调用 Arkclaw TOP 的 `GetMpaInstanceConf`（`app/client/arkclaw.py`，service `arkclaw`，version `2026-03-01`）解析 `mi-*` 实例配置（`account_id`、`resource_account_id`、`runtime_id`、`public_endpoint`、`private_endpoint`、`runtime_api_key`、`apig_instance_id`，以及可选的 `ov_resource_id` / `ov_api_key`）。

对 `arkclaw`、`mpa`、`veadk-python` 三处仓库做全量搜索确认：**该记录的创建对端在任何本地 checkout 中都不存在** —— 只有读客户端、其消费方（`app/services/mpa_meta.py`）、测试和 `docs/mpa-agent-api.md` 引用了 `GetMpaInstanceConf`。因此当前没有一条自包含的、可在 veadk 侧创建可运行 `mpa-agent` 的路径。

同时，所需的后端资源本就由外部管理：

- **PostgreSQL：** veadk 从不创建 RDS 实例或 database。`veadk/memory/short_term_memory_backends/postgresql_backend.py` 只执行 `CREATE SCHEMA IF NOT EXISTS`；部署 IAM 策略（`veadk/cli/frontend_deploy_policy.py`）只授予 `rds_postgresql:DescribeDBInstances/DescribeDBAccounts/DescribeDatabases`，无任何创建动作。数据库是前提，表结构由运行时自动创建。
- **OpenViking：** `mpa-agent` 通过 `OPENVIKING_URL` / `OPENVIKING_RESOURCE_ID` / `OPENVIKING_API_KEY`（`app/core/config.py`）以 HTTP 方式消费 OpenViking Server，不创建 `ov-*` 资源。veadk 无 Python 版 `CreateMemorydbInstance` 实现（`veadk/integrations/ve_viking_db_memory/ve_viking_db_memory.py` 仅暴露 collection/message/search 动作）。资源是前提。

### 1.2 目标

在**不修改 `mpa-agent` 镜像或代码**的前提下，提供一条自包含、不依赖控制面的路径：使用预构建的 `mpa-agent` 镜像，加上外部提供的 PostgreSQL 与 OpenViking 参数，拉起一个 `mpa-agent` 实例，并在 AgentKit Studio 中可聊天使用。

- 新增 `veadk mpa` CLI 命令组及 `veadk mpa create`，部署指定镜像并从外部参数注入全部运行时配置。
- 通过播种 `mpa_meta` 表，使运行时自身启动跳过不可用的 `GetMpaInstanceConf`，从而解除硬依赖。
- 验证实例健康且 Studio 可连接，并确认 `mpa-agent` 既有能力（REST 会话、每会话独立 Codex 沙箱、IM/飞书群聊）不受影响。

### 1.3 非目标

- 不创建 PostgreSQL RDS 实例/database，也不创建 OpenViking `ov-*` 资源（外部前提，见 §1.1）。
- 不实现或调用控制面 `CreateMpaInstance` 动作（延后；作为待决项记录于 §8）。
- 不修改 `mpa-agent` 源码、镜像或其公开 HTTP API。
- 不创建身份资源。在 veadk 创建场景下，`arkclaw-{space}-userpool/-client/-workload` **不使用**：以 `IDENTITY_STARTUP_ENABLED=false` 关闭启动身份初始化，并由 account id 适配出 `CLAW_SPACE_ID`（见 FR-10）。
- 不将 OpenViking collection 创建纳入本命令（OpenViking Server 路径按现状消费）。

## 2. 用户场景

### 场景 1：运维方基于镜像创建实例

**Given** 一个预构建的 `mpa-agent` 镜像 URL、一个已存在的 PostgreSQL 数据库（host/port/db/user/password）、一个已存在的 OpenViking 资源（`url`/`resource_id`/`api_key`）、模型凭据，以及身份/AgentKit 标识。
**When** 运维方带上这些参数运行 `veadk mpa create`。
**Then** CLI 将镜像部署到 VeFaaS + APIG，播种 `mpa_meta` 行，注入运行时 env，并输出 public endpoint、A2A agent-card URL 与 runtime API key 的位置，且 `/health`、`/readiness` 通过。

### 场景 2：在 Studio 中聊天

**Given** 一个成功创建、`<endpoint>/.well-known/agent-card.json` 可达的实例。
**When** 运维方在 AgentKit Studio（`veadk studio`）中以远端 Agent 方式连接并发送消息。
**Then** Studio 与实例通过 A2A `message/send` / `message/stream` 交互并渲染流式回复，复用同一 veadk Agent/Runner 与 PostgreSQL 会话存储。

### 场景 3：不同会话对应不同沙箱

**Given** 一个启用了 Codex 沙箱工具的实例（已设 `AGENTKIT_TOOL_ID`，`DISABLE_CODEX_SANDBOX` 非 `true`）。
**When** 两个不同会话各自触发一次 `sandbox_task` 委派。
**Then** 每个会话获得由 `sha256(app_name:user_id:session_id)` 派生的独立 Codex Worker 沙箱（`app/integrations/agentkit_sandbox.py:derive_sandbox_session_id`），本功能不改变该行为。

### 场景 4：飞书机器人群聊

**Given** 交互式提供 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（或省略，留待后续扫码绑定）。
**When** 实例启动。
**Then** 若已提供，运行时自动 upsert 飞书渠道绑定并注册 IM Gateway Bot（`app/services/channel/service.py`）；若省略，扫码绑定仍可用；群聊通过 `POST /api/v1/channels/events` 工作。

### 场景 5：既有 veadk 命令不受影响

**Given** 新增的 `mpa` 命令组已注册。
**When** 运维方运行任一既有命令（`veadk deploy`、`veadk frontend`、`veadk studio`、`veadk agentkit`、`veadk kb` 等）。
**Then** 行为与本次变更前完全一致。

## 3. 功能需求

- **FR-1 — 新增 `mpa` 命令组，纯增量。** 在 `veadk/cli/cli.py` 中与现有命令并列注册一个新的 `veadk mpa` `click` 组，不改动任何既有命令；控制台入口（`pyproject.toml` `veadk = "veadk.cli.cli:veadk"`）保持不变。
- **FR-2 — 外部参数。** `veadk mpa create` 通过选项和/或 env 回退接收：镜像 URL 与容器仓库；provider/region；PostgreSQL 连接（`PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD/PGSSLMODE/PGCHANNELBINDING`）或等价 DSN；OpenViking（`OPENVIKING_URL`、`OPENVIKING_RESOURCE_ID`、`OPENVIKING_API_KEY`）；模型（`MODEL_AGENT_PROVIDER/API_BASE/API_KEY/NAME`）；身份（`CLAW_SPACE_ID`、`MPA_AGENT_ID`、`IDENTITY_REGION`）；AgentKit（`AGENTKIT_TOOL_ID`、`AGENTKIT_TOOL_REGION`、`SKILL_SPACE_ID`）；鉴权方式；以及可选飞书（`FEISHU_APP_ID`、`FEISHU_APP_SECRET`）。
- **FR-3 — 带 key 鉴权的镜像部署。** 命令复用 `veadk/integrations/ve_faas/ve_faas.py:VeFaaS.deploy_image()` 并启用 key 鉴权将指定镜像部署到 VeFaaS + APIG。由于 `deploy_image()` 当前既不启用 key 鉴权也不返回网关/密钥，故对其做向后兼容扩展（新增可选参数 `enable_key_auth: bool = False`，默认行为不变）：当请求时在 `_create_application` 中启用 key 鉴权，并返回 public URL、application id、function id，以及 APIG 网关 id 与 key 鉴权 API key。未传该参数的既有调用方不受影响（AC-10）。
- **FR-4 — 播种 `mpa_meta` 以跳过 TOP 调用。** 使用所提供的 PostgreSQL 连接写入 `mpa_meta` 行，使 `app/services/mpa_meta.py:mpa_instance_conf_ready()` 成立，从而在启动时跳过 `GetMpaInstanceConf`。必填字段及其在 veadk 场景下的取值来源：
  - `account_id`：由部署凭据的 account id 解析。
  - `resource_account_id`：同一 account id（单账号 veadk 场景）。
  - `runtime_id`：`deploy_image` 返回的 VeFaaS application id。
  - `public_endpoint`：release 后的 application system URL（`framework.url.system_url`）。
  - `private_endpoint`：在 veadk 场景下置为与 `public_endpoint` 相同（public endpoint 为权威；见 FR-11）。这样该字段非空以满足 `mpa_instance_conf_ready()`，运行时 `choose_endpoint` 也能解析出可用 base。
  - `runtime_api_key`：来自 FR-3 的 key 鉴权 API key。
  - `apig_instance_id`：veadk 随函数一起自动创建/复用的 APIG 网关 id（从 release 的 `CloudResource` `framework.triggers[0].DetailedConfig.GatewayId` 获取，与 `VeFaaS.get_application_route` 一致）。已确认：veadk 会随函数一并创建 APIG，网关 id 不是外部前提。

  播种需幂等（fill-empty 语义等价于运行时的 `MpaMetaStore.fill_empty`），不得覆盖非空字段，且写入前必须断言七个字段均非空（否则中止，不留半可用实例）。
- **FR-5 — 运行时 env 注入。** 将所有解析出的配置设置为 VeFaaS 函数环境变量（创建 + release），键与 `mpa-agent` 启动时读取的一致（`.env.example`、`docs/mpa-agent-api.md` §9）。这包括 `IDENTITY_STARTUP_ENABLED=false`（FR-10）、`MPA_CODEX_WORKER_DEFAULT_MODEL=<model-name>`（避免 Codex 委派回退到字面值 `auto`）以及与 public endpoint 决策一致的 `MPA_CODEX_WORKER_ENDPOINT_PREFERENCE`/endpoint 选择（FR-11）。
- **FR-6 — 部署后验证。** release 后命令探测 `GET /health` 与 `GET /readiness`，并确认 A2A agent-card 在 `<public_endpoint>/.well-known/agent-card.json` 可达；失败时给出可操作的详情，且日志不含密钥。
- **FR-7 — Studio 聊天可用。** 命令输出连接实例所需的精确 endpoint、agent-card URL 与 API key 处理方式，以便在 `veadk studio` 中以远端 A2A Agent 方式连接。聊天、多会话/多沙箱、IM 群聊仅依赖运行时，不受本命令门禁限制。
- **FR-8 — 交互式、可选的飞书密钥。** 当提供 `--feishu-app-id` 但未提供密钥时，CLI 以隐藏输入方式提示 `FEISHU_APP_SECRET`；飞书完全可选；密钥不出现在 stdout 或日志中。
- **FR-9 — `mpa-agent` 无回归。** 本功能不修改 `mpa-agent` 源码或镜像；所选镜像仍需自行保证 REST/A2A 会话一致性、Codex 事件投影、定时任务与 IM 行为。若真实 E2E 暴露镜像级故障，创建流程与验收报告必须记录镜像/tag 及阻断证据，不得宣称完全兼容。
- **FR-10 — 身份适配（不使用 arkclaw 身份资源）。** veadk 场景不使用 `arkclaw-{space}-userpool/-client/-workload`。命令注入 `IDENTITY_STARTUP_ENABLED=false` 使启动身份初始化短路，由 account id 派生 `CLAW_SPACE_ID`，并设置 `A2A_TIP_VERIFY_ENABLED=false`，因为该拓扑不存在 TIP 签发方。Runtime 仍由强制 APIG key auth 保护；关闭内层 TIP 门禁后，Studio 服务端鉴权代理可以聊天，且 Runtime key 不会暴露给浏览器。
- **FR-11 — veadk 场景取 public endpoint。** 创建流程以 release 后的 public application URL 作为 `public_endpoint`、`private_endpoint`（镜像同值）、agent-card base 及 Codex worker endpoint 偏好的权威值。不需要任何私网 endpoint。

## 4. 设计与契约影响

### 4.1 职责与边界

本功能是 veadk 侧的**编排 + 配置**命令。它负责：参数采集/校验、通过既有 VeFaaS/APIG 集成部署镜像、播种 `mpa_meta`、组装 env、验证。它**不**负责：创建 PostgreSQL/OpenViking/身份资源，或 `mi-*` 控制面记录。

### 4.2 驱动设计的启动契约

`mpa-agent` 启动（`app/main.py` lifespan → `get_mpa_meta_service().initialize()`）：

1. `ensure_schema()` 在缺失时创建 `mpa_meta` 表。
2. 要求 `MPA_AGENT_ID` 非空。
3. 若缓存的 `mpa_meta` 行已具备全部七个必填字段（`mpa_instance_conf_ready`），则**跳过 `GetMpaInstanceConf`**；否则调用该 TOP 动作，而在没有控制面 `mi-*` 记录时会失败。
4. 由 `apig_instance_id` 懒创建 IM Gateway service（`ensure_im_gateway_service`）。

因此，在当前架构下，播种该行（FR-4）正是让创建流程自包含的机制。

### 4.3 所选方案与备选

- **所选 — 播种 `mpa_meta` + 注入 env（本设计）。** 仅使用本地可用能力，不依赖不可用的控制面动作。CLI 由部署结果加所提供参数计算出七个字段。播种步骤写在一个小的内部函数边界之后，便于未来以控制面后端替换而不改动命令流程。
- **备选 A — 调用控制面 `CreateMpaInstance`。** 暂拒：该动作在所有本地 checkout 中缺失；其名称、字段、version、IAM 要求未知。在 §8 记录为最终"正统"路径。
- **备选 B — 修改 `mpa-agent` 使 `GetMpaInstanceConf` 可选。** 拒绝：违反"不修改 `mpa-agent`"的非目标。

### 4.4 接口

新增 CLI 面（增量）：

```text
veadk mpa create \
  --image <cr-image-url> \
  --registry-name <cr-registry> \
  [--provider volcengine|byteplus] [--region cn-beijing] \
  --mpa-agent-id mi-xxxx \
  [--claw-space-id csi-xxxx]   # 可选；默认 csi-<account_id>（FR-10） \
  --pg-host ... --pg-port 5432 --pg-database ... --pg-user ... --pg-password ... \
  [--pg-sslmode require] [--pg-channel-binding require] \
  --model-provider openai --model-api-base ... --model-api-key ... --model-name ... \
  [--openviking-url ...] [--openviking-resource-id ov-xxx] [--openviking-api-key ...] \
  --agentkit-tool-id ... [--agentkit-tool-region cn-beijing] [--skill-space-id ...] \
  [--auth-method none|api-key|oauth2] \
  [--feishu-app-id cli_xxx] [--feishu-app-secret ...] \
  [--app-name mpa-agent] [--gateway-name ...] [--dry-run]
```

`--dry-run` 解析并打印计划（部署目标、env 键、`mpa_meta` 字段 —— 密钥掩码），不改动任何云或数据库状态。

### 4.5 状态、数据与幂等

- 本命令唯一写入的数据存储是外部 PostgreSQL 的 `mpa_meta` 表（按 `mpa_agent_id` 唯一的单行），采用与 `app/stores/mpa_meta.py:MpaMetaStore.fill_empty` 等价的 fill-empty 语义，并在写入前断言七个必填字段均非空。
- veadk 侧的 `mpa_meta` 表定义（列名/类型/server default）与 `app/stores/mpa_meta.py` 完全一致；以注释记录"运行时表结构变更需在此同步"。
- 以相同 `--app-name` 重复运行 `veadk mpa create` 会复用既有 VeFaaS 应用（`VeFaaS.deploy`/`deploy_image` 按应用名幂等），且不覆盖非空的 `mpa_meta` 字段。

### 4.6 权限与安全

- 需要能部署 VeFaaS + APIG 并访问容器仓库的云凭据（参考动作集见 `frontend_deploy_policy.py`；RDS 仅 `Describe`，此处不使用）。
- 密钥（`--pg-password`、`--model-api-key`、`--openviking-api-key`、`--feishu-app-secret`、runtime API key）在交互时以隐藏输入采集，在 `--dry-run` 输出中掩码，绝不记录日志。这符合 `arkclaw-mpa` 的 `secretless runtime` 原则：CLI 只注入运行时所需内容，不把控制面凭据写入运行时。

### 4.7 兼容性与受影响调用方

- 增量 CLI 命令；不改动任何既有 veadk 命令、公开导入或生成项目（FR-1、FR-9）。
- `VeFaaS.deploy_image` 新增一个可选关键字参数 `enable_key_auth: bool = False` 及扩展返回值；默认保持当前三元组行为，既有调用方（`CloudAgentEngine`、Studio）不受影响，由兼容性守卫测试验证（AC-10）。改动仅追加：不重排任何位置参数。
- 不改动 `mpa-agent` API 或镜像。
- Studio 通过已暴露的 A2A 面连接（`app/a2a/app.py`，`A2A_MOUNT_PATH=/` 时 agent-card 位于 `/.well-known/agent-card.json`）。

## 5. 边界情况

| 场景 | 处理方式 |
| --- | --- |
| `mpa_meta` 行已完整 | 跳过播种；记录跳过；继续验证（幂等）。 |
| 存在部分 `mpa_meta` 行 | 仅填充空的必填字段；绝不覆盖非空值。 |
| 写入前有字段未解析出 | 以具体消息中止；不写入部分行。 |
| PostgreSQL 不可达 | 在部署前快速失败并给出清晰连接错误；不产生云变更。 |
| 省略 OpenViking 参数 | 允许；运行时在无 OpenViking 工具下运行（仅在 URL+key 均设置时挂载）。 |
| 省略飞书密钥 | 允许；跳过自动绑定；运行时扫码绑定仍可用。 |
| 省略 `--claw-space-id` | 派生 `csi-<account_id>`（FR-10）；`IDENTITY_STARTUP_ENABLED=false` 使身份初始化关闭，无需任何 arkclaw 身份池。 |
| release 时镜像仍在同步 | 复用 `deploy_image` 的有界重试（`_release_application` 重试循环）。 |
| 部署中途失败 | 以脱敏日志报告失败；失败前已创建的资源被显式列出以便人工清理（若 `deploy_image` 缺乏与 `deploy` 对齐的清理，作为后续项）。 |
| 同名应用重复运行 | 复用既有应用；更新代码/env；不重复创建函数。 |
| `--dry-run` | 打印掩码密钥后的解析计划；不进行任何云或 DB 写入。 |
| 缺少必填参数 | 以指明缺失选项/env 的具体消息失败。 |

## 6. 涉及文件

- `veadk/cli/cli_mpa.py` — 新增 `mpa` 命令组与 `create` 命令（编排、参数处理、首版 `mpa_meta` 播种、验证）。
- `veadk/cli/cli.py` — 导入并 `veadk.add_command(mpa)`（单条增量注册）。
- `veadk/integrations/ve_faas/ve_faas.py` — 扩展 `deploy_image` 支持 `enable_key_auth` + 扩展返回（向后兼容）；复用 `_create_application`、`get_application_route`、release `CloudResource` 解析。
- `veadk/integrations/ve_apig/ve_apig.py` — 复用，不修改。
- `tests/cli/test_cli_mpa.py` — 新增单测，桩掉云 SDK，使用内存/SQLite `mpa_meta`。
- `prd-spec/features/mpa-agent-oneclick-provision/` — 本双语设计。
- 组件 spec：不改动任何既有 `specs/<component>/` 契约；若日后需要持久化 CLI 契约，可在后续单独新增 `specs/mpa-provisioning/`（本次范围外）。

## 7. 验收标准与追踪

| 需求 | 任务 | 验收标准 | 测试或验证命令 | 结果/证据 |
| --- | --- | --- | --- | --- |
| FR-1 | T-1 | `AC-1`：`veadk mpa --help` 列出 `create`；所有既有顶层命令仍可解析。 | `uv run veadk mpa --help` 与 `uv run veadk --help` | pass（2026-09-11）：mpa 列出 create；`veadk --help` 同时显示 mpa 与既有命令 |
| FR-2、FR-8 | T-2 | `AC-2`：缺失必填参数以具名错误失败；`--feishu-app-id` 无密钥时隐藏输入提示；`--dry-run` 中密钥掩码。 | `uv run pytest tests/cli/test_cli_mpa.py -k params` | pass（2026-09-11）：test_cli_mpa 6/6 |
| FR-3 | T-3 | `AC-3`：桩掉 VeFaaS/APIG 客户端后，经 `deploy_image(enable_key_auth=True)` 触发部署并捕获 public endpoint、apig 网关 id 与 key。 | `uv run pytest tests/cli/test_cli_mpa.py -k deploy` | pass（2026-09-11）：full_flow_orchestration + deploy_image key-auth |
| FR-3 | T-3b | `AC-10`：不带 `enable_key_auth` 调用 `deploy_image()` 时返回不变的三元组且不启用 key 鉴权（兼容性守卫）。 | `uv run pytest tests/ -k deploy_image_compat` | pass（2026-09-11）：test_deploy_image_compat_returns_three_tuple_without_key_auth |
| FR-4、FR-11 | T-4 | `AC-4`：播种写入七个必填字段（`private_endpoint` 镜像 `public_endpoint`）；已完整行保持不变；部分行仅填充空字段；任一字段未解析则在写入前中止。 | `uv run pytest tests/cli/test_cli_mpa.py -k seed` | pass（2026-09-11）：test_mpa_meta_seed 6/6 |
| FR-5、FR-10 | T-5 | `AC-5`：组装的 env 含 `mpa-agent` 启动读取的全部键，含未提供时的 `IDENTITY_STARTUP_ENABLED=false` 与 `CLAW_SPACE_ID=csi-<account_id>`；不记录任何密钥。 | `uv run pytest tests/cli/test_cli_mpa.py -k env` | pass（2026-09-11）：test_mpa_provision_env 6/6 |
| FR-6 | T-6 | `AC-6`：仅当 `/health`、`/readiness` 与 agent-card 均响应时验证通过；失败报告不含密钥。 | `uv run pytest tests/cli/test_cli_mpa.py -k verify` | pass（2026-09-11）：test_mpa_verify 4/4 |
| FR-7 | T-7 | `AC-7`：命令输出含 agent-card URL 与 Studio 连接指引；文档化的手动 Studio 聊天对真实实例成功，且不同会话得到不同沙箱、飞书群聊可用。 | 手动：`veadk studio` 连接 + 一条消息 | 部分通过/阻断：指引与不同 session→sandbox 映射已验证；所选镜像因 ADK session revision 冲突导致 A2A 最终失败；飞书缺凭据/机器人安装与专属客户 APIG id |
| FR-9 | T-8 | `AC-8`：本次变更不修改 `mpa-agent` 仓库任何文件；既有 veadk 命令测试通过。 | `git -C ~/workspace/bytedance/mpa/mpa-agent status --porcelain` 为空；`uv run pytest tests/cli` | pass（2026-09-11）：mpa-agent porcelain 为空；tests/cli 1273 passed, 4 skipped |
| 全部 | T-9 | `AC-9`：仓库门禁通过（pre-commit + 单测）。 | `pre-commit run -a` 与 `uv run pytest` | pass（2026-09-11）：changed files 上 pre-commit（ruff-check/format/gitleaks）Passed；新增套件 25/25 |

检查状态使用 `pass` / `fail` / `blocked` / `not_run` / `not_applicable`。执行时记录执行日期、被测 diff 范围与简要结果。

## 8. 风险与待决事项

- **OQ-1 — 控制面 `CreateMpaInstance`（本设计无需）。** `mi-*` 记录的创建对端在所有本地 checkout 中缺失。刻意置于范围外：veadk 版 `mpa-agent` 无需控制面记录。路线 A（CLI 侧播种 `mpa_meta`）为已接受的交付路径。此项仅作为未来非 veadk 部署的备注保留。
- **OQ-2 — CLI 侧播种 `mpa_meta` —— 已解决（已接受）。** 用户已批准由 CLI 直接下发 `mi-*` 元信息配置；veadk 版 `mpa-agent` 在无控制面记录的情况下运行。此为已接受的机制。
- **已解决 — APIG 实例 id 来源。** 代码确认：veadk 在部署时随函数一并创建/复用 APIG serverless 网关（`VeFaaS._create_application` + `ve_apig` 创建/复用；网关 id 可从 release 的 `CloudResource` `framework.triggers[0].DetailedConfig.GatewayId` 读取，见 `get_application_route`）。因此 `apig_instance_id` 由部署流程产出，非外部输入。
- **已解决 — endpoint 选择。** veadk 场景以 `public_endpoint` 为权威，`private_endpoint` 与其同值（FR-11）；不需要私网 endpoint。
- **已解决 — 身份。** veadk 场景设 `IDENTITY_STARTUP_ENABLED=false` 并派生 `CLAW_SPACE_ID=csi-<account_id>`，从而不使用 `arkclaw-{space}-userpool/-client/-workload`（FR-10）；启动身份初始化在 `app/identity/service.py:166` 短路。
- **风险 — secretless runtime。** 注入的 env 携带模型/OpenViking/runtime 密钥；应将控制面凭据排除在运行时之外并对所有密钥掩码，与 `arkclaw-mpa` 的原则一致。
- **风险 — `deploy_image` 失败清理。** 与 `deploy` 不同，`deploy_image` 缺少 `keep_failed_deploy`/回滚。扩展它时补齐对齐清理，或将已创建资源显式列出以便人工清理（见边界表）。

## 9. 评审与交付记录

- 评审状态：2026-09-10 经 `review-spec` 评审；P0 结论已回写进 FR-3/FR-4/FR-10/FR-11、AC-10 与 §4.7。2026-09-10 状态推进为 `approved`。
- 评审中已解决：APIG 实例 id 来源（部署产出）、endpoint 选择（public）、身份适配（`IDENTITY_STARTUP_ENABLED=false` + `csi-<account_id>`）。
- 用户批准：2026-09-10 已批准 —— 由 CLI 直接下发 `mi-*` 元信息配置（路线 A）；veadk 版 `mpa-agent` 无需控制面记录。OQ-2 已接受；OQ-1 置于范围外。
- 未决阻塞项：所选镜像的 Studio A2A 最终响应；飞书凭据/机器人安装与专属客户 APIG id。当前细节见 2026-09-11 编排对齐设计。
- 已执行检查：路线 A 单测/CLI 覆盖通过；后续对齐验证由 2026-09-11 设计与证据报告追踪。
- 剩余范围：见 2026-09-11 编排对齐设计。
