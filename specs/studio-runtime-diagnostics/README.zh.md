# Studio Runtime 诊断

- **Component ID：** `studio-runtime-diagnostics`
- **状态：** 草案；提议变更由关联 PRD 管理
- **修订日期：** 2026-09-12
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
