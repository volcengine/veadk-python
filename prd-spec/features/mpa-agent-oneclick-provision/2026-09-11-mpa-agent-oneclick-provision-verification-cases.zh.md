# mpa-agent 一键创建 — 功能验证 Case 清单

> 关联设计：`2026-09-10-mpa-agent-oneclick-provision-design.zh.md`（`approved`）
> 用途：dev-loop 步骤 2 前置设计、步骤 7 后置执行的可执行验证 Case。
> 状态：`executed-with-blockers`（单测/CLI 通过；真机结果见 §3.1）。

## 1. 证据留存约定

- 单测证据：`uv run pytest` 输出 + 覆盖到的断言，落 `prd-spec/features/mpa-agent-oneclick-provision/evidence/<case-id>.log`。
- CLI 行为证据：命令 stdout/stderr（密钥须掩码）落同目录。
- 真机 Studio E2E 证据：请求/响应摘要、SSE 片段、截图路径，落同目录；不得含真实密钥。

## 2. 覆盖矩阵（需求 → Case）

| 需求 | Case | 层次 |
| --- | --- | --- |
| FR-1 | VC-1 | 单测/CLI |
| FR-2 | VC-2, VC-3 | 单测/CLI |
| FR-3 | VC-4（key-auth 部署）, VC-5（AC-10 兼容守卫） | 单测 |
| FR-4 | VC-6, VC-7, VC-8, VC-9 | 单测 |
| FR-5 | VC-10, VC-23 | 单测 + 真机 |
| FR-6 | VC-11, VC-12 | 单测 |
| FR-7 | VC-13（输出指引）, VC-18（真机 Studio 聊天） | 单测 + 真机 |
| FR-8 | VC-3（隐藏输入）, VC-14（dry-run 掩码） | 单测/CLI |
| FR-9 | VC-15（mpa-agent 零改动）, VC-16（既有命令回归） | 门禁/回归 |
| FR-10 | VC-10（IDENTITY_STARTUP_ENABLED=false + csi-<account_id>） | 单测 |
| FR-11 | VC-7（private 镜像 public） | 单测 |
| 关键回归 | VC-16, VC-19（不同 session 不同沙箱）, VC-20（飞书拉群） | 回归 + 真机 |
| FR-12/13 | VC-21（生成身份 + 独立 Tool/Runtime）, VC-22（缺 Tool 输入无写入）, VC-24（重试幂等） | 单测/CLI |
| FR-18 | VC-25（APIG id 解析 fail-closed） | 单测 + 真机 |

每个 P0/P1 需求（FR-1..FR-19）均至少 1 个 Case 覆盖。

## 3. Case 明细

### 正常路径

- **VC-1（FR-1 命令注册）**
  - 命令：`uv run veadk mpa --help` 且 `uv run veadk --help`
  - 前置：无
  - 预期：`mpa` 组列出 `create`；`veadk --help` 仍列出 deploy/init/create/frontend/studio/agentkit/kb 等全部既有命令。
  - 通过标准：两条命令 exit 0；子命令齐全无缺失。
  - 失败处理：回 T-12/T-1。

- **VC-4（FR-3 key-auth 部署 + 资源回收）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k deploy`
  - 前置：桩化 `VeFaaS`/`APIGateway`；桩 release 返回含 `framework.url.system_url` 与 `framework.triggers[0].DetailedConfig.GatewayId`。
  - 输入：`enable_key_auth=True` 路径。
  - 预期：编排调用 `deploy_image(..., enable_key_auth=True)`；捕获 `public_endpoint`、`apig_instance_id`(=GatewayId)、`runtime_api_key`。
  - 通过标准：断言四元/五元返回被正确解构；`_create_application` 收到 `EnableKeyAuth=True`。
  - 证据：`evidence/VC-4.log`。

- **VC-10（FR-5/10/11 env 组装）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k env`
  - 输入：不传 `--claw-space-id`、不传 `IDENTITY_STARTUP_ENABLED`。
  - 预期：组装 env 含全部 mpa-agent 启动键；`IDENTITY_STARTUP_ENABLED=false`；`A2A_TIP_VERIFY_ENABLED=false`；`MPA_CODEX_WORKER_DEFAULT_MODEL=<model-name>`；`CLAW_SPACE_ID=csi-<account_id>`；endpoint 相关键取 public。
  - 通过标准：键集合等于期望集合；无任一密钥出现在日志字符串。
  - 证据：`evidence/VC-10.log`。

