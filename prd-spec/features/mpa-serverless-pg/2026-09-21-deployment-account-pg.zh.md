# 托管 MPA 创建自动准备 Serverless PostgreSQL

[English](2026-09-21-deployment-account-pg.md)

> 2026-09-23 当前创建流程已由[手动预建两个 PG Workspace](../mpa-space-scoped-resources/2026-09-23-two-pg-workspaces.zh.md)方案替代：一个管理 Workspace，另一个共享业务 Workspace 内按智能体分库。下文自动创建/每智能体独立 Workspace 设计仅保留历史记录，本次不实施。

## 元信息

- Change ID：`mpa-serverless-pg`
- 创建/修订日期：2026-09-21
- 状态：`draft`，尚未开始实现。
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。
- 前序：[托管创建](../mpa-agent-oneclick-provision/2026-09-20-studio-mpa-creation.zh.md)。
- 用户已确认的意图：在 VeADK 部署凭据所属账号下自动创建 PG。用户要求参考 ArkClaw 确定粒度；源码已确认每个智能体独立业务 PG Workspace。VeADK 注册库适配的详细设计仍在审查中。

## 背景与证据

`managed/config.py:load_profile` 当前强制要求管理员和共享注册库的 PostgreSQL URL。`managed/service.py:provision` 在网络/APIG 创建前初始化注册库。`managed/database.py` 仅在已有实例里创建智能体独立业务库，不创建云端 PostgreSQL。因此，在注册库初始化后增加一个云接口调用，无法支持没有 PG 的账号。

本地检查的 ArkClaw 实现会调用 AIDAP `CreateWorkspace`，等待 Workspace/主分支就绪，解析计算资源、账号、数据库和端点，再调用 `DescribeDBAccountConnection`。其 `CreateWorkspaceReq` 没有 ClientToken 字段。ArkClaw 通过 STS 使用另一个资源账号；VeADK 必须使用自身可刷新且经过账号核验的部署凭据。Go 类型只证明实现方式，不证明当前用户账号具备服务权限，也不证明所有 SDK/服务版本兼容。

## 目标、非目标与场景

目标：配置好的新账号无需填写 PG 凭据即可发起托管 MPA 创建。保留已有 PG 配置及当前 CLI/Studio 创建入口。

已确定业务资源粒度：参考 ArkClaw，每个智能体独立一个 VeADK 管理的 PG Workspace。Workspace 身份为已核验部署账号 + 地域 + 稳定智能体 ID，仅同一智能体重试时复用。即使属于同账号同地域，不同智能体也创建不同 Workspace。复用必须满足归属标记及已记录创建身份匹配，不随意选择已有 PG。此前账号地域共享业务 Workspace 的建议撤回。

非目标：照搬 ArkClaw 的租户/资源账号委托、Debug PG 分支、自动配置 IAM 策略或开通服务、传统 RDS 创建、自动删除/迁移已有 PG、多个独立主机的初始化协调，以及实现期间真实云端部署。

场景：

1. 自动模式下没有受管理的 PG 时，在已核验部署账号 A 下创建、初始化数据库，随后仍在 A 下部署智能体。
2. 同一智能体重试复用其已登记 Workspace，第二个智能体创建另一个业务 Workspace；两者使用独立管理的共享注册库。
3. 已有 PG 配置维持现有连接及权限行为。
4. 权限拒绝、账号变化、无关资源重名、响应不合法、超时或创建结果不确定时，不得静默继续或再分配一个 Workspace。

## 需求与设计

