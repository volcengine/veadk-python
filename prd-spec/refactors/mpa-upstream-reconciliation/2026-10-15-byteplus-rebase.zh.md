# 上游历史整理后的 BytePlus 改动协调

[English](2026-10-15-byteplus-rebase.md)

- 日期：2026-10-15
- 范围：将原本地提交 `078602ec` 协调到远端分支基础 `08197629`。
- 授权：用户要求解决 rebase 冲突并提交结果。
- 状态：协调完成；未改动的 macOS MIME 回归失败如实记录如下。

## 证据与处理方式

中断的 rebase 从 `7f2ae0f8` 开始重放七个提交。远端基础已整理了六个历史生命周期提交，包括通用/MPA 部署隔离、删除、OV 自动创建、最大实例数、依赖锁修复和许可证头。再次重放导致重复的文档、测试脚本冲突和构建产物重命名冲突。终止该 rebase 前已备份原分支顶端及中断状态。通过 `--onto 08197629 2ffe6e14` 重启 rebase，仅重放本地 BytePlus 提交。

## 保留行为与涉及文件

同时保留上游的 TOS 挂载配置、镜像选择规则和 `ensure_tos_mount_permissions`，以及本地 BytePlus OV 创建、IAM 临时错误诊断、Runtime 诊断、原请求名称恢复、分提供商默认镜像和服务端 APM AppKey 注入。`names.py` 使用已批准的本地 Worker 归属检查：`MPA_AGENT_ID` 环境变量匹配，同时核对标准 `managed_by` 和 `mpa_agent_key` 标签；矛盾归属不能授权重试。Runtime 无标签恢复仍只限已认证的原创建账号。保留远端完整的 `frontend/package-lock.json`，因为此次没有请求改变包依赖。从合并后的前端源码重新生成 `veadk/webui`，不手动拼接压缩包。

上游测试替身中的四处 Pyright 问题通过在 `test_iam.py`、`test_service.py` 增加非空断言解决；这些断言不改变生产行为。共享数据库/网络和已部署 Runtime 不在范围内。现有组件契约不变，保留其已批准的双语 BytePlus 补充内容。本次协调不新增公共 API、提供商权限、依赖或云端写操作。

## 审查与验收

review-spec skill 不可用，直接完成等价审查。已检查历史范围、归属校验、提供商隔离、TOS/APM 顺序、完整锁数据、构建产物、测试覆盖和双语文档。验收要求远端基础上只有一个本地功能提交、无冲突标记、上游 TOS 与本地 BytePlus 行为均保留、产物已重建并完成下列检查。真实 Worker 派发、OV 数据面兼容和海外观测仍是单独的 Runtime/镜像联调，本地测试不能证明这些结果。

## 验证（2026-10-15）

- pass：冲突及集成定向测试 383 项通过；测试断言修正后复验 204 项通过。
- pass：`npm --prefix frontend ci --ignore-scripts --no-audit --no-fund`，使用完整锁文件。
- pass：`npm --prefix frontend test`，1,389 项 Node 测试和 111 项组件测试通过。
- pass：`npm --prefix frontend run build`，TypeScript 和两份生产构建通过。
- pass：`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets`，113 个文件、350 个内部引用通过。
- pass：四处测试非空断言修正后，对 25 个改动 Python 文件运行 Pyright。
- pass：`uv run --extra dev pre-commit run --all-files`，首次及最终暂存源码检查通过；本记录完成后再执行仅文档收尾复验。
- fail：`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`，7,441 项通过、1 项失败、53 项跳过、4 项 xfailed，用时 509.32 秒。使用两个 worker 限制本地资源压力。唯一失败为 `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`：这台 macOS 的 Python 无法识别 `.md` MIME，未改动的代码返回 `application/octet-stream` 而不是 `text/markdown`。Writer、MIME 辅助函数和测试均与远端基础 `08197629` 相同；单独执行原测试文件可复现（48 项通过、1 项失败）。没有改动无关生产代码或机器全局 MIME 配置。
- pass：仅在单独进程为 `.md` 增加预期的 `text/markdown` 映射后，49 项产物写入测试全部通过；该受控环境检查不能替代已记录的完整回归失败。
- pass：`uv build --wheel --out-dir /tmp/veadk-rebase-wheel`；新增 BytePlus 模块、迁移后的 contract JSON 均存在，`.env` 不在包内。本地七个新增 Python 模块均与 `078602ec` 逐字节一致。
- blocked：现有 Studio 进程缓存重建前的 HTML，引用已移除资源并返回 HTTP 404。浏览器打开页面后无法验证创建弹窗。没有重启用户正在使用的服务；需重启才能加载重建后的 HTML。
- not_run：真实云端创建/删除与 Runtime smoke；本次 Git 协调任务未授权云端写操作。
