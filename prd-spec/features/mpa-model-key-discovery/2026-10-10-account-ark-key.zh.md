# 部署账号方舟 Key 自动发现

[English](2026-10-10-account-ark-key.md)

- 变更 ID：mpa-model-key-discovery；创建/修订：2026-10-10；状态：implemented。
- 归属：托管 MPA 创建；契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-1/CON-16。

- 后续：[最新创建选择](2026-10-10-latest-created-key.zh.md)取代默认拒绝多个 Key 的规则；下文保留原实现记录。

## 背景和证据

内置配置目前在本地检查时解析 `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY`，需要明文配置且可能使用其他账号的 Key。现有 `get_ark_token` 支持 ListApiKeys/GetRawApiKey，但默认选第一把且可能包含原始错误。新增有界适配器复用无全局状态的签名请求工具，不改变通用智能体鉴权。ArkCLI 文档说明 ListApiKeys 返回掩码，GetRawApiKey 获取真实 Key：https://github.com/volcengine/ark-cli/blob/main/skills/arkcli-profile/references/arkcli-profile-keys.md。旧 ArkClaw 客户端支持缺少 Status 的 Id/Name，计数字段为 Total；当前 VeADK 支持 TotalCount。两者都不证明选中的 Key 能调用指定模型。

## 目标、非目标和场景

使用部署 AK/SK 或轮转 STS 自动读取现有方舟 Key；保留独立 CLI 显式私有配置。不创建/轮转 Key，不修改存量 Runtime 或通用智能体行为，不通过付费推理验证模型权限。本次云验证全部模拟。没有 Key 时由操作者在方舟创建；有多个匹配时要求精确选择。

## 需求

- FR-1：内置本地检查不需要模型密钥，不调用云接口，忽略旧模型 Key 环境变量覆盖。新增 `managed.model-key`，mode 为 `explicit`（CLI 默认）或 `ark`（Studio 默认）；可选互斥的 api-key-id/api-key-name，project-name=default。Studio 选择器使用 `VEADK_MPA_ARK_API_KEY_ID` / `VEADK_MPA_ARK_API_KEY_NAME`，它们是标识而非明文 Key。
- FR-2：Ark 模式只接受所选地域的全新 OpenAI 兼容方舟模板，拒绝环境覆盖模型 Key/provider/base。STS 核验后、资源变更前，使用相同的刷新及账号核验凭据源读取。遍历全部页面（每页 100，最多 100 页），校验总数/ID并去除重叠 ID。按精确 ID/名称选择，或要求恰好一个候选；零个/多个匹配失败。有 Status 时必须为 Active；兼容缺少 Status 的旧响应，不宣称已核验其状态。仅使用 GetRawApiKey.ApiKey，不使用掩码 Key 字段。
- FR-3：每次 HTTP 读取连接超时 10 秒、读取超时 30 秒。连接/超时、限流、暂时不可用最多尝试三次，异步间隔 0.2/0.5 秒。永久错误和格式错误立即失败。取消后停止新请求和变更；已运行的读取可在超时内结束，但结果被丢弃。每次尝试前刷新凭据，账号变化失败。不调用 CreateApiKey 或推理。
- FR-4：明文只在复制的内存 Profile 和授权的 Runtime 环境中，不进入日志、异常、配置摘要、任务/SQLite 记录或仓库文件。输出白名单操作/分类诊断。重试仍由现有部署请求哈希拒绝变更的 Key/配置；重新发现不静默绕过歧义。Runtime 保存的密钥归云平台管理。
- FR-5：保留独立 CLI 显式 Key/引用 Runtime/模板行为。测试后只删除本地 .env 中两个旧赋值，保留其他配置及文件权限。不改前端字段/构建产物或依赖。

## 设计和影响文件

新增 managed/model_key.py，修改 config.py、studio_profile.py、service.py 和诊断白名单。复用使用局部签名状态的 volcengine_signed_request，不使用全局状态签名器或通用 get_ark_token 默认选择。适配器返回新的 Profile。部署权限已包含 ark:ListApiKeys 和 ark:GetRawApiKey，客户自管角色须自行授权。选择不证明模型开通、IP 白名单或模型权限，这些仍是部署前置条件。configured=true 表示本地有效，不代表真实访问成功。API 响应类型和任务阶段不变。维护双语 managed README 与 Studio 组件契约。

## 任务和验收

T-1 / AC-1（FR-1/FR-5）：先写失败的加载/路由测试，再改本地配置；保留独立 CLI 测试。
T-2 / AC-2（FR-2/FR-3）：适配器覆盖 STS、分页、歧义、精确选择、旧/状态响应、畸形/空响应、暂时/永久错误、账号变化和取消。
T-3 / AC-3（FR-4）：服务调用顺序及安全注入测试；错误、诊断、摘要不含明文；重试保留原哈希冲突语义。
T-4 / AC-4（FR-5）：定向及全部 managed/CLI 鉴权回归、修改文件 Ruff/Pyright、双语文档/链接/空白审查、定向密钥扫描；安全移除旧本地赋值。真实云端和浏览器为 not_run：未授权云变更，且无 UI 改动。

