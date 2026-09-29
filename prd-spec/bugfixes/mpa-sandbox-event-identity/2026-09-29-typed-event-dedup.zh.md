# 保留来源 ID 相同的不同 MPA 沙箱事件

[English](2026-09-29-typed-event-dedup.md)

ID：`mpa-sandbox-event-identity`；日期：2026-09-29；状态：implemented。
契约：[Studio Runtime Diagnostics CON-8](../../../specs/studio-runtime-diagnostics/README.zh.md)。

## 证据、范围与需求
只读会话检查及匿名回放确认，`usage.updated` 和 `invocation.completed` 可以共用来源 ID。agentkit-mpa-agent 转发器及 Studio 解码器的两层去重会丢弃完成事件。缺少权威最终标记时，界面可能把流式预览和包装结果保留成两份答案。

FR-1：保留来源 ID 相同而标准化类型不同的事件，包括用量、完成、失败及取消。真正的重放按任务/调用/类型/来源 ID 去重；没有来源 ID 的事件仍然保留。
FR-2：保留同时包含已见和新事件的多部分快照。不改变传输 ID 和 `mpa.sandbox-event.v1` 协议。
FR-3：保留推理、工具及 token 统计；沙箱最终答案只消除完全一致的外层完整答案副本。通用 A2A/ADK 解码保持不变。
非目标：界面重设计、模糊文本过滤、修改历史记录、鉴权调整、镜像构建、部署及云资源变更。

## 设计与影响文件
agentkit-mpa-agent 的 `app/a2a/executor.py` 使用 `(source_event_id, event_type)` 作为请求内转发去重键；处理器闭包已提供调用隔离。原持久化回调及载荷白名单保持不变。
`veadk/cli/runtime_a2a_stream.py` 将 MPA 协议 artifact 帧的去重交给逐事件投影。首个部分的 ID 无法标识整个多部分帧。投影使用 `(task_id, invocation_id, event_type, source_event_id)`。通用帧标识保持不变。不涉及持久化结构、API、权限或依赖变更。集合仍局限于解码器/请求现有生命周期，断开或取消后释放。完成、失败、取消是独立语义，不因来源 ID 相同而互相去重。
测试：`tests/cli/test_runtime_a2a_stream.py`、agentkit-mpa-agent 的 `tests/test_a2a_executor.py`。使用匿名 Python 到 Node 回放验证现有前端投影，不修改前端源码或资源。

## 任务与验收
- T-1 / AC-1（FR-1/2）：先补失败的离线测试，覆盖相同 ID 的用量/完成事件的两种顺序、重放去重、调用/任务隔离、缺失 ID、混合多部分重放、失败/取消。
- T-2 / AC-2（FR-1/2/3）：实施限定范围的转发器和解码器修正，保留原始传输载荷及通用去重。
- T-3 / AC-3（FR-3）：运行受影响 Python 测试、Ruff/Pyright、匿名前端实时/历史回放、范围内敏感信息扫描及空白检查。验证只有一个答案、推理保留及 token 正确，分别记录实际结果及未验证的部署。

## 评审、批准及风险
review-spec 不可用，采用直接评审。已检查职责、兼容性、错误/终态、回调顺序、隐私、请求内生命周期、可测试性及双语一致性，无阻断项。用户在双仓库诊断后以“帮我改下”批准实施。提交的测试夹具不使用生产会话数据。
风险：Studio 无法恢复上游未发送的事件，需部署两端修正才能完整生效；镜像部署不在本次请求范围。迟到的完全重放仍去重，不同事件继续展示。无需迁移，不修改历史持久化记录。

## 验证
日期：2026-09-29。差异基线：VeADK `79acf209`；agentkit-mpa-agent `62cf960`。保留现有无关修改。结果如下。

### 结果
代码修改的 T-1/T-2/T-3 已完成，未部署。以下检查在 2026-09-29 的工作区差异上运行。
- `pass`：修复前，新增 Studio 测试中七项失败，转发器两项失败；缺失 ID 的兼容性测试通过。修复后，`uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q` 通过 156 项（六条已有弃用警告）。
- `pass`：agentkit-mpa-agent 中，`.venv/bin/python -m pytest tests/test_a2a_executor.py tests/test_a2a_codex_terminal.py tests/test_codex_delegation_tool.py -q` 通过 113 项。保留已有 ADK 实验性/弃用警告。
- `pass`：`node --test frontend/tests/mpaResponseGrouping.test.mjs frontend/tests/mpaContentPreservation.test.mjs` 通过 22 项。匿名 Python 解码器 → 实际前端投影/分组回放，在实时及历史模式中均得到一个答案、一个保留的推理块，token 恰为 100。
- `pass`：两个仓库各两个修改 Python 文件通过 Ruff 0.11.12 检查；Studio 格式检查通过；Studio `uv run --with pyright pyright veadk/cli/runtime_a2a_stream.py tests/cli/test_runtime_a2a_stream.py` 零错误/警告。Runtime Ruff 缓存写入被沙箱限制后，改用 `--no-cache` 检查。
- `fail`（已有基线）：Runtime 的 `app/a2a/executor.py` 和 `tests/test_a2a_executor.py` 经 Pyright 检查有 45 个错误。隔离的 HEAD 副本使用相同解释器及导入路径，得到同样的 45 条诊断，本次没有新增。无关类型清理不纳入本次范围。
- `pass`：直接代码/设计评审确认原回调、白名单及通用去重保留；检查双语标识/链接、范围内 gitleaks 扫描及 `git diff --check`。
- `not_applicable`：前端构建/生成资源、sidecar 门禁及新增布局/键盘/输入法检查；未修改前端或 sidecar 文件。
- `not_run`：真实浏览器/云端端到端、镜像构建、部署、服务重启、提交和推送。验证为离线回放；现有 Runtime 镜像仍须替换才能启用上游转发修正，Studio 须重新加载解码器。未运行全仓回归，因为修正仅限显式 MPA 事件；已运行受影响的解码/代理/转发/终态及前端内容保留测试。

## Rebase 验证 — 2026-10-07

为 PR #17 与 main `e0448a4d` 协调。保留原功能补丁及上游发现/鉴权和 Worker 恢复改动。参见[组合协调及验证记录](../mpa-shared-network-bootstrap/2026-09-28-registry-owned-network.zh.md#pr-17-rebase-协调--2026-10-07)。
