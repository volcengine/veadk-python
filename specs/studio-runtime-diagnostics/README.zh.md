# Studio Runtime 诊断

- **Component ID：** `studio-runtime-diagnostics`
- **状态：** 草案；提议变更由关联 PRD 管理
- **修订日期：** 2026-09-30
- **English version:** [README.md](README.md)
- **关联 PRD：** [MPA Runtime 集成加固](../../prd-spec/bugfixes/mpa-runtime-integration/2026-09-12-mpa-runtime-integration-hardening.zh.md)
- **负责代码：** `frontend/server/runtime_logs.py`、`frontend/src/ui/RuntimeLogsDialog.tsx`、`veadk/cli/runtime_a2a_stream.py`、`frontend/src/adk/tokenUsage.ts`、`frontend/src/ui/TraceDrawer.tsx` 以及 `veadk/cli/cli_frontend.py` 中的 Runtime A2A BFF

## 职责

本组件为已授权 Studio 用户提供有界实时 Runtime 日志、当前可见脱敏快照的本地下载、规范化 Token 用量、A2A Runtime 广告能力时的请求级模型选择，以及规范化 APMPlus 链路查看。它不负责 Runtime 日志保留、Provider 计费、模型凭据或 APMPlus IAM 策略。

## 契约

- `CON-1`：Runtime 日志通过 Studio BFF 授权，以替换快照方式刷新，在服务端脱敏并限制为最近 1,000 个逻辑行。下载内容严格等于当前可见快照，不得绕过 BFF 授权或脱敏。
- `CON-2`：A2A 用量 metadata 与 worker `usage.updated` 规范化为现有 ADK `usageMetadata`/`modelVersion` 字段。重放的累计快照不得放大 Session 总量。
- `CON-3`：仅在连接的 A2A Agent 广告多个允许模型时显示模型选择。Studio 只在请求 metadata 中发送模型 ID，由 Runtime 校验。选择属于 Session 本地状态，活跃回合中不可改变。
- `CON-4`：链路加载保持明确状态语义：404 未开启、425 采集中、403 需要权限、502 Provider 失败、200 规范化 Span。空数据或拒绝访问不得报告为成功。
- `CON-5`：Runtime API Key、模型 Key、Provider 凭据和未脱敏原始日志不得进入下载文件、模型选择值、agent-card capability 或前端状态。

## 状态与并发

日志流可以重连；目标或弹窗变化时取消旧流，旧流不得覆盖最新目标。下载后立即回收 Blob URL。Token 快照按来源/请求标识隔离，并在一次流内保持单调。活跃回合中不能切换模型。链路重试在关闭/卸载时停止，并区分可重试采集与终态权限/配置错误。

## 兼容

非 A2A Agent 和未广告模型能力的 A2A Agent 保持现有 Composer。现有 Token 和链路 UI 组件继续作为唯一展示所有者。现有专用 Transcript/Tool renderer 不变。

## 验证

| 契约 | 验证 |
| --- | --- |
| `CON-1` | Runtime 日志服务测试、弹窗测试、浏览器下载及重连检查 |
| `CON-2` | A2A Decoder 与 Token 聚合测试及真实 Runtime 用量 |
| `CON-3` | BFF metadata 测试、mpa-agent 校验测试及浏览器默认/覆盖/非法场景 |
| `CON-4` | 404/425/403/502/200 Endpoint 测试及真实 TraceDrawer 检查 |
| `CON-5` | Secret scan 及浏览器 Payload/下载不含 Key 或原始日志的断言 |

- `CON-6`：A2A 桥接在等待上游前输出非终止 connecting 状态。对话通过现有进度占位将 connecting/submitted/working 展示为等待/排队/执行中。状态不算答案或接受请求的证明，实际内容替换占位。有效流等待完成、错误或取消，不自动重试。

- `CON-7`：已授权 Runtime 代理请求使用 Studio 主体 owner 作为 x-user-id，与任务管理归属一致，浏览器身份头不得覆盖。

