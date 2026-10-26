# 修复普通 MCP 会话死锁

[English](2026-10-26-standard-mcp-deadlock.md)

- 变更 ID：`trusted-mcp-session-routing`
- 创建／修订日期：2026-10-26
- 状态：`approved`
- 组件契约：[可信 MCP 会话](../../../specs/trusted-mcp-sessions/README.zh.md)
- 基线版本：`c662cc8d`；验证覆盖工作区会话管理器及两个相关测试文件。

## 背景与证据

用户报告的环境为 VeADK 1.0.2、Google ADK 2.1.0、MCP 1.26.0、Python 3.12。普通 streamable HTTP 首次创建会话时，包括使用 Bearer 鉴权但未带 `x-trusted-mcp` 的情况，会在连接前无限等待。

`veadk/tools/mcp_tool/trusted_mcp_session_manager.py` 的 `create_session` 获取 `_session_lock` 后，在普通连接分支调用 `super().create_session(headers)`。父类也会获取同一把不可重入锁。因此，缓存未命中时，父类等待的锁正由调用它的子类持有。已有健康缓存的会话可能在到达缺陷前返回。可信分支自行创建会话，不会嵌套调用父类。

最初安装的本地父类实现确认了重复获取锁的机制；当时环境为 Google ADK 1.18.0、MCP 1.20.0。仓库元数据要求 `google-adk>=2.7.0,<2.8.0` 和 `mcp==1.26.0`。最初的代码检查是根因证据，不代表当时已经运行复现，也不代表验证了报告中的依赖组合。运行检查现已使用 `uv` 按仓库要求解析的环境，结果见下文。

现有 `tests/tools/mcp_tool/test_trusted_mcp_components.py` 覆盖可信会话创建和健康缓存复用，缺少普通连接首次创建的测试。

## 目标与非目标

恢复 `TrustedMcpToolset` 的普通 MCP 连接创建，保留可信路由及按鉴权请求头划分的会话池，消除嵌套加锁。

本次不涉及依赖升级、新锁实现、传输重构、扩大可信会话取消清理范围、发布或版本更新、云端调用，以及无关的工具集配置转发。公共导入路径和函数签名保持兼容。

## 场景与需求

| ID | 前提／触发 | 必须达到的结果 |
| --- | --- | --- |
| `FR-1` | 普通 streamable HTTP、SSE 或 stdio 首次请求会话 | 在获取子类会话锁之前委托父类，连接创建能够继续执行。 |
| `FR-2` | Streamable HTTP 且合并后的 `x-trusted-mcp` 严格等于 `"true"` | 使用 `trusted_mcp_client`，保留现有可信会话池和清理行为。 |
| `FR-3` | 同时存在连接请求头和调用请求头，包括可信标记覆盖 | 遵循父类合并优先级。路由检查不修改调用方的两个字典。传给所选传输的鉴权请求头保持正确。 |
| `FR-4` | 普通连接并发请求、重复请求或已有缓存断开 | 由父类负责串行化、复用、替换和资源清理，不重复执行这些操作。 |
| `FR-5` | 普通连接失败，或等待锁时被取消 | 传播失败或取消；释放锁，使后续请求能够继续。不吞错，不新增超时行为。 |

标记缺失、为 `"false"` 或其他不匹配值时选择普通路径。SSE 和 stdio 即使带标记，也不能启用可信传输。测试使用模拟鉴权值和本地传输替身。

## 设计与契约影响

推荐方案：在 `_merge_headers(headers)` 之后，用 `.get` 检查连接类型和标记，检查位置位于生成会话键和获取 `_session_lock` 之前。普通路径立即返回 `await super().create_session(headers)`，传入原始调用请求头，由父类完成正常合并和生命周期管理。

仅可信路径执行子类现有的会话键、锁、缓存、断开清理和 `AsyncExitStack` 操作。先生成可信会话键，再从内部合并副本中移除可信标记，供传输使用。移除子类锁内已经不可达的普通分支。

2026-10-26 按受支持基线复核实现时发现，Google ADK 2.7.1 调用 `_create_client` 会额外传入 `mtls_transport` 和 `session_key`。现有重写方法需要接收并转发父类参数，使普通连接在修复加锁后能够继续创建。可信路由行为保持不变。这是满足 `FR-1` 所需的私有接口适配，不引入新的公共契约或产品范围。现有普通缓存测试也需要用当前父类的 `(session, exit_stack, loop)` 元组替换过期的双元素测试数据。

