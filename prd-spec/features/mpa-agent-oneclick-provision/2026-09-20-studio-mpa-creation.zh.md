# Studio MPA 创建与前置资源准备

[English](2026-09-20-studio-mpa-creation.md)

- 变更 ID：`studio-mpa-creation`
- 创建/修订日期：2026-09-20
- 状态：implemented
- 基线：VeADK `314d43c8`；已检查的 MPA 部署实现 `0368873`。
- 相关契约：[MPA 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)、[Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)。
- 契约扩展：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 背景与证据

`frontend/src/ui/MyAgents.tsx` 为通用智能体和沙箱智能体提供创建卡片，但 MPA 筛选下没有入口。`veadk/cli/cli_mpa.py` 接收现有示例 YAML，采用旧的占位元数据部署流程，不准备账号共享网络或每个智能体的持久业务库，也无法通过 AgentKit 共享端点推断客户 IM 网关。

独立维护的 `agentkit-mpa-agent` 仓库目前拥有 `app.deployment.runtime.AgentRuntimeDeployer`、账号网络准备、独立业务库、技能空间登记和账号共享 APIG/IM Gateway 服务。其 `docs/agent-runtime-deployment.md` 和 `docs/account-shared-apig.md` 明确要求外部 Studio 创建接入该编排。当前任务检索返回空的对话内容，因此这里的结论来自已检查的代码和文档，不假设已读到对话原文。

## 目标与非目标

在 MPA 目录中创建可用智能体，与 CLI 使用相同的前置配置。展示缺失配置、进度、失败及可恢复创建。保留旧 CLI 路径。

不创建 PostgreSQL 云实例、PostgreSQL 登录角色、IAM 角色/策略、模型服务、跨 VPC 连接或数据库白名单。这些前提需提供并检查。不隐式复制其他智能体的渠道或技能空间。不提交凭据；实施过程中未经单独授权不执行真实云部署。

## 场景与需求

- **FR-1：** 有智能体管理权限且选择 MPA 类型时，展示“创建 MPA 智能体”卡片，火山引擎下空列表也有入口。其他类型保持原有创建行为。
- **FR-2：** 打开创建窗口，加载所选地域的安全服务端配置摘要。缺失或不兼容的部署配置阻止提交，并指出未满足的前提。不向浏览器返回密码、令牌、原始环境、可执行文件路径或私有 YAML。
- **FR-3：** 操作者提供稳定智能体 ID 和描述；自动生成的 ID 在重试时保持不变。服务端决定允许使用的配置、运行环境、凭据和资源账号，不允许前端通过账号 ID 选择账号。提交前展示将创建或复用的资源。
- **FR-4：** 扩展 `mpa-create.config.example.yaml`，增加带版本的托管部署区段：地域、PostgreSQL 管理/注册库密钥引用、Runtime 模板或参考 Runtime、网络选择/默认网段和可用区、APIG 复用/接管策略、worker 配置及超时。CLI 和 Studio 共用解析校验。显式旧 CLI 参数保持原优先级和行为。
- **FR-5：** 云写入前检查依赖及配置。准备/复用账号网络，验证/创建共享 APIG 和 IM Gateway，再确保业务库与技能空间并部署 Runtime。复用 MPA 注册库及账号/地域锁，不另建无关注册机制、不随意选取网关。等待应用就绪时不得持有该锁。
- **FR-6：** 使用当前托管元数据初始化，不写占位地址。启用公私网、KeyAuth、MPA 分类、元数据/IM 初始化并绑定 worker。不意外继承参考智能体的身份、渠道凭据、技能空间或 worker 身份。
- **FR-7：** 平台 Ready 且应用 `/readiness` 成功后才返回成功。返回安全的 Runtime/技能空间/APIG ID，并刷新原地域的 MPA 列表。不把本地依赖检查描述为云权限或连通性证明。
- **FR-8：** 防止重复提交，按认证用户隔离任务，保存足够的非敏感身份信息以支持重启或响应丢失后的恢复。同身份/配置复用登记资源；未完成配置冲突时明确失败。复用原生持久化创建意图和 client token。
- **FR-9：** 支持取消、截止时间、进程清理及过期响应隔离。取消停止编排，不等于回滚共享/持久资源；说明保留资源以供恢复。只允许删除本次新建的临时资源，不自动删除已登记业务库、技能空间、共享 APIG/网络或原有 Runtime。
- **FR-10：** 使用本地化文案、现有创建卡片及模态组件、语义颜色、键盘焦点/输入法处理，以及加载、空态、错误、重试和窄窗口布局。

## 设计与备选方案

已批准决策（2026-09-20）：用户选择“迁入 VeADK”。将网络、数据库、技能空间、Runtime 和共享 APIG 编排迁至 `veadk/integrations/mpa/managed/`，保留原生注册库结构、归属标记及锁语义。VeADK 负责迁入实现及测试，不依赖外部仓库、部署 Python 环境或用户指定的子进程命令。Studio 任务通过当前 VeADK Python 解释器启动子进程，以可靠取消阻塞 SDK 调用。旧 CLI 路径保持不变。

直接设计审查：现有 AgentKit/Volcengine、SQLAlchemy 和 asyncpg 依赖可以支持迁移。只迁移部署所需 APIG 操作；机器人路由和应用启动仍在 MPA 镜像内。镜像须支持共享注册库元数据初始化。Runtime、网络、APIG 统一使用同一凭据解析器，防止跨账号准备；支持轮换 STS 和已有部署 AK/SK，不增加 IAM 策略修改。先通过测试和归属校验处理云响应丢失及多用户重试，再接入界面。