- `CON-8`（已实现）：MPA A2A 流中非空的 sandbox `invocation.completed.payload.finalMessage` 投影为合并的 `turnComplete` 答案，保留 sandbox invocationId；兼容旧 `text`/`message` payload。仅省略与该任务已知 sandbox final 去除首尾空白后完全相同的后续完整答案文本 part。保留不同/扩展文本、推理、partial 增量、工具/错误及用量/状态事件。空、失败、取消和没有任务标识的事件不能取得此所有权。已标识的 sandbox 源事件在 artifact 更新和任务快照之间按任务仅投影一次。状态仅在本次 decoder/请求内，完成、断连或取消后销毁。非 MPA 和直接 ADK/原生会话行为不变。

`CON-8` 由 [MPA A2A 最终回答所有权](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-mpa-a2a-final.zh.md) 维护，在 `tests/cli/test_runtime_a2a_stream.py` 及跨层前端回放中验证。本次新增不代表其他草案契约已实现。

- `CON-9`（已实现）：探测为 `a2a-default` 的 Runtime 应用通过 A2A 桥接创建/列表/读取/删除/运行会话，并跳过原生执行配置前置查询，不受 MPA 类型/实例信息影响。其他 MPA 应用保留原生 Profile/session/run/SSE 行为，普通 ADK 应用不变。错误和取消不切换协议。不涉及会话迁移、鉴权或持久化变更。参见 [A2A 会话路由](../../prd-spec/bugfixes/studio-session-protocol/2026-09-22-a2a-session-routing.zh.md) 和 `frontend/tests/runSseAbort.test.mjs`。

- `CON-10`（已实现）：显式 MPA A2A 转录模式合并相邻匹配/扩展的外层完整推理快照，并按一条用户请求判断空回复提示。保留 partial 增量及 sandbox 事件；真正空的已结束请求保留一次提示。通用 ADK/A2A 和原生 MPA 的默认行为不变。参见 [MPA A2A 推理](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-mpa-a2a-reasoning.zh.md)。 MPA 外层及沙箱完整事件不含权威推理文本时，在替换答案预览的同时保留临时预览区的 thinking 块，避免最终答案到达后丢失不同的外层及沙箱推理，包括不调用沙箱的直接回答；权威推理快照仍采用替换语义。 显式 MPA A2A 桥接模式按来源归一化外层多 part 推理快照，并与沙箱调用阶段隔离。追加元数据 `reasoningSegmentId` 让迟于 tool.call 的沙箱推理尾部仍属于原块；工具结果和答案增量分隔阶段。通用/默认解码不变。 MPA 完整/替换 artifact 的推理 part 必须保留精确空白拼接后再比较快照；仅追加分片仍按增量处理。合并不得跨越非推理 part。

- `CON-11`（已实现）：MPA A2A 将相邻助手片段显示为一个回复和一套底栏，按来源统计本轮用量，使用最后可见答案的反馈身份及最新会话轨迹截止时间。原 turn 和通用智能体行为不变。参见[回复合并](../../prd-spec/features/mpa-response-grouping/2026-09-22-mpa-response-grouping.zh.md)。

CON-8/CON-11 修正（已实现）：保留 sandbox 完成后的不同外层文本与推理。桥接只去重完全相同的完整答案 part；MPA 合并视图可以隐藏完全相同的答案副本，但不改变原 turn，片段扩展后完整恢复。通用 Codex 工具行为恢复。参见[保留补充内容](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-preserve-followup-content.zh.md)。

- [MPA 推理快照归一化](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-mpa-reasoning-snapshots.zh.md).

- `CON-12`：仅 MPA A2A 对同源默认 `/a2a/jsonrpc` 卡片地址补齐可信控制面 endpoint 的 `/runtime/[a-z0-9-]+` 前缀。已经有前缀、其他路径、跨源、查询/片段/用户信息不改写。发送和历史恢复一致使用该地址；通用智能体保持不变。参见 [A2A 发现修复](../../prd-spec/bugfixes/2026-09-23-mpa-a2a-discovery-default.zh.md)。

- `CON-13`（已实现）：已授权 GET Runtime 代理 `list-apps` 对控制面识别的 MPA 优先探测可用 Agent Card，在 ADK 探测前返回 `["a2a-default"]`。普通 Runtime 和无可用卡片的 MPA 保留原发现/错误行为。其他请求、授权、凭据/header 构造和已有会话不变；重新连接刷新缓存应用，不迁移会话。参见 [MPA A2A 优先](../../prd-spec/bugfixes/studio-mpa-a2a-preference/2026-09-30-prefer-a2a.zh.md) 及 `tests/cli/test_frontend_runtime_proxy.py`。
