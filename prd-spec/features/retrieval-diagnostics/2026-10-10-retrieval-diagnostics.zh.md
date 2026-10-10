# 检索与记忆性能诊断

[English](2026-10-10-retrieval-diagnostics.md)

Change ID：retrieval-diagnostics；修订：2026-10-10；状态：approved。

## 背景与范围

`veadk/knowledgebase/knowledgebase.py:Knowledgebase.search` 调用后端检索并归一化结果。`veadk/memory/long_term_memory.py:LongTermMemory.search_memory` 捕获后端错误后返回空记忆；OpenViking 调用经过 `asyncio.to_thread`。`add_session_to_memory` 过滤事件并保存。这些边界目前没有独立检索 / 写入 Span，外层工具 Span 无法区分检索与其他工作。

用户已授权整体性能诊断实现、本地验证和草稿 PR 交付。本变更补齐已约定的检索边界，不包含生产部署授权。

## 目标与非目标

记录真实知识检索、记忆检索及保存边界，继承已有 OTel 上下文和 Provider，保持接口、返回值、异常与取消行为。不新增导出器、采样配置、存储、看板，也不拆造后端内部向量生成 / 重排阶段。可观测负责接收、导出、存储和查询；性能诊断负责调用边界及定位慢调用的证据。

## 需求与场景

- FR-1：知识检索生成 `veadk.knowledge.search`，结果归一化后结束；记录后端类型、实际 top_k 和结果数量。后端失败保持抛出原异常，并记录 ERROR。
- FR-2：记忆检索生成 `veadk.memory.search`；后端失败保持现有空返回，但 Span 标为 ERROR 并记录安全错误类型。正常空结果仍是成功。
- FR-3：记忆保存生成 `veadk.memory.save`，覆盖事件过滤与后端保存；记录后端类型、会话 ID 及过滤后的事件数量。错误继续抛出。
- FR-4：继承父上下文，在成功、错误、取消时结束并恢复调用方上下文。不导出原始异常事件、查询、记忆正文、凭证、用户 ID、索引、URL 或任意 kwargs。观测失败不得阻断或重复业务执行。

工具通过 `asyncio.to_thread` 调用知识检索时，检索 Span 应是已有工具 Span 的子调用。两个并发记忆请求分别归属各自父调用。取消等待 OpenViking 时，调用方 Span 以取消结束；底层同步线程可能继续，不得声称后端已完成。

## 设计与契约影响

在 `veadk/tracing/` 增加小型内部 helper，固定操作名、安全记录结果，观测失败不影响业务，不配置导出器。复用 `trace.get_tracer`，不改变全局 Provider。helper 在调用期间激活 Span，finally 恢复上下文；关闭自动异常记录，只保留错误类型与状态，不把业务异常吞成成功。后端属性取配置的类型，不导出完整配置。结果归一化成功后才写数量。记忆检索捕获后端异常时先标失败，再保留既有空返回。`asyncio.to_thread` 已复制上下文，不增加并行传播协议。

公共签名、结果类型、后端参数、鉴权、重试和记忆隔离不变。没有新增持久化状态和部署配置。扩展双语 execution-tracing spec，明确三个边界及错误语义。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| FR-1 | T-1 知识检索 | AC-1 父关系、名称、实际 top_k、数量与原异常不变 | 本地 SpanExporter 的知识检索专项测试 | pass (local) |
| FR-2 | T-2 记忆检索 | AC-2 区分已处理失败与正常空结果 | 成功、空结果、失败、并发父关系、OpenViking 取消测试 | pass (local) |
| FR-3 | T-3 记忆保存 | AC-3 事件数量 / 会话、关联和保存参数不变 | 过滤、后端失败及取消测试 | pass (local) |
| FR-4 | T-4 采集保护 | AC-4 不含敏感正文；采集失败不改变业务调用与上下文 | tracer / span 故障 helper 测试及父关系集成测试 | pass (local) |
| FR-1–FR-4 | T-5 交付 | AC-5 双语文档与受影响回归门禁、记录实际 PR | 仓库本地专项 pytest、全文件 pre-commit；提交前同步基线 | pass (draft PR) |