适配器在创建 Runtime 前组合账号网络准备与 `SharedAPIGService.ensure`，避免嵌套获取账号锁。接管 APIG 需要显式 ID，且账号/地域/VPC 一致。部署凭据与 Runtime 凭据分开：迁入的部署 APIG 客户端与 Runtime/网络调用共用刷新并核验账号的凭据来源。MPA 镜像启动后仍使用自身挂载的 STS 来源。资源准备前报告缺失前提。Runtime 角色仍需自身挂载的 IAM 凭据和云权限。

参考 Runtime 模式只复用部署设置；显式模板模式支持新账号。PostgreSQL 实例及共享注册库须已存在。自动新建账号网络不能证明能访问私网 PostgreSQL，需要时必须显式指定兼容 VPC。适配器保留现有托管命名和归属标记，创建专属 worker 或校验显式指定的可复用 worker。

### 已批准接入决策

采用兼容 CLI 入口 `veadk mpa provision --config /secure/mpa-create.config.yaml --agent-id customer-service`，读取同一个 YAML 文件中的新增 `managed` 区段；`veadk mpa create` 保持当前平铺参数语义。`provision --dry-run` 校验配置并仅输出安全计划，不加载云凭据、不查询或写入云/数据库资源。Studio 通过仅限服务端的 `VEADK_MPA_CREATE_CONFIG` 设置定位同一配置。

`managed` 字段：`version: 1`；环境变量名 `database-admin-url-env`、`shared-database-url-env`；可选的部署 STS 轮换文件 `credential-file`；互斥的 `from-runtime`/`template-file`；`network` 包含 `vpc-id`、`subnet-ids`、`vpc-cidr`、`subnet-prefix`、`zone`；显式接管 `apig.adopt-id`；`worker` 包含显式复用 ID 或镜像/参考配置；以及 `timeout-seconds`。环境变量名是引用，不是数据库 URL 字面值。相对模板路径基于 YAML 所在目录解析。未配置对应地域时报配置错误，不回退到其他地域。

两个来源选择器均未提供时，仍可使用平铺的模型/镜像/PG 参数构建全新 Runtime 模板。托管模式通过原生智能体身份推导业务库名，不把旧 `pg-database` 复用成多个智能体共享的业务库。旧 `account-id` 只能作为期望账号断言，与云端认证账号比较，不能作为账号可信来源。

### 接口

- CLI：`veadk mpa provision` 读取现有 YAML 的托管区段；继续支持旧 `veadk mpa create`。
- `GET /web/mpa-creation/config?region=...`：安全配置摘要及未满足前提。
- `POST /web/mpa-creation/tasks`：经过校验的身份、描述、地域和请求 ID；返回任务 ID。
- `GET /web/mpa-creation/tasks/{id}`：用户隔离的阶段、状态、安全结果及错误码。
- `POST /web/mpa-creation/tasks/{id}/cancel`：界面确认后的幂等取消。
- 状态：`running -> succeeded` 或 `running -> cancelling -> cancelled`；失败以 `failed` 结束。阶段报告 `queued`、`checking`、`network`、`gateway`、`worker`、`database`、`skills`、`deploying`、`verifying`。远端结果未知时可恢复，不标记成功或盲目重新创建。

进程消息使用结构化协议、大小限制和字段白名单。不得向客户端转发原始部署程序 stdout/stderr、数据库 URL、环境变量、SDK 异常或 Pydantic 原始校验输入。取消/超时/服务端关闭时终止并回收进程。弹窗卸载时取消轮询请求；服务端任务保存在 SQLite 中并可查询；没有自动任务历史过期机制。

## 实施任务与影响文件

| 任务 | 范围 | 需求 |
| --- | --- | --- |
| T-1 | 审查双语设计/契约，确认部署编排归属方式 | FR-1–FR-10 |
| T-2 | `veadk/integrations/mpa/` 下共用托管 YAML 结构与安全前提计划；示例 YAML 和 CLI 接入 | FR-2–FR-6 |
| T-3 | VeADK 部署适配器、协议、资源准备及恢复测试 | FR-5–FR-9 |
| T-4 | `frontend/server/` 任务路由及 `veadk/cli/cli_frontend.py` 注册；鉴权和有界生命周期 | FR-2、FR-3、FR-7–FR-9 |
| T-5 | `frontend/src/ui/MyAgents.tsx`、MPA 弹窗/客户端、双语文案 | FR-1–FR-3、FR-7–FR-10 |
| T-6 | 回归/契约测试、浏览器检查、生产静态资源、双语证据同步 | FR-1–FR-10 |

## 验证与验收

先写会失败的回归/契约测试，再改生产代码。默认使用模拟云接口或隔离测试存储。

| 验收 | 所需证据 |
| --- | --- |
| AC-1：仅在预期 MPA 类型及权限下可进入创建 | 组件测试及真实浏览器正常/空态/窄窗口/键盘/输入法流程 |
| AC-2：缺失配置/PG/注册库/网络/worker/STS 时安全报错并阻止执行 | YAML/CLI 和服务端契约测试；dry-run 不创建资源 |
| AC-3：按顺序准备独立业务库/技能空间及账号共享资源 | 模拟部署集成测试断言调用、请求和归属；原生注册库/请求体兼容性检查 |
| AC-4：重复提交、重启、响应丢失、冲突、超时/取消及切换地域安全 | 生命周期和恢复测试、过期响应及进程回收检查 |
| AC-5：凭据不进入输出、任务持久化或生成资源 | 负向脱敏测试、最终 diff/静态资源密钥扫描 |
| AC-6：旧部署行为兼容 | `uv run --extra dev pytest tests/cli/test_cli_mpa.py tests/integrations/` 限定受影响 MPA 测试 |
| AC-7：发布检查完整且如实记录 | 定向 Python 测试；修改文件 Ruff/Pyright；`npm --prefix frontend test`；`npm --prefix frontend run build`；`npm --prefix frontend run test:webui-assets`；真实浏览器证据 |

