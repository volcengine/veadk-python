# 修复 PR #1180 CI 门禁

[English](2026-10-21-repair-ci-gates.md)

## 元数据

- Change ID：`pr1180-ci`
- 创建/修订：2026-10-21
- 状态：implemented（已授权发布；验证进行中）
- 关联组件规范：无；生成元数据、许可证注释和测试夹具文本保持全部运行时契约。
- 前序方案：[前端锁文件恢复](../frontend-lockfile-sync/2026-10-09-restore-esbuild-lock-entries.zh.md)。

## 背景与证据

PR 提交 `8f9911b8` 的运行 `39579012758` 在 `npm ci --ignore-scripts` 失败：缺少 esbuild 0.28.2 及其平台包。提交 `d2dc3da2` 删除了 512 行锁文件；package.json 只改了测试命令，因此依赖声明仍与其父提交一致。

运行 `39579012740` 报告两个 MPA 代理模块及其策略测试缺少 Apache 许可证头。运行 `39579012654` 在 `test_creation_failure_details.py` 的假连接串中报告一个未经验证的 PostgreSQL 扫描发现，没有已验证凭据。工作流扫描 PR 历史，因此仅追加修复提交不能清除该发现。

## 目标与非目标

恢复可复现安装、必需的许可证头和不会触发扫描器的测试数据，保留脱敏断言。依赖升级、运行时变化、扫描排除、部署、提交、推送和历史改写不在本地修复授权内。

## 场景与需求

- `FR-1`：依赖声明不变时，CI 安装必须接受完整锁定依赖图。
- `FR-2`：四个 Python 文件必须包含 `.licenserc.yaml` 的标准许可证头。
- `FR-3`：异常文本包含私密内容时，诊断事件必须保留来源元数据并排除私密文本。夹具不能包含凭据形态的连接串。
- `FR-4`：本地验证必须区分工作区修复与仍存在的历史扫描失败。

## 设计与契约影响

从 `d2dc3da2^` 恢复 `frontend/package-lock.json`，不重新生成或升级依赖。为 `veadk/integrations/mpa/{agents_md_proxy,collaborator_proxy}.py` 和 `tests/test_mpa_{agents_md,collaborator}_proxy_policy.py` 添加仅注释的许可证头。仅替换 `tests/integrations/mpa_managed/test_creation_failure_details.py` 中的异常夹具文本，保留全部断言。

公开 API、权限、状态、并发、配置、生成代码和组件契约不变。没有 UI、网络行为或云调用变化，因此 UI/浏览器和真实云端检查不适用。现有 CI 失败提供修复前的失败基线；复用既有诊断回归测试，不添加仅检查注释或锁文件文本的测试。

不采用扫描白名单或依赖升级，因为它们不能针对性解决根因。后续需单独授权改写：从引入问题的提交中删除该夹具，保留作者信息，发布前同步远端并使用 lease 保护。

## 任务与验证

| 需求 | 任务 | 验收 | 命令/证据 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`：恢复锁文件 | `AC-1`：与父提交依赖图一致，干净安装成功 | `git diff d2dc3da2^ -- frontend/package-lock.json`；`npm --prefix frontend ci --ignore-scripts` | pass：无差异；安装 695 个包 |
| `FR-2` | `T-2`：添加许可证头 | `AC-2`：四个文件均有标准头 | 对照 `.licenserc.yaml` 和既有诊断测试的许可证头；Ruff | pass：四个文件均一致 |
| `FR-3` | `T-3`：修复夹具 | `AC-3`：原有断言通过 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_creation_failure_details.py tests/test_mpa_agents_md_proxy_policy.py tests/test_mpa_collaborator_proxy_policy.py -q` | pass：34 个测试 |
| `FR-1` | `T-4`：前端门禁 | `AC-4`：覆盖率、测试、构建通过 | `npm --prefix frontend run test:harness-sidecar-coverage`；`npm --prefix frontend test`；`npm --prefix frontend run build -- --outDir /tmp/veadk-pr1180-build --emptyOutDir false` | pass：22 个覆盖率测试；1,389 个 Node 和 154 个 Vitest 测试；两项构建 |
| `FR-4` | `T-5`：审查与报告 | `AC-5`：如实报告检查及历史限制 | `uv run --extra dev pre-commit run --all-files`；差异审查；`gh pr checks 1180 --repo volcengine/veadk-python` | 本地 pass；远端仍有原三项失败和排队任务 |

