# 恢复 Studio MPA 的 JWT 绕过默认值

[English](2026-09-30-studio-key-auth-default.md)

- Change ID：`mpa-studio-key-auth-default`
- 创建/修订：2026-09-30
- 状态：approved
- 契约：[MPA Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)
- 前序：[A2A 发现默认配置](../2026-09-23-mpa-a2a-discovery-default.zh.md)；仅替代其中 JWT 默认值的决策。

## 背景与范围

`build_runtime_env` 当前注入 `DISABLE_JWT_AUTH=false`。Studio 使用 Runtime
API key，而不是旧版 `X-Jwt-Token`，因此下载等受 JWT 保护的 REST 调用可能失败。
用户明确要求在现有 PR 中将默认值改为 `true`。Managed flat 创建和
`veadk mpa create` 均使用共享 helper；引用 Runtime/模板使用各自的环境。

目标：恢复共享默认值并保留显式覆盖。非目标：云端部署、已有 Runtime/会话迁移、
镜像构建、前端修改、JWT 签发，或开启 `MPA_AGENTKIT_MODE`。

## 需求与设计

- `FR-1`：给定没有显式覆盖的全新 flat 输入，生成环境包含
  `DISABLE_JWT_AUTH=true`、`ENABLE_A2A=true`、`A2A_TIP_VERIFY_ENABLED=false`；
  外层网关 key-auth 不变。
- `FR-2`：给定 `extra_env` 或 `managed.runtime.env` 显式指定
  `DISABLE_JWT_AUTH=false`，覆盖优先，且不修改输入映射。
- `FR-3`：不自动修改已有 Runtime/模板环境和已部署资源；helper 仍不注入
  `MPA_AGENTKIT_MODE`。

只改 `build_runtime_env` 的一个默认值，不在调用方分别修改。复用既有覆盖机制和
回归测试，不新增配置或依赖。不改变 schema、持久化、并发或重试。

安全：绕过旧版 REST 内层 JWT 同时影响管理权限检查和基于 header 的身份，不只
影响下载。APIG key-auth 仍必需；可信 Studio/网关调用方必须控制用户 header。
直接获取 Runtime principal 的端点不因该开关而修复。使用兼容的 MPA 镜像时，
`/list-apps` 可能发现 ADK，而不是强制走 A2A；本次不保证传输兼容性，也不迁移旧
会话。需要旧版 JWT 的操作方应显式设置 `false`。恢复方式为显式覆盖配置并发布，
不是自动回滚。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`：修改默认值及双语契约/文档 | `AC-1`：默认值与托管创建载荷一致 | `test_mpa_provision_env.py`、`mpa_managed/test_service.py`、CLI 回归 | pass：460 个目标测试 |
| `FR-2` | `T-2`：回归显式覆盖 | `AC-2`：显式 false 优先，其他配置不变 | 既有 helper/managed 覆盖测试 | pass：包含在目标测试中 |
| `FR-3` | `T-3`：核验范围及门禁 | `AC-3`：无云端写操作、mode 未注入、来源保留 | Diff 审查、目标测试、全量回归、Ruff/Pyright/pre-commit | 范围 pass；门禁限制见下文 |

使用 `uv run --extra dev pytest` 运行受影响测试，并测量
`veadk.integrations.mpa.mpa_provision` 及修改的可执行行覆盖率（增量要求超过
95%）。全量回归：
`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`。
对修改的 Python 文件运行 Ruff、Pyright，以及
`uv run --extra dev pre-commit run --all-files`。不需要云端凭据。
真实云端/下载 E2E 为 `not_run`：不属于本次只改代码的请求。

## 审查与交付

2026-09-30：直接设计审查（`review-spec` 不可用）检查了共享调用方、覆盖优先级、
安全/发现变化、可测试性、范围和双语一致性。无设计阻塞项。用户明确要求在现有
PR 恢复 `true`，作为本次批准。实现已完成；因仓库级门禁限制，设计状态保持
`approved`。

2026-09-30 验证，基于 `42120304` 的修改，已同步 `superops/main`（`6fba185d`）：

- 测试先行：默认值断言在修复前失败（`false != true`）。
- 目标命令：`uv run --extra dev python -c 'import pydantic_settings; import pytest; raise SystemExit(pytest.main(["tests/integrations/test_mpa_provision_env.py", "tests/integrations/mpa_managed", "tests/cli/test_cli_mpa.py", "--cov=veadk.integrations.mpa.mpa_provision", "--cov-branch", "--cov-report=term-missing", "-q"]))'`：
  **460 passed**。预先导入避开既有目标测试收集的导入顺序问题，不改变依赖。
- 覆盖率：常量没有独立可执行覆盖行。所属字典构造语句（第 162 行）已覆盖
  **1/1（100%）**，无新增分支。模块语句/分支综合覆盖率 **96.77%**，
  语句覆盖率 **98.98%**。
- 使用前述命令执行全量并行回归：**6152 passed、7 failed、2 个收集错误、
  22 skipped、2 xfailed**。6 个 Harness 失败缺可选 `llama_index`；两个自托管
  收集错误缺 `anthropic`；未修改的 wheel 测试预期 SDK `>=0.8.0`，而声明为
  `>=0.8.5`。这些问题不在本次范围内；全量回归不记为通过。
- Ruff：对三个修改的 Python 文件使用
  `uv tool run --from ruff==0.11.12 ruff check`，pass。直接 `uv run ruff` /
  `uv run pyright` 在项目环境中找不到对应工具，改用隔离运行器。
- 对三个修改的 Python 文件运行
  `uv tool run --from pyright pyright --pythonpath .venv/bin/python`，报告未修改的
  `test_service.py` 第 78/137 行两处诊断（可选模板、动态 `_credentials`）。
  单独检查生产 helper 与环境测试，零诊断通过。
- `uv run --extra dev pre-commit run --all-files`：pass，包括 Ruff 格式化和两种
  密钥扫描。Diff 空白、双语需求 ID 和 Markdown 相对链接：pass。
- 前端构建/浏览器：not_applicable；未修改前端代码/产物。已同步契约、双语
  managed README 和 `frontend/README.md`。云端部署/下载 E2E：not_run，
  不属于本次只改代码的请求。
