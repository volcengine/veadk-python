# AIO 沙箱 Skill 与基础工具

[English](2026-10-26-aio-sandbox-skills.md)

变更 ID：`aio-sandbox-skills` · 日期：2026-10-26 · 状态：implemented，全仓回归限制见下文。

## 背景与范围

VeADK 的 `aio_sandbox` 分支此前不返回工具，Skill 初始化仍在 Runtime 宿主机解析来源。目标是保留 `Agent(skills_mode="aio_sandbox", skills=[...])` 和现有 `SkillsToolset`，由 Runtime 推理，沙箱提供 Skill 文件、命令执行及文件操作。不新增 Agent 字段或执行模式值。HTTP App/Session 接口、Skill 安装、其他运行时及额外发现接口不在范围内。

## 需求与设计

- **FR-1 — 使用入口：** 空 `skills` 也挂载 `SkillsToolset`。AIO 模式下，`skills` 为沙箱内绝对目录，空列表使用沙箱默认目录。构造时不读取宿主机 Skill 文件或加载云端 SkillSpace 来源。`local` 和 `skills_sandbox` 行为保持不变；使用 SkillSpace ID 的 AIO 调用方需改为沙箱目录。
- **FR-2 — Session 绑定：** 推理前，按 ADK app/user/session 身份创建或复用 AgentKit 沙箱。ADK state 仅保存 tool/session 标识和身份摘要。后续对话复用同一沙箱；过期或非 Ready 绑定直接失败，不更换实例、不回退本地。应用负责实例生命周期，闲置实例按 TTL 过期。
- **FR-3 — Skill 加载：** 通过 `GET /v1/skills` 获取名称、描述和说明文件路径；多个目录使用重复 `path` 参数。通过沙箱文件 API 按需读取说明。工具描述和闭包归属执行上下文，不修改共享 Agent instruction，不共用其他 Session 的 Skill 目录视图。
- **FR-4 — 基础工具：** `skills_tool`、`bash_tool`、`read_file_tool`、`write_file_tool`、`edit_file_tool` 均访问同一沙箱。保留已有工具名称及模型可见参数。读取保留行号；编辑要求唯一匹配，除非显式全部替换。调用方额外传入的自定义工具仍由调用方负责。
- **FR-5 — 失败与隔离：** 不将宿主机环境传入命令。保留 endpoint 查询参数及已有认证；凭据不进入 Session state 或诊断信息。拒绝失败/格式错误响应及重定向。Bash 使用有限超时、输出上限，中断时远端 kill/close，清理失败明确可见。不自动重试写操作。同一 ADK Session 的并发 turn 由应用串行化。

组件契约影响仅涉及上述 Agent Skill 初始化和 AIO 工具集分支，不修改 Studio、模型配置或 HTTP API 契约。实现复用已有 lease 解析器，增加小型数据面 helper，不使用 monkey patch 或新增后端继承体系。

## 任务与验收

| 需求 | 任务 | 验收标准 | 结果 |
| --- | --- | --- | --- |
| FR-1 | T-1：调整 Agent 初始化和模式分派 | AC-1：空 skills 也挂载 AIO，不加载宿主机/云端 Skill 来源 | pass |
| FR-2/3 | T-2：实现 Session 绑定和远端发现/加载 | AC-2：目录视图隔离、多个目录、按需读取说明、多轮绑定稳定 | pass |
| FR-4/5 | T-3：转发工具并处理失败/清理 | AC-3：远端文件往返、编辑语义、超时/取消、安全传输错误及不回退本地 | pass |
| FR-1–5 | T-4：执行已授权真实验收 | AC-4：新 Session 使用 `doubao-seed-evolving` 调用 bash，返回配置的 `AGENTKIT_TOOL_ID`；宿主机专有环境变量不存在；五个工具均执行成功 | pass |

影响文件：`veadk/agent.py`、`veadk/skills/check_skills_callback.py`、`veadk/tools/skills_tools/skills_toolset.py`、`veadk/tools/skills_tools/aio_sandbox.py`、`tests/skills/test_aio_sandbox_skills.py` 及双语 Skills 用户文档。

## 评审与验证

用户已确认模式/工具集方案，并授权真实模型和沙箱验收。直接评审覆盖 Session 隔离、兼容性、取消、清理及凭据处理；无可用 `review-spec` 技能。中英文文档的需求及结果一致。用户已授权提交、推送和创建 PR，不包含部署。

验证日期：2026-10-26；范围：`feat/newapi` 工作区差异，已变基到 `upstream/main` 的 `23014771`。

| 检查 | 命令或过程 | 结果 |
| --- | --- | --- |
| 相关 Python 测试 | `uv run --extra dev pytest tests/skills tests/tools/test_skills_bash_tool.py tests/tools/test_skills_session_path.py tests/agents -q` | pass：153 个测试 |
| 真实验收 | 新 ADK Session、`doubao-seed-evolving`、实际工具调用返回值 | pass：Tool ID 一致，宿主机环境隔离，文件写/读/改、Skill 加载及沙箱复用均验证；临时验收文件已清理 |
| Lint、凭据与空白检查 | `uv run --extra dev pre-commit run --all-files`；`git diff --check` | pass |
| 用户文档 | `npm --prefix docs run types:check`；`npm --prefix docs run build` | pass |
| 全仓回归 | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" --maxfail=3` | fail（变基前，基线 `c662cc8d`）：停止前 3409 通过、8 跳过、6 失败；3 个迁移交付测试缺少 `zip`，3 个 Harness 资源测试缺少 `llama_index` |

## 限制与风险

定向及真实验收通过，全仓回归未全绿。本功能未安装缺失的可执行程序/可选依赖。传输失败时远端写操作可能已完成，因此不自动重试。沙箱须提供工具集使用的 Skill、文件和 Bash API。不新增依赖或修改无关组件。
