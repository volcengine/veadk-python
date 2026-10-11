# mpa-agent 创建编排对齐（CreateTool + SkillSpace + Runtime）设计文档

## 元信息

- **Change ID：** `mpa-agent-oneclick-provision`
- **创建 / 修订：** 2026-09-11 / 2026-09-11
- **生命周期状态：** `approved`
- **对应语言版本：** [2026-09-11-mpa-agent-provision-orchestration-alignment-design.md](2026-09-11-mpa-agent-provision-orchestration-alignment-design.md)
- **前序版本：** [2026-09-10-mpa-agent-oneclick-provision-design.zh.md](./2026-09-10-mpa-agent-oneclick-provision-design.zh.md)（`approved`，已实现）—— 本版扩展其范围，不替换已交付部分。
- **相关组件 spec：** 暂未创建；扩展 CLI 契约面（见 §6）。
- **参照实现：** `~/workspace/bytedance/mpa/mpa-runtime/docs/runtime-manager-openapi-map.md`（Runtime Manager 创建链路）。

## 1. 概述

### 1.1 问题 / 背景

已交付的路线 A（`2026-09-10` 设计，commit `18fa2485`）通过 `deploy_image`（VeFaaS + APIG，key 鉴权）→ 播种 `mpa_meta` → 注入 env → 验证 来创建 veadk 版 mpa-agent，并把 Codex 沙箱 **Tool id** 与任何 **Skill Space** 当作外部前提参数。

Runtime Manager 参照链路（`runtime-manager-openapi-map.md`）展示了创建方应负责的完整编排顺序：

```text
... -> CreateSkillSpace/GetSkillSpace -> CreateTool -> tool_id
    -> CreateRuntime(ArtifactUrl, RoleName, ToolId, Envs=PG*+SkillSpaceId+ToolId)
    -> ReleaseRuntime -> GetRuntime Ready -> /run_sse 验证 -> 持久化绑定
```

对照该参照，路线 A 尚缺两处：

- **未编排 CreateTool。** Codex 沙箱 `Tool`（`t-*`，由 `mpa_codex_worker` 镜像构建）必须在创建 agent **之前**创建并拿到 id。路线 A 要求调用方传入已有 `t-*`。
- **未编排 Skill Space。** 参照会创建/选择 Skill Space 并注入 `SKILL_SPACE_ID`；路线 A 仅在给定时透传 `--skill-space-id`。

还存在**计算面建模差异**：参照使用 AgentKit `CreateRuntime`（产出 `r-*` runtime；mpa-agent 自身 `agentkit.yaml` 即以 `runtime_id: r-yerdk5srnk54ppxtxy25` 交付），而路线 A 使用 `VeFaaS.deploy_image`（VeFaaS App + 自建 APIG）。两者都能起镜像，但只有 `CreateRuntime` 与参照资源模型及 mpa-agent 原生交付形态一致。

### 1.2 目标

让 `veadk mpa create` 对齐参照编排，能从镜像端到端拉起 mpa-agent，由 CLI 负责 Tool 与 Skill Space 的创建；PostgreSQL/OpenViking 仍为外部参数，且无需控制面 `mi-*` 记录。

- **G1 — 为每个 Agent 编排独立 CreateTool。** 默认针对每个新生成的 mpa-agent id，从提供的 worker 镜像创建一个专属 Codex 沙箱 `Tool`，并在创建 Runtime 前取得 `tool_id`；已有 `--agentkit-tool-id` 仅保留为显式调试/迁移逃生口。
- **G2 — 编排 Skill Space。** 可选地创建或选择 AgentKit Skill Space 并注入 `SKILL_SPACE_ID`。
- **G3 — 对齐计算面。** 通过 AgentKit `CreateRuntime`（`r-*`）创建 agent 以对齐参照与 mpa-agent 原生 runtime 模型，同时以开关保留既有 `deploy_image` 路径作为回退。
- **G4 — 保持路线 A 保证。** `mpa_meta` 播种、身份适配（`IDENTITY_STARTUP_ENABLED=false`、`CLAW_SPACE_ID=csi-<account_id>`）、public endpoint 权威、验证、密钥掩码、mpa-agent 无回归全部保留。

### 1.3 非目标

- 不创建 PostgreSQL 实例/database 或 OpenViking `ov-*` 资源（外部前提，同路线 A）。
- 不构建镜像本身；`--image`/`--tool-image` 为输入（artifact 优先，符合参照「Artifact 来源」）。
- 不实现 AIDAP Workspace/Branch/Database/DBAccount 创建（参照对 RDS 这样做，我们的 DB 是外部的）。
- 不建控制面 `mi-*` 记录；veadk 版 mpa-agent 无需它。