- **FR-1 / 账号：** 云资源变更前使用现有凭据核验路径获取账号。PG 与 Runtime/网络/APIG 使用同一个可刷新凭据加载器及地域，不引入资源账号扮演或浏览器传入账号/AK/SK。刷新凭据后跨账号则失败。复用前核验 Workspace 的账号、地域及归属。
- **FR-2 / 配置：** 新增 `managed.postgres.mode: existing | serverless`，默认 `existing`。已有模式保留 PG/管理员/注册库参数要求。显式 `serverless` 模式允许省略这些参数，以发现的连接作为托管数据库字段的权威来源，包括参考 Runtime/模板模式。显式 PG 覆盖项有冲突则拒绝，不静默连接其他实例。服务端项目、引擎、计算规格和端点/网络设置须按支持的服务契约校验。配置/UI 新增安全的 `postgresMode` 和本地化资源计划，不返回数据库 URL/密码。旧客户端可忽略新增字段。网页请求不能覆盖云账号和 PostgreSQL 凭据。
- **FR-3 / 初始化：** 连接 PG 注册库前，在现有私有状态目录使用持久化 SQLite 初始化记录。业务初始化按已核验账号、地域和智能体 ID 索引；单独管理的注册库初始化按已核验账号、地域和显式注册库用途索引。只保存创建身份、属主、配置哈希、生命周期状态及服务资源 ID。权限 0600，不保存凭据。共享同一状态文件的 CLI/Studio 进程通过事务确认归属并串行协调。CreateWorkspace 前保存意图，响应后立即保存 ID。每个账号地域需要单一初始化协调器/状态存储；独立主机不在本版本并发保证内。先准备独立共享注册库，再创建或恢复该智能体专属业务 Workspace。其连接只注入该智能体业务库路径，共享注册库 URL 继续指向独立管理数据库。满足服务 SQL 权限时，可在独立 Workspace 中保留现有智能体业务数据库命名。
- **FR-4 / 恢复：** 完整遍历发现接口分页，拒绝无效/重复分页、多个归属匹配候选及归属冲突。创建结果不确定时，必须通过已持久化的唯一标记发现并恢复。尚未确认 ClientToken 支持，因此禁止盲目重试结果不确定的 CreateWorkspace，也不能因为暂未发现资源就允许再次创建。无法恢复的歧义返回可操作且脱敏的恢复错误。已记录就绪的 Workspace 丢失/被删除时不得创建替代资源。未完成任务的配置变化显式失败。任务重试保留原账号、模式和初始化配置身份。
- **FR-5 / 连通性与凭据：** 对批准的服务端点使用有超时边界的签名请求，清理连接并脱敏错误。只解析目标分支/计算资源/账号/数据库/端点。强制 TLS，在继续之前校验 Studio SQL 连通性、CREATEDB/属主权限及必要扩展/初始化条件。显式定义网络/公网访问设置，不新增宽松白名单，不声称新 VPC 自动能访问私网 PG。获取的凭据只保留在服务端内存或现有必要的运行时密钥配置，不进入任务 JSON、SQLite 初始化状态、浏览器、日志或受版本管理的 YAML。脱敏服务连接响应异常。
- **FR-6 / 生命周期：** 在 runner 白名单、任务存储及双语 UI 中增加可观察的 `postgres_creating`、`postgres_waiting`、`postgres_initializing` 阶段。使用任务总期限、单请求超时和有界轮询。取消停止本地工作并回收 runner，但在途云请求仍可能完成。取消/失败保留 PG 和创建意图用于恢复，不自动删除。鉴权失败、其他错误和空状态不能混淆。
- **FR-7 / 兼容：** 旧 YAML、`managed.version: 1`、已有任务行和旧 `veadk mpa create` 行为保持。`veadk mpa provision --dry-run` 仍只做本地操作，展示安全的 PG 计划，不调用网络或 SQL。已有 PG 连接失败时不隐式切换到自动创建。已有智能体不更换数据库、不重新部署。通过现有注册库继续复用已准备的账号资源。

实现顺序：本地配置校验 → 部署身份 → 独立共享注册库准备 → 智能体级持久化 PG 初始化/发现 → 确认安全缺失后创建 → 等待/获取业务连接 → SQL 权限 → 原网络/APIG/worker/业务库/Skill Space/Runtime 流程。能够提前校验的 Runtime 模型/镜像参数应在计费资源变更前校验；新 PG 的数据库权限校验必须在 PG 创建后进行。后续校验失败时保留已创建 PG 供恢复。

## 契约影响与文件范围

更新 `specs/studio-mpa-creation/README.*` 两种语言：CON-1 配置、CON-2 前置准备、CON-3 身份、CON-6 阶段、CON-7 取消、CON-8 持久化/安全、CON-9 UI，并增加 PG 初始化/恢复不变量。旧部署契约保持；SDK Agent/Runner、harness 和渠道协议不受影响。

实现涉及 `veadk/integrations/mpa/managed/{config,service,runner,tasks,diagnostics}.py`、新增 PG 云适配/初始化模块；`frontend/server/mpa_creation.py`、`frontend/src/adk/mpaCreation.ts`、创建弹窗和双语文案。在 `tests/integrations/mpa_managed/` 增加定向测试并更新前端创建测试。同步托管创建 README、示例 YAML、必要 CLI 帮助和生成的 `veadk/webui/`。不修改用户原有两份未提交类型验证文档；私有运行配置的启用/修改需另外确认具体操作。

## 任务与验收

