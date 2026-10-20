# 恢复 main 的 MPA 创建镜像默认值

[English](2026-10-09-restore-main-images.md)

- Change ID：`restore-main-images`
- 日期：2026-10-09
- 状态：用户明确要求撤回公开镜像查询，已批准；已实施并完成本地验证；未提交或推送。

## 背景与证据

Studio 通过 digest 引用选择公开镜像后，Worker CreateTool 请求返回 `InvalidParameter.ImageUrl`。用户要求撤回公开仓库查询改动，并遵循 main 的两个 `/mpa/` `:latest` 默认镜像。此前创建页面修正已遵循 main。

## 范围、场景与需求

- FR-1：恢复内置 MPA 镜像 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa/mpa_agent:latest` 和 Worker 镜像 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa/mpa_codex_worker:latest`。配置检查和 POST 使用本地 profile 默认值，不查询仓库或转换 digest。
- FR-2：恢复 main 的创建弹窗/客户端接线和回归。删除仅供查询使用的解析器、fixture、测试、请求镜像查询方法及超时/查询参数扩展。保留旧 API 显式镜像和此前已有的首次提交镜像快照。
- FR-3：保留 STS 推导部署账号、自动 IAM 准备、网络/APIG 修复、独立 Worker 创建、安全 IAM 诊断，以及 main 的名称创建/基本详情。
- FR-4：同步双语契约/说明并重新生成 WebUI 产物。删除已撤回功能的文档及误提交的 Vite 缓存产物。

非目标：修改数据库/任务/注册库、清空未完成意图、真实部署、迁移、提交或推送。旧失败请求的不可变快照可能仍包含被拒绝的 digest；重试不得静默更换。新请求使用恢复的默认值。`latest` 可变，不能保证不同时刻镜像内容不变。

## 设计、影响文件与契约评估

恢复 main 版本的 Studio 路由、API 客户端、弹窗及镜像/名称测试；保留 IAM 回归覆盖。仅调整 `managed/studio_profile.py` 的镜像设置，保留新账号/IAM/无参考模板配置。删除 `frontend/server/mpa_creation_images.py`、仅用于仓库查询的测试/conftest，以及 `CreationTasks.request_images`。`CreationTasks.start` 快照语义不变。当前归属/API 默认值由 [Studio 创建 CON-1/CON-9](../../../specs/studio-mpa-creation/README.zh.md) 维护；双语均恢复本地默认值合同。其他资源合同不变。删除已取代的公开镜像 PRD，当前契约改为链接此次修正。

## 任务、测试与验收

1. T-1 / FR-1：恢复 main 路由/名称回归期望，先在查询实现上观察失败。
2. T-2 / FR-1–FR-3：撤回查询接线并恢复默认值；通过 diff 确认本分支其他行为保留。
3. T-3 / FR-4：同步文档并构建产物；运行创建/CLI Python 测试、改动文件 Ruff/Pyright、前端测试/构建/i18n/产物、pre-commit 及隔离浏览器流程。

验收：配置和新任务快照中包含准确的默认 URL，无查询代码引用或仓库网络依赖，旧快照/owner 隔离不变，main 表单不提供镜像字段，新账号改动完整保留，受影响检查通过。无需云写入证明撤回；真实云端拉取/就绪仍未验证。

## 审查与风险

`review-spec` 不可用；直接审查覆盖范围、双语等价、兼容性、归属、密钥排除、重试、取消和测试。用户明确批准撤回，此范围内无需再次批准。旧失败 digest 快照和可变 latest 标签是已知限制，无阻塞项。

## 验证

范围：相对 `df797f94` 的未提交撤回，参考 `origin/main` 的 `f6ed8ffa`。执行日期：2026-10-09。T-1–T-3、FR-1–FR-4 在本地撤回范围内完成。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 回归先行 | pass | 恢复 `test_new_creation_generates_owner_scoped_id_and_latest_images` 与 `test_authorized_config_returns_defaults_and_task_freezes_them`；撤回前两项失败，撤回后通过。 |
| `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q` | pass | 614 项通过，10 条警告；本机采用 2 个 worker。 |
| `npm --prefix frontend test` | pass | 1,377 项 Node 测试与 65 项 Vitest 测试通过，无跳过。覆盖恢复、重试、错误、取消、加载、键盘/IME 和 owner 隔离。 |
| `npm --prefix frontend run build` | pass | App 与 widget 构建通过，包内产物已重新生成。已有包体积/依赖警告不阻塞。 |
| `npm --prefix frontend run check:i18n` / `run test:webui-assets` | pass | 2 种语言 / 21 个 namespace；验证 113 个文件及 350 个内部引用。 |
| 改动文件 Ruff / Pyright | pass | 对路由、profile、tasks 和两个恢复的测试模块运行 `uvx --from ruff==0.11.12 ruff check` 与 `uvx pyright --pythonpath .venv/bin/python`：无问题。 |
| `uv run --extra dev pre-commit run --all-files` | pass | Ruff check/format、硬编码密钥检测和 YAML 密钥扫描通过。 |
| 隔离真实浏览器 | pass | 仅模拟配置：名称必填、描述保留、三步流程、无镜像输入；最终创建入口可用。390×844 窗口无横向溢出。未实际提交；临时文件、标签和 Vite 进程已清理。 |
| 契约/diff 审查 | pass | 路由/客户端/弹窗与 main 一致；profile 保留 STS/IAM/无参考模板差异，tasks 保留 IAM 诊断。无运行时查询引用或已撤回 PRD 的悬空链接。双语标识符、链接已核对；`git diff --check` 通过。 |
| 真实云创建 / 拉取就绪 | not_run | 此次撤回未授权云修改。未编辑旧失败任务快照；重载 Studio 后新建请求以使用新默认值。 |
| 全量 SDK 回归 / harness smoke | not_applicable | 此次仅撤回托管 Studio 镜像选择并恢复 main 合同；共享 SDK 与 sidecar 行为不变。 |

本地测试证明默认值选择和兼容性，不证明云服务接受或可拉取这两个可变标签。未重启用户现有 Studio 进程。