其他方案：

1. 把锁换成异步重入锁：引入自定义锁行为，并与父类锁的管理职责冲突，没有必要。
2. 在子类复制父类会话创建流程：能避开嵌套加锁，但会重复传输及生命周期代码，增加上游兼容风险。

本次调整普通会话的并发管理职责，因此需要范围明确的双语组件契约。Studio、生成代码、依赖元数据、权限、事件结构和部署契约均不受影响。调用方无需迁移。交付核对时评估现有用户文档；修正超出本次路由缺陷的通用文档错误，需要另行确定范围。

## 任务与受影响文件

| 任务 | 工作 | 对应需求 |
| --- | --- | --- |
| `T-1` | 审查双语 PRD 与 `specs/trusted-mcp-sessions/README{,.zh}.md`，记录用户批准。 | 全部 |
| `T-2` | 新增 `tests/tools/mcp_tool/test_trusted_mcp_session_routing.py`。先使用真实父类会话方法、传输／会话替身和有界 `asyncio.wait_for`，证明修复前普通连接创建会超时。 | `FR-1` |
| `T-3` | 在 `veadk/tools/mcp_tool/trusted_mcp_session_manager.py` 中实施入口分流及父类客户端参数转发。 | `FR-1`、`FR-2`、`FR-3` |
| `T-4` | 覆盖普通传输类型、标记值／覆盖、模拟 Bearer 请求头、可信创建／复用、并发创建、断开替换、失败重试和等待锁时取消。保留现有组件测试，并按父类会话池元组更新普通缓存测试数据。 | `FR-2`–`FR-5` |
| `T-5` | 执行定向及扩大回归检查，审查差异、资源职责和双语一致性，按实际证据核对文档。 | 全部 |

顺序：`T-1` → `T-2` 的失败回归 → `T-3` → `T-4` 的其余覆盖 → `T-5`。实施前记录修复前的失败证据。

执行步骤（已批准范围）：

- [x] `T-1`：用户于 2026-10-26 批准代码和测试修改：“按这个方案修改代码和测试”。
- [x] `T-2`：构建隔离传输夹具，保留真实父类加锁和会话池。运行 `uv run --extra dev pytest tests/tools/mcp_tool/test_trusted_mcp_session_routing.py -k standard_first_session`，预期在进入传输前有界超时。
- [x] `T-3`：在生成会话键前插入 `if not (isinstance(self._connection_params, StreamableHTTPConnectionParams) and merged_headers and merged_headers.get("x-trusted-mcp") == "true"): return await super().create_session(headers)`。保留可信会话键，在进入传输前从合并副本移除标记，删除锁内父类回退。再次运行首次会话测试，预期成功。
- [x] `T-4`：使用隔离传输／会话上下文运行全部路由和组件测试，检查创建次数、对象复用、请求头值、清理、失败传播和取消后继续执行。
- [x] `T-5`：执行下文验证命令，按 `FR-1`–`FR-5` 审查最终源码／测试差异，同步双语和组件状态，记录实际结果。用户后续已授权提交本次修改，并将本地历史同步到 `origin/main`。

## 验证与验收

使用 `uv run --extra dev` 和当前仓库元数据。不能把过期的本地环境当成受支持基线。测试替换网络／进程传输，不替换父类加锁实现。

