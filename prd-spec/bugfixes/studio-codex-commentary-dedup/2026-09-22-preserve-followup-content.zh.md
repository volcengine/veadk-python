# MPA 去重时保留不同的补充内容

[English](2026-09-22-preserve-followup-content.md)

## 元信息与证据
ID：`mpa-preserve-followup`；日期：2026-09-22；状态：implemented。
替代 [Codex 所有权](2026-09-22-studio-codex-commentary-dedup.zh.md) 和 [A2A 最终答案所有权](2026-09-22-mpa-a2a-final.zh.md) 中宽泛的过滤规则；保留最终事件投影、wrapper 处理和 MPA 合并。
隔离审查复现三项问题：通用智能体 delegate 完成后的不同文本消失；包含答案及警告的 commentary 整段被删；A2A 桥接不比较内容就丢弃 sandbox final 后的所有外层文本。用户明确授权修正这些问题。

## 需求与设计
- FR-1：将通用 Codex delegate 投影/活动恢复到远端基线行为。删除通用答案所有权、子串过滤及相应过时测试，补充内容保留回归。不改变普通 ADK/原生 MPA 协议。
- FR-2：A2A 桥接按任务记录成功且非空的 sandbox final 文本，只删除去除首尾空白后完全相同的完整答案文本 part。保留推理、不同/扩展文本、partial 增量、工具/错误和元数据；未知/失败/空 final 不建立参考。保留 sandbox event-ID 回放去重。不缓冲流，新增状态仅为任务局部参考文本。
- FR-3：仅明确启用的 MPA A2A 投影标记最终答案所属 turn。合并展示仅在其他片段拼接后的完整答案与已知 sandbox final 相等时隐藏该片段的答案文本。不修改原 turn，不删除推理/工具/附件。后续增量扩展该片段时，完整原文重新显示。这避免永久丢失前缀，无需缓冲即可隐藏完全相同的流式副本。反馈指向可见答案，而非隐藏副本。用户/系统边界隔离分组。
- FR-4：保留 MPA 单一底栏和用量统计。包含正文的用量/进度事件仍需进入渲染，空控制事件不得擦除既有预览。不改变鉴权、接口路由、云部署、持久化 schema 或通用智能体分组。

## 任务与验收
T-1/AC-1：先增加失败测试，覆盖通用补充文本、混合 commentary、后端不同文本/推理/完全重复/partial/任务隔离，以及 MPA 展示的完全重复/扩展/实时历史/反馈。
T-2/AC-2：删除过时的通用过滤，实现后端严格相等比较与不破坏原文的 MPA 展示去重；同步双语 runtime diagnostics CON-8/CON-11 及工具活动契约。
T-3/AC-3：相关前端/Python 测试、完整前端套件/构建/产物、Ruff/Pyright、密钥扫描、使用真实 projector/分组/Blocks 的浏览器回放；实际服务生效情况单独记录。后端重启会丢失本地 A2A 会话索引，需先明确安排。

## 评审与风险
review-spec 不可用，已直接评审源码/契约、检查双语一致，无阻塞。用户“修正吧”授权本次修正。流式文本与最终答案相等时仅在派生视图隐藏；扩展后完整重现。不重建 Runtime 缺失历史。通用智能体有意保持原有工具 commentary 行为。失败/取消不擦除不同的部分输出。既有轨迹/复制/分享处理函数不变。

## 验证
2026-09-22 在基于 `3bbd260a` 的工作区差异上验证。T-1 至 T-3 已实现并评审。通用工具实现及测试恢复到 `origin/main`，新增内容保留套件替代此前宽泛过滤断言。严格相等的视图过滤可逆，保留非文本 block 及可见答案反馈目标。

- `pass`：红灯基线复现七项后端失败；前端反例复现通用补充文本/commentary 丢失和缺少限定范围的 final 元数据。测试修正了一处断言：检查拼接文本，而非强制正文位于独立 block。
- `pass`：`uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q` — 126 项通过，五项既有 SDK 弃用警告。
- `pass`：`npm --prefix frontend test` — 1,298 项 Node 和 25 项 Vitest 测试，含六项新增内容保留场景与原有通用 Codex 回归。
- `pass`：`npm --prefix frontend run build` 与 `npm --prefix frontend run test:webui-assets`；TypeScript 和 app/widget 构建通过，104 个文件、248 条引用。保留既有 chunk 大小警告。
- `pass`：对 `veadk/cli/runtime_a2a_stream.py` 与 `tests/cli/test_runtime_a2a_stream.py` 执行 Ruff 0.11.12 check/format 和 Pyright，类型错误/警告均为零。通过临时 `uv run --with` 工具执行，未改依赖或全局设置。
- `pass`：隔离真实浏览器回放，使用实际 Python 桥接投影的模拟事件、真实 TypeScript 投影/分组与 Blocks。完全相同的 final/前缀副本只显示一次；扩展后完整显示原前缀与独有警告。无浏览器错误，临时页面/服务已清理。这是模拟数据，不是真实云端生成。
- `pass`：限定文件 gitleaks、双语/契约评审及 `git diff --check`。
- `not_run`：后端生效及真实云生成；等待用户确认重启，因为重启会清空当前进程内的 A2A 会话索引。代码测试不代表 8000 端口服务已生效。
- `not_applicable`：新增布局/输入法/键盘行为、无关 SDK/sidecar 变更；渲染结构与输入控件不变。未提交或推送。
