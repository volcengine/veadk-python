# Managed Agents 非 UI 改动合入

[English](2026-10-10-non-ui-migration.md)

变更 ID：`managed-agents-upstream`。创建/修订：2026-10-10。状态：implemented（本地迁移，未发布）。

## 背景与证据

来源仓库 `main` 的 `89a90e02` 与官方 VeADK `main` 的 `171d8d86` 从
`80e968d7` 分叉。直接比较完整代码树会覆盖官方 Codex、Studio、MPA 资源准备和
兼容性更新。来源的新增运行时位于 `examples/16_self_host_sandbox`，库逻辑通过
裸模块名导入示例代码，镜像依赖相邻 Managed Agents Anthropic SDK checkout。
目标已经拥有 `veadk/runtime/provider.py` 与 `veadk/integrations/mpa/managed`。

## 目标与非目标

在官方当前基线上交付来源全部非 UI 增量，包含包化运行时、兼容示例入口、隔离测试
和可复现镜像输入。来源只读。排除 UI、仅服务于 Studio 的后端路由和仓储、构建后的
网页资源、无关上游代码、个人部署记录和线上云资源修改。此范围不授权 commit、push
或创建 PR。

## 场景与需求

- `FR-1`：调用方不依赖示例目录即可导入循环与客户端；导入不需要凭据，不访问网络，
  不创建全局远程示例 Agent。
- `FR-2`：Worker 执行原生工具、Session 固定的 Skills/MCP 资源，保留来源的 Work
  轮询、租约/心跳、取消、跨 Worker 重放、凭据轮转、事件顺序和清理行为。
- `FR-3`：Ark 续接请求保留工具声明；默认使用服务端保留期，保留显式过期参数，
  仅在开启时记录安全的元数据跟踪。
- `FR-4`：Runtime Identity 支持显式凭据池查询与 Session 级模型/MCP 凭据；
  Skills 操作保持受限的账号作用域。
- `FR-5`：飞书流式配置默认关闭，保留官方优雅关闭与应用事件循环生命周期。
- `FR-6`：非 UI 构建、示例与测试脚本使用安装的库；镜像默认使用公共包源，保留
  锁定哈希，不依赖固定镜像仓库或本地 SDK checkout，SDK 缺少所需能力时提前失败。
  镜像发布与线上云 E2E 属于独立操作。

## 设计与契约影响

依赖方向为运行时 → MPA Session 集成 → Anthropic/AgentKit SDK。
`veadk/runtime/managed_agents` 负责 Worker、循环、原生工具、事件跟踪、Identity
适配与健康入口；`veadk/integrations/mpa/session_client.py` 和
`session_resources.py` 负责协议客户端与 Session 资源快照。复用现有 MPA 资源准备，
其 `managed/worker.py` 是沙箱资源创建，不能混同于模型 Work 执行。
保持现有 RuntimeProvider。示例兼容包装导入包实现；示例启动器可加载本地环境，
库导入不能加载。部署专属 ID 和默认值改为必填配置。模型、Skills、IdentityClient
和飞书扩展保持原有目录归属。

状态和事件格式保持来源契约，不引入后端 schema 或云资源迁移。取消必须关闭 Runner、
工具及临时 Skill 目录；终态重放不能重复执行已完成输入。凭据只作为运行时输入，
不写入文档、镜像、跟踪或 Git；错误报告保持脱敏。Python 3.10-3.13 的导入必须使用
兼容的 datetime 与 asyncio 原语。

组件契约：[运行时](../../../specs/managed-agent-runtime/README.zh.md)、
[资源](../../../specs/managed-agent-resources/README.zh.md)、
[飞书](../../../specs/feishu-channel/README.zh.md)。

## 任务与职责

| 任务 | 需求 | 文件 / 负责人 |
| --- | --- | --- |
| `T-1` | `FR-1`、`FR-2` | Runtime/Session 包、运行时测试、示例 Python 包装：runtime agent |
| `T-2` | `FR-3`、`FR-4` | Ark、IdentityClient、Skills 客户端、模型/资源测试：model/skills agent |
| `T-3` | `FR-5` | 飞书扩展、渠道测试、双语用户文档：channel agent |
| `T-4` | `FR-6` | Docker、依赖/锁文件、非 UI 脚本、示例文档：root agent |
| `T-5` | 全部 | 集成、回归、打包、密钥扫描、文档同步：root agent |

