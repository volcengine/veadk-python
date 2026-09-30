# Worker 元数据阶段期限

[English](2026-09-30-worker-metadata-deadline.md)

- ID：mpa-worker-metadata-deadline；创建/修订：2026-09-30；状态：approved。
- 前序：[元数据可见性](2026-09-20-worker-metadata-visibility.zh.md)。
- 契约：[Studio 创建 CON-10](../../../specs/studio-mpa-creation/README.zh.md)。

## 证据、目标与范围

云端诊断显示 Worker 初始化期间四次归属标签不完整，35 秒后创建失败。随后只读检查显示同一个 Tool 在创建约 151 秒后 Ready，归属、项目和智能体绑定均匹配。源码在 600 秒 Worker 期限之外设置了独立的四次观察限制。共享 `ensure_worker` 同时服务托管 Studio 和 CLI 创建。

让归属元数据延迟在现有期限内等待，不提前失败。非目标：修改 TOS 校验、镜像、HTTP/UI/数据库结构、延长期限、部署、创建资源或真实重试。模板就绪不证明 Sandbox/会话/TOS 执行成功。

## 需求与设计

- FR-1：已有完整托管创建意图且处于已识别初始化状态时，归属元数据缺失每 5 秒检查，直到可见或现有期限/取消结束操作。删除独立四次观察预算，不使用无界指数等待。
- FR-2：Ready 缺必需元数据、已有值冲突、终态/未知状态及创建意图不完整仍快速失败。中途完整初始化响应不重置或延长期限。保留 Worker 绑定，轮询不创建第二个 Tool。
- FR-3：元数据观察计数最大保持 4，保留诊断协议 attempt 的 1–4 范围。后续事件仍为 `metadata_pending`/`retrying`，任务历史上限及脱敏不变。Worker API 错误重试仍最多四次，间隔 1/2/4 秒。

复用 `ensure_worker` 的 `asyncio.wait_for`，仅修改 `worker.py` 的元数据缺失分支。不新增配置、依赖、持久化或公共接口。更新 CON-10 及双语操作指南；旧创建路径和 TOS 凭证边界不变。

## 任务与验收

| 需求 | 任务 | 验收 / 验证 |
| --- | --- | --- |
| FR-1/3 | T-1：失败回归及最小循环修复 | AC-1：超过四次缺失后到达 Ready，包括穿插完整初始化响应；固定间隔及饱和诊断合法 |
| FR-2 | T-2：超时/取消及原安全回归 | AC-2：持续轮询受期限/取消限制，保留绑定，不额外创建；严格负例通过 |
| FR-1–3 | T-3：覆盖率、门禁和双语文档 | AC-3：增量可执行行覆盖率 >95%；受影响/全量 Python 测试、改动文件 Ruff/Pyright、pre-commit 及文档检查通过 |

## 审查与风险

用户批准：“那你改下代码”批准此前在阶段超时内等待、保留 Ready 严格归属校验的方案。直接设计审查（`review-spec` 不可用）覆盖调用者、期限/取消、冲突、凭证隔离、诊断范围及双语等价，无阻塞。固定间隔相比指数退避会增加查询，但与原就绪轮询一致且受期限限制。TOS 挂载元数据缺失仍独立严格校验，不属于此次已确认的归属标签缺陷。

## 验证记录

2026-09-30 工作区改动：

- pass：测试先行执行 `uv run --extra dev pytest tests/integrations/mpa_managed/test_worker_metadata.py -q`，修复前复现缺陷（13 failed、17 passed）。
- pass：`uv run --extra dev python -c 'import pydantic_settings; import pytest; raise SystemExit(pytest.main(["tests/integrations/mpa_managed", "tests/cli/test_cli_mpa.py", "-q", "--tb=short", "--cov=veadk.integrations.mpa.managed.worker", "--cov-branch", "--cov-report=json:/tmp/veadk-worker-metadata-coverage-20260930.json", "--cov-report=term-missing"]))'` — 443 passed。直接目标测试收集最初遇到已有的 `pydantic.RootModel` 延迟导入顺序问题；收集前初始化 `pydantic_settings` 即可避免，未修改源码/依赖。模块行/分支覆盖率为 89%，增量可执行行覆盖率 100%（3/3），满足 >95%。模拟元数据测试覆盖 4/30/200 次缺失、穿插初始化响应、合法饱和诊断、取消/期限、冲突及创建次数不变。
- pass：改动文件 Ruff 0.11.12、Pyright、全文件 pre-commit（含 Gitleaks/YAML 密钥扫描）、新相对链接与 `git diff --check`。第一次 pre-commit 格式化了两个改动 Python 文件，第二次全部通过。
- fail：`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q --tb=short` — 6151 passed、8 failed、2 个收集错误、22 skipped、2 xfailed、6 个子测试通过。六个 Harness 失败依赖未安装的可选 `llama_index`；两个自托管收集错误缺 `anthropic`；一个 GitHub 交付测试未模拟外部请求而超时；一个 wheel 元数据断言要求 `>=0.8.0`，未修改的 `pyproject.toml` 已要求 `>=0.8.5`。本修复未修改这些文件/依赖声明，Worker 元数据测试无失败。AC-3 全仓门禁仍受阻，因此设计保持 approved，不声称全部验收完成。不纳入无关依赖/测试修改。
- not_run：云端/浏览器/部署不属于本次代码改动。前端测试/构建及 Codex/provider 冒烟：not_applicable，无 UI/生成产物或进程/服务商执行改动。

直接实现审查确认：调用接口、严格归属/TOS 校验不变，固定间隔轮询受已有包装期限限制，取消继续传播，绑定保留。双语 FR/AC/T 标识及数字限制一致。验证前已 fetch 并 rebase 至现有 PR 的 `superops/main` 基线，分支已是最新。未修改运行中的 Studio 或云资源。