共享 API/生命周期变化需要扩大 Python 回归：`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`。获得提交授权后，提交前同步目标远端基线，运行 `uv run --extra dev pre-commit run --all-files` 和单元测试。真实部署冒烟需单独授权，模拟部署测试不能替代它。

## 风险、审查与交付记录

- 用户于 2026-09-20 批准迁入 VeADK。部署实现及兼容测试由 VeADK 维护，共享数据契约仍与 MPA 镜像互通。
- 原生取消保留持久资源；需协调 Studio 临时 Runtime 清理规则与已登记持久智能体，不建议自动破坏性回滚。
- 原生模板继承可能携带其他智能体的 worker，必须显式校验/准备 worker。
- 每个步骤校验 SDK 响应结构及资源就绪状态。本地配置检查不能在云写入前证明所有真实 IAM 权限。
- PostgreSQL session advisory lock 需要直连或 session pooling，不能使用 transaction pooling。
- 2026-09-20 直接审查发现两个额外实施阻塞项，修复纳入 T-3/T-4：
  - 原生 `deploy_runtime` 在创建 Runtime 前准备网络，但通常在 Runtime 启动时才创建 APIG。只调用该 CLI 不满足 FR-5。适配器必须准备账号网络、释放锁、调用 `SharedAPIGService.ensure`，再以解析后的网络调用 `AgentRuntimeDeployer`。写入前核对两个云客户端账号一致，避免嵌套加锁。
  - 现有 `ensure_codex_worker_tool` 按名称复用，并在创建时生成新的 ClientToken，无法证明归属或安全恢复 CreateTool 响应丢失。托管创建必须在原生智能体部署记录中保存 worker 创建意图/token 及已验证归属，或校验显式配置的外部 worker。不能原样调用旧 helper 就宣称具备持久重试安全性。
- 鉴权审查：四个接口均使用 `_require_agent_management`。启用认证的多用户 Studio 中，生成的智能体身份要绑定所属用户，并在持久服务端状态中记录归属；其他管理者猜到智能体 ID 也不能覆盖该用户的部署。本地无认证开发模式明确沿用已有 `local` 主体行为。
- 仓库和可用本地技能目录未找到 `frontend-design`、`ui-ux-pro-max`、`review-spec`。遵循已读取的前端标准并直接进行设计审查。
- 2026-09-20 实现审查：已解决账号锁顺序和 worker 持久创建意图；增加 Universal SDK 原始响应解析回归、云写入前数据库权限检查、响应丢失后输入锁定、任务库连接清理及子进程回收。共享 `ModalLayout` 增加可选 footer 插槽（默认行为不变），弹窗不再通过 CSS 隐藏组件内部结构。用户迁入批准覆盖 T-1；T-2–T-5 已实现。T-6 验证见下文。
- 不改变 SDK 智能体执行、harness/sidecar 协议或文档站契约。现有控制面与旧部署规范链接到新责任方，避免重复契约。[操作指南](../../../veadk/integrations/mpa/managed/README.zh.md)说明前提和恢复流程。


### 验证记录（2026-09-20）

范围：基于 `314d43c8` 的工作区改动；未提交、推送或部署云资源。已批准的迁入已实现；发布验收受下列既有类型检查基线和明确排除的真实云验证限制。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| 定向 Python | pass | `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q`：162 项通过。含最终重复取消/关闭回归，保护清理前该测试失败。 |
| 前端全量 | pass | `npm --prefix frontend test`：1208 项 Node 测试、22 项 Vitest 测试通过。覆盖缺失配置、重复提交、配置迟到、POST 响应丢失、默认/自定义模态 footer。 |
| 生产资源 | pass | `npm --prefix frontend run build`；`npm --prefix frontend run test:webui-assets`：验证 104 个文件、248 个引用。构建仍有既有大包提示。 |
| 本地化 | pass | `npm --prefix frontend run check:i18n`：2 个语言、21 个命名空间一致。 |
| Ruff | pass | `uv run --extra dev --with 'ruff==0.11.12' ruff check veadk/integrations/mpa/managed frontend/server/mpa_creation.py tests/integrations/mpa_managed veadk/cli/cli_mpa.py veadk/cli/cli_frontend.py`；检查新增 Python 和 CLI 增量格式。 |
| Pyright，新增模块 | pass | `uv run --extra dev --with pyright pyright veadk/integrations/mpa/managed frontend/server/mpa_creation.py`：17 个文件，零错误。 |
| Pyright，完整改动 Python 范围 | fail | 加上 `veadk/cli/cli_mpa.py` 和 `veadk/cli/cli_frontend.py` 后有 37 项错误。对未修改的 HEAD 源文件执行相同工具，得到完全一致的 37 项诊断签名；无新增错误。未屏蔽或修改无关既有错误。 |
| 真实浏览器，隔离接口 | pass | 本地 Vite 中实际 MyAgents/弹窗：空 MPA 创建卡片；缺失配置与重试；中文多行、Tab/Enter 提交、Escape 关闭/焦点返回；APIG 进度；成功 ID；失败/重试；取消确认/终态/重试；关闭重开恢复；390×844 及桌面下浅/深主题。仅模拟接口。已移除临时页面/服务/标签并恢复视口。未自动化操作原生输入法候选窗口。 |
| 仓库密钥规则 | pass | Gitleaks 以 `.gitleaks.toml` 扫描改动/新增文件快照，无发现。已从生产源码移除公开 RFC 1918 范围字面量，保持相同范围校验并增加边界回归。未关闭扫描规则或钩子。 |
| 额外生成资源扫描 | fail（已核验误报） | 默认 Gitleaks 规则扫描全部 `veadk/webui` 共 19.17 MB，报告一处编辑器压缩表达式 `anchor.key` / `focus.key`，并非凭据。仓库规则有意排除第三方构建包；此次独立发现已人工检查，未发现敏感值。 |
| 文档及空白 | pass | 核对双语文件、FR/CON/AC/任务标识、相对链接和本地化键；`git diff --check` 无问题。 |
| 真实云 / Codex / piagent 冒烟 | not_run | 未授权分配真实云资源；Codex/piagent 运行时不受影响并从回归排除。模拟云及浏览器结果不能证明真实 IAM/镜像/网络/PostgreSQL 互通。 |
| 全库 pre-commit / 远端同步 | not_run | 未授权或执行提交；获得提交授权后，必须先同步远端再执行这些门禁。 |