文件写入范围互不重叠。并行期间不操作共享 Git index 或提交；root 统一依赖并执行
最终检查。

## 验证与验收

| 需求 | 验收 | 验证 | 状态 |
| --- | --- | --- | --- |
| `FR-1`、`FR-2` | `AC-1`：可安装且生命周期等价 | Runtime/Session 定向测试与真实 SDK transport/原生工具 | pass；包含在最终 387 项定向测试中 |
| `FR-3`、`FR-4` | `AC-2`：保留官方行为并加入资源/模型增量 | 模型/Identity/Skills 测试 | pass；首轮 109 项，纳入最终定向回归 |
| `FR-5` | `AC-3`：流式与关闭测试通过 | 渠道测试 | pass；18 项，纳入最终定向回归 |
| 全部 | `AC-4`：集成回归和仓库检查 | 并行回归与全文件/变更文件 pre-commit | 范围内回归 pass；无排除的检查有 7 个已复现官方 UI 失败，见下文 |
| `FR-6` | `AC-5`：wheel/导入/CLI/构建输入检查 | wheel/导入/CLI、shell 语法、镜像构建与容器检查 | pass；仅本地镜像 |

测试使用模拟服务与临时状态。线上云/模型 E2E 和镜像发布为 not_run，超出本次本地
迁移授权。UI 检查为 not_applicable，因为 UI 和 Studio 后端修改均排除。

## 风险与恢复

来源的 EnvironmentWorkDispatcher 需要普通 Anthropic 安装没有的 Managed Agents
SDK 能力。必须检查 SDK 能力并实现明确的受支持集成，不能虚报 Worker 就绪。
交付记录区分模拟运行时测试、安装包导入、镜像构建与真实云 E2E。原来源和官方基线
保留完整；放弃新分支即可恢复到基线。

## 审查与交付记录

用户以“ok, just do it, do it best”批准架构与非 UI 范围，并明确授权多个 subagent。
直接设计审查已解决：使用官方基线、保留 MPA 与运行时接口、排除 UI 后端接线、明确
SDK 要求、禁止导入时访问凭据、保持 Python 3.10 兼容、验证异步清理。
未安装 `review-spec` skill，因此采用仓库要求的等价直接审查。组件负责人在生产代码
修改前审查双语契约。非 UI 范围内的 `T-1` 至 `T-5` 均完成。

### 来源与目标核对

| 来源 | 交付位置 / 决策 |
| --- | --- |
| `main.py`、`managed_agent_loop.py`、`event_debug.py`、`runtime_identity.py` | `veadk/runtime/managed_agents/{worker,loop,events,identity}.py` |
| 示例 Agent/Session 生命周期 | 包内 `sandbox.py`；示例发现工厂保留薄包装 |
| `sandbox_client.py`、`managed_session_resources.py` | `veadk/integrations/mpa/{session_client,session_resources}.py` |
| 缺失的私有 SDK dispatcher | 基于公开 SDK 的包内 dispatcher，具备真实协议测试 |
| Ark/Identity/Skills/飞书 | 保持原 SDK 模块归属，新增独立 `veadk/skills/ma_infra.py` |
| Worker/Runtime 启动与 claimed Tool 入口 | `docker/managed-agents/`、安装包入口、`/opt/gem/run.sh` 与示例薄启动器 |
| 对话/分布式/Kubernetes/压测/故障检查 | 可移植示例脚本及包化 Runtime/Session/completion-gate 测试 |
| 个人 rollout/build-candidate、RDS 和外部 ma-server/task-server 部署 | 以公共 Worker 构建及通用 Kubernetes 模板替代，不复制部署专属状态 |
| UI、Studio 专用 Skills 仓储/路由、UI 网关镜像与构建资源 | 按批准范围排除 |
| 历史部署证明与一次性分析文档 | 不作为当前证据复制；本设计记录新执行的本地验证 |

### 验证记录（2026-10-10）

