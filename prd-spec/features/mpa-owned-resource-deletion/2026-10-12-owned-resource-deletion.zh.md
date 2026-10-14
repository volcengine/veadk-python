# MPA 独占资源删除

[English](2026-10-12-owned-resource-deletion.md)

变更 ID：`mpa-owned-resource-deletion`。日期：2026-10-12。状态：implemented。
契约：[Studio MPA](../../../specs/studio-mpa-control-plane/README.zh.md)、[创建流程](../../../specs/mpa-runtime-provisioning/README.zh.md)。

## 证据和范围
MPA 删除预览先查询 Profile，再查询会话。Profile 鉴权失败导致无法确认；详情页隐藏了包含错误的侧栏。当前删除只清理会话和 Runtime。管理部署记录已有 Worker/Skill Space ID、归属标记及对应云资源标签。

## 目标、场景和需求
- FR-1：通用 Runtime 删除不变。MPA 删除不查询 Profile。运行中的生命周期操作和会话仍阻止删除；失败操作为终止状态，本身不再阻止删除。会话查询失败必须返回错误，不得当作零会话成功。
- FR-2：仅删除受管且独占的沙箱模板和 Skill Space。核验部署 Runtime 绑定、受管标记、账号/地域/项目、归属标签，以及其他部署/Runtime 是否引用。共享、导入或无法证明归属的资源保留，并在预览中解释。发现查询失败或归属冲突时安全失败。
- FR-3：按空闲会话、沙箱模板、Skill Space、Runtime 顺序清理。在现有账号/地域 advisory lock 下持久保存清理意图和完成状态。清理时资源已不存在允许重试；其他错误保留 Runtime 供重试。数据库、Workspace、网络、APIG、身份、存储及无关数据保留。
- FR-4：立即打开确认弹窗并显示加载状态。预览和执行错误在弹窗内显示，支持重试预览。取消/卸载终止预览；晚到结果不得重开或覆盖弹窗。执行时重新检查服务端授权、会话和资源归属。

## 设计和影响文件
使用已授权 Runtime 的服务端注册库 URL 和当前 Provider 凭据，不解析创建配置，也不创建前置资源。增加受管删除服务，给现有预览路由接入资源计划回调。Runtime/Tool/Skills SDK 调用遵循 Provider 和地域。缺少注册库 URL/记录时保留相关资源；部署记录不匹配时阻止清理。记录删除状态，防止创建流程在清理进行中或完成后重建资源。预览以兼容方式增加保留资源及资源 ID；`profile` 保持 null。UI 沿用现有确认弹窗。
影响文件：managed 删除/数据库/云适配器；Studio BFF、cli_frontend；AgentWorkspace/client/i18n；定向 Python 和 React 测试；发布产物；双语组件契约与 frontend README。

## 任务和验收
| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1 | T-1 移除 Profile 依赖 | AC-1 不调用 Profile；通用不变；保护运行任务 | BFF 与 Studio RBAC 回归 |
| FR-2/FR-3 | T-2 独占清理 | AC-2 删除独占资源；保留共享/归属不明资源；安全重试部分失败 | managed 删除离线测试 |
| FR-4 | T-3 可见状态 | AC-3 加载/错误/重试/取消/晚到事件正确 | React 测试及浏览器 fixture |
| 全部 | T-4 同步与验证 | AC-4 本地化发布构建及必要检查 | frontend test/build、定向 pytest、Ruff、Pyright、i18n/assets |

## 风险和边界
外部操作者可能绕过 advisory lock 修改引用；清理前重新读取云端状态。云接口可能拒绝删除被引用资源；应返回错误并保留 Runtime，不能报告成功。会话可见范围仍由已认证 Runtime API 决定，不能宣称全局会话已检查。取消 Profile 查询不绕过会话鉴权。验证使用隔离模拟及浏览器 fixture，不删除用户云资源。现有创建/操作存储之间没有跨系统事务。

## 评审和批准
review-spec skill 不可用，已直接评审归属、Provider 隔离、部分失败、并发、密钥、兼容性、双语等价及测试。用户于 2026-10-12 明确批准本方案。无设计阻断项。设计批准不授权提交、推送或部署。

## 验证记录
范围：d6065d6e 上的本地改动，2026-10-12；未提交或推送。