首次全量回归 `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` 使用两个 worker：4687 项通过、6 项失败、2 项收集错误、11 项跳过、2 项 xfailed。失败原因是可选 `anthropic`/LlamaIndex 包缺失；临时加载可选包后，剩余 Harness 配置测试需要虚拟模型密钥，避免发现真实 IAM。隔离重跑使用 `MODEL_AGENT_API_KEY=test-only MODEL_EMBEDDING_API_KEY=test-only` 和 `--with anthropic --with 'llama-index-embeddings-openai-like>=0.2.2' --with 'llama-index-llms-openai-like>=0.5.1'`；未修改依赖文件或机器全局配置。最终全量结果记录在下方。后续局部修复由最终 162 项定向测试覆盖。

最终全量回归：**pass**，使用两个 worker 和上述临时可选依赖环境，4711 项通过、7 项跳过、2 项 xfailed、91 项警告，用时 293.20 秒。跳过/xfail 项不宣称已验证。已批准实施范围内 T-1–T-6 完成；真实云验证和既有基线类型错误仍作为明确限制记录。


### 后续：明确的本地配置错误（2026-09-20）

用户报告了笼统的配置加载错误。已复现：Studio 进程从 VeADK 根目录运行，默认 `mpa-create.config.yaml` 不存在；加载该路径得到相同错误。此修复属于已批准 FR-2/CON-1/CON-8：配置错误须指出缺失前提且不泄露密钥。保留配置路径/默认路径契约，不创建云资源或自动选择其他部署账号。区分配置缺失/不可读、YAML 格式错误、Runtime 模板缺失/格式错误，并给出安全提示。修改加载器前增加负向测试，保持脱敏，执行相关 config/routes/CLI 测试及 Ruff/Pyright。复用已有资源属于独立运维选择，等待用户回答。直接设计审查：不改变 HTTP 结构或部署行为，现有本地化界面展示安全服务端细节，仍隐藏私有路径/原始解析异常。

后续验证：**pass**，`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q`（167 项通过）；修改加载器/测试的 Ruff、加载器 Pyright 通过；`git diff --check` 通过。五个新增负向用例在修复前失败。本次后续不改前端行为或静态资源，前端构建/浏览器门禁不适用。用户已选择复用已有北京资源。实际本地凭据转移因自动审批拒绝读取进程凭据及跨仓库复制数据库密钥而暂停，等待明确授权；未改动凭据或云资源。

本地配置完成（2026-09-20）：明确说明凭据范围后，用户要求“帮我加上试试”，授权在本地私有配置中复用。通过只读云调用核验已有北京账号、参考 Runtime 和 worker。创建 Git 忽略的 `.env`、`mpa-create.config.yaml`，权限均为 0600；部署 AK/SK 仅在内存中使用，没有写入这两个文件。确认没有活动创建任务后，以现有启动环境重启本地 Studio。真实配置检查接口返回 HTTP 200、`configured: true`，地域 `cn-beijing`，来源 `reference`，保留 `requiresLiveChecks: true`。未创建云资源或执行部署。此前本地配置授权阻塞已解除；这是配置验证，不是真实部署冒烟。

### 后续修正：worker 查询分页（2026-09-20）

对用户发起的创建进行只读检查：任务停在 `worker`，原生记录只有 `studio_owner`，尚未写入 worker 创建意图。`ListTools(PageNumber=1, PageSize=100)` 与第 2 页返回完全相同的工具 ID。响应提供 `NextToken`，按该游标读取能获得剩余 27 个工具。单次请求不到一秒，旧查询却可能重复调用 1,000 次。这是已批准 FR-5–FR-9/T-3 范围内的正确性缺陷，并非 worker 启动缓慢的证据。

