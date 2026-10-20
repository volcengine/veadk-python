# Studio TOS 凭据传递

- Change ID：`studio-tos-credentials`
- 日期：2026-10-15
- 状态：implemented
- [English](2026-10-15-tos-credentials.md)
- 契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)

## 证据与范围

DeploymentResourceService 收到已解析的凭据，但 TOSService 构造时没有使用，
而是独立解析凭据，导致云端 BytePlus 资源查询可能在请求 TOS 前失败。
CR 已使用这些凭据。不修改前端、Runtime 镜像、数据库、依赖、权限或云资源。

## 需求与设计

- FR-1：显式 AK/SK 完整时，通过 VolcConfiguration 解析 provider/region 对应
  的 TOS endpoint，以该 AK/SK 和 session token 构造 TosClientV2。
  适配为既有 client/actual_region 结构读取桶响应，不修改 SDK 全局状态或进程环境。
- FR-2：没有完整显式凭据时，保留既有 TOSService 解析路径。
  火山和 BytePlus 均保留 endpoint 解析、地域过滤、分页及资源验证。
- FR-3：每次路由请求重新解析凭据并创建 service，轮换后的凭据在下一次请求生效。
  不增加跨请求客户端缓存，不改变重试或取消策略。
- FR-4：错误继续按类型返回 HTTP 400/502；既有路由处理器脱敏凭据值。
  不增加密钥持久化或响应字段。

## 任务与验收

1. T-1：在 tests/frontend/server/test_deployment_resources.py 增加先失败的
   显式凭据、轮换、脱敏测试（FR-1/3/4）。
2. T-2：适配 frontend/server/deployment_resources.py 并保留回退路径，覆盖
   两个 provider 和已有桶验证（FR-1/2）。
3. T-3：更新双语契约，执行定向 pytest、Ruff、Pyright 和 diff 检查。
   无 UI 改动，前端构建和浏览器检查不适用。

验收：模拟 TOS 调用收到当前凭据及 token；无凭据调用保留 SDK 回退；
已有列表及验证测试通过；SDK 错误不暴露传入凭据。
真实云端部署单独验证，本次代码修复请求不授权部署。

## 风险与评审

原生 TOS 响应与封装响应不同：复用 _tos_buckets 归一化，并测试列表和验证调用方。
endpoint 继续由 SDK 解析，不写死域名。单次请求使用一个凭据快照，不自动重试
请求期间的凭据轮换。回滚仅涉及代码。

用户以“改改”批准方案。因无 review-spec 技能，直接评审确认范围、provider 兼容、
密钥处理、可测试性及双语等价，无阻塞项。验证待执行。
评审前未修改生产代码或测试。


## 验证（2026-10-15）

范围：基于 `8ae26a6d` 的本地 TOS 凭据传递改动。
- `pass`：回归测试先复现五项失败，两项回退测试通过。
- `pass`：`uv run --extra dev pytest -q tests/frontend/server/test_deployment_resources.py`
  — 38 项通过，一条上游 Starlette 弃用警告。所有云调用均使用模拟。
- `pass`：两个改动 Python 文件的 Ruff 0.11.12 check 和 format。
- `pass`：`uv tool run pyright --pythonpath .venv/bin/python frontend/server/deployment_resources.py tests/frontend/server/test_deployment_resources.py`
  — 零错误、零警告。
- `not_applicable`：前端产物、构建和浏览器；未修改 UI 或 HTTP 结构。
- `not_run`：真实云端验收及部署，需使用 IAM 凭据运行更新后的 Studio。
  未修改任何云资源。

实现评审确认复用既有桶归一化与地域验证，回退路径不变。
不向日志、持久化状态或浏览器输出新增凭据。
凭据刷新覆盖连续资源列表请求，不包含请求中途自动恢复。

2026-10-15 提交前验证：fetch origin 并 rebase 到未变化的跟踪分支
`8ae26a6d`；`uv run --extra dev pre-commit run --all-files` 全部钩子通过，
定向测试再次全部通过（38 项）。
