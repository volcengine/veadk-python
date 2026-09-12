# A2A 首事件心跳修复

- **状态：** 已实施并完成验证
- **日期：** 2026-09-12
- **变更类型：** Bugfix
- **英文版本：** [2026-09-12-a2a-first-event-heartbeat.md](2026-09-12-a2a-first-event-heartbeat.md)
- **影响组件：** [Studio 工具活动](../../../specs/studio-tool-activity/README.zh.md)

## 1. 证据与问题

Studio 在 30 秒内未收到 SSE 帧时会中止 `/run_sse`。本次真实 Runtime 请求中，A2A task 于 22:15:41 开始，模型于 22:16:02 产生首个可展示内容；由于此前还有 agent-card 协商，总请求耗时超过 30 秒。Runtime 返回 HTTP 200 且记录了执行中的 invocation，证明公网 APIG 链路可达。

当前桥接会丢弃 A2A 的 `submitted` 状态以及不含消息的 `working` 状态。因此，健康但耗时较长的调用可能在浏览器截止时间前没有任何下游 Studio 帧，并被误判成网络超时而取消。

## 2. 范围与设计

- 将非终态且不含 Agent 消息的 A2A `submitted`、`working` 状态转换为 Studio metadata-only heartbeat 事件。
- 保留带可见文本的 `working` 消息现有投影行为。
- heartbeat 不显示文本、不创建 transcript block、不结束 turn，也不重新提交请求。
- 不修改 Runtime 创建、mpa-agent、task 语义、历史持久化或现有 30 秒客户端截止时间。

`a2a_event_to_studio_events()` 输出一个包含空 `parts` 和 `customMetadata.a2aStatus` 的 partial ADK 兼容事件。`runSSE()` 将解析成功的帧视为首事件，而 `createAssistantEventProjector()` 会忽略不影响 assistant turn 的事件。终态 status update 继续不输出。

## 3. 测试与验收

- 单测覆盖 `submitted` 和无消息 `working` heartbeat 投影。
- 单测覆盖 heartbeat 被 transcript 投影忽略。
- 保持带文本的 working 和终态 status 行为不变。
- 执行定向 A2A/Studio 测试、前端测试、构建、资产校验和 pre-commit。
- 真实 Runtime 验收：首个下游 SSE 帧在 30 秒内到达，原始请求只提交一次。

## 4. 风险

- heartbeat 不得创建空 assistant turn。缓解：使用空 parts，并增加显式 projector 测试。
- 终态不得伪装成存活信号。缓解：仅输出非 final 的 `submitted`/`working`。
- retry 可能造成重复执行。缓解：不修改 retry 或 fallback 行为。

## 5. 验证记录

- `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q`：85 项通过。
- 真实 Runtime `r-yeuujrrcowb21078p9jh`：仅含 metadata 的首个 heartbeat 在 0.737 秒到达，最终回答在 5.999 秒到达，一次请求共产生 9 个下游帧。
- 重复的无消息 `working` 更新由请求内 decoder 按 `(taskId, state)` 去重。