## 风险和恢复

没有/多个可读 Key 或读取权限缺失时在 checking 阶段停止；配置选择器或修正方舟权限。Active Key 仍可能无模型访问权限或被撤销；不承诺 Runtime 自动刷新/轮转。Key 明文变化可能阻止未完成任务重试，不静默替换凭据。存量智能体不变。需要手动模式时可使用独立 CLI 私有配置，不把明文恢复进受版本控制的文件。

## 审查和批准

直接审查（review-spec 不可用）：边界一致，无新增依赖，读取/取消有界，云错误脱敏，旧行为兼容和双语语义明确，无阻塞。用户在“帮我这么改，然后需要删掉这个.env文件是不是”批准了按账号自动获取方案。该批准不授权提交/推送/部署。

## 验证记录

日期：2026-10-10。验证范围：f7576c40 上的工作区差异；未提交/推送/部署。

- pass — 测试先行的加载/路由检查复现三个缺失 Key/默认值失败（82 个原用例通过）；新增适配器测试在模块存在前收集失败。
- pass — `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py tests/auth/veauth/test_ark_veauth.py -n 2 -q --no-cov`：739 个通过，覆盖发现、模拟完整 Studio 创建、显式 CLI/通用方舟鉴权兼容及 IAM 权限。两个 worker 遵循仓库默认资源预算。.env 清理后重跑也通过。
- pass — `uv tool run --from ruff==0.11.12 ruff check <11 changed Python files>` 和 `ruff format --check` 全部通过。`uv tool run --from pyright pyright --pythonpath .venv/bin/python <11 changed Python files>` 零错误。test_iam.py 基线副本复现原有九个类型错误；通过最小的测试类型/断言和类型化 Worker 构造修复，未改生产 IAM。
- pass — `uv build --wheel --no-build-isolation --out-dir <temporary directory>` 与 wheel 检查：包含新增 model_key.py 和无全局状态签名工具，排除 .env。未在工作区新增发布产物。
- pass — Gitleaks v8.24.2 脱敏扫描全部本次修改/新增的版本控制范围文件、`git diff --check`、双语需求/验收标识及新增相对链接审查。
- pass — 私有 .env 清理只移除 VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY 和 VEADK_MPA_CONFIG_PGPASSWORD 赋值，保留其他行和文件权限，确认仍被忽略且未跟踪。未打印值或复制到证据。
- not_applicable — 前端构建/测试和 Codex smoke：无前端、生成 JavaScript 或 harness 改动。原 HTTP 结构和部署 Runtime 请求由 Python 路由及模拟创建测试覆盖。
- not_run — 浏览器/真实方舟/模型推理/云部署：无 UI 改动，未授权真实云验证。实际账号权限、Key 可用性、模型开通及网络/IP 限制仍未实测。
- not_run — 全量 pre-commit 和全仓库测试：未要求提交；已执行定向密钥扫描、静态检查及全部受影响测试。

实现审查：明文不进入持久化/结果/错误；局部签名避免跨请求全局状态变更；刷新凭据保留账号核验；取消后无后续请求；原显式模型鉴权不变。T-1–T-4 与 AC-1–AC-4 已完成，真实验证限制如上。

## 提交准备（2026-10-10）

用户授权：“把当前的修改都提交吧”。仅提交，不推送或部署。已 fetch origin/upstream，再执行 `git rebase --autostash upstream/main`：上游基础分支已同步，自动暂存成功恢复。172 个修改/删除/未跟踪文件状态与同步前哈希一致，检查期间未改生产或测试文件。按用户授权包含已有 package-lock 改动；`npm ci --prefix frontend --dry-run --ignore-scripts --offline` 通过，未修改锁文件。

- pass — `uv run --extra dev pre-commit run --all-files`：Ruff 检查/格式化、硬编码凭据扫描及 YAML 密钥扫描。
- pass — 已改 Python 生产/测试文件执行 `uv tool run --from pyright pyright --pythonpath .venv/bin/python`：零错误/警告。
- pass — 同步后重跑前端完整测试：1,377 个 Node 测试及 65 个 Vitest 测试；重跑多 Bot/渠道/任务回归：162 个通过。同步及检查未改变源码/产物，此前构建、国际化、覆盖率、产物及隔离浏览器证据仍有效。
- fail，基线已有问题 — `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`：6,933 个通过、53 个跳过、四个 xfailed、一个失败、55 个警告，耗时 412.63 秒。唯一失败为 `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`：期望 `text/markdown`，实际 `application/octet-stream`。写入实现及测试与 HEAD 逐字节一致，使用仓库 Python 环境运行隔离 `git archive HEAD` 基线可复现；本机 `mimetypes.guess_type("summary.md")` 返回 `(None, None)`。当前 writer 单独测试也复现，另 48 个用例通过。本提交未加入无关 MIME 实现/测试变更，不将全仓检查表述为通过；该结果未发现提交功能范围的回归。
- pass — 暂存差异空白检查及密钥钩子；本地 `.env` 保持忽略，未包含到提交。真实方舟/飞书/云验证及浏览器原生确认/IME 限制保持前述记录，跳过的测试不证明真实行为。
