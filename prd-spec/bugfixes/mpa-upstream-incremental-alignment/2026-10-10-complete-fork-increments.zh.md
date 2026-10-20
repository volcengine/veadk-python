# 在官方 main 补齐 fork 的 MPA 增量

- 变更 ID：`mpa-upstream-incremental-alignment`；日期：2026-10-10；状态：implemented。
- [English](2026-10-10-complete-fork-increments.md)。
- 契约：[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)。

## 背景与证据
上次官方贡献分支 `feat/mpa-studio-upstream-alignment-20261009` 的末端是 `033b2711`；官方 PR #1156 以 `171d8d86` 合入。fork main `035387d1` 的历史不同。官方 PR #1160 直接基于 `171d8d86`，已包含 fork PR #23，但漏了 PR #22 的 MPA 详情仅基本信息。整体复制 fork 文件树会删掉官方较新的 Codex 等改动。

增量核对范围为 fork 对齐合并 `ef0ad519` 至 `035387d1`，与官方基线及贡献 HEAD `80fd1e19` 对比，以功能覆盖为准，不把每个历史提交都当作未应用的改动。

| fork 改动 | 本次处理 |
| --- | --- |
| PR #21：手填 Runtime 名称、描述、三步创建、镜像默认值、名称校验、TOS 提示 | 已在官方 PR #1156 中，保持。 |
| PR #22：MPA 详情仅基本信息、同步归一化焦点、停止隐藏 Profile 请求 | 迁入生产代码、回归测试、文档并重建发布资源。 |
| PR #23：STS 账号解析、IAM 准备及 Python 3.10 超时、网络发现/描述/子网顺序、标准 APIG、独立 Worker 创建/默认值/名称、技能空间描述、部署诊断 | 已在 #1160 中，保持并运行相关回归。 |
| lockfile 修复 | 有效内容已在官方 main 中，保持。 |
| 官方密钥扫描排除与取消时 PID 竞争修复 | 保留官方实现；fork 缺少这些贡献时修复。 |
| 官方 BytePlus sidecar 行为和 SDK 功能 | 保留；与 fork 的差异不属于 fork 新增功能。 |

## 目标、场景与需求
FR-1 / AC-1：上次贡献以来 fork 的全部有效增量在官方贡献中保留；不整体合并 fork/main，不反向撤销官方功能。
FR-2 / AC-2：选择 MPA、恢复任意隐藏页面或从普通智能体切换时，在副作用前仅渲染基本信息；不请求 Agent View/Profile/会话配置，不执行 Profile 操作。普通智能体的导航和更新行为保持。
FR-3 / AC-3：源码附带包测试、双语契约及历史设计；生成资源与合并后的官方源码一致。
FR-4 / AC-4：保留官方密钥扫描和取消修复，运行当前仓库检查并如实记录。
非目标：重设计后端 API、聊天改动、创建云资源、部署、合并官方 PR、改写 fork main、关闭其他 PR。

## 设计与影响文件
将已审查的 PR #22 迁入 `frontend/src/ui/AgentWorkspace.tsx`，按类别和请求页面同步计算有效页面。保留隐藏控制面实现及清理逻辑，仅由所属页面触发。无新增依赖、数据迁移、鉴权或并发契约变化。更新 `frontend/tests/mpaBasicDetails.test.tsx`、源码契约测试及包测试命令；在双语组件规范和 README 追加仅基本信息约束，保留官方文档。迁入历史 PRD 双语文件，其有日期的云端证据仅为历史记录，不代表此次整合验证。从合并后的源码重建 `veadk/webui`。

## 任务与验证
T-1（FR-1）：逐个核对 `ef0ad519..035387d1` 的路径，排除生成哈希及历史文档纯格式差异，对剩余差异逐项说明。
T-2（FR-2）：迁入组件回归，在修改生产代码前验证失败，再迁入实现和源码契约断言。
T-3（FR-3）：前端测试、构建、i18n、资源引用、组件覆盖率及真实组件配合模拟网络的本地浏览器检查。
T-4（FR-4）：定向创建/CLI 测试、默认双 worker Python 回归、获取并 rebase 官方基线、全文件 pre-commit 及差异/文档审查后，按授权提交推送。
浏览器场景：MPA 和普通导航、隐藏焦点、切换、Runtime 正常/加载/空/失败、只读、窄窗口、键盘焦点。新增输入/IME、写入取消及重试不适用，因为本次不增加输入或写入；既有创建/sidecar 回归仍须运行。不执行真实云端写入。

## 风险与审查
风险：从 fork 整体替换文件可能覆盖官方增强。处理：仅迁入核对过的 PR #22 行为，用内容比较确认保留的创建路径。资源差异来自必须提交的哈希构建产物，不是新增手写功能。
因 `review-spec` 不可用已直接审查：边界、副作用顺序、清理、兼容、安全、测试和双语一致性无阻塞。引用的前端设计 skill 本地缺失，采用既有 SPEC/Foundation 规范及直接审查。本次不重设计外观或新增组件。
批准：用户于 2026-10-10 明确要求对比上次贡献并带上 main 全部新增功能，批准本次有限整合；此前准备并推送官方 PR 的授权继续有效。

