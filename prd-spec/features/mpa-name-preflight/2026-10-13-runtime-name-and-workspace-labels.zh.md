# MPA 名称预检查与可读业务 Workspace 名称

[English](2026-10-13-runtime-name-and-workspace-labels.md)

- Change ID：`mpa-name-preflight`
- 创建/修订：2026-10-13
- 状态：implemented
- 归属契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-20
- 前置设计：[独立业务 Workspace](../mpa-agent-pg-workspace/2026-10-13-independent-business-workspace.zh.md)

## 背景与证据

表单校验 Runtime 名称字符和长度，但未查询云端是否可用。创建流程准备 PG/网络后，`ensure_worker` 才发现其他资源占用同名模板。`RuntimeCloud.list_runtimes` 为删除检查逐个展开全部 Runtime 详情，不适合输入时查重，应增加轻量分页名称查询。新独立 PG 当前以哈希命名，在控制台不便查找。

[AIDAP CreateWorkspace](https://docs.volcengine.com/docs/87275/2105881)规定名称为 2–128 字符，以字母或中文开头。Runtime 名称允许 4–64 位 ASCII 字母、数字、下划线和连字符。建议的 `mpa_agent_<Runtime 名称>` 最长 74 字符，且以字母开头。新独立业务库使用 `aidb`；已有数据库名称保持固定。

## 目标、场景与需求

- FR-1：启动新 MPA 任务前检查所选部署提供商/账号/地域。其他智能体占用同名 Runtime、沙箱模板或目标业务 Workspace 时，明确以本地化重名消息阻止创建，不返回云凭据及其他资源详情。
- FR-2：向导首次“下一步”检查名称，最终 POST 和后台编排独立校验，不依赖前端。查询失败明确阻止并允许重新检查，不伪装成名称可用/空数据。覆盖分页、超时、取消、IME 和过期响应。
- FR-3：相同请求重试在身份/绑定可证明时复用自己的资源；其他归属或不明确归属明确失败。已有任务/登记资源保留原绑定和名称。用户认证和提供商选择仍由服务端控制。
- FR-4：新独立业务 Workspace 使用 `mpa_agent_<手填 Runtime 名称>`。新独立请求业务库为 `aidb`，已有请求保留登记的名称。引导/登记身份保存并保持已选 Workspace 名称，不重命名已有 Workspace，不在重试中切换端点。兼容显式/手动/共享配置。
- FR-5：不改通用智能体创建、共享管理 PG/网络/APIG、Runtime 业务表、OV 创建及资源删除行为。

## 设计与契约评估

增加 Studio 授权的只读名称检查和轻量 Runtime 分页，仅在同名候选需要验证归属时读取详情。复用 `WorkerCloud.find` 和 AIDAP `find`；PG 连接准备可能修改端点设置，不能用作只读预检查。同时检查本地进行中的创建请求与云资源名称，在购买前复核。平台唯一性仍是并发创建的最终边界，先读后创建不能保证独立 Studio 主机间原子互斥；额外共享占位协议需先审查契约再实现。

MPA 输入沿用原校验，Workspace 加前缀兼容数字开头的 Runtime 名称。删除 Runtime 后若同名旧 PG 被其他归属占用，应明确冲突，不自动共享。Workspace ID、归属标签、端点校验和内部稳定 ID 仍是权威绑定。已有哈希 Workspace 使用引导文件保存名称或已核验登记名称，不改用新推导名称。密钥仅留在服务端。

受影响文件：受管 Runtime/worker 查询调用、名称检查模块、PG 引导/配置/service 与 runner 错误映射；BFF 创建接口/tasks、前端 API 类型/弹窗/文案、定向 Python/React 测试、双语维护契约/说明和 WebUI 构建资源。兄弟 MPA 仓库不需修改。

## 任务与验收

- T-1 / FR-1,2,3 / AC-1：先写其他归属重名、合法重试、分页、检查失败与过期/取消响应的失败测试，再实现只读接口和服务端提前拦截。
- T-2 / FR-4 / AC-2：覆盖数字开头/大小写/64 字符名称、旧哈希引导/登记绑定、重启和购买结果未知；仅在已核验独立 Workspace 使用 `aidb`，不切换已有资源绑定。
- T-3 / FR-5 / AC-3：通用智能体/删除回归，双语文档/资源及审查。测试不创建云资源。

通过 `uv run --extra dev pytest` 执行定向测试，再使用两个 worker 执行已有 managed/部署回归；对改动 Python 跑 Ruff/Pyright；执行 `npm --prefix frontend test`、构建、国际化、资源引用检查及隔离真实浏览器验证。不授权真实购买、提交、推送或部署。实现后的结果在下方记录。

## 风险与审查记录

云列表存在最终一致性，预检查不能保证跨主机原子性；后续平台重名拒绝须明确展示。新增查询依赖部署凭据现有 Runtime/tool/AIDAP 读取权限。旧 Workspace 名称和失败任务资源不能静默重命名/接管。`review-spec` 不可用，已直接核对归属边界及拟定兼容要求；用户批准见下方补充，最终实现审查在交付时记录。用户于 2026-10-13 要求创建前查重，并询问用 MPA 名称替代 Workspace 哈希；已按 AGENTS.md 提交具体范围/命名确认。实现按下方已批准补充执行。

## 已批准的 aidb 与请求兼容补充

用户于 2026-10-13 通过“改成aidb吧 … 这个也一起改了？”批准三项修改。直接设计审查替代不可用的 review-spec，无设计阻塞。新配置/表单显式携带 `businessDatabaseName: aidb`，要求 `businessWorkspaceMode: per-agent`。省略时保留前一版哈希库名/Workspace 契约及已保存请求指纹。CLI/YAML 可通过 `managed.postgres.business-database-name: aidb` 启用。名称化 Workspace 的引导意图保留布局标记，注册元数据保留 Workspace 名和数据库选择。旧二元素引导配置及已登记哈希名称，即使用新表单重试也保持原布局。

AIDAP 默认预建 `aidb`。标记为该智能体业务库前，核验独立 Workspace 身份、数据库属主、无非系统/非扩展关系对象、无已有 Runtime/ready 绑定，并持有事务 advisory lock。标记不匹配、初始库非空或登记库缺失均明确失败。写标记前保存初始化意图，匹配标记使重试幂等。Runtime 校验、PGDATABASE、token/meta 初始化及就绪检查统一使用已选数据库。共享管理库仍为 mpa_admin_db。

BFF 在创建任务前查重，通过私有任务名称范围快照（已核验提供商/账号/地域）在 SQLite 事务中阻止本主机并发同名请求；旧无范围的活跃请求按其提供商/地域保守检查。失败任务占位不会阻塞后续任务。Runner 在新布局副作用前核验快照部署账号，并再次查重。只读检查有超时，只返回是否可用/错误码。通用智能体 API 不变。跨主机先查后创建仍依赖云端约束与归属校验，不宣称分布式占位保证。

实现遵循已批准范围；实际验证记录如下。不授权云购买、提交、推送或部署。

## 实现审查与验证（2026-10-13）

T-1–T-3 与 AC-1–AC-3 已实现。直接审查确认了归属检查的失败关闭行为、数据库标记/空库保护、重试兼容性及提供商/账号边界。新布局 Web 请求必须使用服务端按用户/请求生成的内部身份；传入不同 agent ID 会在受理任务前拒绝，防止复制其他请求的内部 ID 接管其部分创建的 Workspace。旧请求保留原显式 ID 契约。

验证范围：基于 `71175c68636dc5b951e9804eb292d85402511e68` 的工作区差异，包括工作区此前已有的独立 PG 和自动 OV 改动。先写回归测试时有 12 项 Python、2 项 React 失败，随后实现通过受影响检查。没有撤回无关用户改动。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| Managed/部署 Python 回归 | pass | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_skill_space.py tests/integrations/test_ve_faas_deploy_image_key_auth.py -q --no-cov`：978 项通过；根据本地资源选择两个 worker。 |
| 改动 Python 静态检查 | pass | Ruff 0.11.12 和使用 `.venv/bin/python` 的 Pyright，覆盖所有改动 Python 文件。仓库本地工具不可用，使用临时 `uvx` 工具，无全局安装。 |
| 前端测试 | pass | `npm --prefix frontend test`：Node 和 React 测试，含下一步/POST 重名、进行中检查取消和过期结果抑制、已有通用智能体/删除测试。 |
| 前端构建 | pass | `npm --prefix frontend run build`；同步 WebUI 构建产物。 |
| 国际化与资源引用 | pass | `npm --prefix frontend run check:i18n` 与 `npm --prefix frontend run test:webui-assets`：2 个语言 / 21 个命名空间，113 个资源 / 350 个引用。 |
| 浏览器流程 | pass | 真实 React 弹窗配隔离模拟 HTTP：重名/可用名称、查询不可用、POST 后置冲突后可编辑、旧共享请求恢复、BytePlus 手动 OV，以及 390×844 布局。没有发送云操作；已移除临时夹具/服务。 |
| 密钥扫描 / 差异空白 | pass | 使用仓库配置对改动文件执行 Gitleaks，输出脱敏；`git diff --check`。 |
| 真实云创建与 PostgreSQL 集成 | not_run | 本次未授权。提供商购买、数据库接管 SQL 和就绪仍需独立真实验收。 |
| Harness/进程 smoke 门禁 | not_applicable | 未修改 harness/sidecar 或进程契约。 |
| 提交 / pre-commit 门禁 | not_run | 未授权提交；后续提交前仍须执行 pre-commit 和分支同步。 |

本地审查无剩余阻塞。跨主机查询/购买竞态仍依赖云端约束及归属校验，不宣称分布式锁保证。已有数据不迁移。重启 Studio 并开启新请求后使用新布局。