## 2. 用户场景

### 场景 1：从镜像完整编排

**Given** 一个 mpa-agent 镜像、一个 Codex worker 镜像、一个已存在的外部 PostgreSQL、模型凭据、account/region。
**When** 运维方带 `--tool-image <worker-image>`，且不带 `--mpa-agent-id`、`--agentkit-tool-id` 运行 `veadk mpa create`。
**Then** CLI 生成全局唯一的 `mi-<12位小写字母数字>`，将 `-` 替换为 `_` 得到 Tool 名，创建该专属 Tool（拿到 `t-*`），可选创建/选择 Skill Space，以生成的 id 命名 Runtime，播种 `mpa_meta`、验证并输出 Studio A2A 连接指引。

### 场景 2：复用已有 Tool

**Given** 一个已有 Codex worker Tool `t-*`（如 `t-yeslt9bv9ckgnctgwaaf`）。
**When** 运维方传 `--agentkit-tool-id t-*` 且省略 `--tool-image`。
**Then** CLI 跳过 CreateTool，复用该 id 继续。（保留路线 A 行为。）

### 场景 3：Runtime 就绪与验证

**Given** 已创建的 runtime。
**When** 创建完成。
**Then** CLI 等待 runtime 达到 Ready（或 VeFaaS 应用 release），再探测 `/health`、`/readiness` 与 A2A agent-card,通过后报告成功。

### 场景 4：幂等重跑与回滚

**Given** 之前的部分执行。
**When** 运维方以相同 名称/id 重跑。
**Then** 按精确名称复用 Tool/Skill Space/Runtime。非 Ready Tool 会等待；复用 Runtime 时更新并发布以收敛镜像、Tool、env，并等待更新后的版本 Ready。出现多个精确同名资源时明确失败，不任意选择。创建后失败时，两阶段 `mpa_meta` 可保留占位供重试，但不会被报告为已完成绑定。

## 3. 功能需求

路线 A 的 FR-1..FR-11（前序设计）继续生效。本版新增：

- **FR-12 — 每 Agent CreateTool 编排。** 省略 `mpa_agent_id` 时，CLI 生成 `mi-` 加 12 位小写字母数字。未提供 `--agentkit-tool-id` 时必须提供 `--tool-image`；CLI 经 `CreateTool` 创建 Codex 沙箱 Tool，默认以 agent id 将连字符替换为下划线后的值命名，并取得 `tool_id`。已实测的 Tool 契约保持不变。显式 `--agentkit-tool-id` 仅作为调试/迁移逃生口并跳过 CreateTool。
- **FR-13 — 每 Agent 身份与幂等。** 正常自动生成的 agent id 每次调用唯一，因此映射到不同 Tool 名和 Runtime 名。显式传入同一个 `--mpa-agent-id` 时用于失败重试，可复用该派生名称下已 Ready 的 Tool。`--tool-name`、`--runtime-name` 仅保留为显式调试覆盖。
- **FR-14 — Skill Space 编排。** 当提供 `--skill-space-name` 时，CLI 经 `agentkit.sdk.skills`（`list_skill_spaces`/`create_skill_space`/`get_skill_space`）创建或选择 Skill Space，并把解析出的 `SKILL_SPACE_ID` 注入 runtime env。仅提供 `--skill-space-id` 时直接使用；两者都不提供时省略 Skill Space。
- **FR-15 — 计算面选择。** `--compute-plane {runtime,vefaas}` 选择创建方式：`runtime`（默认）用 AgentKit `CreateRuntime`/`ReleaseRuntime`（`r-*`，对齐参照与 mpa-agent 原生模型）；`vefaas` 用既有 `deploy_image` 路径（路线 A）。两者须产出相同下游契约：public endpoint、APIG key 鉴权 API key、供 `mpa_meta` 的 APIG 实例 id。
- **FR-16 — Runtime 路径 env 与绑定。** `--compute-plane runtime` 时，`CreateRuntime` 以 `ArtifactType`/`ArtifactUrl=<mpa-agent 镜像>`、`ToolId`、`RoleName`、key 鉴权 authorizer、`Envs`=路线 A runtime env 加 `SKILL_SPACE_ID`（解析出时）与 `AGENTKIT_TOOL_ID` 调用。env 变更放在 `CreateRuntime`/`UpdateRuntime`（绝不放 `ReleaseRuntime`，其无 `Envs`），符合参照约束。
- **FR-17 — 有序幂等编排与回滚。** CLI 按 SkillSpace → Tool → **预播种 `mpa_meta`（FR-19）** → 计算面创建 → **完成 `mpa_meta`（FR-19）** → 验证 顺序执行。每个创建按 名称/client-token 幂等；资源创建后失败会显式列出已创建 id 以便清理。
- **FR-18 — `mpa_meta` 字段来自任一计算面。** runtime 模式下 `runtime_id` 为 AgentKit runtime id（`r-*`），vefaas 模式下为 VeFaaS app id；`apig_instance_id`、`runtime_api_key`、`public_endpoint` 由所选计算面解析。`private_endpoint` 镜像 `public_endpoint`（FR-11 不变）。
- **FR-19 — 首次容器启动前的两阶段播种（smoke 实测得出）。** mpa-agent 容器在 runtime release 后立即启动，启动时若 `mpa_meta` 行未完整就调用 `GetMpaInstanceConf`。在测试账号上该调用对 `arkclaw:GetMpaInstanceConf` 返回 `403 AccessDenied`，因此若播种发生在 release 之后，启动会失败。故播种改为两阶段，按调用方已知的 `mpa_agent_id` 主键：
  - **阶段 1（计算面创建之前）**：以真实 `account_id`/`resource_account_id` 和 `runtime_id`/`public_endpoint`/`private_endpoint`/`runtime_api_key`/`apig_instance_id` 的**非空占位**播种 `mpa_meta` 行，使首次容器启动时 `mpa_instance_conf_ready()` 已为真、runtime 跳过 `GetMpaInstanceConf`。
  - **阶段 2（Ready 之后）**：用真实的部署解析值覆盖占位字段。这要求 seeder 支持显式 overwrite 更新（区别于路线 A 的 fill-empty），仅作用于阶段 1 的占位字段。
  - 占位值不影响 A2A 聊天启动（agent-card URL 来自单独注入的 `A2A_PUBLIC_URL`）；真实 endpoint/apig/key 主要供 IM 网关路径使用，在阶段 2 完成。