| 需求 | 任务 | 验收条件 | 检查 | 当前结果 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-2`、`T-3` | `AC-1`：普通连接首次创建在修复前有界超时，修复后成功 | `uv run --extra dev pytest tests/tools/mcp_tool/test_trusted_mcp_session_routing.py -k standard_first_session -q` | `pass`：修复前两条在嵌套加锁处超时，修复后两条成功 |
| `FR-2`、`FR-3` | `T-3`、`T-4` | `AC-2`：可信路由、合并优先级、调用方请求头和鉴权保持正确 | `uv run --extra dev pytest tests/tools/mcp_tool -q` | `pass`：包含在 24 条通过的测试中 |
| `FR-4`、`FR-5` | `T-4` | `AC-3`：普通生命周期、并发复用、失败重试和等待锁时取消通过 | `uv run --extra dev pytest tests/tools/mcp_tool -q` | `pass`：24 条测试通过，耗时 3.05s |
| 全部 | `T-5` | `AC-4`：扩大后的相关回归通过 | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | `fail`：7556 条通过、17 条失败、58 条跳过、4 条 xfailed、2 条收集错误；436.40s；两个 worker |
| 全部 | `T-5` | `AC-5`：修改的 Python 及文档检查通过 | 下文记录中的 Ruff 0.11.12 lint／格式命令；`git diff --check`；双语／路径／链接审查 | `pass`：三个 Python 文件和两组双语文档 |

用户后续已授权提交并推送到 `origin/main`，包括同步本地历史，因此提交前必须运行 pre-commit。创建 PR、软件包发布和部署尚未获授权。真实云端／服务商及可信证明检查为 `not_applicable`：缺陷发生在进入传输之前的锁管理中，验证使用隔离环境。现有可信组件测试只能证明模拟兼容，不能证明真实可信证明流程。

## 风险与未决问题

- Google ADK 私有方法可能变化，需要按声明的 2.7.x 基线验证。额外测试报告中的 2.1.0 组合只能补充兼容证据，不代表改变依赖策略或作出发布保证。
- 普通路径委托后，父类会再次合并请求头。第一次合并只用于路由检查，必须没有副作用。
- 父类在资源进入后的传输失败及取消，保留上游语义。本次保证子类不会额外持锁，不承诺修复上游清理问题。
- 现有可信分支捕获 `Exception`，未覆盖所有取消情况。扩大清理范围不属于本次死锁修复。
- Google ADK 2.7.1 的父类会话池使用三个元素，未改动的可信分支仍保存两个元素。可信分支继承的最终 `close()` 兼容问题是既有局限，不属于本次普通路由修复。可信模拟测试会显式关闭它们持有的栈，不声称已验证继承的最终关闭兼容性。
- 没有未决产品选择阻塞设计。受支持环境准备及定向行为已验证；报告中的 Google ADK 2.1.0／Python 3.12 组合尚未测试。

## 审查与交付记录

2026-10-26，基线 `c662cc8d`，实际差异范围：会话管理器、新增隔离路由测试、现有普通缓存测试数据，以及本次 PRD／组件规格双语文件。

提供的技能目录没有 `review-spec`，因此直接完成同等设计审查。已检查职责、可行性、接口、错误、安全、兼容、可测试性和双语一致性。设计中已解决的问题：先分流后加锁；检查请求头时不修改它；移除标记前生成可信会话键；使用声明的依赖基线；区分源码检查和运行证据。没有未解决的设计阻塞项。

用户已于 2026-10-26 批准：“按这个方案修改代码和测试”。范围内的源码／测试修改和文档核对已完成。最终实现审查未发现范围内的正确性、并发、请求头隔离、资源职责或兼容阻塞项。`AC-1`、`AC-2`、`AC-3`、`AC-5` 通过。由于完整仓库检查在本次路由变更之外失败，`AC-4` 未满足；保留 `approved`，不声称所有验收条件均已实现。未包含无关修复或软件包发布。

用户随后授权提交：“提交并推送到origin/main上”、“将本地历史一并同步到 origin/main”和“提交代码”。首次同步尝试为 `blocked`：Git 要求 GPG 签名，但文件系统沙箱拒绝 GPG 写入 `~/.gnupg`。已撤销 rebase，恢复全部七个任务文件；尚未提交或推送。备份 stash 仍保留。Git hooks 和签名配置均未更改。

2026-10-26 提交准备，基线仍为 `c662cc8d`，范围为暂存的七个文件：`uv run --extra dev pytest tests/tools/mcp_tool -q` 为 `pass`，24 条测试通过，耗时 4.09s。首次 `uv run --extra dev pre-commit run --all-files` 因 virtualenv 尝试写入沙箱之外的缓存目录而 `blocked`。改用临时缓存后，`VIRTUALENV_OVERRIDE_APP_DATA=/tmp/veadk-mcp-precommit-virtualenv uv run --extra dev pre-commit run --all-files` 为 `pass`：Ruff 检查、Ruff 格式、Gitleaks、运行时依赖策略和 YAML 密钥扫描全部通过。所有 hooks 均保留。`git diff --cached --check` 为 `pass`。这些是成功同步之前的准备检查；同步后的必需检查仍待执行。此前记录的完整回归失败仍未解决。

2026-10-26 文档验证：PRD／规格双语配对、需求／任务／验收／契约 ID 一致性、相对链接目标存在性、占位符扫描和行尾空白检查均为 `pass`；`git diff --check` 为 `pass`。这些检查覆盖四个新增设计文件，不证明运行行为。

2026-10-26 实施证据：

- `uv` 解析后的环境：Python 3.11.14、Google ADK 2.7.1、MCP 1.26.0。
- 修复前首次会话测试：`fail`，两条各在 2s 后得到 `TimeoutError`，未进入传输，堆栈停在父类获取锁处。
- 修复后首次会话测试，在修正夹具隔离后：`pass`，两条测试耗时 1.93s。首次修复后运行暴露了 Google auth 自动发现凭据的行为；最终夹具显式禁用此行为，并修正内存流方向。
- 最终定向检查：`uv run --extra dev pytest tests/tools/mcp_tool -q` 为 `pass`，24 条测试，包括 19 条新增测试及保留的五条组件测试。新夹具用内存流替换外部传输和可信证明；ADK `SessionContext`、MCP 初始化、本地 MCP 服务、工具发现和调用均使用真实实现。
- 首次组合运行发现普通缓存元组过期，以及可信测试夹具漏传超时参数。均已修正测试夹具，没有增加生产绕过逻辑。
- `uv run --extra dev ruff check ...` 为 `blocked`，dev extra 未提供 Ruff 可执行文件。未修改依赖元数据，改用仓库 pre-commit 的版本：`uvx --from ruff==0.11.12 ruff check veadk/tools/mcp_tool/trusted_mcp_session_manager.py tests/tools/mcp_tool/test_trusted_mcp_components.py tests/tools/mcp_tool/test_trusted_mcp_session_routing.py` 为 `pass`。相同文件的 `ruff format --check` 为 `pass`，三个文件均已符合格式。
- 仍有上游既有弃用警告，不代表测试失败。
- 使用最终隔离夹具对照基线：在独立 Python 进程中加载 `git show HEAD:veadk/tools/mcp_tool/trusted_mcp_session_manager.py` 的会话管理器源码，仅替换工具集使用的管理器类。`pytest.main(["tests/tools/mcp_tool/test_trusted_mcp_session_routing.py", "-k", "standard_first_session", "-q", "--tb=short"])` 为 `fail`，两条均出现预期的锁超时，17 条未选中，耗时 4.31s。这确认最终夹具能检测原始缺陷，且没有修改工作区文件。

完整回归发现：

- `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` 为 `fail`，7556 条通过、17 条失败、58 条跳过、4 条 xfailed、52 条警告、2 条收集错误，耗时 436.40s。相关 MCP 测试全部通过。跳过及 xfailed 的测试不证明行为通过。
- 十条 Codex 运行时失败需要尚未安装的可选包 `openai_codex`；两条自托管沙箱收集错误需要尚未安装的可选包 `anthropic`。这些依赖与 MCP 路由无关。
- 三条失败尝试写入工作区之外的路径，包括 Studio 状态和同级应用输出；文件系统沙箱拒绝了这些路径。未请求扩大文件系统访问范围，也未修改机器配置。
- 未改动测试中的四个断言失败：Markdown 工件内容类型、两条 harness 模型配置检查，以及一条 sidecar 子进程环境检查。不记录真实本地模型标识符或原始环境值。
- 基线确认：在独立进程中，把原始管理器类替换进管理器／工具集两个模块，再用 `pytest.main([... , "-q", "--tb=no", "-o", "cache_dir=/tmp/veadk-mcp-baseline-pytest-cache"])` 运行下列节点。五条全部失败，耗时 6.87s，在变更前管理器下复现了对应失败：
  - `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`
  - `tests/runtime/codex/test_codex_runtime.py::test_turn_usage_reports_this_turn_not_the_resumed_threads_total`
  - `tests/cloud/test_harness_app_http.py::test_harness_app_exposes_agent_info`
  - `tests/cloud/test_harness_app_http.py::test_harness_session_create_accepts_id_and_get_agent_config`
  - `tests/extensions/harness/sidecar_runtime/test_sidecar.py::test_run_wraps_child_with_sidecar_environment`
- 终端轮询重试在沙箱拒绝结果后重新启动了完整命令；已中断这次重复运行，不重复执行。记录的检查结果来自上文已经完成的 436.40s 运行。
- 已评估用户文档／示例：现有可信示例无需 API 或配置迁移。不声称任何已发布版本包含本次工作区修复。真实可信证明及报告中的精确依赖组合仍未验证；可信最终关闭兼容性仍是已记录的既有局限。
