# 技能空间描述使用手填 MPA 名称

[English](2026-10-09-entered-name-description.md)

- Change ID：`mpa-skill-space-description`；日期：2026-10-09；状态：implemented。
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-3/CON-4。

## 背景与范围

`managed/skills.py` 当前创建 `Description: Skills for MPA agent <agent_id>`。Studio 创建已将手填 Runtime 名称与自动生成内部 ID 分开。用户通过手填名称识别智能体时，难以辨认该描述。用户要求描述使用手填名称。

仅修改新建名称请求的技能空间描述。保持生成的 `mpa_skills_<scoped hash>` 名称、`display_name` 标签、ID、归属标签、数据库/渠道/Worker 绑定及内部 ID 生成不变。已有/显式配置空间复用，不更新。不涉及云资源改名、迁移、部署、提交或推送。通用智能体、UI、依赖与权限不变。

## 需求、场景与验收

- FR-1 / AC-1：新名称部署创建 `Description: Skills for MPA agent <trimmed runtime_name>`。沿用现有 Runtime 名称校验。不提供名称时保留原内部 ID 描述。
- FR-2 / AC-2：Runtime 部署将 `runtime_name` 传给技能空间准备。空间名称、标签及绑定继续由内部标识派生。已有空间不创建/更新，与传入的展示名称无关。
- FR-3 / AC-3：保留结果未知恢复，不盲目重复 CreateSkillSpace。升级前持久化请求仅在完整当前请求恢复为原内部 ID 描述后完全匹配时，才重放该请求用于发现和归属校验。其他未完成输入变化仍拒绝，包括新描述或项目变化。

场景：新名称请求描述可辨认；不提供名称的 CLI 保持原行为；已有空间不修改；旧/新请求丢失响应后准确发现且只创建一次；无法发现的丢失响应或改变未完成请求仍明确报错。

## 设计与受影响契约

为 `ensure_skill_space` 增加可选仅关键字参数 `runtime_name: str = ""`，非空时使用 `validate_runtime_name` 校验，由 `RuntimeDeployer.deploy` 传入。描述使用 `runtime_name or agent_id`。已有持久化 `skill_space_request` 包含完整恢复输入，不增加字段或数据库迁移。仅在完整旧描述候选匹配时允许旧版恢复。名称发现、归属验证、锁、取消、超时和资源清理保持不变。描述属于展示信息，不得作为归属键。

生产文件：`managed/skills.py`、`managed/runtime.py`。测试：`test_agent_deployment.py`、`test_service.py`。更新双语创建契约和 managed README。不修改前端、生成产物、外部 API 请求体或 Runtime 镜像。可选 Python 关键字兼容调用方。测试/证据不含凭证或真实用户数据。

## 任务与验证

1. T-1 / FR-1–FR-3：补充先失败回归，覆盖有/无名称描述、内部绑定稳定、名称校验、已有复用、旧/新丢失响应恢复及未完成输入变化拒绝。
2. T-2 / FR-1–FR-3：实现名称传入及完整旧描述恢复。
3. T-3：运行部署/服务目标测试、使用两个进程的 managed/CLI 回归、改动文件 Ruff/Pyright、pre-commit、双语/链接及空白检查；审查一致性并记录结果。

命令：`uv run --extra dev pytest tests/integrations/mpa_managed/test_agent_deployment.py tests/integrations/mpa_managed/test_runtime_deployment_edges.py tests/integrations/mpa_managed/test_service.py -n 2 -q`；`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`；改动文件 Ruff/Pyright；`uv run --extra dev pre-commit run --all-files`；`git diff --check`。

## 审查、批准与风险

用户要求描述中的内部 ID 改为手填名称，批准对前序命名修复的这一小范围扩展。`review-spec` 不可用；直接审查核对请求兼容、完整请求恢复、归属边界、错误及双语等价，无阻塞。旧/已有空间保留原描述；重启 Studio 后对新建请求生效。展示信息不代表云 ID 或唯一性保证。未授权真实云操作。本次仅后端展示元数据变化，前端/构建/浏览器/sidecar 检查不适用。

## 交付记录

T-1–T-3 和 AC-1–AC-3 已完成。直接实施审查确认描述不授权接管、完整旧请求比较保留连续结果未知恢复、已有空间不修改、改变未完成输入仍失败。此前所有未提交修改，包括镜像查询撤回和 Worker 名称修复，独立保留。

2026-10-09 测试范围：基于 `df797f94` 的未提交差异中四个 Python 文件及受影响的 managed/CLI 测试。

- `pass`：先失败回归在实施前复现 6 项失败（两项兼容/默认场景已通过）。
- `pass`：上述部署/边界/服务目标命令 182 项通过；最终 managed/CLI 命令使用两个进程，686 项通过，包含有/无名称创建、内部绑定不变、已有复用、非法名称及旧/新恢复。
- `pass`：四个改动 Python 文件的 Ruff 0.11.12 check/format；Pyright 零错误/警告。
- `pass`：`uv run --extra dev pre-commit run --all-files`，包含两项密钥检查；双语配对、契约标识及本地设计链接；`git diff --check`。
- `not_run`：全仓 Python 回归；针对本次有限元数据变更，选择受影响的 managed/CLI 覆盖。
- `not_run`：真实云创建/更新，未授权也未执行。控制台验证新的创建前应重启 Studio；此前创建的空间保留原描述。
- `not_applicable`：前端/浏览器/构建、sidecar 及运行时进程 smoke；没有修改这些契约或产物。

未执行提交、推送或部署。
