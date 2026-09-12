# mpa-agent Studio A2A 流式输出设计文档

## 元信息

- **Change ID：** `mpa-agent-studio-a2a-streaming`
- **创建 / 修订：** 2026-09-12 / 2026-09-12
- **生命周期状态：** `approved`
- **对应语言版本：** [2026-09-12-mpa-agent-studio-a2a-streaming-design.md](2026-09-12-mpa-agent-studio-a2a-streaming-design.md)
- **前序设计：** [2026-09-11-mpa-agent-provision-orchestration-alignment-design.zh.md](2026-09-11-mpa-agent-provision-orchestration-alignment-design.zh.md)
- **实现分支：** mpa-agent `fix/a2a-studio-streaming`；veadk-python `feat/mpa-agent-oneclick-provision`

## 1. 概述

### 1.1 问题与证据

veadk Studio 已能通过 A2A 兼容桥接连接 mpa-agent Runtime，但当前 `/run_sse` 并不是真正的流式链路：

1. Studio BFF 固定调用 A2A `message/send`，并设置 `blocking=true`。
2. BFF 使用 `_runtime_proxy_buffer()` 缓冲完整 JSON-RPC 响应，任务结束前不会向浏览器发送事件。
3. mpa-agent 的 agent-card 当前返回 `capabilities={}`，未声明 streaming。
4. sandbox 的 `CodexNormalizedEvent` 通过 `codex_event_handler` 写入 PostgreSQL 和 Session Stream，但不会自动进入 A2A `EventQueue`。

真机验证已证明 Runtime、sandbox 与最终结果本身正常：Runtime `r-yeuujrrcowb21078p9jh` v25 能在约 13–16 秒完成命令，A2A task 为 `completed`，最终结果位于 artifact 的 ADK function-response data part。缺失的是任务执行期间的实时协议桥接。

### 1.2 目标

- **G1：** Studio 实时展示 A2A task 状态、sandbox 启动、工具调用、命令输出、文本增量和最终结果。
- **G2：** 同一用户请求最多执行一次；流式失败不得通过重新提交请求实现自动降级。
- **G3：** 不破坏普通 ADK Runtime、旧版非流式 A2A Runtime、Web、飞书、定时任务和机器人拉群。
- **G4：** 不新增数据库 schema，不让 Studio 直接读取 mpa-agent 数据库，不新增全局事件总线。
- **G5：** 浏览器断开后任务继续执行；首期不支持实时断点续传，刷新后可读取最终持久化结果。

### 1.3 非目标

- 首期不实现从最后一个 event id 继续实时订阅。
- 不修改 mpa-codex-worker 协议。
- 不替换 A2A SDK。
- 不修改 Agent、Tool、Runtime 创建流程和数据库表。
- 不改变飞书和定时任务的展示与终态语义。

## 2. 用户场景

### 场景 1：实时查看 sandbox 执行

**Given** mpa-agent agent-card 声明 `streaming=true`。
**When** 用户在 Studio 要求 sandbox 执行一个分阶段输出的命令。
**Then** Studio 在任务结束前依次显示 working、工具开始、输出增量、工具完成和最终文本。

### 场景 2：旧 Runtime 兼容

**Given** A2A Runtime 未声明 streaming。
**When** 用户发起聊天。
**Then** Studio 继续使用现有阻塞式 `message/send`，最终结果正常显示。

### 场景 3：连接中断

**Given** Runtime 已接受任务并开始返回事件。
**When** 浏览器或 Studio BFF 连接中断。
**Then** 任务继续执行并持久化；Studio 不自动重提原请求。刷新后用户可从原 session/task 读取最终结果，但首期不续传中断期间的实时增量。

### 场景 4：并发 session

**Given** 两个 Studio session 同时调用同一个 Runtime。
**When** 两个 sandbox 并发执行。
**Then** 每个 session 只收到自己的 invocation 事件，且 sandbox 实例保持隔离。

## 3. 功能需求