方案与设计评审：使用 `MaxResults=100` 和 `NextToken`，仅在没有后续游标时结束，拒绝重复游标，保留原有最多 1,000 页的保护。对重叠页中匹配的 ToolId 去重，但保留不同 ID 的同名资源，供归属冲突检查。云端错误向上传递，不能把未完成的查询视为资源不存在。不改变凭据处理、归属、创建请求、取消、任务标识、API 或 UI。维护 CON-2/CON-3，在双语组件规范中补充分页约束。用户已批准迁入实现，并要求排查正在运行的创建，涵盖本次实现修正；重启或重试线上任务仍属于独立的运维操作。

任务：先补充失败回归，覆盖未满的中间页、满的末页、重复匹配、不同资源同名、重复游标和页数上限；修复 `WorkerCloud.find`；运行 managed/CLI 测试以及变更文件的 Ruff/Pyright。验收：查询按游标遍历所有页且每个游标只访问一次，不得在查询不完整或失败后静默继续创建。评审确认无需数据库迁移、新依赖、破坏性消费者契约或前端产物变更。验证待执行；线上检查仅为只读，未取消或重新启动创建。

分页验证（2026-09-20，基于 `314d43c8` 的工作区，仅本次 worker 实现/测试与双语设计/规范）：**pass**。六个新增回归用例在修复前全部失败；修复后 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` 为 173 passed。变更文件的 Ruff 0.11.12 检查/格式、worker Pyright 和 `git diff --check` 均通过。使用修复后的 `WorkerCloud.find` 进行云端只读检查，两次 ListTools 调用在 1.05 秒内遍历两页，未找到匹配资源。原任务现已失败在 `worker`，原生记录仍只有 `studio_owner`。持久化错误为统一错误码，未保留最终异常的准确内容；反复查询第一页的问题已独立验证。未重试任务或执行云端写操作。本次仅修改 Python，前端/构建/浏览器检查为 **not_applicable**；未再次运行全量回归（**not_run**），因为本次隔离改动已由 managed/CLI 套件覆盖，此前全量验证仍记录在上方。沿用原任务重试会启动新的 runner 进程并导入修复代码，无需重启 Studio。本次诊断未执行完整线上创建（**not_run**）。

线上创建观察（2026-09-20）：用户在 Studio 新发起创建后，只读检查观察到 worker Ready、独立数据库和技能空间已登记、Runtime 从 Creating → Releasing → Ready，任务最终达到 `succeeded`。原生部署记录为 `state=ready`、`pending=false`；独立鉴权访问 `/readiness` 返回 HTTP 200。旧任务仍失败在 `worker`；新旧任务的智能体和任务标识不同。这为所选本地参考配置下的一次北京地域真实创建提供 **pass** 证据，不代表所有配置、IAM 边界或云端失败恢复场景均已验证。本次跟进没有再次发起创建、取消任务、修改云资源或提交/推送代码，仅观察用户发起的部署。

### 后续调整：直观的 Runtime 名称（2026-09-20）

用户批准：提出使用 `MPA_AGENT_ID` 作为新 Runtime 名称后，用户要求实施（“帮我改下”）。FR-11/T-7/AC-8：新建托管 Runtime 直接使用稳定的智能体 ID 作为 `Name`；资源 ID、数据库/worker/技能空间的命名和归属保持原样。背景：自动生成的 `mpa-agent-<账号-地域-智能体哈希>` 名称无法直观对应 Studio 中输入的 ID。Studio 和托管 CLI 均通过 `AgentRuntimeDeployer` 生效。

方案与直接评审：已登记的现有 Runtime 保留云端返回的名称。旧版创建未完成且响应丢失时，只有完整的旧请求哈希与持久化创建意图完全相同，才沿用旧哈希名称，并重用原 token 和完整请求。其他输入变化仍应失败。新部署直接使用智能体 ID，即使参考模板带有其他名称。当前 SDK `UpdateRuntimeRequest` 与[官方 UpdateRuntime 契约](https://www.volcengine.com/docs/86681/1923461) 均未提供 `Name`，不能声称可以重命名已有实例，也不能静默替换它。因此现有云实例改名尚未实现，本次代码改动不执行云端写入。不改变前端 API、任务生命周期、IAM、凭据、数据库结构或现有资源的遥测标识。双语 CON-3 和操作文档需说明该兼容规则。

任务与测试：先添加失败用例，覆盖新名称直接对应 ID、保留已有旧名称、旧版创建响应丢失后用完全相同的请求/token 恢复，以及拒绝旧请求输入变更；仅实现 Runtime 名称选择与请求哈希兼容。验收：命名/恢复用例与 managed/CLI 回归通过，变更文件 Ruff/Pyright 和空白检查通过。无需重新生成前端产物。风险：云端重名仍作为提供方错误返回，不会接管其他资源；旧版程序无法恢复新版的待完成请求哈希。状态：已批准，验证待执行。`review-spec` 技能不可用，以此处的边界、兼容和双语直接评审替代。

FR-11 验证（2026-09-20，基于 `314d43c8` 的工作区）：**pass**，`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` 为 176 passed。实施前，直接名称回归失败（1 failed、19 passed）；旧版兼容用例验证已有请求仍可恢复。变更 Runtime/测试文件的 Ruff 0.11.12 检查/格式、Runtime Pyright 和 `git diff --check` 通过。直接实现评审确认：兼容回退要求完整旧请求哈希匹配，且尚未登记 Runtime ID，不会忽略任意输入变化或替换现有 Runtime。双语 PRD、CON-3 与操作文档已同步。FR-11/T-7/AC-8 的新建命名与兼容部分已实现。浏览器/构建检查为 **not_applicable**（没有 UI 或产物变更）；未再次运行全量 Python 回归（**not_run**），该独立命名改动已由 managed/CLI 套件覆盖。未创建另一个智能体验证新名称（线上创建 **not_run**）；已有云实例改名为 **blocked**，因为受支持的更新契约没有 Name 参数。未修改已有资源，未提交或推送。

### 后续调整：显式配置 MPA 镜像（2026-09-20）

FR-12/T-8/AC-9，用户要求 MPA 镜像像 worker 镜像一样配置，已批准实施。背景：`managed.from-runtime` 继承 ArtifactType/ArtifactUrl、角色、CPU/内存、扩缩容/并发、APM/项目、VPC 和经过身份清理的环境变量，并非只有镜像。操作者需要在保留基础设施、模型和数据库配置时独立固定 MPA 镜像。

方案：新增可选 `managed.runtime.image`，与 `managed.worker.image` 并列。显式提供的非空镜像覆盖 ArtifactUrl，并将 ArtifactType 设为 `image`，对参考 Runtime、JSON 模板、平铺配置三种来源均生效。省略/null 保持原有来源行为；本地校验拒绝空白、含空格/占位符的镜像及未知 runtime 配置项。平铺模式可用该字段替代原顶层 `image`，其他前置配置仍然必需。浏览器配置摘要不新增镜像值。模板复制及继承环境变量清理不变。未完成部署的请求哈希仍拒绝镜像变化；不会自动更新已有智能体。将已验证的当前 MPA 镜像写入本地 Git 忽略的 YAML，实际选用镜像和其他私有配置不变。确认没有活跃创建任务后才重新加载本地 Studio，不部署或分配云资源。

直接设计评审：这是 CON-1 的增量配置契约，模板来源仍互斥，显式镜像不能替代必要的凭据、网络、数据库或模型设置。测试覆盖所有来源的覆盖优先级、省略兼容性、非法配置和平铺镜像前置条件，仅模拟云调用。运行 managed/CLI 测试、Ruff/Pyright 和本地配置 GET。同步双语组件/操作文档与占位符 YAML 示例。现有前端行为与产物不受影响。风险：指定镜像仍需兼容继承配置；未完成请求必须保留原实际镜像。review-spec 不可用，已直接完成双语、兼容和安全评审，无未解决的实施阻断。状态：已批准，验证待执行。

FR-12 验证（2026-09-20，基于 `314d43c8` 的工作区，配置/服务/测试与双语文档/示例）：**pass**。实施前针对性测试 5 failed、20 passed；实施后 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` 为 188 passed。变更文件 Ruff 0.11.12 和 config/service Pyright 通过，已格式化；示例 Managed schema、双语文档评审和 `git diff --check` 通过。Git 忽略的私有 YAML 已通过 `managed.runtime.image` 固定先前验证的 MPA 镜像，并保留 0600 权限及其他配置。确认活跃创建任务为零后，保留内存中的原启动环境重启了本地 Studio。实际 GET `/web/mpa-creation/config?region=cn-beijing` 返回 HTTP 200、configured=true、source=reference。没有输出或新增持久化秘密。FR-12/T-8/AC-9 已实现。线上部署为 **not_run**（验证该配置变更无需新分配资源）；前端/构建/浏览器检查为 **not_applicable**（未修改前端代码或产物）；未再次运行全量 Python 和 pre-commit（**not_run**，已完成 managed/CLI 定向回归，用户未要求提交）。未变更云资源、提交或推送。

