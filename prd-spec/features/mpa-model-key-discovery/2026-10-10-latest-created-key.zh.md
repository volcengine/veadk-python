# 选择最新创建的已有方舟 Key

[English](2026-10-10-latest-created-key.md)

- 变更 ID：mpa-latest-created-key；创建/修订：2026-10-10；状态：implemented。
- 前序：[按账号发现 Key](2026-10-10-account-ark-key.zh.md)。
- 组件：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-16。

## 背景和证据

`resolve_model_key` 当前在没有精确选择器且存在多个候选时拒绝创建。用户要求自动选择最新创建的 Key，保持一键创建。分页、账号核验、状态过滤和密钥处理已由发现适配器负责。只读元数据探测无法加载本地部署凭据，真实时间字段结构尚未验证。适配器将明确接受创建时间元数据，无法判断最新时失败；列表顺序不能证明创建顺序。

## 目标、非目标和场景

无需额外配置，按配置项目内候选 Key 的创建时间选最新。保留显式 ID/名称选择、通用智能体鉴权、CLI 显式模式和现有 Runtime 凭据。不创建 Key、不调用推理、不持久化明文、不迁移现有任务。

## 需求和设计

- FR-1：没有选择器且存在多个候选时，遍历现有有界分页，选择最大创建时刻。接受 `CreateTime`（兼容 `CreatedAt` / `CreationTime`）、正且有限的 Unix 秒/毫秒（包括数字字符串）或带时区的 ISO 8601，统一为 UTC。任何候选的元数据缺失/无效时，在 GetRawApiKey 前失败。恰好一个候选无需时间字段。
- FR-2：创建时间相同时选择字符串 ID 字典序最大者，与分页顺序无关；该规则用于稳定打破平局，不推断创建先后。显式 ID/名称优先且仍要求恰好一个匹配，包括重名时报错。非 Active Key 在时间比较前过滤；兼容缺少 Status 的旧响应，不宣称已核验其状态。
- FR-3：账号核验、凭据刷新、取消、有界重试、安全诊断和只向 Runtime 注入明文保持不变。重试重新发现 Key；部分部署后出现新 Key 时，现有请求哈希可能拒绝变化，不静默替换凭据。存量智能体不变。

影响文件：`managed/model_key.py`、`test_model_key.py`、双语 managed README 和 Studio 创建规格。不改 API 结构、前端、依赖或数据结构。时间解析属于适配器职责，选择器仍可选。

## 任务、测试和验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1 | T-1 | AC-1：跨页和不同时间格式选最新；异常元数据不读取明文 | 适配器回归测试，实现前失败 |
| FR-2 | T-2 | AC-2：保留显式覆盖、状态过滤和同时间稳定排序 | 反转列表顺序、较新禁用 Key、显式选较旧 Key 的适配器测试 |
| FR-3 | T-3 | AC-3：全部受影响回归与静态/安全检查通过，文档一致 | managed/CLI/auth 测试、Ruff、Pyright、Gitleaks、双语链接和空白检查 |

## 风险和恢复

最新 Key 不证明模型权限、IP 限制或推理可用性。真实账号返回的创建时间仍未验证；不支持的元数据明确失败，可显式指定选择器恢复。未完成任务期间创建新 Key 可能改变请求并触发现有哈希冲突。不引入隐式轮转或重试回退。

## 审查和批准

review-spec 不可用，直接审查：确认有界解析、稳定排序、选择器兼容、密钥隔离、取消及双语等价，无阻塞。用户批准：“账号下有多个key，选最新创建的那个吧”。该批准授权选择规则改动，不授权提交/推送/部署。前序保留历史选择决策，CON-16 和维护中的用户文档描述后续规则。

## 验证记录

2026-10-10；f7576c40 上的工作区范围。实现和回归结果如下。真实元数据探测：blocked，本地部署凭据不可用，在云请求前失败；未读取明文或变更云资源。前端/浏览器：not_applicable，无 UI 改动。全量 pre-commit 和全仓库回归：not_run，未要求提交；须执行全部受影响测试和修改文件检查。


- pass — 测试先行的适配器运行：35 个失败复现缺少最新选择/错误行为，29 个原用例通过；实现后全部 64 个适配器用例通过。
- pass — `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py tests/auth/veauth/test_ark_veauth.py -n 2 -q --no-cov --tb=short`：773 个通过，最终类型收窄修复后重跑。两个 worker 遵循仓库资源规则，仍有十条原有弃用警告。
- pass — 对 model_key.py 和 test_model_key.py 执行 `uv tool run --from ruff==0.11.12 ruff check`、`ruff format --check`；两文件执行 `uv tool run --from pyright pyright --pythonpath .venv/bin/python`：使用显式类型收窄替代仅运行时类型判断后，零错误。
- pass — Gitleaks v8.24.2 脱敏目录扫描全部 19 个本次修改/新增的源码及文档、双语需求/验收/任务标识与设计相对链接、`git diff --check`。
- blocked — 真实账号时间验证：本地部署凭据不可用，未获得 ListApiKeys 结果或明文 Key。字段别名和时间格式属于经过隔离测试的适配器输入，不宣称真实观测。
- not_applicable — 前端构建/浏览器和 Codex smoke：无 UI、生成 JavaScript 或 harness 改动。
- not_run — 全量 pre-commit/全仓库测试：未要求提交；全部受影响测试和定向检查已通过。

实现审查：比较全部候选时间，非 Active 记录不影响选择，显式选择无需时间字段，同时间排序不依赖列表顺序。错误文本不包含云元数据或明文。T-1–T-3 / AC-1–AC-3 在所述真实验证边界内完成。

## 提交准备（2026-10-10）

用户授权：“把当前的修改都提交吧”。仅提交，不推送或部署。已 fetch origin/upstream，再执行 `git rebase --autostash upstream/main`：上游基础分支已同步，自动暂存成功恢复。172 个修改/删除/未跟踪文件状态与同步前哈希一致，检查期间未改生产或测试文件。按用户授权包含已有 package-lock 改动；`npm ci --prefix frontend --dry-run --ignore-scripts --offline` 通过，未修改锁文件。

- pass — `uv run --extra dev pre-commit run --all-files`：Ruff 检查/格式化、硬编码凭据扫描及 YAML 密钥扫描。
- pass — 已改 Python 生产/测试文件执行 `uv tool run --from pyright pyright --pythonpath .venv/bin/python`：零错误/警告。
- pass — 同步后重跑前端完整测试：1,377 个 Node 测试及 65 个 Vitest 测试；重跑多 Bot/渠道/任务回归：162 个通过。同步及检查未改变源码/产物，此前构建、国际化、覆盖率、产物及隔离浏览器证据仍有效。
- fail，基线已有问题 — `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：6,933 个通过、53 个跳过、四个 xfailed、一个失败、55 个警告，耗时 412.63 秒。唯一失败为 `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`：期望 `text/markdown`，实际 `application/octet-stream`。写入实现及测试与 HEAD 逐字节一致，使用仓库 Python 环境运行隔离 `git archive HEAD` 基线可复现；本机 `mimetypes.guess_type("summary.md")` 返回 `(None, None)`。当前 writer 单独测试也复现，另 48 个用例通过。本提交未加入无关 MIME 实现/测试变更，不将全仓检查表述为通过；该结果未发现提交功能范围的回归。
- pass — 暂存差异空白检查及密钥钩子；本地 `.env` 保持忽略，未包含到提交。真实方舟/飞书/云验证及浏览器原生确认/IME 限制保持前述记录，跳过的测试不证明真实行为。