- pass：先复现失败（资源模块未实现、Profile 依赖、弹窗错误不可见），再实现；AC-1 至 AC-3 的离线和 React 用例通过。
- pass：`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/frontend/server/mpa/test_runtime_profile_client.py tests/cli/test_studio_rbac.py`，1004 passed，使用 2 个 worker。
- pass：后续归属复核、Provider SDK 请求和引用变化补充验证：完整资源清理文件 17 passed；最后删除相关定向选择 21 passed。覆盖执行顺序、共享保留、导入/旧资源、归属冲突、发现失败、部分重试、NotFound、取消意图、国内/海外请求、伪造客户端 ID 以及预览资源计划。
- pass：`npm --prefix frontend test`，1379 Node + 78 Vitest = 1457 passed；`npm --prefix frontend run build`、`check:i18n`、`test:webui-assets`（113 文件、350 引用）和 `git diff --check`。
- pass：真实浏览器中的隔离模拟验证：错误、重新检查、清理失败、重试成功、加载、Escape 取消/焦点返回、晚到结果不重开、通用原确认、390×844 窄窗口。浏览器不操作真实云资源。
- pass：按仓库 `.pre-commit-config.yaml` 的 Ruff 0.11.12，使用 `uvx --from ruff==0.11.12 ruff check --config pyproject.toml <changed-python-files>`；新增/受影响 managed 模块 Pyright 为 0 errors；`uvx pre-commit run gitleaks --files <changed-files>` 通过。
- fail（既有基线）：`uvx pyright --pythonpath .venv/bin/python frontend/server/mpa/routes.py veadk/cli/cli_frontend.py` 有 49 条既有诊断；与 HEAD 两文件基线逐项比较，没有新增诊断。未扩大范围清理历史问题。
- not_run：真实云删除（不使用用户资源验证）；仓库全部 Python 测试（本次选择所有 MPA managed 和受影响 Studio 权限/控制面测试）；完整 pre-commit（未请求提交）。
- not_applicable：原生 IME（无输入框改动）。本地未安装 Ruff/Pyright，通过临时工具环境验证，未修改全局配置。AC-4 的发布产物、文档和针对性检查完成；全文件 Pyright 保留已确认的历史基线限制。

剩余边界：移除 Profile 查询不会绕过会话鉴权；会话接口失败仍阻止删除并显示原因。云端实际清理行为尚未做实时验证。外部引用修改不受注册库锁约束；云删除与注册库保存之间无法提供跨系统事务。

## 会话身份补正（2026-10-12）

用户实测预览返回 `x-user-id header is required`（HTTP 422）。之前会话 transport 只传 Bearer，遗漏用户身份。沿用已批准 FR-1/FR-4 范围：预览和实际删除的会话查询/清理必须传 Studio 服务端已认证的 `owner_id`，与聊天/定时任务一致；不采信浏览器伪造的 `x-user-id`。Runtime client 增加可选 `user_id` 参数，未提供时保持原调用兼容，通用删除不变。评审已核对调用身份、兼容性和错误传播；增加 client 请求头及 BFF/删除执行的反伪造回归测试。验证：先复现 2 条失败回归后修复；删除定向 22 passed；`uv run --extra dev pytest -n 2 -q tests/frontend/server/mpa tests/cli/test_studio_rbac.py` 为 242 passed；Ruff、Runtime client Pyright（0 errors）、Gitleaks 和 diff whitespace 均 pass。通用删除未进入 MPA 会话调用。真实云删除 not_run；本轮无前端代码改动，因此无需重建已匹配的前端产物。

## 预览耗时补正（2026-10-12）

用户实测停在检查状态；当前服务根页面在 0.003 秒内返回 HTTP 200，表明服务仍响应。已确认的代码瓶颈是 Runtime 详情串行读取，以及每次 SDK 调用重复核验 STS；尚未通过逐步骤日志证明本次最慢的具体调用。沿用已批准 FR-2/FR-4，保持完整引用核验，详情分批最多 4 个并发。仅删除上下文可启用同一凭据的请求内身份缓存；凭据变化时重新核验且账号变化继续拒绝，创建流程默认逐次核验不变。预览整体限时 25 秒（早于前端 30 秒），超时返回结构化 `mpa_delete_preview_timeout`（HTTP 504）供重试；删除预览的同步授权读取移入线程，避免阻塞事件循环。补充限时、并发、默认兼容、凭据轮换/账号变化回归，并直接评审边界和中英文等价性。未增加真实云资源删除验证。验证（2026-10-12，d6065d6e 上的本地差异）：pass — `uv run --extra dev pytest -q tests/integrations/mpa_managed/test_deletion.py tests/frontend/server/mpa/test_runtime_profile_routes.py tests/integrations/mpa_managed/test_runtime_deployment_edges.py tests/integrations/mpa_managed/test_byteplus.py`（106 项通过）；`uv run --extra dev pytest -q tests/cli/test_studio_rbac.py -k 'delete'`（7 项通过）。覆盖 Python 3.10 超时取消。pass — 固定版本 Ruff；runtime/deletion 的 `uvx pyright --pythonpath .venv/bin/python`（0 错误）；Gitleaks；差异空白检查。完整 routes/CLI Pyright：fail，仍为基线 49 条错误，新增 0 条诊断。not_applicable — 重新构建前端/重跑浏览器夹具，本次补正没有修改前端源码或响应结构。not_run — 真实云资源删除、重启后的真实预览耗时、全仓测试和完整 pre-commit（未要求提交）。已有浏览器状态、错误和重试验证仍适用。取消无法终止已经运行的同步 SDK 线程；此类预览工作仅为只读，预览不会执行删除。
