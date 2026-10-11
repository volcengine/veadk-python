# BytePlus 托管 MPA 创建

[English](2026-10-10-byteplus-creation.md)

- 变更 ID：`mpa-byteplus-creation`
- 创建/修订：2026-10-10
- 状态：approved
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与证据

Studio 已支持选择 BytePlus 地域 `ap-southeast-1`，但 MyAgents 在 BytePlus 下隐藏 MPA 创建入口，创建路由也拒绝该平台。托管配置、凭据加载及 VPC/APIG/AIDAP/模型 Key 适配器仍使用国内端点。已安装的 AgentKit SDK 支持按平台选择 Runtime、Skills 和 Tools 客户端；仓库 Identity 客户端已有 provider 参数。国内流程已经可用，必须保持兼容。

## 目标与非目标

让 BytePlus 使用相同三步创建流程，隔离平台选择、凭据、配置及端点。保留国内默认值、权限、资源共享及重试行为。不修改通用智能体聊天，不持久化凭据，不自动回退国内服务，不迁移现有资源，不发布镜像，不修改其他仓库。

## 场景与需求

- **FR-1：** BytePlus Studio 在配置地域显示 MPA 创建入口；拒绝国内地域及浏览器传入的平台、账号、端点覆盖。
- **FR-2：** 无参数国内配置的值保持完全等价。BytePlus 默认 `ap-southeast-1`、已有 BytePlus ModelArk 模型/地址及 `CLOUD_PROVIDER=byteplus` / `AGENTKIT_CLOUD_PROVIDER=byteplus`。用户没有海外镜像，继续默认现有公开镜像；允许可信服务端镜像覆盖，拉取能力单独验证。
- **FR-3：** 只使用所选平台 AK/SK/token 或明确配置的轮换 IAM 文件，每次调用通过对应 STS 校验账号。在 SDK 工作线程内选择平台上下文；使用对应 VPC/ECS/APIG/AIDAP/Ark/IAM/Identity 端点。不支持的服务或策略必须明确失败，不能跳过准备或调用国内服务。
- **FR-4：** 将可信平台信息传入固定子进程及持久请求指纹；平台变化不能恢复同一任务。BytePlus 默认任务和 PG 引导 SQLite 文件单独存储；国内输入及默认路径保持兼容。
- **FR-5：** 保留管理/业务 Workspace、库级隔离、锁、有限重试、未知创建结果恢复、取消及就绪语义。BytePlus 初始沿用所需 IAM 策略契约；策略名称不可用时明确失败，不能静默遗漏权限。
- **FR-6：** 向 Runtime 注入平台、模型、地域及 APIG 端点。OpenViking 继续可选且全填或全不填。弹窗复用已有组件，资源链接对应平台，不携带其他账号或资源 ID。

## 设计与影响文件

Profile 增加服务端拥有的平台属性，默认国内。复用已有平台及 ModelArk 工具，对未覆盖服务增加托管平台端点助手。适配器增加可选 provider，保留现有签名和默认行为。平台由服务端选择，浏览器不可指定。BytePlus 持久任务增加非敏感平台标记，经 stdin 传给 runner；国内负载保持不变。构造 Runtime/Skills/Tools 客户端时应用平台上下文，不改机器全局配置。保留 IAM 绕过单例的机制，注入 MPA 镜像已识别的海外 APIG 覆盖。

影响模块：`managed/{studio_profile,config,credentials,runtime,worker,network,network_cloud,gateway_cloud,pg_cloud,model_key,iam,service,tasks,runner}.py`、新增平台助手、托管模块双语 README、`frontend/server/mpa_creation.py`、`veadk/cli/cli_frontend.py`、`MyAgents.tsx`、`MpaCreateDialog.tsx`、相关测试和发布产物。组件契约变化限于平台/配置/隔离与创建可用性。

真实预检修正：最初使用的 BytePlus 地域 STS 地址超时或断开连接。使用同一服务进程凭据，AgentKit STS SDK 在 `open.byteplusapi.com` 成功返回非空身份；仅 BytePlus 改用该地址，国内 STS 行为不变。直接设计评审确认这是 FR-3 的修正，未扩大范围。用户提交了真实创建，诊断探测仅为只读。

海外可用区校验接受 `ap-southeast-1a` 与 `ap-southeast-1-a`，不改写资源 ID，国内校验保持不变。`VEADK_MPA_BYTEPLUS_CREDENTIAL_FILE` 显式选择轮转文件；没有 BytePlus 环境凭据时，不读取国内默认挂载文件。服务端镜像覆盖项与可选 AIDAP 主机名仅在本地检查；无效 URL、路径、用户信息在资源变更前失败。TOS 挂载地址按平台选择。