- **FR-20 — APIG 绑定完整性。** finalize 前必须得到真实非空的 `runtime_id`、`public_endpoint`、`runtime_api_key`、`apig_instance_id`。Runtime 模式仅接受显式 `--apig-instance-id`、计算面直接返回值或能从 public endpoint 唯一映射出的 APIG id；禁止回退到账号下任意 gateway。AgentKit 共享网关返回 `GatewayInstanceId=""` 时 fail-closed，阶段 1 占位不得 finalize。

## 4. 设计与契约影响

### 4.1 编排顺序（对齐参照）

```text
解析参数，省略时生成 mpa_agent_id
  -> [FR-14] ensure SkillSpace（创建/选择）-> skill_space_id
  -> [FR-12/13] 从 mpa_agent_id 派生 Tool/Runtime 名
  -> ensure Tool（复用同 Agent Ready Tool 或 从 --tool-image CreateTool）-> tool_id
  -> 组装 runtime env（路线 A env + SKILL_SPACE_ID + AGENTKIT_TOOL_ID）
  -> [FR-19 阶段 1] 预播种 mpa_meta（真实账户 + 非空占位）
                     使首次容器启动跳过 GetMpaInstanceConf（测试账号返回 403）
  -> [FR-15/16] 计算面：
       runtime : CreateRuntime(ToolId, ArtifactUrl, Envs) -> ReleaseRuntime -> GetRuntime Ready
       vefaas  : deploy_image(enable_key_auth=True)   （路线 A）
     -> public_endpoint, apig_instance_id, runtime_api_key, runtime_id/app_id
  -> 要求 runtime/endpoint/key/APIG 均为真实非占位值；共享网关无客户 APIG id 时
     fail-closed（或显式传 --apig-instance-id）
  -> [FR-19 阶段 2] finalize mpa_meta（用真实值覆盖占位）
  -> [路线 A] 验证 /health /readiness /agent-card
  -> 输出 Studio A2A 指引
```

### 4.2 所选方案与备选

