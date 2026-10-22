# 已注册 Agent 别名写入 MPA 业务库

[English](2026-10-22-agent-alias-business-store.md)

- Change ID：agent-alias-business-store
- 日期：2026-10-22
- 状态：implemented
- 用户授权：明确同意别名写入业务库、移除别名对 AGENTKIT_ACCOUNT_ID 的依赖，并同步修改 VeADK 与 agentkit-mpa-agent。
- 取代 2026-10-22 space-aliases 设计中的账号共享存储决定。

## 背景与证据

当前 Runtime 别名 provider 单独连接 SHARED_APIG_DATABASE_URL 并要求 AGENTKIT_ACCOUNT_ID，但别名属于当前 MPA 中某个空间下的已注册 Agent。账号标识缺失时 Studio 因此禁用编辑，其代理还会在转发前拒绝别名 PUT。空间绑定已使用持久化 MPA 业务库引擎，应复用该引擎。

## 目标与非目标

已注册 Agent 别名持久化到业务库；管理、发现和精确 @名称解析使用同一份数据。修正 Studio 文案并让现有别名更新路由通过鉴权代理。本次不修改普通 Agent 行为、中心注册名称、Agent Card、云配置或派发/Harness 授权；不新增依赖、不写云、不部署、不自动导入共享数据、不破坏已有表结构。

## 场景与需求

- FR-1：没有账号 ID 和共享库配置时，使用持久化业务引擎保存、清除 Agent 别名；重启保留值与 revision。
- FR-2：作用域为 (mpa_id, region, space_id, agent_id)，规范化别名在 (mpa_id, region, space_id) 内唯一；同一引擎中的不同 MPA、空间、地域互不共享。
- FR-3：列表、发现和 @名称解析使用相同作用域。保留 NFKC、80 字符上限、casefold 唯一性、revision CAS、清空墓碑以及实时成员与派发校验。业务库存储错误明确失败，不回退账号库。
- FR-4：Studio 显示“Agent 别名”并解释当前 MPA/空间作用域；旧 Runtime 未声明能力时继续禁用并提示升级。PUT 仅允许现有绑定路由和 Agent ID 合法的精确别名路由；保留所有者/管理员鉴权。

## 设计与契约影响

Runtime A2AAliasStore 复用 A2ASpaceStore.engine，不新建或释放独立引擎。新增业务表 mpa_a2a_registration_aliases：主键 mpa_id VARCHAR(256)、region VARCHAR(64)、space_id/agent_id VARCHAR(128)；字段 alias VARCHAR(80)、alias_key VARCHAR(240)、revision INTEGER NOT NULL；唯一约束 (mpa_id, region, space_id, alias_key)。追加 0016 迁移，不修改已发布迁移。PostgreSQL 懒初始化继续使用现有 advisory lock。不修改或读取旧 mpa_a2a_agent_aliases 表；已有共享别名需重新填写，避免错误复制到其他 MPA。回滚保留新增表并回退二进制，无须删数据。

服务持有复用业务引擎的别名 store。管理列表/保存通过服务端 dependency 获取当前 MPA，不接收请求体身份；地域来自 Runtime 配置。外部 API 路径、请求体和响应字段兼容。业务库失败明确报错，不返回空成功、不回退。管理可编辑有权限的空间，但派发仍需已绑定空间。保留取消、有限名称查询超时、绑定重查与实时中心校验。

VeADK 仅修改双语提示、文档、代理白名单与对应构建产物，不改普通 Agent 部署/配置。复用现有别名编辑器和基础控件，不做视觉重设计。同步两个仓库协作 Agent 长期契约与 VeADK 双语文档。

## 任务与受影响文件

- T-1 / FR-1–3：先补 Runtime store/service/路由回归，覆盖隔离、重启、冲突、错误和 PostgreSQL 迁移。
- T-2 / FR-1–3：app/stores/a2a_alias.py、app/services/a2a_space.py、app/api/v1/collaborating_agents.py，追加 app/migrations/0016_a2a_registration_aliases.sql。
- T-3 / FR-4：代理回归、veadk/cli/cli_frontend.py、frontend 双语提示、现有编辑器测试与 web 构建产物。
- T-4：同步契约、用户文档、验证证据；审查安全、兼容性、资源归属和双语等价性。

