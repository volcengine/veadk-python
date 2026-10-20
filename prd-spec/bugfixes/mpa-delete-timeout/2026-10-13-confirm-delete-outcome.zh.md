# MPA 客户端超时后确认删除结果

[English](2026-10-13-confirm-delete-outcome.md)

- Change ID：`mpa-delete-timeout`
- 创建/修订：2026-10-13
- 状态：implemented
- 契约：[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)，CON-30a

## 证据、目标与范围

MPA 删除使用 `deleteRuntime`，沿用普通 `apiFetch` 的 30 秒超时。服务端复核会话和资源引用，先删除独占模板/Skill Space，再删 Runtime。浏览器超时不会取消这些后台副作用。一次报超时后，已确认 Runtime 返回 NotFound、Skill Space 不再存在；未独立查询模板。没有从日志恢复准确耗时/阶段。

FR-1：仅明确选择的 MPA 删除使用 180 秒请求超时。通用智能体删除保留 30 秒及既有行为。
FR-2：TimeoutError 后，对同一 Runtime ID/地域执行一次只读、不缓存、限时 30 秒的确认，经过智能体管理授权 BFF。仅云端明确 Runtime NotFound 且完整 ListRuntimes 不存在时报告成功。授权产生的 404、权限拒绝、网络错误、格式错误、重复 token 或超出分页预算都不能视作删除成功。仅在 ListRuntimes 可见的 Runtime 仍然存在。
FR-3：若确认仍存在或无法确认，保留本地化结果待确认提示及既有错误/重试 UI。不自动重复 DELETE。非超时删除失败保留原错误。

不修改创建、公共超时、异步任务体系、删除顺序、Profile 查询或通用智能体行为；不购买资源、迁移或修改镜像。Runtime 不存在只能确认目标 Runtime 结果，不等于独立核验外部操作导致的其他资源清理。

## 设计与受影响文件

增加小型只读后端模块和 `/web/mpa-runtime-deletion-status?runtimeId=...&region=...`，返回 `{deleted: boolean}`，设置 `Cache-Control: no-store`。要求当前智能体管理权限。存在的 Runtime 使用既有授权核验；授权产生的 HTTP 错误不会进入资源缺失分支。若 GetRuntime 返回结构化 Runtime 特定 NotFound，则用同一部署凭据、提供商及地域完整扫描分页，设置分页上限。不返回资源/环境数据或原始异常。接口超时和无法确认均返回安全明确错误。云端 GetRuntime 隐藏但仍在列表的 Runtime 不能误判成功。

客户端复用 requestSignal/apiFetch 与既有确认 UI。仅 MPA 的 catch 处理 TimeoutError，核验布尔结果，仅 true 时完成原删除 promise。false/查询失败用本地化文案提示稍后刷新检查。测试使用模拟超时和云响应，不实际删除。

文件：`frontend/src/adk/client.ts`、双语 ADK 文案、`frontend/server/mpa_deletion_status.py`、`veadk/cli/cli_frontend.py` 路由挂载、前端可执行客户端测试、后端路由/归属/分页测试；双语 PRD/spec、frontend README 与 WebUI 构建资源。不改布局/CSS/图标；视觉基准为现有确认弹窗的加载/错误/重试/键盘行为。

## 任务与验收

- T-1 / FR-1 / AC-1：先写 MPA 180 秒、通用 30 秒回归；通用请求不调用结果确认。
- T-2 / FR-2 / AC-2：实现授权、有界状态查询，覆盖结构化/包装 NotFound、分页缺失/存在、查询失败、错误分页、取消和无写操作。
- T-3 / FR-3 / AC-3：核验确认完成、待确认/仍存在、错误 payload、权限和非超时失败；完成已有删除/UI 回归、构建与隔离浏览器检查。

## 审查、授权、风险与验证

用户于 2026-10-13 通过“改下”批准 MPA 专属超时/结果确认方案。`review-spec` 不可用，直接审查确认双语等价、通用智能体与清理顺序不变、有界读取及失败关闭行为，无审查阻塞。安全审查补充有界私有确认上下文：仅登记服务端已授权的 MPA 删除尝试，按 Studio 用户/Runtime/地域隔离，保存当前部署凭据的哈希。最多 1024 条，保留一小时；凭据及哈希均不返回客户端。上下文缺失、服务重启或凭据轮换只能返回待确认，不能成功。云查询后复核凭据，发现查询中途账号变化。这不是持久删除任务或新的写协议。未授权真实云删除、提交、推送、部署或重启 Studio。

