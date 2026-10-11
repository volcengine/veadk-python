# MPA A2A 最终回答所有权

[English](2026-09-22-mpa-a2a-final.md)

- 日期：2026-09-22
- ID：`mpa-a2a-final`
- 状态：已实现；本地服务生效待完成
- 组件：[Runtime 诊断 CON-8](../../../specs/studio-runtime-diagnostics/README.zh.md)、[Studio 工具活动](../../../specs/studio-tool-activity/README.zh.md)

## 证据与背景

只读检查用户已完成的 v7 A2A 任务，发现 sandbox artifact 包含 57 个推理增量、14 个答案增量、1 个用量更新，以及 1 个 payload 包含 `finalMessage` 的 `invocation.completed`。答案增量拼接后与 finalMessage 哈希相同，另一个 artifact 保存外层 function response。恢复的会话只有一份最终答案。测试数据不保留凭据、原任务标识或私有事件原文。

`runtime_a2a_stream._sandbox_event` 忽略了 `finalMessage`；沙箱增量携带 invocationId，外层结果没有，所以前端把两份答案放入不同累加器。前几次针对 delegate 工具活动、原生 MPA 会话包装响应的修复没有覆盖这条 A2A 桥接链路。

## 目标、非目标与需求

- **FR-1：** 把非空的 sandbox `invocation.completed.payload.finalMessage` 投影为权威合并完成答案，保留 sandbox invocation 标识。
- **FR-2：** 成功答案投影后，抑制同一个已知 A2A 任务后续的外层文本/推理/结果副本，保留沙箱工具事件、错误和用量统计。不比较任意答案文本，不影响普通 ADK/原生会话路径。
- **FR-3：** 同一任务中已标识的 sandbox 源事件，在流式更新和任务快照间最多投影一次。其他任务及非 MPA 的旧 A2A 流保持原有行为。
- **FR-4：** 失败/取消的调用以及空 final 不得取得答案所有权。没有 sandbox final 的流保持原有回退行为。已合并的 sandbox 答案不得在流结束时再次合成答案。

非目标：鉴权/部署变更、修复独立的临时发现错误、改变 worker 生成、隐藏任意推理、修改已存任务数据。

## 设计与涉及文件

在 `veadk/cli/runtime_a2a_stream.py` 增加成功 sandbox final 投影，并按 A2A 任务 ID 在 decoder 内跟踪所有权。按任务跟踪已投影的 sandbox 事件 ID，处理重放，同时不把可追加的外层 artifact ID 视作不可变事件。仅在取得所有权后过滤外层投影文本；仅含 metadata 的用量/状态继续通过。状态仅存在于本次请求 decoder，取消或断连后正常销毁，不改变既有流边界和网络超时。

`tests/cli/test_runtime_a2a_stream.py` 按已观察到的沙箱增量/final 加外层结果结构建模。脱敏的 Python 到 TypeScript 投影回放检验真实前端累加器。更新双语组件契约；只有前端生产代码变更时才需要前端发布资产。

## 任务、测试与验收

- **T-1 / AC-1：** 先写失败用例，证明沙箱 final 缺失且外层重复结果仍存在；最终必须只有一份权威答案。
- **T-2 / AC-2：** 覆盖迟到外层推理、相同/不同文本副本、sandbox final/任务快照重放、任务隔离、工具/用量保留、空 final、失败/取消和旧 A2A 回退。
- **T-3 / AC-3：** 执行定向 Python 桥接/代理测试、修改 Python 文件的 Ruff/Pyright、跨层/浏览器回放及相关前端回归，记录真实门禁与剩余线上验证限制。

## 评审与授权

用户在发现接口恢复后明确要求继续修复原重复问题。本次基于已核验任务证据实现已有范围。直接设计评审（review-spec 不可用）确认不改变公共请求 schema 或云端状态，预期变更为 A2A 投影契约。仅成功非空 final 取得答案所有权。风险：委派结束后外层模型的改写将被有意省略。任务需要先发 sandbox final 再发外层副本，符合已检查 executor 实现；缺失标识时不能安全地建立跨事件所有权。

## 验证

- **pass：** 只读任务结构检查，没有新执行智能体。
- **pass：** 实现前 3 个新增回归用例失败，32 个已有/负向用例通过。
- **pass：** `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q`：121 项通过，有 5 条已有 SDK 弃用警告。
- **pass：** 两个修改 Python 文件的 Ruff 0.11.12 检查、格式检查及 Pyright（零错误/警告）。仓库环境缺少独立 Ruff/Pyright 可执行文件，通过 `uv run --with ruff==0.11.12 ...` 和 `uv run --with pyright ...` 临时提供工具，没有修改项目依赖或全局配置。
- **pass：** 使用已观察协议结构和占位文本的 Python 到 TypeScript 回放：HEAD 桥接产生两个 Turn、两个答案块，修复后一个 Turn、一个答案块。真实浏览器使用生产 `eventsToTurns` 和 `Blocks` 验证了该差异，控制台无错误。该构造数据并非完整 SSE 抓包。
- **pass：** 相关前端投影/活动回归 70 项通过；`git diff --check`、双语文档与链接检查通过。临时浏览器页面及 Vite 服务已移除。
- **pass：** 仓库 pre-commit `gitleaks` hook 检查本次跟进修改的代码/文档，未检测到硬编码密钥。
- **blocked：** 进一步完整原任务回放查询遭遇间歇 HTTP 429/500，之前成功的只读任务结构/哈希证据见上文，没有触发新生成。
- **not_run：** 用户本地 Studio 需要重启才能加载修复。A2A 任务/会话映射当前保存在进程内，重启会清空本地历史索引，但不会删除远端任务。在这一中断性操作前等待用户同意。未云部署、提交或推送。
- **not_applicable：** 前端构建/IME/布局/网络生命周期变更：本次跟进仅修改 Python 投影，保留之前的前端构建资产。未跑无关 Python 全量套件，相关桥接和 Runtime 代理套件覆盖本次改动。

2026-09-22 实现评审确认成功 final 按任务取得所有权、重放标识隔离、旧 payload 回退以及用量/工具保留。T-1–T-3 与 AC-1–AC-3 在已记录回归和回放范围内通过，生产生效仍待完成。

> 宽泛过滤规则由[保留补充内容](2026-09-22-preserve-followup-content.zh.md)替代。下文历史验证描述的是此前行为。