- **VC-13（FR-7 输出 Studio 指引）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k guidance`（或 dry-run 输出断言）
  - 预期：成功路径 stdout 含 `public_endpoint`、`<endpoint>/.well-known/agent-card.json`、runtime API key 的处理说明。
  - 通过标准：三项均出现；key 值本身掩码。

### 异常路径

- **VC-2（FR-2 缺必填报错）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k params`（缺 `--image`/`--mpa-agent-id`/`--pg-*`/`--model-*` 各一例）
  - 预期：每例以**指明缺失项名**的错误退出（非通用 traceback）。
  - 通过标准：错误消息含具体选项名；exit != 0；无云/DB 写入。

- **VC-11（FR-6 探测失败即失败）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k verify`
  - 输入：桩 `/health` 200 但 `/readiness` 非 200；及 agent-card 404。
  - 预期：验证判定 fail，报告指出未通过的探测项。
  - 通过标准：任一探测未通过则整体 fail；报告文本不含密钥。

- **VC-8（FR-4 字段未解析写前中止）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k seed_abort`
  - 输入：`runtime_api_key` 解析为空。
  - 预期：播种前抛具名错误，**不写入任何行**。
  - 通过标准：DB 无新增/修改行；错误指明缺失字段。

- **VC-17（PostgreSQL 不可达）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k pg_unreachable`
  - 输入：连接串指向不可达端口。
  - 预期：**部署前**快速失败，未触发任何云部署调用。
  - 通过标准：VeFaaS 部署桩零调用；错误为连接类错误。

### 边界条件

- **VC-6（FR-4 空行写 7 字段）**：`-k seed` 子用例，空表 → 写入 7 字段齐全且值正确。
- **VC-7（FR-4/11 private 镜像 public）**：断言 `private_endpoint == public_endpoint`。
- **VC-9（FR-4 幂等）**：完整行不被覆盖；部分行仅补空字段，非空字段保持原值。
- **VC-14（FR-8 dry-run 掩码）**：`--dry-run` 输出含计划但所有密钥呈掩码；无云/DB 写入。
- **VC-5（FR-3 AC-10 兼容守卫）**：`deploy_image()` 不传 `enable_key_auth` → 返回原三元组 `(url, app_id, function_id)`，`_create_application` 收到 `EnableKeyAuth=False`。

### 权限/环境隔离

- **VC-3（FR-2/8 飞书密钥隐藏输入）**
  - 命令：`uv run pytest tests/cli/test_cli_mpa.py -k feishu_prompt`
  - 输入：给 `--feishu-app-id` 不给 secret。
  - 预期：触发 `click.prompt(hide_input=True)`；secret 不回显、不入日志。
  - 通过标准：prompt 被以 `hide_input=True` 调用；捕获输出无 secret 明文。

### 跨模块联动 / 关键回归（真机，步骤 7/10 执行）

- **VC-15（FR-9 mpa-agent 零改动）**
  - 命令：`git -C ~/workspace/bytedance/mpa/mpa-agent status --porcelain`
  - 通过标准：输出为空。

- **VC-16（FR-9 既有命令回归）**
  - 命令：`uv run pytest tests/cli`
  - 通过标准：既有 CLI 测试全绿（新增用例不破坏存量）。

- **VC-18（FR-7 真机 Studio 聊天）**
  - 步骤：`veadk studio` → 以远端 A2A Agent 连接实例 agent-card → 发送一条消息。
  - 预期：SSE 流式回复渲染成功。
  - 证据：请求/响应摘要 + SSE 片段（脱敏）落 `evidence/VC-18.md`。

- **VC-19（关键回归 不同 session 不同沙箱）**
  - 步骤：两个不同 session 各触发一次 `sandbox_task`。
  - 预期：两个 session 的 sandbox_session_id 不同（`sha256(app_name:user_id:session_id)` 派生）。
  - 证据：两次 sandbox id 记录（脱敏）。

- **VC-20（关键回归 飞书拉群）**
  - 前置：提供 `FEISHU_APP_ID/SECRET`（或扫码绑定）。
  - 步骤：群内 @ 机器人发消息 → 观察 IM Gateway 回复。
  - 预期：群 session 复用、回复送达。
  - 证据：入站/出站 envelope 摘要（脱敏）。

### 生成身份与独立资源

- **VC-21（FR-12/13 生成身份与每 Agent 资源）**：省略 agent/tool id、提供 `--tool-image`，断言生成合法且唯一 `mi-*`、派生 Tool/Runtime 名，并先 CreateTool 后 CreateRuntime。
- **VC-22（FR-12 缺 Tool 输入无写入）**：runtime 模式缺少 tool image/id 时，在 SkillSpace、DB、Tool、Runtime 调用前具名失败。
- **VC-23（FR-5 worker 模型选择）**：真机 `sandbox_task` 使用 CLI 指定模型，模型请求 2xx 且 binding 最终 `completed`。
- **VC-24（FR-13 重试幂等）**：同名 Tool/Runtime 复用并收敛配置；非 Ready Tool 等待；重名歧义失败；Runtime 更新等待更新版本 Ready。
- **VC-25（FR-18 APIG id 完整性）**：只接受 endpoint 唯一映射的 gateway id 或显式 `--apig-instance-id`；共享 gateway 无 ID 时 fail-closed，不写入任意 gateway 或 `pending`。

## 3.1 真机 E2E 结果（2026-09-11）

- Runtime `r-yeuugf44qob21078l38i`、Tool `t-yeuugdts00zn6n5iqhin`，mpa-agent 镜像 tag `20260908154102-d34fdab`。
- VC-23 通过：两个新 context 均使用指定模型、模型 HTTP 200、命令 exit code 0，并持久化 `invocation.completed`。
- VC-19 在资源层通过：两个 context 映射到不同 worker session。
- VC-18 在协议结果边界阻断：worker 已完成，但 A2A 均因 PostgreSQL ADK session revision 冲突返回 failed；属所选 mpa-agent 镜像缺陷。
- VC-20 未执行：未提供飞书凭据/机器人安装；且 Runtime 为 `GatewayMode=Shared`、`GatewayInstanceId` 为空，现有行仍为 `apig_instance_id=pending`。CLI 已 fail-closed 并允许显式传专属 `--apig-instance-id`，客户 gateway 自动分配仍未解决。

## 4. 验证执行计划

1. 单测级（VC-1..VC-14, VC-17）：桩云 SDK + SQLite/内存 `mpa_meta`，随 TDD 每任务即时执行。
2. 回归（VC-15, VC-16）：实现完成后统一执行。
3. 真机（VC-18, VC-19, VC-20, VC-23, VC-25）：一次真实 `veadk mpa create` 部署后，在 Studio 与飞书群验证；证据脱敏留存。
4. 失败处理：P0/P1 Case 失败回 T-8..T-12 修实现，或回本清单修 Case（并记录原因），重跑受影响 Case。

## 5. 准出门禁

- 所有映射到 FR-1..FR-19 的单测/CLI P0/P1 Case 通过。
- VC-15/VC-16 回归通过（不破坏 mpa-agent 与既有命令）。
- 真机 VC-18、VC-20 按 §3.1 保持 blocked；VC-19、VC-23 通过。
