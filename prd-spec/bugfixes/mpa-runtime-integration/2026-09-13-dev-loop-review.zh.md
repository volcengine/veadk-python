# Dev Loop Spec 评审：MPA Runtime 集成加固

- **Change ID：** `mpa-runtime-integration-hardening`
- **状态：** 已批准
- **日期：** 2026-09-13
- **English version:** [2026-09-13-dev-loop-review.md](2026-09-13-dev-loop-review.md)
- **评审方案：** [2026-09-12-mpa-runtime-integration-hardening.zh.md](2026-09-12-mpa-runtime-integration-hardening.zh.md)

## 评审结论

方案具备可落地性，且与当前 VeADK/mpa-agent 边界一致。当前没有 P0/P1 阻塞项。评审覆盖上下文一致性、歧义、SDD/TDD 适配、最小实现、兼容性、存量部署、失败恢复、安全、可观测性和扩展性。

## 问题与处理

| 优先级 | 问题 | 处理 |
| --- | --- | --- |
| P1 | 宽泛的 VeADK 模式开关可能关闭无关缓存。 | 使用窄粒度 `APPCENTER_RESOURCE_DISCOVERY_ENABLED`，原生默认保持 `true`。 |
| P1 | 模型生成的 `sandbox_task.modelOverride` 可能绕过 Studio allowlist。 | 经校验的请求级模型始终覆盖工具参数。 |
| P1 | 首个 A2A 进度更新在 artifact 不存在时使用 `append=true`。 | 第一次成功 enqueue 创建 artifact，后续事件才 append。 |
| P1 | Runtime key 注入可能通过 dry-run 输出泄露。 | 将 `CODEX_MCP_RUNTIME_API_KEY` 作为 Secret，仅在第二阶段服务端注入。 |
| P2 | 重放用量快照可能放大 Session 总量。 | 按来源/请求记录快照，只发出正向增量。 |
| P2 | 开启 APMPlus 可能意外暴露 Prompt 内容。 | 开启 Runtime 链路，同时保持 `APMPLUS_TRACE_CONTENT=false`。 |
| P2 | 日志下载可能绕过展示上限或脱敏。 | 只下载服务端已脱敏的当前 1,000 行快照。 |
| P3 | 现有 Runtime version 31 无法证明新行为。 | 在发布新镜像并更新 Runtime 前，将真实验证记录为 blocked。 |

## 批准门禁

- P0：无
- P1：全部解决
- P2/P3：处理方案已记录
- 结论：批准进入现有 SDD/TDD 实现及验证流程。
