# 稳定 PR #1190 CI 测试

[English](2026-10-28-stabilize-concurrent-tests.md)

Change ID：`pr1190-ci`；创建/修订：2026-10-28；状态：approved。
比较基线：功能提交 `7527a832`；上游 `23014771`。
关联设计：[首 Token 时间戳](../../features/first-token-timestamps/2026-10-28-first-token-timestamps.zh.md)。

## 证据与范围

Unit Tests 运行 `40649026439` 的 Python 3.10 作业 `122684493009`：1 failed、7,937 passed、46 skipped、4 xfailed。启动预取测试要求先检查 `tool-codex`，再检查 `tool-codex-snapshot`。生产代码使用 `asyncio.gather` 与 `asyncio.to_thread` 并发执行，两种顺序都有效。Python 3.12 被矩阵 fail-fast 取消。

此前本地全量回归还暴露了一条 Sidecar 基线测试：继承开发机模型上游配置后启用稳定中继，却断言固定的伪运行时发现地址。`run_with_harness_sidecar` 已支持显式 `env` 映射。

目标：按真实契约稳定测试。非目标：修改运行时、串行化生产并发、放宽断言、添加重试或跳过、修改 CI 配置、前端、依赖和再次部署云端。

## 需求与设计

- FR-1：两个已配置 Sandbox 工具均恰好检查一次，不依赖调度顺序；最终缓存状态出现在 system-info 响应中。
- FR-2：通过有时限的线程 Event 明确覆盖两种检查顺序；比较精确调用次数，不要求生产顺序。
- FR-3：有界轮询响应状态，不能把进入检查桩当作缓存已发布。
- FR-4：伪 Sidecar 的子进程在显式隔离环境中收到精确发现地址，即使父进程存在模型/MCP 上游变量。

仅修改 `tests/cli/test_studio_rbac.py`、`tests/extensions/harness/sidecar_runtime/test_sidecar.py` 和双语设计/证据。保留全部现有响应及地址断言。不修改组件规格：公共接口、运行时、权限、数据与可观测契约均不变。回滚只需撤回本次测试提交。

## 任务与验收

| 需求 | 任务 | 验收 | 证据 |
| --- | --- | --- | --- |
| FR-1/2 | T-1：控制两种线程顺序，再修正顺序断言 | AC-1：修正前反向调度失败，修正后两种调度均通过 | 定向 pytest 与原始 CI 失败 |
| FR-3 | T-2：等待两种响应状态均发布 | AC-2：全部现有模型状态精确断言通过 | 同一个参数化 TestClient 测试 |
| FR-4 | T-3：为伪 Sidecar 显式提供空环境 | AC-3：父进程存在上游变量时，精确地址断言仍通过 | 伪运行时与真实子进程测试 |
| 全部 | T-4：必需检查、推送并确认 CI | AC-4：受影响套件、默认全量回归、pre-commit 与远端 CI 通过；生产变更行覆盖率保持 >=95% | 下述仓库命令 |

命令：`uv run --no-sync --extra dev pytest tests/cli/test_studio_rbac.py tests/extensions/harness/sidecar_runtime/test_sidecar.py -n 2 -q`；`uv run --no-sync --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q`；`uv run --no-sync --extra dev pre-commit run --all-files`。生产代码不变，复用功能覆盖率与真实云端证据，并确认源码哈希。

## 审查与授权

2026-10-28：用户授权完成飞书方案后修复 PR #1190 CI；此前对此分支的提交、推送授权继续有效。直接设计审查（`review-spec` 不可用）确认仅修改测试、精确次数/状态/地址断言、有界同步、生产并发不变，且隔离真实凭证。双语标识与验收一致，无设计阻塞。

风险：进入检查线程不代表缓存已发布，通过响应状态轮询解决。本地 Python 3.12 与 CI 的 3.10/3.12 矩阵不同，交付需远端结果。仅测试修复不适用再次云端验证；保留此前真实云端 6/6 通过的结论。

## 验证记录

2026-10-28，`7527a832` 加本次仅测试变更，Python 3.12.13：