测试入口：`tests/test_knowledgebase.py`、`tests/test_long_term_memory.py`、`tests/test_openviking_long_term_memory.py`、`tests/tools/builtin_tools/test_load_knowledgebase.py`；按现有 tracing 测试组织新增 helper 测试。使用仓库 `.venv`，命令为 `uv run --extra dev pytest`。fixture 不接真实服务，不使用凭证。线程取消使用受控阻塞后端，退出测试前完成清理。

## 风险与评审

后端内部阶段及部署环境 APMPlus 接收尚未验证。取消线程调用后远端可能继续，只测调用方边界并标取消，不标后端成功。全局观测未初始化时，无操作采集不得改变执行。不重复记录 Token / 成本，不推断未知内部阶段。

设计评审：pass（2026-10-10）。已核对公共边界、to_thread 上下文传播、既有捕获异常语义、属性白名单及双语需求一致性。无阻塞项；取消调用方不证明线程完成，验收保留此限制。评审后通过 TDD 进入代码和测试。授权来自用户现有 active goal，不推导新的部署权限。

## 本地实现证据（2026-10-10）

| 检查 | 结果与范围 |
| --- | --- |
| TDD | helper 测试最初因模块不存在失败。首轮边界失败是 fixture 初始化问题，不作为缺失 Span 的有效证据；修正隔离后端 fixture 后才验证公开方法。 |
| 检索 / Worker 专项 | 76 项通过，1 项可选依赖跳过；helper 行覆盖率 100%，综合分支覆盖率 98%。覆盖并发父关系、线程取消与显式清理、采集修改 / 结束故障、属性白名单及实际工具到检索的关联。 |
| 首次广回归 | fail：6607 项通过、16 项失败、59 项跳过、4 项预期失败、2 项收集错误（422.59 秒）。失败与错误均报告缺少 llama_index、openai_codex 或 anthropic；未删除测试或修改分类。 |
| 环境修复 | 安装仓库声明的 dev / extensions / codex / sandbox extras。Codex 二进制首次下载因 30 秒超时失败；仅对重试命令设置 UV_HTTP_TIMEOUT=180，退出 0。未修改全局配置。 |
| 修复后受影响回归 | pass：199 项通过，无跳过或错误，7 条现有依赖弃用警告（46.95 秒）。覆盖此前失败的 Harness / Codex 测试、两组 Sandbox 测试、检索 / 记忆 / 工具关联与 Worker 请求。 |
| 最终源码 / 安全审查 | pass：保留后端参数、过滤、正常空结果、异常与取消语义；没有新增 exporter / 配置或敏感正文采集。 |
| 基线与 hooks | 重新 fetch 后 origin/main 仍为 171d8d86，已完成 rebase 且为 HEAD 的祖先。保留完整 extras 的全文件 pre-commit 已通过 Ruff 和两项密钥扫描。 |
| 全量回归 | pass：6698 项通过、50 项跳过、4 项预期失败、88 条依赖警告，耗时 427.41 秒。跳过不证明相关行为。首轮中断无结果，仅确认进程不存在后重跑。本地 metrics 导出报告 localhost:8000 不可用，不证明远端可观测接收。 |
| 交付 / 部署 | 草稿 PR 已交付：[#1161](https://github.com/volcengine/veadk-python/pull/1161)，代码提交 e2c1e887。推送后已核验远端 PR 提交；没有合并或部署，APMPlus 接收与真实性能仍未验证。 |

证据：`/tmp/codex-retrieval-save-tests.log`、`/tmp/codex-veadk-retrieval-broad.log`、`/tmp/codex-veadk-complete-env-retry.log`、`/tmp/codex-veadk-complete-env-retest.log`、`/tmp/codex-retrieval-extras-final-hooks.log`、`/tmp/codex-veadk-complete-broad-resumed.log`。
