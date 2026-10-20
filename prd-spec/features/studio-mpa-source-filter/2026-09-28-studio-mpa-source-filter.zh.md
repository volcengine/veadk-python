# Studio 创建的 MPA Runtime 过滤

[English version](2026-09-28-studio-mpa-source-filter.md)

- Change ID：`studio-mpa-source-filter`
- 创建/修订日期：2026-09-28
- 状态：`approved`
- 所属仓库：`veadk-python`
- 影响组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)、[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)
- 批准记录：用户于 2026-09-28 选择渐进来源过滤（方案 1）。

## 1. 背景与证据

Studio 当前仅通过 `veadk:agent-type=mpa` 分类 MPA Runtime。管理员获得 `runtimeScope=all`，因此其他产品或运维流程创建的 MPA Runtime 也会出现。`scope=mine` 是基于 `veadk:owner` 的归属过滤，不能证明 Studio 来源。

通用 Studio 部署已写入 `veadk:managed=true`、`veadk:owner` 和 `veadk:author`，但 MPA 分支没有专用 provisioner 标记。托管式一键创建在注册表持久化 `studio_owner`，但目前只把 `veadk:agent-type=mpa` 投影到 Runtime 标签。因此名称、镜像、`mi-` 前缀和仅有 owner 都不是安全来源信号。

## 2. 目标与非目标

目标：

- Studio MPA 列表只展示 Studio 管理的 MPA Runtime。
- 在 Runtime 补齐和分页前使用服务端 Tag 查询过滤。
- 两条 Studio MPA 创建路径写入一致的来源和归属标签。
- 保留已经带 `veadk:managed=true` 的通用 Studio 历史 MPA。
- Runtime 授权与来源过滤保持独立。

非目标：

- 不使用名称、镜像、artifact URL、Runtime ID 前缀、环境值或注册表启发式判断。
- 不自动修改云资源或执行无人值守的批量回填。可由用户显式授权一次性、可验证的运维回填，把已知历史 MPA Runtime 指定为 Studio-managed，并必须在本 PRD 记录。
- 不改变通用 Agent 列表、授权、企业可见性、删除权限、响应 schema 或 UI 布局。
- 不把 `veadk:managed=true` 当作授权凭据。

## 3. 备选方案与决策

1. **渐进来源过滤——已选择。** 写入既有兼容标记 `veadk:managed=true` 和新标记 `veadk:provisioner=studio-mpa`；当前列表按 `agent-type=mpa + managed=true` 过滤。
2. **严格新标签过滤。** 立即要求 `veadk:provisioner=studio-mpa`；新资源准确，但全部历史 Studio MPA 在回填前隐藏。
3. **关联注册表。** 从部署注册表恢复历史来源；这会为每次列表增加数据源耦合、成本和可用性故障面。

方案 1 是最小安全变化。未来可显式回填 `veadk:provisioner`；此前 `veadk:managed=true` 作为兼容准入标记。

## 4. 功能需求

### FR-1：创建来源

两条 Studio MPA 创建路径写入：

- `veadk:agent-type=mpa`
- `veadk:managed=true`
- `veadk:provisioner=studio-mpa`
- 写入 `veadk:owner=<可信 Studio owner id>`；若该身份不可用，Studio 创建必须在云变更前失败
- 路径拥有 MPA 身份时写 `veadk:mpa-instance-id=<MPA instance id>`

标签对账替换这些受管键、保留无关非系统标签，且不把 `sys:*` 标签复制到 create/update payload。
托管 provisioning 服务也被 `veadk mpa create` CLI 复用，因此仅当 Studio 路由显式提供可信 Runtime owner 时才注入 Studio 来源。任务数据库和原生部署注册表继续保存 owner 哈希以隔离私有任务；原始可信 owner 只传给固定子进程和 Runtime 标签 payload，不持久化到本地任务状态。CLI 创建的 MPA Runtime 仅保留 MPA 分类标签，不进入 Studio-managed 过滤结果。

### FR-2：服务端来源过滤

