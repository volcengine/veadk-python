# Studio Codex 最终回答所有权

[English](2026-09-22-studio-codex-commentary-dedup.md)

- ID：`studio-codex-commentary-dedup`
- 创建/修订：2026-09-22
- 状态：superseded
- 组件：[Studio 工具活动](../../../specs/studio-tool-activity/README.zh.md)

## 背景与证据

**证据更正（2026-09-22）：** 下述诊断在缺少用户原始事件时假设了 delegate 工具链路。原生 MPA 使用自身的会话 SSE 端点，因此本次尝试不能证明已修复用户报告的 MPA 会话。参见[原生 MPA 跟进修复](2026-09-22-mpa-wrapper-preview.zh.md)。此前构造事件的检查结果仅对所测事件格式有效。

旧 `arkclaw-team -> mpa-agent` 链路为委派的 Codex 结果指定唯一的最终回答所有者。`mpa-agent` 会标记已完成的 sandbox invocation、阻止顶层模型继续输出文本，并从 SSE/历史中过滤重复模型文本。当前 `Studio -> agentkit-mpa-agent` 链路改用动态注入的 `delegate_to_codex_sandbox` 工具。VeADK 已为成功工具结果设置 `skip_summarization`，但 Studio 会保留一条可见的 Codex commentary，同时又把 function response 的 `message` 追加为最终回答。

已复现的 Turn 在工具活动前后各出现一次完全相同的完整回答。第一份来自 commentary activity，第二份是权威直接回答。现有 final event 过滤会移除嵌套的 `assistant_final`，但会刻意保留 commentary，因此未覆盖该场景。

首版精确匹配修复仍不足以覆盖真实链路。Codex 还可能输出包含完整最终回答的已完成 reasoning，外层模型也可能在成功 function response 后继续输出 reasoning 和答案文本。旧链路把委派响应作为该 Turn 的最终回答所有者；Studio 需要补齐相同的所有权边界，而不是只比较一条 commentary。

## 目标与非目标

### 目标

- Codex 委派成功后只展示一个权威最终回答，包括 activity reasoning 含有该回答或外层模型继续输出文本的情况。
- 对实时 progress 和持久化 `codex_activity` 重放使用相同规则。
- 保留命令、搜索、文件修改、失败、不重复最终回答的不同 activity，以及最终回答。

### 非目标

- 修改 Codex 生成、app-server 事件 schema、Studio Channel 传输或 `agentkit-mpa-agent`。
- 进行模糊、语义或跨 Turn 去重。
- 隐藏独立包含相同文字的命令输出。
- 修改普通聊天 Turn 或 `delegate_to_codex_sandbox` 以外的工具调用。

## 场景

1. commentary 内容为 `结果`，随后有工具活动，成功响应 message 也是 `结果`：Studio 删除该 commentary，只渲染一次最终 `结果`。
2. 已完成的 Codex reasoning 包含完整 `结果`：Studio 省略这条冗余 reasoning，同时保留相邻命令和搜索。
3. 成功 Codex function response 后外层模型继续输出 reasoning 和答案：Studio 保留委派响应，忽略同一 Turn 后续的模型文本 part。
4. commentary 为 `正在检查技能`，最终响应为 `结果`：两者都保持可见。
5. 通用智能体执行普通聊天或其他工具：reasoning 和答案投影保持不变；如果通用智能体明确调用 `delegate_to_codex_sandbox`，则使用相同的工具范围最终所有权规则。
6. failed 或 busy Codex 响应携带 message：保持既有行为，不合成直接回答。

## 需求与设计

- **FR-1 — 委派最终回答所有权。** 成功的 `delegate_to_codex_sandbox` 响应提供非空 `message` 后，该响应拥有当前 assistant Turn 的最终回答。完成投影后，忽略同一 Turn 后续的外层模型文本和 thought part。
- **FR-2 — 调用范围内 activity 对账。** 匹配工具完成 activity snapshot hydration 后，如果 commentary 或 reasoning 去除首尾空白后的文本逐字包含去除首尾空白后的完整最终回答，则省略该 block。不得使用模糊或语义匹配。
- **FR-3 — 保留结构化和无关活动。** 保留命令、搜索、文件修改、计划、授权、失败，以及不包含完整最终回答的 activity 文本。不得对命令输出使用该规则，也不得修改另一个工具 block。
- **FR-4 — 工具范围。** 只有存在成功 `delegate_to_codex_sandbox` 结果时才应用最终所有权。无论智能体类别如何，普通模型聊天和其他工具均保持既有投影行为。
- **FR-5 — 实时/历史一致和幂等。** 对实时 progress 加 response hydration 与持久化历史使用相同对账规则。重放响应或收到外层模型后续答案时仍只产生一个最终回答。

实现在 `frontend/src/ui/builtin-tools/codexSandboxProgress.ts` 使用纯 activity 转换，并在 `frontend/src/blocks.ts` 匹配到 Codex function response 后、追加权威回答前调用。Turn projector 仅从已完成且成功的 Codex 工具响应推导最终所有权，并在继续处理结构化事件的同时抑制后续非结构化模型文本/thought part。没有活动变化时返回原 activity 对象。

本次修改维护中的 `studio-tool-activity` transcript 契约，因此同步更新组件规范双语版本。不修改传输、后端、持久化、鉴权或公开 API 契约。

## 影响文件与任务