| 任务 | 需求 | 验收 |
| --- | --- | --- |
| T-1 | FR-1–7 | AC-1：记录与 ArkClaw 一致的智能体级粒度；确定独立注册库初始化方案并完成双语契约/设计审查；生产代码修改前核验服务请求/响应 schema。 |
| T-2 | FR-1–5 | AC-2：先写 PG 适配/初始化测试，覆盖账号不符、凭据刷新、分页、无效响应、创建结果未知、重复进程、归属冲突、两个智能体的 Workspace 不同、同智能体重试复用、注册库/业务库连接分离、重启和资源丢失。 |
| T-3 | FR-2–7 | AC-3：接入配置/服务/任务重试快照和 SQL 初始化；已有模式测试通过；自动模式无需预填 PG URL；dry-run 不调用云端。 |
| T-4 | FR-2,6 | AC-4：真实弹窗配合隔离 API 验证双语计划/进度及安全的错误/取消/重试状态。 |
| T-5 | FR-1–7 | AC-5：同步双语文档/契约、重建产物、运行必要检查，区分模拟验证与真实服务证据。 |

## 验证计划

先写失败的契约/回归测试。运行 `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`、修改文件的 Ruff/Pyright、`npm --prefix frontend test`、`npm --prefix frontend run build`、`npm --prefix frontend run test:webui-assets`、`npm --prefix frontend run check:i18n`。共享配置/编排变更运行默认双 worker 非 smoke Python 回归。任何获授权的提交前获取远端并变基到目标远端基线，运行 `uv run --extra dev pre-commit run --all-files` 和单元测试。真实浏览器通过模拟 API 覆盖正常/加载/错误/取消/重试/键盘/窄窗口，不分配真实云资源。另行授权的服务 smoke 应验证实际账号归属、服务权限、SQL 权限和连通性，之后才能宣称真实部署可用。

## 风险、待决项与审查记录

- 用户要求参考 ArkClaw，业务粒度已确定为每个智能体独立 Workspace。剩余设计决策是下述独立管理注册库方案，不再让用户任意选择业务资源粒度。
- 尚未实测：当前账号/地域 AIDAP 权限、引擎/计算规格限制、默认数据库账号 CREATEDB 权限、返回端点连通性。不支持时明确失败，不伪造成功或放宽检查。
- 尚未确认服务创建幂等 token：结果不确定的创建可能需要人工核对。本地单协调器保证不等于跨主机分布式严格单次创建。
- 创建会分配计费 PG 资源；实际部署授权与代码修改分开。设计阶段不包含云端写操作、私有配置修改、提交或推送。
- 本地技能目录没有 `review-spec`、`frontend-design`、`ui-ux-pro-max`。直接审查归属、兼容、初始化循环依赖、取消、凭据、可测试性和双语一致性。不设计新视觉布局，按 `frontend/SPEC.md` 复用现有弹窗。
- 2026-09-21，基线 `3bbd260a`：代码/契约检查 **pass**；实现/运行时/浏览器/云端验证 **not_run**（仅设计草案）。组件契约以明确的提案标记记录已选粒度；实现前不改变现行行为。详细设计尚待批准。

## ArkClaw 参照结论与注册库适配（2026-09-21）

已核实 `arkclaw-team` 参照路径：

- `pkg/service/multiplayer_agent/create.go:253` 分配 MPA 实例身份，并保存该实例自己的资源字段。
- `pkg/service/multiplayer_agent/create_workflow_executor.go:729` 读取该实例的 `PgWorkspaceID`，不存在时调用 `CreateWorkspace`，并将结果保存到该实例。`create_workflow.go:334` 使用实例 ID 推导资源名。
- `create_workflow_executor.go:775` 在同一 Workspace 内增加 Debug 分支，`:831` 获取两个连接。这证明是每个智能体独立 Workspace，正式/Debug 环境并非分别独立 Workspace。Debug 创建记为参考实现事实，不纳入本次已有单 Runtime 的范围。
- `pkg/model/model.go:22` 根据服务端配置初始化 ArkClaw 管理数据库，独立于各智能体 PG。不能用第一个智能体的 Workspace 代替这一管理库归属边界。

VeADK 的 `SharedAPIGRegistry` 明确要求所有部署器使用同一 PostgreSQL 注册库，并向 Runtime 注入 `SHARED_APIG_DATABASE_URL`。建议适配：已有共享注册库配置则复用；全新账号通过显式启用的自动注册库模式，按账号地域创建一次独立管理 PG Workspace。业务 Workspace 仍每个智能体独立，绝不承载共享注册库。复用范围、标签、持久化键和计划文案区分 `registry` 与 `agent` 资源。缺少注册库配置时不能静默多创建 PG。

此适配需要详细确认，因为资源数量发生变化：完全自动模式首次创建会准备一个管理 Workspace 加一个业务 Workspace；后续智能体只增加自身业务 Workspace。配置已有注册库时不额外创建管理 Workspace。这是适配 VeADK 现有共享 APIG 契约的方案，不代表 ArkClaw 每账号也自动创建这个额外 Workspace。不得将其作为不可见默认行为，也不能削弱注册库契约。本次参考审查未修改代码、测试、云资源、本地凭据或已有私有 YAML。