真实 IAM 修正：用户重试通过账号及模型 Key 检查，在 `iam_role` 失败。只读 `GetRole` 请求发往 `iam.byteplusapi.com` 时超时；同一 SDK、凭据、签名地域及请求改用 `open.byteplusapi.com` 后返回 `RoleNotExist`。托管 BytePlus IAM 选择已验证地址，并保留可信 `IAM_OPENAPI_HOST` 覆盖。共享 IAM 助手、国内地址、权限和协调逻辑不变。直接评审确认保持 FR-3 范围及失败语义。

真实 PG 诊断：用户重试通过运行角色准备，在 `admin_workspace` 失败。只读 DescribeWorkspaces 使用地域 AIDAP 地址超时；同一 SDK/凭据/地域改用 `open.byteplusapi.com` 后正常返回。BytePlus 托管 AIDAP 默认改用该地址，继续保留并校验可信服务端主机覆盖；国内行为不变。查询发现同名管理 Workspace 处于 `CreateFailed` 且未返回属主标签，因此本次修正不删除、不接管该资源，也不清空不确定创建记录。失败资源恢复另需证据和授权。直接评审确认地址修正属于 FR-3。

## 任务与验收

- **T-1 / AC-1：** 先增加失败的平台/地域/凭据/默认值回归测试，国内配置快照和任务行为保持不变（FR-1–FR-4）。
- **T-2 / AC-2：** 接入配置、凭据及 SDK/传输传播；模拟调用验证 host、签名地域、平台，不使用真实密钥（FR-2–FR-3）。
- **T-3 / AC-3：** 接入路由/runner/UI；验证海外入口、请求和链接，以及拒绝、重试、隔离场景（FR-1、FR-4–FR-6）。
- **T-4 / AC-4：** 执行相关 Python 测试、Ruff/Pyright、前端测试/构建/类型/国际化/产物及浏览器正常、错误、取消、窄窗检查，保留国内回归（全部 FR）。
- **T-5 / AC-5：** 单独记录镜像、服务开通/配额、IAM 策略、AIDAP Workspace/IM Gateway API、就绪和聊天的真实云验证。隔离的真实创建需要明确授权。模拟不能证明用户海外账号具备这些服务。

## 风险与待确认事项

BytePlus AgentKit 官方文档及已安装 SDK 可证明 Runtime 支持。AIDAP 有文档，但完整海外 Workspace 和 IM Gateway API 可用性、IAM 策略目录、模型开通及镜像可达性尚未验证。地域服务适配器需要实测确认，可能遇到平台限制。MPA/Worker 镜像还可能包含国内假设，宣称端到端成功前必须检查并报告限制。证据不得包含凭据、原始 Key、生产日志或私有账号信息。

## 评审、批准与验证

用户于 2026-10-10 批准：“国内流程是好的了，不要改坏了；帮我适配BytePlus”，并确认没有海外镜像地址。`review-spec` 不可用，已直接评审平台边界、国内兼容、可信子进程传播、取消、密钥与测试。无新视觉设计，复用当前弹窗和布局控件；本地未找到所引用 frontend-design/ui-ux 技能，因此不包含推测性布局重设计。生产改动在失败测试后实施。生产改动在失败回归测试之后实施。最终直接评审核对了配置/传输/runner/UI 一致性、轮转凭据、单例绕过、线程内平台上下文、已有资源哈希、终态竞态及双语等价性。