- 原有顺序断言加受控调度：1 passed、1 failed；反向顺序复现原 CI 失败。
- 显式 `env={}` 前注入父进程上游变量：1 failed，固定发现地址与中继地址不符。原始单用例隔离运行通过，确认问题依赖环境。
- 修正后：3 项定向用例通过（两种调度与子进程环境）。
- 合并受影响套件：185 passed、4 failed。Studio 的全部 174 项通过；另四项回环请求走本机代理并收到 HTTP 403。对完整 15 项 Sidecar 文件使用命令级 `NO_PROXY=localhost,127.0.0.1,::1 no_proxy=localhost,127.0.0.1,::1` 后全部通过。因此 189 项受影响用例在正确本地环境中均通过；未修改网络断言或代理策略。
- 格式修正后 all-files pre-commit 通过；双语标识、字面命令、相对链接与空白检查通过。
- 九个生产文件哈希与原真实云端构建一致。生产变更行覆盖率仍为 100%（208/208），真实云端 E2E 仍为 6/6 通过。本次修复未新增生产可执行行。
- 默认全量回归使用同一命令级回环直连配置，`--junitxml` 保存于 Git 外：**7,942 passed、0 failed、42 skipped、4 xfailed；6 subtests passed；472.66s**。选中 7,988 项，包括已执行 7,946 项（含四项预期失败）及跳过 42 项。最终远端 3.10/3.12 结果由推送后的 PR 记录。用户随后要求额外测试仅运行失败项，不再安排广泛测试。


### Gate 状态

| Gate | Status | 证据 |
| --- | --- | --- |
| Change Basis | PASS | 对 `7527a832` 检查完整测试/设计差异；上游 `23014771` 未变；无无关变更。 |
| Contract | PASS | 工具精确调用次数、已发布状态及子进程发现地址；生产契约不变。 |
| Impact | PASS | R-CI-1/2 覆盖受影响测试断言与环境边界。 |
| Portfolio | PASS | 两种受控线程调度、TestClient 状态发布、真实伪运行时/子进程。 |
| Baseline | PASS | 修正前反向顺序断言与父进程上游注入均已观察到 RED。 |
| Execution | PASS | 3 项定向用例、全部 189 项受影响用例、默认全量回归与 all-files pre-commit。 |
| Evaluation | PASS | 保留原状态/地址断言；重复调用仍失败；源码哈希及 208/208 生产覆盖率不变。 |
| Handoff | PASS | 双语设计/证据同步；最终推送版本 CI 证据由 PR #1190 链接提供。 |

### Change Impact

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
| --- | --- | --- | --- | --- | --- |
| FR-1/2/3 | 测试调度与完成判定 | 启动预取测试与 system-info 缓存响应 | `asyncio.gather`、`asyncio.to_thread`、`test_system_info_prefetches_codex_model_env_state_on_startup` | 有效调度导致 CI 误报，或状态发布前检查响应 | R-CI-1 Medium |
| FR-4 | 测试子进程环境 | 伪 Sidecar 与子进程执行 | `run_with_harness_sidecar(env=...)`、子进程环境测试 | 父进程上游变量改变预期发现地址 | R-CI-2 Medium |

两项风险均跨越自有集成边界；固有影响/暴露/变更危险/检测困难为 Medium/Medium/Medium/Low。本次测试范围没有重大未知项。剩余不确定性限于未测的主机负载；不作负载或性能结论。

### Test Portfolio

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-CI-1 | 线程化提供方桩与真实 ASGI 响应 | 受控调度与状态转换 | Codex 先执行、snapshot 先执行、各类型精确最终状态 | 两个工具 ID 各一次；受控首个入口；原有全部状态/错误断言 | RED：1 failed/1 passed；GREEN：两用例与受影响/全量套件 | VERIFIED |
| R-CI-2 | 真实伪运行时与子进程 | 父环境注入与隔离 | 父模型/MCP 上游；显式空子进程基环境 | 退出 0，原有模型/MCP 地址完全一致 | RED：1 failed；GREEN：定向用例及全部 15 项 Sidecar 测试 | VERIFIED |

生产、前端、依赖、CI 策略、凭证与云端行为均不变。现有源码哈希证据可以识别意外生产漂移。没有新增格式测试或重复实现测试。需显式启用的 Codex/Pi smoke 不属于仅测试修复；远端 CI 仍执行既有 Codex smoke 作业。最终远端结果以 https://github.com/volcengine/veadk-python/pull/1190/checks 为准。