验证范围是基于官方 `171d8d86` 的未提交功能 diff，包含新增包文件。锁定版本、哈希
与无关平台 marker 均保留，只将 sandbox 的 Anthropic 下限从 `>=0.40.0` 改为来源
实现所需的 `>=1.3.0`。

- **pass**：Python 3.12 最终定向回归 387 项，包含真实 SDK HTTP、原生文件/bash、
  MCP、跨 Worker 权威历史重放、清理与进程监督。
- **pass**：Python 3.10.20 独立冻结环境 356 项定向测试，加真实 SDK transient
  发布测试；已用 `typing.Dict` 修复 SDK generic-alias cast 兼容问题，没有用 mock
  掩盖不受支持的生产导入。
- **pass**：`MODEL_AGENT_API_KEY=offline-regression-test-key .venv/bin/python -m
  pytest -n 4 -m "not codex_smoke and not piagent_smoke" -q --tb=short`，显式排除
  下述 7 个基线失败后：6963 passed、42 skipped、4 xfailed、6 subtests passed。
  最终大规模回归选用 4 个 worker；首次默认 2-worker 回归暴露测试环境与基线问题。
- **fail，官方基线**：无排除回归中的 7 个
  `tests/frontend/test_migration_delivery_recovery.py` 用例，在同依赖的未修改官方
  worktree 也失败，分别是：
  `test_mirror_delivery_writes_the_documents_the_cli_would_have_written`、
  `test_mirror_delivery_keeps_the_sequence_the_cli_already_started`、
  `test_mirror_delivery_refuses_a_delivery_the_cli_already_settled`、
  `test_verification_mirrors_the_cli_finding_projection`、
  `test_an_unparseable_findings_file_reports_no_findings_at_all`、
  `test_a_startup_fallback_degrades_the_delivery`、
  `test_a_rebuild_that_lands_settles_the_task_on_the_cli_delivery_contract`。
  范围内回归逐项使用 `--deselect <file>::<name>`，未修改 marker、生产 UI 代码或
  断言来掩盖失败。
- 首次无排除回归还暴露既有示例/Harness 测试依赖无关示例测试在导入时偷偷设置的
  模型 Key。新测试不再在收集时修改全局凭据；最终命令明确提供离线 fixture Key。
  测试包命名也已避免与 Studio scheduler 的 `test_dispatcher` 冲突。
- **pass**：全文件与变更文件 pre-commit（Ruff check/format、gitleaks、YAML 密钥
  扫描）、`git diff --check`、双语 Markdown 链接和无 UI 改动范围检查。
- **pass**：`uv build --wheel`；在临时目录和清理后的环境中导入解压安装包并执行
  CLI help，不依赖示例路径。
- **pass**：`npm --prefix docs run types:check` 和 `npm --prefix docs run build`。
  依赖安装使用仓库冻结的 pnpm lock；生成的 workspace policy 与 Corepack 意外修改
  的父目录配置均已从功能范围中撤销。
- **pass**：本地 `veadk-managed-agents-worker:upstream-local` 镜像通过公共包源和锁定
  sandbox 依赖构建；网络/proxy 设置只用于本地构建。专用 Worker 不安装可选集成、
  开发或 Codex extras，不使用相邻 SDK wheel。
- **pass**：禁用网络、只读文件系统、UID 10001 的容器内验证 SDK 导入/CLI 与
  `/opt/gem/run.sh`；同样隔离的安装包健康服务 `/ping` 返回 HTTP 200。这些检查
  不执行真实 Work 网关、模型提供方或 AgentKit 部署。
- **not_run**：真实云/模型 E2E、镜像发布、Git commit/push 和 PR 创建。镜像仅在
  本地，分支跟踪 `volcengine/main`，原来源 worktree 保持干净。

### 审查修复

独立审查解决了：导入时访问凭据、失败轮次错误完成及泄漏错误文本、Skill 工作区
冲突/符号链接清理、清理失败后仍关闭全部工具、Work 租约栅栏/Session FIFO/凭据
刷新、首次合法轮询就绪、Python 3.10 cast、含凭据的包源参数、分布式脚本过时的
数据库假设与独立命名 BuildKit 缓存。claimed Tool 保留历史启动路径，并在部署的
OS 隔离中默认本地执行工具。