验证日期：2026-10-10。范围：相对 `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91` 的工作区差异；未提交代码，未执行云资源变更。项目环境没有 Ruff/Pyright，采用临时 `uv --with` 环境；Ruff 固定为仓库钩子的 `0.11.12`。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| `uv run --extra dev pytest tests/integrations/mpa_managed -q` | pass | 752 项，包括 24 项 BytePlus 用例；保留国内创建、重试及资源测试。 |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail | 6,951 通过、1 失败、53 跳过、4 xfailed。已有 artifact writer MIME 测试预期 `text/markdown`，本机返回 `application/octet-stream`；在隔离的未修改 HEAD 中复现。按仓库默认使用两个 worker。 |
| `npm --prefix frontend test` | pass | 1,377 项 Node 测试及 67 项 Vitest 测试。 |
| `npm --prefix frontend run build` | pass | TypeScript 编译及 production/main/website 构建，重新生成匹配的 `veadk/webui` 产物。 |
| `npm --prefix frontend run check:i18n` | pass | 2 种语言、21 个命名空间。 |
| `npm --prefix frontend run test:webui-assets` | pass | 113 个发布文件、350 处内部引用。 |
| `uv run --with ruff==0.11.12 ruff check <changed-python-files>` | pass | 全部修改的 Python 源码及新增回归测试。 |
| `uv run --with pyright pyright <changed-python-files>` | fail | 托管模块、创建路由及新增 BytePlus 测试 0 错误；CLI 文件的 37 项错误在未修改 HEAD 中同样存在，没有新增诊断。 |
| 隔离真实浏览器验证 | pass | 实际弹窗/路由使用模拟子进程及临时任务库；核对三步、链接、禁用字段、失败/重试、取消/终态竞态、新请求、成功关闭、中文/键盘输入及 420px 布局。未调用云 API，已移除预览文件和服务。 |
| Codex smoke / harness coverage | not_applicable | 未修改 Codex runtime 实现或 harness/sidecar 事件契约。 |
| 全文件 pre-commit 及提交同步 | not_run | 未获提交授权，也未尝试提交；定向 lint、产物及密钥检查单独执行。 |
| 真实 BytePlus 创建 / 账号预检 | fail / pass | 用户提交的创建因地域 STS 传输失败，在 `checking` 阶段停止，尚未修改 PG/VPC/APIG。仅修正 BytePlus 地址后，实际 `RuntimeCloud.account_id()` 使用运行中 Studio 凭据核验成功，不记录身份值。未自动提交任务重试。 |
| 真实 BytePlus IAM 只读诊断 | fail / pass | 用户重试通过账号/模型 Key 检查，在 `iam_role` 失败。原 IAM 地址超时；仅修正托管地址后，实际 `IamCloud.call("get_role")` 返回可识别的 `RoleNotExist`；只读 GetPolicy 确认 12 个所需系统策略均存在。角色/策略创建及绑定权限尚未验证，助手未提交云端 IAM 写操作。 |
| 镜像拉取、后续 API/策略、就绪/聊天 | not_run | 等待用户重试及真实服务准备，模拟不能满足 AC-5。 |
| 修改/新增文件脱敏密钥扫描 | pass | Gitleaks 扫描隔离副本 1.43 MB，未发现泄漏。 |

AC-1–AC-3 已实现并通过隔离验证。AC-4 受上述未修改基线的完整回归及 CLI 错误限制。STS 修正前两个回归断言失败，修正后通过，并重新执行全部 752 项托管测试。AC-5 仍未完成，不能描述为海外端到端流程已验证。

IAM 后续验证（2026-10-10）：修正前两个接口回归测试失败；修正后 752 项托管测试通过，包括 24 项 BytePlus 用例及可信覆盖保留。修改的助手/测试通过 Ruff check/format、Pyright 及差异空白检查。本次后续修正不改变前端行为，已有浏览器/构建证据仍适用。

PG 后续验证（2026-10-10）：地址修正前两个回归断言失败；修正后 752 项托管测试通过，Ruff check/format、修改助手/测试的 Pyright 和差异空白检查通过。真实审计确认用户提交的 CreateWorkspace 外层 InternalError 包含内部 40016:Forbidden，原因是调用者没有购买当前配置的权限；并非已确认的配额错误。Workspace 状态为 CreateFailed，详情没有失败摘要，属主标签未返回。AIDAP 查询可达性已验证，实际 PG 创建仍被购买权限阻塞。没有执行删除、清除引导记录或重新创建。权限开通及失败资源恢复后才能继续 AC-5；无需为此重跑未受影响的前端验证。


## 提交前验证（2026-10-10）

用户已授权提交并推送本地修改。获取 `origin` 和 `upstream` 后，在 `feat/mpa-account-fixes-upstream-clean-20261010` 执行 `git rebase --autostash upstream/main`。分支已经同步；同步后原有 159 个改动文件状态全部一致。基础版本仍为 `5644e146c9dfff6d2e290b1663cb2ea41dbb6b91`。随后唯一的生产代码调整是 Ruff 格式化 CLI 中的创建路由注册调用。

- **pass：** `uv run --extra dev pre-commit run --all-files`：Ruff 检查/格式化及两项敏感信息扫描。首次运行格式化了 CLI 调用，再次运行全部通过。
- **pass：** 同步后 `uv run --extra dev pytest tests/integrations/mpa_managed -q --tb=short`：782 项通过，5 条已有警告。
- **pass：** 同步后 `npm --prefix frontend test`：1,377 项 Node 测试和 67 项 Vitest 测试。
- **pass：** 同步后 `npm --prefix frontend run check:i18n` 及 `npm --prefix frontend run test:webui-assets`：2 种语言 / 21 个命名空间，113 个文件 / 350 个引用。
- **not_run：** 重复执行完整 Python 回归、前端构建/浏览器及 Pyright。同步保留了此前已验证的源码，CLI 调整仅改变格式。完整回归的 MIME 及 CLI Pyright 基线失败仍按上文记录。本次提交请求不涉及新的云端创建、发布或部署；海外全流程就绪仍未验证。

提交包含 BytePlus 适配、PG 创建失败终态恢复、双语文档、测试及配套前端构建产物，不包含凭据、本地状态数据库或生产日志。