云列表具有最终一致性，无法保证跨服务事务式清理。只读确认不能推断外部操作者删除资源的细节。账号改变/授权失败不能静默报告成功。旧文件静态错误需对照基线，不能隐藏。实际验证结果记录如下。必需检查：受影响 Python 测试、改动文件 Ruff/Pyright、`npm --prefix frontend test`、build/国际化/资源引用、隔离浏览器及仓库配置密钥扫描。不影响 harness/进程契约。

## 交付审查与验证（2026-10-13）

T-1–T-3 / AC-1–AC-3 已实现。审查确认客户端仅 MPA 启用，通用 POST/超时不变、不重复删除、仅结构化缺失确认、完整有界分页、凭据/用户隔离及部分清理语义保留。Python >=3.11 使用标准库超时，较早支持版本使用现有 async-timeout 依赖，没有新增依赖。未修改创建、Profile、Runtime 镜像、schema 或删除顺序。现有 `frontend*` 包发现规则会包含新服务端模块。

验证范围：基于 `71175c68636dc5b951e9804eb292d85402511e68` 的本次删除修复，保留工作区已有 PG/名称/OV 改动。修复前前端可执行回归失败；后端测试最初因状态模块尚不存在而收集失败。模拟云操作及隔离浏览器响应与真实验证明确分开。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| Python 删除/角色回归 | pass | `uv run --extra dev pytest tests/frontend/server/test_mpa_deletion_status.py tests/integrations/mpa_managed/test_deletion.py tests/cli/test_studio_rbac.py -q --no-cov`：最终追加负例前 210 项通过。 |
| 最终确认单元/路由测试 | pass | `uv run --extra dev pytest tests/frontend/server/test_mpa_deletion_status.py -q --no-cov`：25 项通过，含真实 Studio 路由挂载下模拟云删除、服务端真实类别的通用隔离、超时、过期/数量上限与包装提供商错误。 |
| 前端客户端回归 | pass | `node --test frontend/tests/mpaDeletionTimeout.test.mjs`：10 项通过，含确认查询网络超时及保留非超时服务端诊断。 |
| 前端完整回归 | pass | `npm --prefix frontend test`：1389 项 Node +84 项 React 通过，包含全部 10 项新增客户端回归。 |
| 构建/国际化/资源 | pass | `npm --prefix frontend run build`、`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`：同步发布资源，2 个语言 /21 个命名空间，113 个文件 /350 个引用。仍有既有大 chunk 警告。 |
| 浏览器 | pass | 内置 Playwright、隔离无头 Chrome 及真实 AgentWorkspace/client：正常成功、超时确认、仍存在、查询失败、忙碌禁用、Enter/Escape、取消重开、通用删除及 390×844 视图。模拟 fetch 阻止真实云调用；已清理临时服务/夹具。 |
| Ruff / 新模块 Pyright | pass | 临时 `uvx` 工具；Ruff 覆盖 3 个改动 Python 文件，新模块/测试以 `.venv/bin/python` 跑 Pyright。无全局安装。 |
| 旧 CLI Pyright | fail | 37 条已有错误；与 HEAD 对比诊断消息/规则完全一致，本修复无新增诊断。未修改无关历史错误。 |
| 文档 / 空白 / 密钥 | pass | 双语/标识符/链接核对、`git diff --check`，对改动源码/资源使用仓库配置及脱敏输出 Gitleaks。 |
| 真实破坏性 E2E | not_run | 未授权或执行新删除；此前只读诊断不是本修复的真实验证。 |
| 广泛 SDK/进程/harness 测试 | not_applicable | 未修改 SDK、进程或 harness 契约；定向删除、RBAC 与前端回归覆盖改动路径。 |
| 提交/pre-commit | not_run | 未授权提交；后续提交前仍需同步分支并执行全量 pre-commit。 |

请在保有原凭据的终端重启 Studio 并刷新页面，加载后端及配套资源。本次未重启服务、提交、推送或部署。剩余限制：确认上下文按进程保存并会到期；重启、切换服务进程或轮换凭据会导致结果无法确认。Runtime 缺失不能独立证明由外部操作触发的相关资源清理。本次范围内无新增审查阻塞。