### 后续调整：显式配置 Runtime 基础设施与环境（2026-09-20）

FR-13/T-9/AC-10。用户要求列出实际继承的设置并将其配置化。只读检查确认所选来源使用 CPU 2000 milli、内存 4096 MiB、最少/最多实例 1/1、并发 100、开启 APM、项目 default、Runtime IAM 角色、公网/私网双网络，以及模型/PostgreSQL/应用环境设置。目标：让这些选择在 YAML 中明确可查，移除本地配置对 `from-runtime` 的依赖。既有 worker 参考配置属于独立范围，保持原样；不部署云资源或替换实例。

方案：扩展可选 `managed.runtime`，增加 role-name、cpu-milli、memory-mb、min-instance、max-instance、max-concurrency、apmplus-enable、project-name 和 env。省略字段保持所选模板/默认值，显式值覆盖对应字段。资源变更前验证计算规格/并发为正、最少实例非负、最多实例为正，且合并后的 min<=max。既有 `managed.network.vpc-id/subnet-ids` 指定双网络，仍要求公网与私网连通。现有平铺 model/PG 字段显式设置模型地址/名称/提供方和数据库地址/端口/登录/SSL。`runtime.env` 提供显式应用环境覆盖，并在服务端解析完整 `${ENV_NAME}` 引用。值必须为字符串，键必须是合法环境变量标识。拒绝创建流程拥有的字段（智能体/Runtime/工具/技能标识、派生数据库名、Runtime 端点/鉴权/加密、共享注册库/管理员 URL、请求/遥测标识）；模型与数据库连接仍可配置。配置摘要和校验错误不返回环境变量值。

迁移：将当前实际基础设施、模型/PG/应用设置固定到被 Git 忽略的本地 YAML，移除 `from-runtime`；秘密值放入现有 Git 忽略且权限为 0600 的 .env，YAML 仅引用变量。两个文件保持 0600，并保留私有回退副本。使用之前已授权的内存凭据读取云端值，仅输出非秘密摘要与等价校验结果。保存前比较新模板设置与旧参考配置，不改变所选镜像、网络、角色、凭据或资源标识。仅在没有活跃创建任务时重启本地 Studio 并验证配置接口。部署 AK/SK 始终只在内存中使用。

