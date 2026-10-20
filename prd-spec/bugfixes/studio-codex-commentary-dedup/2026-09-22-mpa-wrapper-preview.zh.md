# MPA 包装结束后保留预览替换边界

[English](2026-09-22-mpa-wrapper-preview.md)

- ID：`mpa-wrapper-preview`
- 日期：2026-09-22
- 状态：已实现；原始会话验证待完成
- 组件：[Studio 工具活动](../../../specs/studio-tool-activity/README.zh.md)
- 前次尝试：[Codex 工具最终回答所有权](2026-09-22-studio-codex-commentary-dedup.zh.md)

## 证据和范围

用户反馈重复回答没有变化，两份答案之间有推理块。前次尝试假设使用 `delegate_to_codex_sandbox`；检查 `client.ts` 确认原生 MPA 端点使用 `/api/v1/sessions/{id}/run` 和 `/sse`。本地 agentkit-mpa-agent 实现会投影携带 sandbox metadata 的 `message.delta`、`thought.completed` 和 `invocation.completed`。尚未拿到用户原始会话；本次为根据契约构造的复现，并非生产抓包。

Studio 在以下顺序下复现两份答案：`sandbox_task` 调用、sandbox 答案增量、带 `finalAlreadyEmitted: true` 的包装响应、已完成推理、sandbox 最终回答。包装响应把 `liveStart` 推进到块数量，错误地将预览定稿，后到的权威回答就追加在已定稿的预览后面。

## 需求和设计

- **FR-1：** 包装结束关闭父工具和推理，但保留原有预览边界，不得将流式答案定稿或丢弃。
- **FR-2：** 后到的合并事件按已有 ADK 投影规则替换预览。权威答案可以与预览不同，不需要文本相等的启发式判断。
- **FR-3：** 如果传输结束时没有持久化最终事件，仍保留预览并完成展示。工具失败/结果、没有增量的历史、其他 invocation 和通用智能体保持原有行为。

仅修改 `frontend/src/blocks.ts` 的 `isFinalAlreadyEmittedSandboxResponse` 分支。在 `frontend/tests/parallelStreamAggregation.test.mjs` 添加回归测试，更新双语组件契约，重新生成 `veadk/webui`。不涉及后端、传输、持久化数据、权限、输入、样式或部署。本次跟进不重新设计独立的 delegate 工具实现。

## 任务和验收

1. **T-1 / AC-1：** 为包装先于最终事件的顺序添加失败回归，包括中间已完成推理以及最终文本变化，只保留一份权威答案。
2. **T-2 / AC-2：** 保留预览边界，验证仅包装结束时仍保留答案且完成工具；验证历史一致性和通用聊天回归。
3. **T-3 / AC-3：** 执行定向及全部前端测试、类型检查、构建/资产检查和浏览器回放，在双语文档记录结果与限制。

## 评审、授权和风险

用户已多次授权修复同一重复展示问题。直接设计评审（review-spec 不可用）确认改动仅限 MPA 包装标记，符合已有预览语义，没有需要额外批准的新范围或外部操作。风险：后续事件可能替换实时预览，这是预期的合并行为；仅传输结束必须保留预览。仅凭生产截图无法确定就是该顺序导致，原始会话验证仍待完成。

## 验证

- **pass：** 修改前独立回放根据契约构造的顺序，同一个 Turn 出现文本、推理、重复文本。
- **pass：** 先写回归：4 个新增用例在一行边界修复前全部失败，修复后通过。`node --test frontend/tests/parallelStreamAggregation.test.mjs frontend/tests/toolActivityModel.test.mjs frontend/tests/codexSandboxProgress.test.mjs`：70 项通过。
- **pass：** `npm --prefix frontend test`：1,261 项 Node 测试和 25 项 Vitest 测试通过，Node 无跳过。类型检查：frontend 下 `npx tsc --noEmit -p tsconfig.json`。
- **pass：** `npm --prefix frontend run build`、`npm --prefix frontend run test:webui-assets`（104 文件、248 引用）和 `git diff --check`。保留已有构建分块大小/导入警告。
- **pass：** 浏览器使用真实 `eventsToTurns` 和 `Blocks` 回放根据契约构造的数据：运行预览、仅包装结束、完整回答、持久化历史、通用智能体回答及 360px 内容宽度。只显示一份答案，控制台无错误。临时测试页面与 Vite 服务已移除。
- **pass：** 发现本地 Studio 仍返回缓存的旧入口，因为 `_index_html` 在进程启动时读取。已按原 `uv run veadk studio` 命令重启（省略自动打开浏览器），新构建入口为 `index-i19v0vDQ.js`。
- **not_applicable：** 后端、输入/IME、网络重试/取消 UI 和云端执行门禁：本次跟进仅修改预览合并。用户未要求提交/推送，未运行提交时门禁。已保留工作区中已有相关及无关改动。
- **blocked：** 原始会话验证等待已向用户请求的会话地址/标识。

2026-09-22 评审：没有引入文本匹配、跨智能体状态或存储数据变更。T-1–T-3 与 AC-1–AC-3 已在复现的原生事件顺序下通过，原始会话仍明确标记未验证。