`GET /web/runtimes?agentCategory=mpa` 必须在 Runtime 补齐和分页前，同时查询 `veadk:agent-type=mpa` 和 `veadk:managed=true`。`scope=mine` 再增加 `veadk:owner=<当前 principal owner id>`。管理员 `scope=all` 返回全部 Studio 管理的 MPA，而非账号下全部 MPA。

### FR-3：兼容

仅带 `veadk:agent-type=mpa` 的 Runtime 隐藏。已有通用 Studio MPA 只要带 `veadk:managed=true`，即使没有新 provisioner 标签仍可见。缺少 `veadk:managed=true` 的历史一键 Runtime 在显式更新/重试写入标签前保持隐藏。禁止启发式 fallback。

### FR-4：安全与失败

来源过滤只控制发现范围。既有角色、owner、企业可见性、Runtime 授权和写操作检查继续作为权威。Tag 服务失败保持 fail-closed，不能回退到未过滤扫描。浏览器参数不能关闭 managed-MPA 强制过滤。

## 5. 设计与任务

- 新增一个内部 MPA Runtime 标签模块，统一分类、managed、provisioner、owner 和 MPA instance 标签常量；不新增公共 Python API。
- 通用 Studio MPA 部署增加 provisioner；现有 managed/owner/author/instance 标签不变。
- 仅当 Studio 路由显式提供可信 Runtime owner 时，才在托管式一键部署前把 owner 和来源标签对账到 Runtime template；任务/注册表 owner 继续使用哈希，CLI provisioning 不获得 Studio 来源。
- `_list_mpa_region` 始终添加 category 与 managed 正向过滤，owner 过滤继续叠加。
- `CloudRuntime`、缓存、分页 token、响应 payload 和前端渲染不变。

| 任务 | 工作 | 文件 |
| --- | --- | --- |
| `T-1` | 增加创建/列表来源过滤失败测试。 | `tests/cli/test_frontend_runtime_proxy.py`、`tests/cli/test_studio_rbac.py`、`tests/integrations/mpa_managed/` |
| `T-2` | 增加内部共享标签常量，并为通用 Studio MPA 增加 provisioner。 | `veadk/integrations/mpa/tags.py`、`veadk/cli/cli_frontend.py` |
| `T-3` | Studio 一键 MPA 增加 managed/provisioner/owner/instance，同时保留任务/注册表 owner 哈希，并排除 CLI provisioning。 | `frontend/server/mpa_creation.py`、`veadk/integrations/mpa/managed/tasks.py`、`runner.py`、`service.py`、`runtime.py` |
| `T-4` | 强制 Tag 服务过滤 Studio-managed MPA。 | `veadk/cli/cli_frontend.py` |
| `T-5` | 对齐文档/验证；仅当前端源码变化时重建 WebUI。 | PRD/spec 双语文件及必要生成资产 |

## 6. 验收与验证

| 需求 | 验收标准 | 验证 | 结果 |
| --- | --- | --- | --- |
| `FR-1` | `AC-1`：两条 Studio 创建路径写入精确 managed/provisioner/owner 与 MPA instance 标签；可信 owner 缺失时在云变更前失败；CLI provisioning 不写 Studio 来源。 | 检查 create/update 精确 tag payload、owner 缺失、owner 透传与 CLI 负向用例。 | `pass` — 创建/service/task 定向测试，2026-09-29 |
| `FR-2` | `AC-2`：MPA Tag 查询始终包含 category/managed；mine 还包含 owner。 | admin/all 和 owner/mine 路由测试。 | `pass` — Runtime 列表定向测试，2026-09-29 |
| `FR-3` | `AC-3`：仅 agent-type 的外部 MPA 不出现；managed 历史 Studio MPA 仍可见。 | 正向/负向分页 fixture。 | `pass` — Runtime 列表定向测试，2026-09-29 |
| `FR-4` | `AC-4`：失败保持 fail-closed，通用 Runtime 行为不变。 | Tag 失败/general category 回归。 | `pass` — 定向及仓库回归测试，2026-09-29 |

```bash
uv run --extra dev pytest -q tests/cli/test_frontend_runtime_proxy.py tests/cli/test_studio_rbac.py tests/integrations/mpa_managed
uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"
npm --prefix frontend test
npm --prefix frontend run build
uv run --extra dev pre-commit run --all-files
```

