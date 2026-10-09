# 新 MPA 沙箱模板使用手填 Runtime 名称

[English](2026-10-09-runtime-named-worker.md)

- Change ID：`runtime-named-worker`；创建/修订：2026-10-09；状态：implemented。
- 契约：[Studio MPA 创建 CON-3](../../../specs/studio-mpa-creation/README.zh.md)。
- 前序：[从智能体 ID 派生 Worker 名称](2026-09-28-agent-derived-worker-name.zh.md)。

## 背景、目标与非目标

Studio 名称创建将自动生成的智能体 ID 与手填 Runtime 名称分开。`service.provision` 将名称传给 Runtime 部署，却没有传给 `ensure_worker`，所以沙箱模板仍显示将连字符替换为下划线的内部 ID。用户取消了内部 ID 改造，只要求新模板名称与手填名称一致。

保持内部 ID 生成、归属、数据库/技能空间/渠道绑定、Runtime 名称、镜像默认值、列表搜索及三步表单不变。未授权云资源改名、任务/数据库修改、凭证变更、部署、提交或推送。通用智能体及不提供名称的旧 CLI 调用不变。

## 需求与场景

- FR-1 / AC-1：新的名称创建请求创建/发现 Worker 时，使用经过校验、去除首尾空白的 Runtime 名称，保留大小写、连字符和下划线。沿用 4–64 位 ASCII 名称合同；非法名称在 Worker 云调用前失败。[官方 CreateTool 合同](https://docs.volcengine.com/docs/agentkit/CreateTool_-_Creates_tool?lang=zh) 支持相同字符和长度。
- FR-2 / AC-2：服务将名称传给 Worker 准备；`MPA_AGENT_ID`、作用域归属标签、注册库键及 Runtime `ToolId` 仍使用原标识。不提供名称的旧调用仍使用标准化的智能体 ID。
- FR-3 / AC-3：已绑定/显式配置的 Worker ID 优先，不进行改名。升级前未完成的 Worker 意图仅在完整候选请求与已存 hash 一致时，才可重放标准化 ID 名称或更早的哈希名称，保留原 ClientToken。其他请求变化在发现/创建前失败。
- FR-4 / AC-4：新的未完成意图在已有部署 JSON 中保存选中的 `worker_name`。后续不同名称不得被视为旧版兼容回退。同名但属于其他智能体的资源仍报错，不静默接管或视为成功。

给定新的名称请求，模板名称与 Runtime 名称一致，内部绑定稳定。给定创建响应丢失或升级，重试完整原请求/token。给定已登记 Worker，不发现/创建/改名。给定无关同名资源或镜像变化，不降低归属检查并直接失败。

## 设计、契约与影响文件

为 `ensure_worker` 增加可选仅关键字参数 `runtime_name`，由 `service.provision` 传入。使用现有 Runtime 名称校验器校验，并直接作为新 CreateTool `Name`。已有 ID 跳过命名协调。新意图保存时持久化非密钥字段 `worker_name`。旧记录没有该字段时，对两种历史 Name 分别计算完整当前请求的 hash，仅完全匹配才允许回退；重试时仍不补写该字段，确保连续丢失响应时继续重放原名称。名称本身不授权复用。账号锁、重试次数、超时/取消及元数据验证保持不变。

生产文件：`managed/worker.py`、`managed/service.py`。测试：`test_worker.py`、`test_service.py`。维护双语创建契约及 managed README 命名段落。不需要 SQL 迁移、外部 API/请求体变更、新依赖、权限或前端/构建产物修改。公开可选关键字参数兼容现有调用。搜索已使用 Runtime `name`，行为不变。用户名称可能冲突；保留现有冲突拒绝，不添加未要求的后缀。

## 任务、验收与验证

1. T-1 / FR-1–FR-4：补充先失败回归，覆盖准确名称、边界、服务透传、未完成重放、名称/镜像变化拒绝、同名冲突拒绝和已有 ID 复用。
2. T-2 / FR-1–FR-4：实现可选名称和完整 hash 的旧版兼容。
3. T-3：同步双语文档；运行 Worker/服务目标测试、managed/CLI 回归、改动文件 Ruff/Pyright、pre-commit 及空白/链接检查。

命令：`uv run --extra dev pytest tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_service.py -n 2 -q`；`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`；改动 Python 文件 Ruff/Pyright；`uv run --extra dev pre-commit run --all-files`；`git diff --check`。真实云创建未授权，单独报告。前端/浏览器/sidecar 检查不适用，本次只修改托管创建，无 UI 或 sidecar 变化。

## 审查、批准与风险

用户最终要求“保持原样吧，但是把沙箱模板的名称也换成手填的就行”，批准此范围，并取代尚未修改代码的内部 ID 方案。`review-spec` 不可用；直接审查核对归属、hash/token 恢复、已有 ID、准确名称约束、取消/超时、双语等价和可测试性，无设计阻塞。已有同名 Tool 可能使新请求失败。已有模板继续保留旧名称，修正须另行授权。若回滚后要重放新的名称意图，需要此版本代码。

## 交付证据

T-1–T-3 与 AC-1–AC-4 已完成。交付前直接实施审查发现并修复了旧任务连续重试的问题。之前未提交的镜像查询撤回独立保留，其测试/构建产物不归属于本次命名修复。测试范围：基于 `df797f94` 的未提交差异中四个 Python 文件及受影响的 managed/CLI 测试，执行日期 2026-10-09。

- `pass`：先失败回归中，新名称测试最初 16 项失败；随后旧任务连续重试回归在修复前 2 项失败。
- `pass`：Worker/恢复/服务目标测试 175 项；最终 managed/CLI 回归使用两个进程，678 项通过，包含旧任务连续重试和已有 ID 复用。
- `pass`：四个改动 Python 文件的 Ruff 0.11.12 check/format；Pyright 零错误/警告。
- `pass`：`uv run --extra dev pre-commit run --all-files`，包含两项密钥检查；`git diff --check`；双语配对及本地链接检查。
- `not_run`：全仓 Python 回归；针对本次有限的创建流程变更，选择受影响的 managed/CLI 集成覆盖。
- `not_run`：真实云创建/改名，未授权。创建新的名称请求前，应重启正在运行的 Studio 服务加载改动。
- `not_applicable`：前端/浏览器/构建、sidecar 和运行时进程 smoke；本次修复没有 UI、生成产物、sidecar 或运行时进程变更。

未执行提交、推送、部署或已有资源改名。