直接评审：CON-1 增量覆盖字段，旧配置保持默认行为；继续执行 CON-3/CON-8 的生成标识和脱敏规则。未完成部署中修改来源模型仍会触发已有请求哈希冲突，重试必须保持原实际设置。先测试全部覆盖字段、优先级/省略、false 布尔值、最少实例为零、合并后扩缩容冲突、秘密引用解析/脱敏与保留键拒绝，再运行 managed/CLI 回归和 Ruff/Pyright。同步双语契约/操作文档/示例。前端 API 和产物不变，无需浏览器构建。风险：显式固定后不再跟随参考 Runtime 的后续修改，更新由操作者负责。用户请求授权本次配置工作，不包含提交、部署或新建智能体。review-spec 不可用，已完成直接评审。状态：已批准，验证待执行。

FR-13 验证（2026-09-20，基于 `314d43c8` 的工作区，config/service/测试与双语文档/示例）：**pass**。实施前针对性回归 5 failed、40 passed；实施后 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` 为 208 passed。变更文件 Ruff 0.11.12、config/service Pyright、示例 schema 和 `git diff --check` 通过。Runtime 覆盖测试涵盖 false/零值、实际 min/max 约束、非法/创建流程保留环境键、秘密解析/脱敏及原来源兼容。本地配置迁移逐项验证镜像、全部基础设施字段、VPC 及有效环境值相同，仅排除创建阶段重新生成的流程专属字段。已移除 from-runtime，保留 worker 引用，将两个秘密值改为环境引用，并保留私有回退文件；YAML/.env 仍被 Git 忽略且权限为 0600。重启前确认活跃创建任务为零，原启动环境仅在内存保留；实际配置 GET 返回 HTTP 200 和 configured=true。没有云端写入、新建智能体、提交或推送。浏览器/构建为 **not_applicable**（无前端或产物变更）。未再次运行全量 Python 回归/pre-commit（**not_run**，managed/CLI 定向套件覆盖该增量配置变更，用户未要求提交）。显式配置下的完整线上创建为 **not_run**；等价比较与本地配置验证不能证明所有云配置组合。FR-13/T-9/AC-10 的配置与本地迁移已实现。

### 后续调整：创建弹窗可编辑镜像（2026-09-20）

FR-14/T-10/AC-11，用户明确批准：新增 MPA 镜像和 Worker 镜像文本输入框，默认填入当前配置，可手动覆盖；留空则使用服务端配置。复用现有弹窗输入和本地化帮助/错误文案，不接镜像仓库选择或列表。仍要求现有管理员权限。

契约与设计评审：鉴权后的配置 GET 仅新增本地可确定的镜像引用（`runtimeImage`、`workerImage`），不返回环境变量/凭据。旧版仅引用 Runtime 的配置无法在本地确定镜像时，留空并保留原来源行为。POST 可选字段同名，去除首尾空白，限制 1024 字符，拒绝 URL/凭据/查询参数/片段及非法 digest。显式 Runtime 镜像覆盖所选来源；显式 Worker 镜像选择独立 worker，不再复用配置指定的已有 worker。留空保持默认值。SQLite 新增 `images` JSON 列，首次提交时保存本地可确定的实际镜像，独立于原请求标识，防止空字段重试时默认配置变化。旧记录填 `{}`，保留旧行为；迁移不调用云端或隐式接管资源。Runner 接收并应用持久化镜像快照。同一请求更改显式镜像构成冲突。不含秘密的任务响应返回实际镜像，提交后输入锁定，session storage 保留原请求，包含响应丢失情况。迟到配置响应不覆盖手动编辑、清空值或恢复的已提交输入。关闭/取消延续现有任务生命周期。

任务：先补充失败的配置/接口/任务/runner 与前端回归；实现类型、校验、快照迁移/runner 传递和两个输入框；同步语言包、双语契约/操作文档与 frontend README；运行针对性及全量前端测试、managed/CLI 测试、变更 Python Ruff/Pyright、生产构建/产物/i18n 检查，并用隔离真实浏览器验证正常/空白/非法/加载/重试/恢复/取消/键盘/窄窗口。不在验证中创建云资源；镜像可访问性和 IAM 兼容性仍由用户发起部署时的云端检查确定。兼容旧配置、旧客户端和旧记录。frontend-design、ui-ux-pro-max 和 review-spec 仍不可用，遵循 frontend/SPEC.md 并直接评审。评审覆盖重复/丢失请求、结构迁移、固定重试、显式已有 worker 覆盖、错误和秘密边界。状态：已批准，验证待执行。

FR-14 验证（2026-09-20，基于 `314d43c8` 的工作区，弹窗/客户端/语言包、创建接口/配置/任务/runner、测试/文档及重建前端产物）：**pass**。实施前 4 个新增后端用例与 3 个前端用例失败。最终 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` 为 221 passed，覆盖旧 SQLite 结构迁移、重试固定快照、worker 复用覆盖及实际 runner 配置应用。`npm --prefix frontend test`：1208 个 Node 测试、25 个 Vitest 测试通过。`npm --prefix frontend run build`、`test:webui-assets`（104 文件/248 引用）、`check:i18n`（2 种语言/21 命名空间）通过。变更 Python Ruff 0.11.12 检查/格式与 Pyright 通过。按仓库规则对本次源码/构建产物快照运行 Gitleaks，无发现，保留 vendor 排除规则。`git diff --check` 通过，双语文档与 API 标识已评审。