- **所选 — 扩展 CLI 负责 SkillSpace + Tool + Runtime，默认 `CreateRuntime`。** 对齐参照资源模型与 mpa-agent 原生 `r-*` 交付；以 `--compute-plane vefaas` 保留 `deploy_image` 回退，不丢弃已交付的路线 A。
- **备选 — 保持 Tool/SkillSpace 外部（仅路线 A）。** 本迭代拒绝：用户要求对齐参照——由创建方创建 Tool 并在创建 agent 前拿到 id。
- **备选 — 完全弃用 `deploy_image`。** 拒绝：它已交付、已测、在不需要 AgentKit Runtime 时有用，以开关保留。

### 4.3 接口（在路线 A 基础上增量）

```text
veadk mpa create \
  ...（全部路线 A 选项）... \
  [--compute-plane runtime|vefaas]        # 默认 runtime \
  [--tool-image <codex-worker-image>]     # 设置且无 --agentkit-tool-id 时创建 Tool \
  [--mpa-agent-id mi-*]                   # 省略则生成 mi-<12位小写字母数字> \
  [--tool-name <name>]                    # 调试覆盖；默认把 mi-* 的 '-' 替换为 '_' \
  [--tool-role-name IDRoleForArkClawShareAgent] \
  [--skill-space-name <name>] [--skill-space-id ss-*] \
  [--runtime-role-name <role>] [--runtime-name <name>] # 默认 mpa-agent-id \
  [--min-instance 1] [--max-instance 1] \
  [--apig-instance-id <gateway-id>]       # IM 路由使用的专属客户 APIG \
  [--agentkit-tool-id t-*]                # 设置时跳过 CreateTool（路线 A 复用）
```

`--dry-run` 扩展为打印计划中的 SkillSpace/Tool/计算面动作与解析出的 env（密钥掩码），不进行任何云或 DB 写入。

### 4.4 SDK 事实（在账号 2112682748 实测）

- Tools：`agentkit.sdk.tools.client.AgentkitToolsClient` — `create_tool`、`get_tool`、`list_tools`；`CreateToolRequest` 含 `image_url`、`command`、`port`、`tool_type`、`role_name`、`skill_space_id`、`authorizer_configuration`、`network_configuration`、`envs`、`client_token`。
- Runtime：`agentkit.sdk.runtime.client.AgentkitRuntimeClient` — `create_runtime`、`release_runtime`、`get_runtime`、`list_runtime_instances`、`update_runtime`；`CreateRuntimeRequest` 含 `artifact_type`、`artifact_url`、`tool_id`、`role_name`、`authorizer_configuration`、`network_configuration`、`envs`、`min_instance`、`max_instance`、`client_token`。
- Skills：`agentkit.sdk.skills.client.AgentkitSkillsClient` — `create_skill_space`、`get_skill_space`、`list_skill_spaces`。
- 既有 Codex worker Tool 契约（来自 `t-yeslt9bv9ckgnctgwaaf`，镜像 `mpa_codex_worker:apihelpers-b3818f5-...`）：`ToolType=Private`、`command=/opt/gem/run.sh`、`port=8000`、`cpu 2000/mem 4096`、`role IDRoleForArkClawShareAgent`、公网+私网 APIG 端点、key 鉴权。

### 4.5 状态、数据、幂等、回滚

- 幂等键：SkillSpace 按名；Tool 与 Runtime 按精确名称。单一匹配时复用，非 Ready Tool 等待；Runtime 经 `UpdateRuntime(..., ReleaseEnable=True)` 收敛配置并等待更新版本 Ready。多个精确同名资源视为歧义并失败。
- `mpa_meta`：阶段 1 以占位写齐七个必填字段；仅在所有真实值通过完整性检查后，阶段 2 覆盖部署绑定字段。`runtime_id` 来源取决于 `--compute-plane`。
- 回滚：创建后失败时显式列出已创建 `ss-*`/`t-*`/`r-*` id。完整自动拆除超出范围；阶段 1 占位可保留供幂等重试，但不报告为完成绑定。

### 4.6 权限与安全

- 在路线 A 凭据集上新增 AgentKit Tools/Skills/Runtime 创建权限。RDS 仍仅 `Describe` 且不使用。
- 密钥处理不变：隐藏输入、`--dry-run` 掩码、不记录日志；不向 runtime 注入控制面凭据。

### 4.7 兼容性与受影响调用方

- 增量 CLI 选项；`--compute-plane runtime` 成为默认，这**改变了路线 A 的默认行为**（路线 A 一贯用 `deploy_image`）。这是经批准、限定于 `veadk mpa create` 的行为变更；`--compute-plane vefaas` 精确复现路线 A。
- `VeFaaS.deploy_image` 签名相较路线 A 不变（已扩展并由 AC-10 兼容守卫）。
- 不改 mpa-agent 源码/镜像/API。

