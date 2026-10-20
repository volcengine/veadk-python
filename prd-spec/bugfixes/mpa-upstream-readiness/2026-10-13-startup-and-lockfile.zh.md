# MPA 官方 PR 的启动与锁文件检查修正

[English](2026-10-13-startup-and-lockfile.md)

- Change ID：`mpa-upstream-readiness`；日期：2026-10-13；状态：implemented。
- 范围：rebase 到官方 `b8038fb1` 的四个 MPA 生命周期提交。
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)；[原锁文件恢复设计](../frontend-lockfile-sync/2026-10-09-restore-esbuild-lock-entries.zh.md)。

## 证据、需求与范围

`ea949fee` 全量离线回归得到 7,184 passed、2 failed、53 skipped、4 xfailed。隔离源码快照中的官方 `b8038fb1` 启动测试通过，但同一 Python 3.10/macOS 环境下复现了产物写入 MIME 测试失败。分支新增 OV 适配器提前导入 `veadk.utils.volcengine_sign`，违反已有 Studio 延迟加载启动契约。被删除的 512 行锁文件也使 npm 10.9.2（前端 CI 所用运行时系列）拒绝 esbuild 条目，虽然 npm 11 接受。

FR-1：注册 MPA 路由/配置时保留原延迟加载启动边界。只在执行 OV API 请求时加载签名函数。保留请求参数、重试/错误/取消和平台边界。
FR-2：恢复官方完整前端锁文件。依赖声明与官方 main 相同，仅测试脚本选择不同。不更改依赖范围或无关产物写入逻辑。

## 设计、任务与验收

T-1 / AC-1：以已失败的隔离 Studio 启动测试作回归。将签名 import 移入原请求闭包，两处适配器模拟 patch 指向函数所属模块；同步双语 OV 启动契约。
T-2 / AC-2：从 `upstream/main` 恢复生成的 `frontend/package-lock.json`，在隔离目录按 Linux/x64 选择重跑 npm 10.9.2 `ci --ignore-scripts --dry-run`。
T-3 / AC-3：重跑启动、managed/部署/RBAC 测试、相关前端测试/覆盖率、lint/type 和全文件 pre-commit，记录实际结果。既有云操作、凭据、会话身份和清理策略不变。

## 审查、授权与风险

直接审查（review-spec 不可用）确认这是已批准 OV 功能和此前已批准锁文件恢复范围内的修正，为用户明确要求的官方 PR 做准备。不增加功能或云操作；无需推测性 wrapper、依赖升级或无关 MIME 修复。保留已发布原开发分支，在独立官方 PR 分支提交修正。须披露本地基线失败，不以跳过或修改无关生产行为来隐藏。

## 验证

以上失败证据记录于修正前，执行后补充最终结果。真实云/OV smoke 为 not_run，未授权额外付费资源操作。

### 最终准备结果（2026-10-13）

范围：`ea949fee` 加本次检查修正，基于 `b8038fb1`。AC-1–AC-3 完成。

- pass：修正后 1,185 项相关启动/managed/Profile 路由/RBAC 测试；未使用外部服务。因修正仅延迟一个签名 import、恢复生成元数据，没有重复全仓测试；已重跑失败启动用例及所有受影响部署边界。
- pass：1,389 项 Node、95 项 React、生产构建、22 项 sidecar 覆盖测试（lines 100%、branches 94.44%）、国际化与发布资源引用。构建产物与 rebase 后已跟踪资源逐字节一致。
- pass：恢复官方锁文件后，隔离目录 npm 10.9.2 按 Linux/x64 执行 `ci --ignore-scripts --dry-run`；依赖声明/范围不变。验证的是锁文件图，并非真实 Linux 安装。
- pass：修正适配器/测试的 Ruff 0.11.12、Pyright（0 错误/警告），全文件 pre-commit（含密钥/YAML 扫描），双语链接/标识符/空白审查。
- fail（基线）：修正前全量本地测试 7,184 passed、2 failed、53 skipped、4 xfailed。启动问题已修正；`tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes` 在原样官方 main、同一 Python 3.10/macOS 环境也失败（Markdown MIME 解析为 `application/octet-stream`）。未修改无关 writer/测试。
- not_run：额外付费云/OV smoke 及真实 Codex/Pi smoke；未改 harness 协议，也未授权真实资源操作。

用户于 2026-10-13 明确授权创建官方 PR，包含必要准备提交及分支推送，不包含合并/部署。原 fork 开发分支不变。实际命令：

```bash
uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"
uv run --extra dev pytest -n 2 -q tests/cli/test_studio_startup_imports.py tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/cli/test_studio_rbac.py
uv run --extra dev pre-commit run --all-files
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:harness-sidecar-coverage
npm --prefix frontend run check:i18n
npm --prefix frontend run test:webui-assets
```
