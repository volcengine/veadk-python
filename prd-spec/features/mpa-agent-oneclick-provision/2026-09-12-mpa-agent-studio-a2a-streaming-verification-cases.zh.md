# mpa-agent Studio A2A 流式输出验证 Case

## 环境

- mpa-agent 分支：`fix/a2a-studio-streaming`
- veadk-python 分支：`feat/mpa-agent-oneclick-provision`
- 测试 Runtime：`r-yeuujrrcowb21078p9jh`
- Studio：`http://127.0.0.1:8001`
- 证据目录：两个仓库均使用 `.artifacts/a2a-streaming/`，不得写入密钥。

## Case

| Case | 覆盖 | 前置条件与操作 | 预期结果 | 证据 |
| --- | --- | --- | --- | --- |
| `VC-1` | FR-1 | curl agent-card | `capabilities.streaming=true` | `agent-card.json` |
| `VC-2` | FR-2/3/5 | 原始 `message/stream` 执行 `sleep 2; echo step-1; sleep 2; echo step-2` | task 完成前收到 working、tool 和两个分时输出 | `raw-a2a-stream.jsonl`、带时间戳日志 |
| `VC-3` | FR-2/5 | 经 Studio `/run_sse` 执行 VC-2 | 浏览器流在任务完成前收到过程事件和增量输出 | `studio-stream.txt`、截图 |
| `VC-4` | FR-4 | 统计一次执行的 terminal/final | terminal 与最终正文各一次 | `terminal-count.txt` |
| `VC-5` | FR-6 | mock 无 streaming capability | 只调用一次 `message/send` | pytest 输出 |
| `VC-6` | FR-6 | mock stream method-not-supported 且零事件 | 仅回退一次；总任务创建一次 | pytest 输出 |
| `VC-7` | FR-6/7 | 首事件后断开 Studio | 不发起第二个请求；原 task 后台完成 | 请求计数、task 查询 JSON |
| `VC-8` | FR-7 | VC-7 后刷新原 session | 可读取最终结果，不承诺补发全部 delta | Studio 截图、session/task JSON |
| `VC-9` | FR-8 | 慢速消费者和大量 delta | 可合并文本；tool result 与 terminal 不丢 | pytest 输出 |
| `VC-10` | FR-9 | 扫描所有流式 payload | 不含 API key、Authorization、完整 env 或签名 URL | secret-scan 输出 |
| `VC-11` | FR-10 | 连接旧非流式 Runtime | 阻塞模式仍能返回最终文本 | `legacy-runtime.txt` |
| `VC-12` | FR-10 | 普通 Web、飞书私聊/群聊、拉群、定时任务 | 行为与修改前一致 | 回归日志；外部条件不足则明确 blocked |
| `VC-13` | FR-3/5 | 两个 Studio session 并发执行不同 marker | sandbox/session 不同，输出不串流 | `concurrent-streams/` |
| `VC-14` | FR-4/7 | 流中取消任务 | 单一 canceled 终态，worker 收到取消 | cancel JSONL |
| `VC-15` | FR-2/5 | 普通模型直接回答 | 文本 delta 正常流式，无 sandbox 事件 | `direct-answer-stream.txt` |

## 执行顺序与失败处理

1. 单元测试执行 VC-1、VC-4 至 VC-6、VC-9、VC-10。
2. 本地双端集成执行 VC-2、VC-3、VC-11、VC-15。
3. 测试 Runtime 执行 VC-2 至 VC-4、VC-7、VC-8、VC-13、VC-14。
4. 最后执行 VC-12，避免在协议未稳定前影响外部渠道。
5. 任一 P0/P1 Case 失败即回到 TDD 实现，不进入代码审查。

## 执行结果（2026-09-12）

- `VC-1`–`VC-11`、`VC-13`、`VC-15`：在 Runtime v31（`mpa_agent:a2a-v8`）和 Studio `127.0.0.1:8001` 上通过。
- `VC-12`：Web、飞书、定时任务、群机器人相关自动化回归路径通过；因未提供机器人凭证和安装目标，飞书在线投递仍受环境条件阻塞。
- `VC-14`：executor 回归测试验证取消和单一终态归属；已有断线真机证据后未再执行额外破坏性取消。
- 沙箱时序：20.23s 工具调用、22.87s 命令输出、26.51s 文本 delta、27.44s 唯一 final；刷新后可读完整 `v31-final-1` / `v31-final-2` 结果。
- 并发验证：两个 session 分别产生 25/26 帧，invocation ID 不同，marker 无串流。
- 普通直答：转发真实 ADK delta，抑制累计 working 快照，仅保留一个持久 final；delta 粒度取决于上游模型/ADK。
- 敏感信息扫描：13 个证据文件中，用户提供的 PostgreSQL/OpenViking 凭证、Authorization header 和 API key 模式均为 0 命中。
- 前端包命令受本地环境阻塞：checkout 缺少 `vite`、`esbuild`、`typescript`；Python 桥接测试通过。