## 验证与验收

AC-1（FR-1/T-1–2）：无需共享配置；新服务/连接可读取业务库持久化别名。AC-2（FR-2/T-1–2）：SQLite 与隔离 PostgreSQL 验证 MPA/地域/空间隔离、唯一性、CAS 与清空。AC-3（FR-3/T-1–2）：管理保存/列表、发现与精确名称解析一致；无成员权限或数据库失败不能派发。AC-4（FR-4/T-3）：真实 Studio 代理使用服务端凭据转发别名 PUT、保留上游冲突、拒绝无关 PUT 和未授权写；UI 不再要求配置共享账号。

执行后在下方记录实际命令/结果。Runtime：定向 pytest、make lint、全量 make test、governance/project-skills/project-tooling 检查、隔离 PostgreSQL 迁移/store 契约。VeADK：定向 uv run --extra dev pytest、变更 Python 的 Ruff/Pyright、npm --prefix frontend test、npm --prefix frontend run build、i18n/assets 检查，真实浏览器模拟接口的正常/错误/键盘/IME/取消/窄屏流程。不调用真实云；本地模拟不构成部署证据。

## 风险与评审

旧共享别名不自动导入；完整启用需同时升级 Studio 和 Runtime。业务库故障阻断依赖别名的操作；业务引擎生命周期归 channel store，别名代码不得释放。未增加外部副作用权限。review-spec 不可用，已直接评审归属、作用域、错误、API 兼容性、新增迁移回滚、测试和双语等价，无设计阻塞；以上用户授权覆盖此次修正。

## 交付记录

2026-10-22，Runtime 0d3dd35 与 VeADK 46f60e12 上的未提交修正：

- pass：实现前 RED 复现 3 项 Runtime 失败、6 项代理拒绝、2 项文案失败；对应回归现已通过。
- pass：最终隔离 PostgreSQL/Runtime 定向命令覆盖 tests/test_a2a_aliases.py、tests/test_a2a_business_aliases.py、tests/test_a2a_business_alias_migration.py、tests/test_a2a_rebase_migration.py、tests/test_a2a_registry_collaborators.py、tests/test_a2a_management_routes.py、tests/test_schema_migration_contracts.py，54 passed、无跳过。临时 PostgreSQL 16 验证全新/v15、全部 v14 迁移来源、重复初始化、跨连接冲突及旧共享表保留，容器已删除。
- pass：PATH=/tmp/a2a-codex-0155/node_modules/.bin:$PATH make test，10823 passed、386 skipped，634.22 秒；前后源码指纹均为 5a56a035892b8a93396e4d82a69df257965e39da64f9d02ec8c13c5748db7694。跳过不能证明真实集成。早期运行因修改了候选树而中断/失效，不计入通过。
- pass：make lint、变更 Runtime 文件 Ruff、三个变更实现文件 Pyright（0 错误）；显式初始化分页 total，不改变查询行为。
- pass：make governance-check BASE_SHA=HEAD HEAD_SHA=HEAD（当前工作区修正，契约检查和 14 项测试）、make project-skills-check。默认 origin/master 比较包含多个历史 change-id，无法唯一选择；未修改或绕过门禁。
- fail：make project-tooling-check，既有 OpenViking CLI/skill 缺失；用户选择不另写环境说明，未修改全局配置。不声称完整发布准出。
- pass：uv run --extra dev pytest -q tests/cli/test_frontend_runtime_proxy.py，142 passed；扩大到 uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/cli，1844 passed、6 skipped，使用 2 个 worker。
- pass：npm --prefix frontend test，1389 项 Node、236 项 Vitest；npm --prefix frontend run build、npm --prefix frontend run check:i18n（2 语言/23 命名空间）、npm --prefix frontend run test:webui-assets（114 文件/351 引用）；重新生成匹配哈希资源并移除旧哈希。
- pass：真实浏览器使用实际别名编辑器、Studio tokens/CSS、真实 Runtime HTTP 路由，中心为 fake registry，业务库为临时 SQLite：中文保存、刷新页面读回、清空、CAS 冲突/刷新、Escape 取消、旧 Runtime 提示和 360 像素容器均已验证。合成 IME、请求取消/卸载和重复提交测试通过；未单独验证原生输入法和缩放浏览器窗口。临时文件、服务与数据库已清理。
- pass：VeADK Ruff hooks、pre-commit --all-files（含密钥扫描）；Pyright 使用同一解释器对照 HEAD：57 个既有诊断、0 新增。因此原始 Pyright 对基线仍为 fail，不顺手修复无关类型问题。仓库依赖未安装独立 Ruff 命令，改用仓库锁定的 pre-commit hooks。
- pass：双语需求/标识符/相对链接及 diff 空白检查。Runtime 全量运行后的最终修改仅为文档及其 ignore 例外，实现/测试与已验证版本相同。
- not_run：真实云/模型烟测、部署、镜像发布、提交和推送，均不属于本次授权。未改 Tool/MCP 声明或 adapter，路径触发的 MCP tool gate 为 not_applicable；本地代码交付未执行完整 coverage/发布门禁。