真实浏览器使用实际弹窗和隔离模拟接口，验证通过：默认值、非法镜像提示/禁止提交、自定义 MPA 镜像与 worker 留空回退、多行中文输入、Tab/Enter、提交锁定、失败/重试、关闭后任务恢复、取消、加载时字段禁用，以及 390×844 深浅主题布局。缺失配置与 POST 响应丢失恢复由自动化测试覆盖；尝试的浏览器缺失配置场景结论不明确，不声称通过。原生操作系统 IME 候选交互为 **not_run**。已删除临时测试页、停止测试服务、关闭测试标签并重置视口。没有继续操作生产 Studio 登录页，没有新建账号/接受条款或实际云端创建。确认没有活跃创建任务后保留原启动环境重启 Studio，实际配置 GET 为 HTTP 200、configured=true，两个镜像默认值非空，未返回环境/凭据字段。没有改变已有云端智能体。未再次运行全量 Python 回归或 pre-commit（**not_run**，定向生命周期/接口/CLI 覆盖已通过，用户未要求提交）。未提交/推送。FR-14/T-10/AC-11 已实现；模拟部署不能证明镜像可拉取及云端权限。


### 集成验证：变基到 main（2026-09-21）

范围与授权：用户要求解决 PR #5 的合并冲突。将 `feat/from-main` 变基到 `origin/main` 的 `f55e8918`，审查合并后的 `703859c7` 及集成差异。保留 main 的定时任务、A2A、沙箱下载、JWT 和 tracing 文档，以及本分支的 MPA 信息侧栏和托管创建文档。从合并后的源码重新构建全部打包 WebUI 产物。冲突解决不引入新行为或组件契约，现有双语契约继续生效。原有两份本地类型验证文档修改已单独保存，待集成提交后恢复。

干净安装最初因合并后的锁文件缺少可选依赖记录而失败。使用 npm 重新生成 `frontend/package-lock.json`，未改变任何已有依赖版本，随后 `npm --prefix frontend ci --no-audit --no-fund` 通过。本机 Node 26 的实验性 Web Storage 导致沙箱下载测试的四个清理步骤失败；使用 `NODE_OPTIONS=--no-experimental-webstorage` 运行相同套件后通过，未修改应用或测试行为。首次 pre-commit 仅格式化了合并后 Runtime 代理测试的两处表达式，Ruff 检查和敏感信息扫描通过。最终 pre-commit 与格式化文件回归结果补充在下方。

2026-09-21 验证结果：

- **pass** — `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_cli_mpa.py tests/frontend/server/test_mpa_cron.py tests/cli/test_frontend_runtime_proxy.py tests/cli/test_frontend_apmplus_trace.py tests/cli/test_studio_trace_pagination.py -q`：398 项通过。
- **pass** — `MODEL_AGENT_API_KEY=test-only MODEL_EMBEDDING_API_KEY=test-only uv run --extra dev --with anthropic --with 'llama-index-embeddings-openai-like>=0.2.2' --with 'llama-index-llms-openai-like>=0.5.1' pytest -n 2 -m 'not codex_smoke and not piagent_smoke'`：4,850 项通过、7 项跳过、2 项预期失败。使用两个 worker 控制本地资源占用。跳过项、预期失败项以及真实运行时 smoke 不由此证明。
- **pass** — `npm --prefix frontend test`：1,215 项 Node 测试和 25 项 Vitest 测试；`npm --prefix frontend run test:mpa-cron-coverage`：71 项测试及配置的覆盖率门禁；`NODE_OPTIONS=--no-experimental-webstorage npm --prefix frontend run test:sandbox-download-coverage`：26 项测试及配置的覆盖率门禁。
- **pass** — `npm --prefix frontend run build`、`npm --prefix frontend run test:webui-assets`（104 个文件、248 处引用）和 `npm --prefix frontend run check:i18n`（2 种语言、21 个命名空间）。保留现有的大体积 chunk 构建警告。
- **pass** — 使用真实组件和模拟 API 的隔离浏览器 smoke：定时任务未选 Runtime 状态；创建镜像默认值、无效镜像提示与禁用提交、自定义 MPA 镜像与空 Worker 镜像、多行中文描述、提交后字段锁定、模拟失败及重试成功。临时测试入口、服务和标签页已删除或关闭，未修改云资源或生产用户状态。
- **not_run** — 再次完整浏览器矩阵、原生 IME 和真实云端/运行时 smoke：本次集成保留现有行为，前文保留功能级浏览器证据，自动回归与合并源码的定向浏览器 smoke 覆盖冲突解决范围。真实镜像访问及 IAM 组合仍不在本次验证范围内。

直接审查未发现残留冲突标记或遗漏文档章节。最终集成提交仅包含重建产物、锁文件规范化、合并后测试的格式化及本双语验证记录。本次不合入或发布 main，而是更新 PR 分支以继续正常审查与 CI。

最终检查：**pass**，`uv run --extra dev pre-commit run --all-files`（Ruff 检查、Ruff 格式、Gitleaks）；**pass**，格式化后 `uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py -q`（80 项通过）；**pass**，源码/文档 `git diff --cached --check -- . ':!veadk/webui'`。未过滤的差异空白检查为 **fail**，仅涉及生成 bundle 中七行变更行的第三方字符串空白。集成 bundle 重建前后均有 36 行尾部空白，因此保留生成字符串内容，未手工改写。最后一次获取远端确认 base 和原 PR 分支没有新提交。索引中无未解决冲突项。本次集成同时修正文档章节间距。