- **FR-1 — Streaming 能力声明。** mpa-agent agent-card 必须声明 `capabilities.streaming=true`，同时继续支持 `message/send`。
- **FR-2 — 标准流式调用。** Studio 在 capability 为 true 时使用 `message/stream`，并对上游 SSE 逐 frame 解析。
- **FR-3 — Invocation 内事件桥接。** mpa-agent 在当前 A2A invocation 内组合现有 `codex_event_handler`，将白名单化的 `CodexNormalizedEvent` 同步投递到当前 A2A `EventQueue`；不建立进程级全局 relay。
- **FR-4 — 单一终态所有权。** callback relay 只发布 progress/artifact；A2A task 的 completed/failed/canceled 终态继续由官方 executor 和现有 distributed-control 线性化逻辑产生。
- **FR-5 — Studio 事件映射。** BFF 将 A2A status、text、data、artifact 转换为现有 Studio ADK event 结构，并保留 `eventId`、`invocationId`、`commandId`、`eventType` 和 append/terminal 语义。
- **FR-6 — 安全降级。** agent-card 未声明 streaming 时直接选择 `message/send`；只有 `message/stream` 在尚未产生事件前明确返回 method-not-supported 时，才允许回退一次。网络超时、5xx、401/403、协议损坏或已收到事件后禁止重提。
- **FR-7 — 断线语义。** 客户端断开不取消 Runtime 任务，不自动重提请求；task/session 标识必须保留，刷新后可读取最终持久化结果。首期不提供实时断点续传。
- **FR-8 — 背压。** 工具状态和终态不得丢失；连续文本 delta 可按最多 50ms 或 512 字符合并，单个输出事件必须有长度上限。
- **FR-9 — 安全输出。** 仅转发 normalized 且允许展示的字段，不透传 API key、Authorization、endpoint credential、完整环境变量或未经脱敏的原始 worker payload。
- **FR-10 — 兼容性。** 普通 ADK `/run_sse`、Web、飞书、定时任务、机器人拉群以及旧版 A2A 阻塞模式行为保持不变。

## 4. 方案设计

### 4.1 总体流程

```text
Studio /run_sse
  -> 读取 agent-card capability
  -> message/stream
  -> mpa-agent A2A executor
  -> invocation-local codex_event_handler
       -> 原路径：Session Stream + PostgreSQL
       -> 新路径：A2A progress/artifact event
  -> A2A SSE
  -> veadk incremental decoder / adapter
  -> Studio ADK SSE
```

### 4.2 mpa-agent 边界

`app/a2a/app.py` 在构建 agent-card 时传入 `AgentCapabilities(streaming=True)`。A2A SDK 已原生注册 `message/stream`，不新增 HTTP 路由。

`ObservableA2aAgentExecutor.execute()` 为当前 invocation 构造组合 callback：

1. 调用原 `codex_event_handler`，保持现有 Session Stream 和持久化。
2. 将允许展示的 normalized event 投影为 A2A progress/artifact。
3. 投递到当前请求的 `EventQueue`。
4. invocation 结束即释放闭包，不维护全局 session/event queue 映射。

`sandbox_task` 继续使用 ADK 原生 `tool_context.actions.skip_summarization`，避免 sandbox 完成后主模型重复调用；A2A 最终结果使用标准 function-response artifact。

### 4.3 公开事件契约

过程事件采用 A2A data part：

```json
{
  "kind": "data",
  "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
  "data": {
    "eventId": "worker-event-id",
    "invocationId": "e-...",
    "eventType": "tool.call",
    "payload": {}
  }
}
```

允许的 `eventType`：`status.notice`、`message.delta`、`tool.call`、`tool.output`、`tool.result`、`tool.error`、`file.change`、`usage.updated`、`invocation.completed`、`invocation.failed`、`invocation.cancelled`。`thought.delta` 默认不对 Studio 展示。

### 4.4 Studio 桥接

新增 `veadk/cli/runtime_a2a_stream.py`，职责限定为：

- A2A SSE frame 增量解码。
- JSON-RPC/A2A 外部响应边界校验。
- A2A event 到 Studio ADK event 的转换。
- 请求内去重、tool call/result 配对、文本 delta 合并和终态保护。

`cli_frontend.py` 只负责 capability 选择、上游连接、鉴权、fallback 和 `StreamingResponse`。流式路径不得调用 `_runtime_proxy_buffer()`。

### 4.5 事件映射

| A2A 事件 | Studio 事件 | 展示 |
| --- | --- | --- |
| submitted/working | 状态 metadata | 执行中 |
| `status.notice` | progress metadata | 沙箱启动/等待 |
| `tool.call` | `functionCall` | 工具卡片开始 |
| `tool.output` | sandbox progress metadata | 实时命令输出 |
| `tool.result` | `functionResponse` | 工具完成 |
| `message.delta` | text part，`partial=true` | 文本增量 |
| final function response | text part，`partial=false` | 最终文本 |
| failed/canceled | error/status event | 失败或取消 |

### 4.6 去重、顺序与终态

- 去重键优先使用 `(taskId, eventId)`。
- 同一 `commandId` 的 call/output/result 必须保持顺序。
- 收到 terminal 后忽略迟到的非终态事件。
- 每个 task 最多向 Studio发送一个最终文本事件和一个 terminal marker。
- A2A callback 不自行提交 terminal status，避免绕过 distributed-control。

### 4.7 断线与恢复

- 上游已接受任务或 Studio 已收到任何事件后，连接失败只结束当前浏览器流。
- 不自动调用 `message/send` 或再次调用 `message/stream`。
- A2A SDK 继续后台消费并持久化任务。
- Studio 保留 session/task 映射；页面刷新后读取 task 或 session history 展示最终结果。
- 首期不保证恢复中断期间的完整增量序列。

## 5. 边界情况