- `frontend/src/ui/builtin-tools/codexSandboxProgress.ts`：增加调用局部的纯去重 helper。
- `frontend/src/blocks.ts`：在响应 hydration 后、最终回答投影前执行去重。
- `frontend/tests/codexSandboxProgress.test.mjs`：增加 commentary 相同和不同的回归覆盖。
- `specs/studio-tool-activity/README.md` 和 `README.zh.md`：记录最终回答所有权规则。
- `veadk/webui`：重新生成前端打包资产。`.gitattributes` 将已有的生成 JavaScript 空白例外同步应用于 `website-integration.js`，保留打包模板字符串中有语义的空白。

| 任务 | 需求 | 验收 |
| --- | --- | --- |
| T-1：增加失败的投影测试 | FR-1–FR-5 | 用户报告的 commentary/reasoning/后续答案顺序可复现重复；无关工具 fixture 保持普通文本 |
| T-2：实现工具范围最终所有权 | FR-1–FR-5 | 回归通过，且不改变结构化活动或普通聊天 |
| T-3：验证并核对双语文档 | 全部 | 记录定向测试、完整前端测试、TypeScript/build、资产、i18n 和 diff 检查 |

## 测试

- 定向：`node --test frontend/tests/codexSandboxProgress.test.mjs`。
- 前端回归：`npm --prefix frontend test`。
- 构建和生成资产：`npm --prefix frontend run build` 和 `npm --prefix frontend run test:webui-assets`。
- 国际化：`npm --prefix frontend run check:i18n`。
- 真实浏览器：复现包含相同 commentary/final 文本的 Codex Turn，确认回答仅一次、工具活动保留、刷新后重放一致，并验证不同 commentary。

## 风险

- 较短的最终回答可能出现在更长 reasoning 内。由于同一次成功委派已提供用户可见答案，省略该已完成 reasoning 是可接受行为；结构化执行证据仍然保留。
- 去除边界空白后逐字包含可以覆盖报告中的自我对话，同时避免语义比较或 Markdown 归一化。
- 若广泛抑制后续模型文本，可能影响无关 Turn。因此所有权只从当前 accumulator 内成功的 Codex 工具响应推导，不跨 Turn、Session 或其他工具。

## 验收标准

- AC-1：已复现的 `commentary -> 包含答案的 reasoning -> 工具 -> 成功响应 -> 外层 reasoning/final` Turn 只展示一次回答。
- AC-2：结构化 activity 和不同内容的 commentary/reasoning 保持顺序且可见。
- AC-3：普通聊天、非 Codex 工具以及 failed/busy Codex 调用保持既有投影行为。
- AC-4：实时和持久化响应路径产生相同 blocks，包括响应重放。
- AC-5：所需自动化检查通过；无法执行的浏览器检查明确记录为 blocked 或 not run。

## 评审与批准

2026-09-22，用户先批准首版精确匹配实现，随后在说明真实反例和通用智能体边界后，批准扩展后的工具范围最终所有权方案。当前没有可用的 `review-spec` skill，因此执行直接设计评审。评审确认方案结果确定、传输边界向后兼容、仅限成功 Codex 委派、不涉及凭据或数据变更，并可由现有 projector 测试覆盖，无阻塞项。

## 验证

执行日期：2026-09-22。范围：`codex/from-main-20260921` 分支上基于 `3bbd260a` 的工作区修复。

- **pass** — 测试先行：扩展的重复 activity 测试和后续事件/历史测试在实现前失败，实现后通过。
- **pass** — 在 `frontend` 执行 `node --test tests/codexSandboxProgress.test.mjs tests/parallelStreamAggregation.test.mjs`：39/39。覆盖实时 activity、持久化 snapshot、重复响应、后续模型文本/thought、普通工具、不同 author/invocation、下一轮用户消息、未完成的成功响应、failed/busy/cancelled/timeout 响应以及既有并行 Turn 行为。
- **pass** — `npm --prefix frontend test`：1,258 个 Node 测试和 25 个 Vitest 测试通过。之后扩展的取消/超时 fixture 已通过上述定向重跑。
- **pass** — 在 `frontend` 执行 `npx tsc --noEmit -p tsconfig.json`；`npm run check:i18n`（2 个 locale，21 个 namespace）。
- **pass** — `npm --prefix frontend run build` 和 `npm --prefix frontend run test:webui-assets`：已验证 104 个文件和 248 个引用。构建告警来自既有的混合 import 和较大 bundle。
- **pass** — 使用生产 `eventsToTurns`、`Blocks` 模块和合成事件进行隔离真实浏览器渲染：执行中转完成、后续重复输出、历史重放、保留不同 commentary 和命令、普通聊天、失败响应、键盘选择以及 360 像素内容栏。完成后只显示一次最终答案，浏览器错误日志为空。验证后已移除临时 fixture 并停止开发服务器。
- **pass** — 本地 8000 端口 Studio 提供重新构建的 `index-WJxKEjkM.js` 入口。这确认的是服务端提供的版本，不代表已有标签页缓存的版本。
- **pass** — `git diff --check`；双语需求/标识符和相对链接已核对。
- **not_run** — 云端 MPA 实际复现：尚未取得发生问题的真实 Session 原始事件。浏览器和单元验证模拟用户报告的事件顺序，不能证明在线会话使用了该委派工具。
- **not_applicable** — Python、IME/输入和请求取消 UI 检查：未修改后端、输入或请求生命周期代码；已测试取消结果的投影。当前未请求提交，因此未执行提交前 pre-commit 门禁。

直接实现评审确认最终所有权仅保存在当前 assistant author/invocation 状态中，直到传输结束或进入新的用户轮次；结构化工具活动及不同 author/invocation 均保留。T-1–T-3 和 AC-1–AC-5 已由所记录的检查满足，云端实际验证明确保留为待确认项。

> 宽泛过滤规则由[保留补充内容](2026-09-22-preserve-followup-content.zh.md)替代。下文历史验证描述的是此前行为。