## 5. 边界情况

| 场景 | 处理方式 |
| --- | --- |
| runtime 模式既无 `--tool-image` 也无 `--agentkit-tool-id` | 在任何云端或数据库写入前校验失败。 |
| `--tool-image` 与 `--agentkit-tool-id` 同时给 | 优先显式 `--agentkit-tool-id`；提示 `--tool-image` 被忽略。 |
| 同名 Tool 存在但非 Ready | 有界超时内等待 Ready；始终未就绪则带 tool id 失败。 |
| 存在多个精确同名 Tool 或 Runtime | 以歧义错误失败，绝不任意绑定一个资源。 |
| `--skill-space-name` 与 `--skill-space-id` 都不给 | 省略 `SKILL_SPACE_ID`；runtime 无 skill space 运行。 |
| `--compute-plane runtime` 但 artifact 类型未知 | 创建前带清晰消息失败；不创建半配置 runtime。 |
| Runtime 始终未 Ready | 带 runtime id 与最后状态失败；阶段 1 占位保持未 finalize，供明确重试/清理。 |
| 部分失败后重跑 | 按精确名称复用既有 SkillSpace/Tool/Runtime；阶段 1 fill-empty，阶段 2 仅覆盖占位字段。 |
| Runtime 为共享网关且 `GatewayInstanceId` 为空 | 除非用 `--apig-instance-id` 提供专属客户 gateway，否则 finalize 前 fail-closed；不选择账号下其他 gateway。 |
| `--dry-run` | 打印 SkillSpace/Tool/计算面计划 + 掩码 env；不写入。 |

## 6. 涉及文件

- `veadk/cli/cli_mpa.py` — 新增 `--compute-plane`、`--tool-image`、`--tool-name`、`--skill-space-name`、runtime/APIG 选项；编排 SkillSpace → Tool → 预播种 → 计算面 → 完整性检查 → finalize → 验证。
- `veadk/integrations/mpa/mpa_tool.py`（新）— CreateTool/按名复用辅助，镜像已实测 Codex worker Tool 契约。
- `veadk/integrations/mpa/mpa_skill_space.py`（新）— 创建/选择 Skill Space 辅助。
- `veadk/integrations/mpa/mpa_runtime.py`（新）— `CreateRuntime`/`ReleaseRuntime`/等 Ready 辅助，并把结果归一为 `(public_endpoint, apig_instance_id, runtime_api_key, runtime_id)`。
- `veadk/integrations/mpa/mpa_provision.py` — 扩展 params/env 以含 skill space + tool 镜像。
- `veadk/integrations/ve_faas/ve_faas.py` — 不变（复用 vefaas 回退）。
- `tests/cli/test_cli_mpa.py`、`tests/integrations/test_mpa_tool.py`、`test_mpa_skill_space.py`、`test_mpa_runtime.py`（新增/扩展）— 桩 SDK 单测。
- `prd-spec/features/mpa-agent-oneclick-provision/` — 本双语设计。

## 7. 验收标准与追踪

路线 A 的 AC-1..AC-10 保持绿色（代码路径不变）。新增：