必须执行浏览器验证：使用本地 Studio 的只读 Runtime 发现，证明未打标的外部 MPA 不出现、managed MPA 正常出现、loading/error/empty 状态仍可区分，并且通用 Agent 发现不变。截图和原始 provider 响应不提交。后续经用户显式授权的一次性回填记录如下；该操作不会在产品中启用自动迁移行为。

2026-09-29 针对基线 `69dd24cd15b2372b76d1666246fc40fbac27235e` 未提交差异的验证记录：

- `pass`：最终 code review 后的 MPA 后端定向测试 — 506 passed、6 warnings。
- `pass`：最终 code review 后的仓库 Python 回归 — 6142 passed、18 skipped、2 xfailed、84 warnings；按上方仓库命令排除 smoke markers。
- `pass`：前端测试 — 1367 项 Node 测试和 39 项 Vitest 测试通过。
- `pass`：前端生产构建；只有既有 Vite chunk-size/dynamic-import 警告，且没有生成资产差异。
- `pass`：全部变更 Python/测试文件通过 Ruff 和格式检查；`git diff --check` 通过。
- `pass`：除 `cli_frontend.py` 外 6 个变更/新增聚焦后端模块通过 Pyright，0 errors。
- `fail`（既有基线）：对变更文件 `veadk/cli/cli_frontend.py` 直接运行 Pyright 报告 36 个既有错误，均不在本次新增行；本变更不扩展到无关类型清理。
- `pass`：仓库 pre-commit — Ruff、格式、硬编码密钥检测和具体 YAML 密钥检测全部通过。
- `pass`：两轮实现/spec 审查修正了 CLI 来源准入及原始 owner/哈希 owner 分离。第一次 code review 修复 3 个 medium finding：旧 pending create 先按原始 payload 精确重放再升级标签；非 NotFound 的 Runtime 补齐失败保持错误态而非空成功；任务 owner 必须匹配原始 Studio Runtime owner 的哈希。回填后的复审又修复 1 个 medium 跨地域补齐放大问题（在 `GetRuntime` 前按权威 Runtime TRN 过滤）和 1 个 low 验证记录歧义。无剩余阻断项。
- `pass`：已从本 worktree 重启本地 Studio；`/`、`/web/ui-config`、过滤后的 MPA 发现和通用 Runtime 发现均成功返回。在授权回填前，过滤后 MPA 响应包含 1 项，通用 Runtime 首页面包含 5 项；未持久化原始 provider 响应。
- `not_run`：真实浏览器只读发现验证，等待重启 Studio 后由用户在本机验收。
- `pass`：经显式授权的一次性标签回填 — 对北京地域 18 个真实存在、带 `veadk:agent-type=mpa` 且缺少 managed 标记的 Runtime 仅补写 `veadk:managed=true`；18 个写入全部成功，写后 managed 集合包含 19 个唯一真实 Runtime，逐项比较未发现其他标签变化。无法通过 `GetRuntime` 解析的跨地域重复标签映射未执行写入。
- `not_applicable`：Runtime 部署、镜像发布、环境变量修改和自动迁移。

## 7. 风险与交付记录

- 后续任何缺少 `veadk:managed=true` 的 MPA Runtime 仍会隐藏，直到显式更新/重试或再次获得授权的受控回填。这是有意的 fail-closed 行为。
- 特权外部运维可修改标签；标签是发现 metadata，不是授权。
- 服务端过滤保持分页正确，禁止浏览器后过滤。
- 2026-09-28：方案 1 已批准。实现、commit、push、PR、部署和云回填仍需分别授权。
- 2026-09-29：已在独立 worktree 完成实现、自动化验证和本地 API 验证；未执行 commit、push、PR、部署或回填。
- 2026-09-29：用户显式授权历史 MPA 标签回填。已对北京地域 18 个核验存在的 MPA Runtime 仅补写 `veadk:managed=true`；随后 Studio MPA 列表返回 19 个唯一实例。未执行 Runtime 部署、镜像/环境修改、commit、push 或 PR。