## 交付记录
以下检查针对 `80fd1e19` 之上的整合差异，英文版同步记录证据。不宣称本次云端验证。

2026-10-10 验证记录，针对 `80fd1e19` 之上的整合差异：
- **pass**：逐路径核对 `ef0ad519..035387d1` 的 83 个非生成文件，全部有效新增源码/测试/契约/设计与 fork main 一致。例外：README 保留官方文档并追加双语说明；`test_tasks.py` 保留官方 PID 竞争修复；四份历史 PRD 仅末尾空白不同。保留官方密钥扫描排除、BytePlus 行为和 Codex SDK 文件。
- **pass**：先运行回归：`npm --prefix frontend exec -- vitest run --root frontend tests/mpaBasicDetails.test.tsx` 在迁入生产实现前 10 个用例全部失败；迁入后 10 个全部通过。
- **pass**：`npm --prefix frontend test`：1,377 个 Node 和 65 个 Vitest 测试。
- **pass**：`npm --prefix frontend run build`（TypeScript 及 app/widget 构建）；`npm --prefix frontend run check:i18n`；`npm --prefix frontend run test:webui-assets`（113 文件、350 引用）。
- **pass**：`npm --prefix frontend run test:harness-sidecar-coverage`：语句 98.55%、分支 94.44%、函数/行 100%，达到既有阈值。
- **pass**：`npm --prefix frontend exec -- vitest run --root frontend tests/mpaBasicDetails.test.tsx --coverage --coverage.include=src/ui/AgentWorkspace.tsx --coverage.reporter=json`：变更可执行语句起始行覆盖 7/7（100%），不是整个组件覆盖率。
- **pass**：本地内置浏览器使用真实 `AgentWorkspace` 与模拟 fetch：MPA 仅基本信息及恢复 Profile/会话焦点、聊天回调、普通导航/集成页、切回 MPA、Runtime 正常/加载/失败、空环境变量及只读、Tab 键盘焦点、390px 窗口（body 宽 390px），无隐藏控制面请求。集成发现失败为模拟结果，不代表实际云端。临时夹具、标签页、窗口覆盖及服务已清理。
- **pass**：`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py -q`：678 passed。首次附加了不存在的测试路径而未执行测试，已按上述命令修正。
- **not_applicable**：新增 Python 代码的定向 Ruff/Pyright（此次整合没有修改 Python）；仍须执行全文件 pre-commit。未运行真实云端创建/部署及新增 IME/写入流程，原因见上文。
- **fail**（未修改的基线）：`uv run --extra dev --extra codex --extra extensions --extra sandbox pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：6,869 passed、53 skipped、4 xfailed、1 failed，耗时 480.71s。按仓库默认使用两个 worker，通过项目声明的 extras 在仓库本地环境准备可选依赖，无依赖文件变更。唯一失败为 `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`：本地 Python 3.10/macOS 的 `mimetypes.guess_type("reports/summary.md")` 未返回类型，得到 `application/octet-stream`，而测试期待 `text/markdown`。该测试及整个 `frontend/server/runtime_artifacts/` 实现与官方 main 相同。此无关基线问题仍是验证限制，不算通过。
- **pass**：重新获取 `origin/main` 和 `upstream/main`，仍为 `035387d1` 和 `171d8d86`；`git -c rebase.autoStash=true rebase upstream/main` 显示已最新，并恢复全部整合改动。
- **pass**：双语链接/需求 ID/引用标识和 scoped diff 空白检查。直接最终审查没有发现漏掉增量、新增依赖、后端/聊天变更或覆盖官方修复。
- **pass**：同步后再次通过 `uv run --no-sync --extra dev pre-commit run --all-files`、`uv run --no-sync --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py -q`（678 passed）、`npm --prefix frontend test`（1,377 Node / 65 Vitest）。`--no-sync` 保留仓库本地已准备的可选依赖。提交/推送元数据以 Git 和官方 PR 为准。

| 需求 | 任务 | 验收 | 证据 |
| --- | --- | --- | --- |
| FR-1 | T-1 | AC-1：全部有效增量保留 | 83 路径核对及记录的官方例外：pass。 |
| FR-2 | T-2 | AC-2：MPA 仅基本信息，普通行为不变 | 10 回归用例及本地浏览器：pass。 |
| FR-3 | T-3 | AC-3：测试、文档及匹配资源 | 前端/构建/i18n/资源/覆盖率及双语审查：pass。 |
| FR-4 | T-4 | AC-4：保留官方修复并如实执行检查 | rebase、pre-commit、定向测试：pass；全量回归记录一个未修改的 MIME 基线失败。 |