先执行 T-1 至 T-3，再执行 T-4，最后执行 T-5。不包含发布。需要撤销本地修复时，在保留后续用户改动的前提下，从 HEAD 恢复相关文件。

## 风险与评审记录

- 本地 macOS/Node 26 验证与 Ubuntu/Node 22.17.0 CI 环境不同。
- 构建输出必须隔离，避免验证引入无关的打包资源变化。
- 用户授权改写并发布 PR 提交前，历史密钥扫描仍未解决。
- 2026-10-21：用户以“帮我修一下”批准了此前已说明的三处修复。
- 2026-10-21：`review-spec` 评审确认范围收敛、无契约影响、保留断言且双语等价。历史扫描限制与本地验收明确区分，没有本地设计阻塞项。
- 2026-10-21：上表全部本地验收检查针对 HEAD `8f9911b8` 加本次修复执行。依赖声明、扫描规则、生产语句、测试断言和已跟踪 Web 资源均未变化。使用 `head -14` 和 `diff` 对照四个文件的许可证头，全部一致。
- Ruff：`uv run --extra dev ruff check` 加五个修改的 Python 路径通过。Pyright 最初无法通过 `uv run` 启动；使用隔离的 `uvx pyright --pythonpath .venv/bin/python` 加这些路径通过，0 错误、0 警告。最初未指定仓库解释器的 uvx 检查报告缺少导入；选择正确解释器后解决，未修改配置。
- 覆盖率：语句 98.55%，分支 94.44%，函数和行 100%。`git diff --check` 通过。最终人工审查确认夹具的脱敏覆盖不变，恢复的锁文件与完整父提交 blob 完全一致。
- 测试流程：Step1–Step5 完成，一轮夹具修复/验证（`all-pass`）；没有新增测试用例或生产缺陷发现。Step6 Python 覆盖率对此夹具/注释修复为 not_applicable，没有适用覆盖率目标变化。Step7 `utree flush` 通过。
- 全量 Python 回归和后端 Sidecar 门禁：本地 not_run，因为没有可执行生产逻辑或共享契约变化；PR Python 3.12 回归已通过。真实云端、运行时 smoke 和浏览器检查：对此修复为 not_applicable。本地 Apache Eyes 和 TruffleHog 二进制：not_run，工具不可用；标准许可证头对照和 pre-commit 密钥门禁通过，但不能证明历史 TruffleHog 扫描干净。
- 安装报告 16 个既有依赖审计发现；依赖整改不在本次恢复范围。构建报告大分块警告，仍成功完成。
- 仓库辅助工具 plan/handoff 因缺少 Manifest 返回 `onboarding_required`；实际验收使用仓库原生命令记录于本文，未引入仓库接入改动。
- 2026-10-21：用户以“允许”明确授权改写并发布。已拉取两个远端：`upstream/main` 仍为 `5e5deb6a`，预期远端 PR 提交仍为 `8f9911b8`。对 `upstream/main` 执行交互式 rebase，将各项修复放入引入问题的提交，保留作者身份和作者日期。
- 第一条改写提交 `03814668`：修改提交前全量 pre-commit 和 30 个受影响测试通过。提交钩子通过，没有绕过检查。
- 第二条提交的最终工作区：远端同步后，全量 pre-commit 通过，34 个受影响测试在 2.28s 内全部通过。六个修复文件与此前验证过的本地修复完全一致，没有引入无关实现或资源差异。空白检查通过。
- 发布计划：将其余许可证头和本双语证据纳入第二条提交，重跑全量 pre-commit 和 34 个受影响 Python 测试，验证最终差异和改写历史，然后使用绑定远端提交 `8f9911b8188c5bba20085c0ff68c6b7e5fe02050` 的显式 lease 推送。云端部署和合并仍不在授权内。