| 场景 | 处理方式 |
| --- | --- |
| agent-card 无 streaming 字段 | 使用现有 `message/send` |
| stream 建立前返回 method-not-supported | 回退一次阻塞模式 |
| 已收到 submitted 后断流 | 不重提；提示连接中断，允许刷新查看结果 |
| 401/403 | 返回认证错误，不回退 |
| malformed SSE/JSON | 返回协议错误，不重提 |
| 重复 event id | 丢弃重复事件 |
| 慢消费者 | 合并文本 delta；不得丢工具结果和终态 |
| final text 为空 | 不伪造成功正文，按真实 task 状态收尾 |
| 两个 session 并发 | callback 闭包绑定各自 invocation/EventQueue |

## 6. 实施任务

| 任务 | 内容 | 依赖 | 交付物 |
| --- | --- | --- | --- |
| `T-1` | 整理 mpa-agent 独立分支与现有修复 diff | 无 | `fix/a2a-studio-streaming` |
| `T-2` | 先写 agent-card streaming 红灯测试 | T-1 | capability contract test |
| `T-3` | 先写 invocation callback relay 红灯测试 | T-2 | 顺序、隔离、终态测试 |
| `T-4` | 实现 mpa-agent capability 与 relay | T-3 | 原始 `message/stream` 可见过程事件 |
| `T-5` | 定义并测试 veadk SSE decoder | T-4 | `runtime_a2a_stream.py` |
| `T-6` | 接入 Studio `message/stream` 与安全 fallback | T-5 | `/run_sse` 增量代理 |
| `T-7` | 工具卡片、输出增量、最终文本映射 | T-6 | Studio 流式展示 |
| `T-8` | 断线、并发、取消和旧 Runtime 回归 | T-7 | 集成验证报告 |
| `T-9` | 飞书和机器人拉群回归 | T-8 | 无回归证据 |

## 7. 测试与验收

| 需求 | 验收标准 | 验证方式 |
| --- | --- | --- |
| FR-1 | `AC-1`：agent-card 返回 `streaming=true` | mpa-agent 单测 + curl |
| FR-2/3 | `AC-2`：`message/stream` 在任务结束前返回事件 | 原始 A2A SSE 集成测试 |
| FR-3/5 | `AC-3`：工具开始、输出、完成按顺序进入 Studio | 两仓库集成测试 |
| FR-4 | `AC-4`：每个 task 只有一个 terminal event | 单元 + E2E |
| FR-6 | `AC-5`：只有 method-not-supported 且零事件时回退 | veadk 单元测试 |
| FR-6/7 | `AC-6`：断流不产生第二个 task | 请求计数断言 + task store |
| FR-7 | `AC-7`：断开后任务完成，刷新可读最终结果 | 真机断线测试 |
| FR-8 | `AC-8`：慢消费者不丢 tool result/terminal | 有界队列压力测试 |
| FR-9 | `AC-9`：流中无密钥、credential、原始 env | secret scan + payload 断言 |
| FR-10 | `AC-10`：旧 Runtime、Web、飞书、定时任务和拉群通过 | 回归测试 + 真机验证 |
| 全部 | `AC-11`：`sleep 2; echo step-1; sleep 2; echo step-2` 分时到达 | 带时间戳 E2E 记录 |
| 全部 | `AC-12`：两个 session 使用不同 sandbox 且事件不串流 | 并发 E2E |

完成标准要求同时满足：单元测试通过、原始 A2A SSE 有过程事件、Studio 页面真机可见过程与最终文本、旧 Runtime fallback 正常、飞书核心链路无回归。只看到最终结果不算完成。

## 8. 风险与回滚

- **重复执行风险：** fallback 严格限制为零事件的 method-not-supported。
- **事件泄漏风险：** 对 normalized payload 使用白名单，不透传原始 worker 数据。
- **终态竞争风险：** progress relay 不生成 terminal，终态仍归官方 executor。
- **内存风险：** invocation 内有界队列和文本合并；任务结束立即释放。
- **发布风险：** 测试 CR 仓库存在 tag 上限，发布前仅删除确认未被 Ready Runtime 使用的测试 tag。
- **回滚：** mpa-agent 回滚到上一 Ready Runtime version；veadk 关闭 capability 路径后自动回到 `message/send`。两者均不涉及数据迁移。

## 9. 评审与决策记录

- 2026-09-12：`review-spec` 发现仅切换 `message/stream` 无法获得 sandbox 旁路事件，补充 invocation-local callback relay。
- 2026-09-12：拒绝 PostgreSQL 轮询和进程级全局 relay，避免数据库耦合与多副本路由复杂度。
- 2026-09-12：确认首期不做断线后实时续传；必须保证任务不重复提交，刷新可读取最终结果。
- 2026-09-12：mpa-agent 已从 `main` 安全迁移到 `fix/a2a-studio-streaming`，未提交修改完整保留。