| 需求 | 任务 | 验收标准 | 测试 / 验证 | 结果 |
| --- | --- | --- | --- | --- |
| FR-12/13 | T-10 | `AC-11`：动态 CreateTool；单一同名 Tool 复用/等待，多个精确同名失败。 | `uv run pytest tests/integrations/test_mpa_tool.py` | pass（2026-09-11） |
| FR-12/13 | T-10b | `AC-11b`：自动生成合法唯一 `mi-*`，派生 Tool/Runtime 名；缺少 Tool 输入时在写入前失败。 | `uv run pytest tests/cli/test_cli_mpa.py -k generated_identity` | pass（2026-09-11） |
| FR-14 | T-11 | `AC-12`：创建/选择 Skill Space 并注入；无配置时省略。 | `uv run pytest tests/integrations/test_mpa_skill_space.py` | pass（2026-09-11） |
| FR-15/16 | T-12 | `AC-13`：创建或收敛精确同名 Runtime，发布并等待当前/更新版本 Ready；重名歧义失败；`ArtifactType=image`。 | `uv run pytest tests/integrations/test_mpa_runtime.py` | pass（2026-09-11）；真机确认 ArtifactType=image |
| FR-15 | T-12b | `AC-14`：`--compute-plane vefaas` 保持路线 A。 | `uv run pytest tests/cli/test_cli_mpa.py -k vefaas` | pass（2026-09-11） |
| FR-17/19 | T-13 | `AC-15`：SkillSpace→Tool→预播种→计算面→绑定完整性→finalize→验证。 | `uv run pytest tests/cli/test_cli_mpa.py -k orchestration` | pass（2026-09-11） |
| FR-18/20 | T-14 | `AC-16`：APIG id 来自 endpoint 唯一映射或显式参数；共享网关无 id 时 fail-closed，不 finalize 占位。 | `uv run pytest tests/cli/test_cli_mpa.py -k gateway` | pass（2026-09-11） |
| FR-19 | T-17 | `AC-19`：阶段 1 写完整占位；阶段 2 仅以真实值覆盖部署绑定字段。 | `uv run pytest tests/integrations/test_mpa_meta_seed.py` | pass（2026-09-11） |
| 全部 | T-15 | `AC-17`：真机创建 Tool/Runtime、Ready，并验证 Studio A2A 与两个 context。 | 手动真机 + Studio | 部分通过/阻断：Runtime 与两个不同 worker session 通过；所选镜像因 ADK session revision 冲突导致 A2A 最终失败；飞书还缺专属 APIG id/凭据 |
| 全部 | T-16 | `AC-18`：pre-commit + CLI/相关单测回归；本实现不改 mpa-agent 仓库。 | `uv run pre-commit run --files <功能文件>`；MPA 测试；`uv run pytest tests/cli` | pass：MPA 57；CLI 1282 passed/4 skipped；pre-commit hooks 通过 |

## 8. 风险与待决事项

- **OQ-4 — 默认计算面 —— 已解决。** 默认 `--compute-plane runtime`（`CreateRuntime` → `r-*`）以对齐参照与 mpa-agent 原生模型；`--compute-plane vefaas` 复现路线 A。
- **OQ-5 — CreateTool env 完整性 —— 已解决。** 以参照 Codex worker Tool（如 `t-yeslt9bv9ckgnctgwaaf`）的 env 集作为模板克隆，允许按键覆盖。这是获得 Ready 沙箱最稳的路径。
- **OQ-6 — ArtifactType 取值 —— 已解决（实现阶段验证）。** 用户批准在实现阶段于测试账号（2112682748）做一次真机 smoke `CreateRuntime`，确认镜像 `ArtifactType`/`ArtifactUrl` 契约；结论回写本设计。
- **风险 — 真实资源成本。** Runtime/Tool/APIG 创建计费且不易回收；先 `--dry-run` 再确认后真实创建。测试账号（2112682748）已授权用于验证运行。
- **阻断 — 所选 mpa-agent 镜像的 A2A 结果。** Runtime 与委派 worker 能完成，但 A2A 因 `The session has been modified in storage since it was loaded` 返回失败；镜像修复 ADK session revision 协调前，Studio 无法完成交互聊天。
- **阻断 — 共享 APIG 无法标识客户 IM gateway。** 实测 Runtime 为 `GatewayMode=Shared` 且 `GatewayInstanceId` 为空，endpoint 不映射到账户 APIG id。`--apig-instance-id` 提供显式适配，但自动分配专属 gateway 不在本实现范围。
- **阻断 — 飞书验证。** 未具备飞书凭据/机器人安装与专属客户 APIG id，拉群能力保持未验证。
- 路线 A 待决项（控制面 `CreateMpaInstance` 范围外；CLI 侧播种已接受）维持既定结论。

## 9. 评审与交付记录

- 评审状态：2026-09-11 经 `review-spec` 评审；OQ-4/OQ-5/OQ-6 已与用户敲定。2026-09-11 状态推进为 `approved`。
- 决策：默认计算面 `runtime`；CreateTool env 克隆自参照 worker Tool；`ArtifactType` 由实现阶段测试账号 2112682748 的 smoke `CreateRuntime` 确认。
- 前序路线 A 保持已交付且不变；本版除默认计算面外为增量。
- Review 修复：Tool/Runtime 精确名称重试已确定化；等待非 Ready Tool 与 Runtime 更新版本；APIG 解析 fail-closed，不选择无关 gateway。
- 未决阻塞项：Studio A2A 最终响应受所选镜像 ADK session revision 冲突阻断；飞书拉群受凭据/机器人安装和专属客户 APIG id 阻断。
- 剩余范围：最终本地门禁、提交并推送；镜像/APIG/飞书阻断作为外部残余风险留存，不标记为通过。