AC-1–4、T-1–4 的本地行为验收已满足。实现/安全/测试/架构审查无本次阻塞：业务引擎生命周期保留原所有者、作用域由服务端确定、存储失败拒绝、新增迁移、代理鉴权保持。旧共享别名需重填；Studio 和 Runtime 应一起升级，无需补云端账号 ID。完整发布准出仍有上述工具与基线静态检查限制。未提交、推送、发布镜像或部署。

附加密钥扫描：默认 Gitleaks 扫描全部变更文件（17.70 MB）时将压缩依赖表达式 一段压缩后的成员访问表达式 报为一项疑似密钥；人工核对为标识符表达式，不是凭据。随后 VeADK 使用既有 .gitleaks.toml 扫描纳入范围的源码（1.02 MB）、Runtime 使用默认规则（456.14 KB），均为零泄漏；未修改扫描规则或白名单。

2026-10-22 提交授权补充：用户授权仅提交、推送 VeADK 并跟踪 PR CI。已 fetch 官方 main 和 fork 分支，并 rebase 官方 main（无新增提交，基线仍为 cb9975df）。锁文件仅丢失 27 个可选构建工具记录，已保留备份并恢复，未修改依赖。暂存扫描发现文档中引用的压缩依赖表达式误报，已删除样例，不修改扫描规则。Runtime 仓库本轮不提交。

CI 准备补充：静态检查发现本 PR 已有 5 个 Python 文件缺失 Apache 头，现仅补齐许可证注释：frontend/server/a2a_center.py、frontend/server/mpa_images.py、tests/cli/test_a2a_center_actions.py、tests/cli/test_a2a_center_registration.py、tests/cli/test_mpa_images.py。无业务行为或契约变化；此纯注释修正无需递归 PRD。

提交前最终验证（2026-10-22）：同步 cb9975df 后，pre-commit 全部通过；前端 1389 Node + 236 Vitest、build、i18n、114 文件/351 引用检查通过；依赖 policy 和 uv lock --check 通过。按 CI 脚本执行 Sidecar 后端四组：143 passed/1 skipped（覆盖率 96%，门槛 91%）、9 passed/50 deselected、97 passed、39 passed；前端 Sidecar 22 passed，行覆盖 100%、分支 94.44%。5 个仅补许可证头文件 Pyright 0 错误；PR 全部 30 个 Python 文件有规定头。默认 Python 全量（2 workers）为 7861 passed、53 skipped、4 xfailed、1 failed（474.00 秒）；唯一失败仍为 tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes，原 HEAD 46f60e12 的独立归档在同一环境也失败；本机 Python 3.10 的 .md MIME 查询为 None，未改动无关产物行为。提交推送已获本轮用户授权；GitHub CI 需以新提交的远端结果为准，目前旧运行均为 action_required，不能记为通过。
