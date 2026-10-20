# Studio MPA 自动准备 OpenViking

[English](2026-10-13-default-model-creation.md)

变更 ID：`mpa-openviking-auto`。日期：2026-10-13。状态：已实现；待真实验收。
契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)、[Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)。

## 证据、目标与非目标
Studio 目前收集可选的 OV 地址/资源 ID/API Key。MPA 镜像已使用运行角色 STS 注册 OV 用户身份。参考库只读核对为企业版 READY，返回模型名/版本但没有模型 API Key/Key ID；控制台显示自配凭证为零、内容理解限时免费已启用。这不证明新 API 创建的库可以使用默认模型。官方 Create/Get/Access 文档定义异步 INIT/READY/FAILED 以及默认用户取 Key。
目标：北京 Studio 的新 MPA 请求自动准备独立企业版 OV，无需手填连接参数，先尝试默认 VLM/Embedding 配置。BytePlus、通用智能体、已有任务、手动 CLI 配置和已有 Runtime 保持行为。不包含创建方舟接入点/Key、复制旧 Key、数据迁移或删除 OV。新 OV 是保留的付费资源，实现批准不等于授权真实建库。

## 要求与场景
- FR-1：北京内置配置提供自动 OV 能力。新 UI 请求持久化 `openvikingMode: auto`；缺省/manual 保留旧请求语义。非火山北京的 auto、auto 与手动连接参数混用均在写操作前拒绝。CLI 通过 managed 配置显式启用。
- FR-2：在已有授权部署锁内，以合法哈希 Name、作用域 Description、默认项目创建独立企业库；VLM 为 `doubao-seed-2.0-lite`/`260428`，Embedding 为 `doubao-embedding-vision`/`251215`，显式提供 Source/EndpointID Credentials，已解析方舟 Key 仅加入复制的网络请求。发送前保存非秘密意图，响应后立即保存 ResourceID。复用注册 ID 前核验名称/描述/项目/版本/模型；deleting/deleted 智能体不能创建。
- FR-3：在有界期限内轮询 INIT 至 READY，FAILED/非法状态/缺失 ID/权限失败均明确报错。通过 AccessOpenVikingApiKey 取得 default 用户 Key，部署前注入地址/资源 ID/Key/用户。Key 不进入 SQLite、注册库、结果、日志或夹具。Runtime 用户注册继续由 MPA 镜像负责。
- FR-4：后续部署失败复用注册库。明确拒绝的创建允许重试相同意图；结果不确定时阻塞，不能盲目新建，由管理员核实并补齐注册 ResourceID。取消保留已知/未知资源并停止后续调用。仅取 Key 等读取操作重试瞬时错误，创建不自动重试。
- FR-5：第三步显示自动准备及企业版计费信息；新 auto 请求没有手动输入框。已提交手动任务和 BytePlus 保留字段/校验。安全本地化错误和阶段可见，重试保留原模式/身份。沿用现有布局、TOS 控件、键盘/IME、取消和焦点行为。

## 设计与影响文件
新增 OpenViking 配置、签名控制面适配器及持锁资源准备。复用刷新且核验账号的部署凭据、已有签名函数及诊断接收器。仅使用已公开的 CreateOpenVikingCollection/GetOpenVikingCollection/AccessOpenVikingApiKey；不假设未公开的名称发现接口或幂等 token。库与 Runtime Key 生命周期独立。默认模型接受情况是明确未验证的平台能力；拒绝时不能静默新建付费方舟接入点或省略 OV。
影响：managed config/profile/service/runner/tasks/diagnostics；新增 openviking 模块；Studio 请求/client/dialog/locales；目标测试、既有前端发布产物和使用说明。不修改通用创建/聊天/删除及 MPA 镜像。
Studio 配置将能力展示与执行模式分开：读取配置或直接调用 provision 不会为旧请求自动开启 OV。只有新请求显式模式或 CLI 显式 managed 设置才启用创建。Runtime 部署保留现有环境、归属及请求哈希契约；四个 OV 变量已受支持，因此不需要单独修改 Runtime 契约。
部署凭据需要 vikingdb CreateOpenVikingCollection/GetOpenVikingCollection/AccessOpenVikingApiKey 权限。Runtime 角色已有 VikingdbFullAccess 用于用户管理。仅已核验部署账号的凭据能建 OV。库绑定保存在 mpa_admin_db；智能体删除不新增 OV 库或记忆清理。

## 任务、验证与验收
| 要求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1/5 | T-1 模式透传与 UI | AC-1 新 auto 请求，旧/手动/BytePlus 不变 | config/route/task、React 测试及浏览器 |
| FR-2/4 | T-2 持锁意图与绑定 | AC-2 同智能体复用，冲突/未知/取消安全 | 离线适配器/资源准备测试 |
| FR-3 | T-3 就绪/Key 注入 | AC-3 四个环境变量、无秘密持久化、明确错误 | service/runner/安全测试 |
| 全部 | T-4 同步 | AC-4 双语文档、构建及必需检查 | 受影响 Python 回归、前端 test/build、Ruff/Pyright、i18n/assets、秘密扫描 |
实际验证记录见下文。真实验证需要另行批准的隔离库和清理决定；没有实测时，默认模型新建可用性标记未验证。

## 风险、评审与批准
API 的可选模型凭证行为及默认模型权益可能与旧控制台库不同，默认路径拒绝时明确报错。企业版就绪即按小时计费，失败/取消/删除后保留云资源。未找到公开的名称发现/幂等契约用于恢复创建丢失响应，优先安全阻塞而非盲目重试。外部修改注册库/云资源无法与云调用组成事务。
review-spec 不可用，已直接评审边界、凭据、归属、超时/取消、未知结果、兼容、可测试性及双语等价。用户在 2026-10-13 批准默认模型优先的北京实现，并明确确认 BytePlus 不变；未授权扩大范围。SPEC 引用的两个前端 skill 在目标路径及本地 skill 根均未找到，复用现有 ModalLayout/字段并直接核验 Foundation S1-S8，不另建设计系统。

## 实现评审与验证（2026-10-13）

测试范围：基于 `71175c68636dc5b951e9804eb292d85402511e68` 的未提交 OV 改动；未修改用户状态或云资源。测试先行证据：适配器模块缺失时收集失败；auto UI 回归在仍显示手动字段时失败。实现覆盖模式透传、账号/地域拒绝、注册锁与归属、INIT/READY/FAILED、取消、未知创建结果、安全错误、秘密排除以及 Runtime 部署前环境注入。评审发现并修正两项兼容问题：必须先核验账号再构造 OV 适配器，能力展示不能替旧请求/直接调用开启 OV。

| 检查 | 结果 | 证据 / 范围 |
| --- | --- | --- |
| `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/cli/test_studio_rbac.py` | pass | 1,074 通过；根据本地资源使用两个 worker。 |
| `npm --prefix frontend test` | pass | 1,379 项 Node、79 项 Vitest 测试。 |
| `npm --prefix frontend run build` | pass | 同步生成 main/widget 发布产物。 |
| `npm --prefix frontend run check:i18n` | pass | 2 个语言 / 21 个 namespace。 |
| `npm --prefix frontend run test:webui-assets` | pass | 113 个发布文件 / 350 个引用。 |
| `uvx ruff==0.11.12 check <changed-python-files>` 与 `format --check` | pass | 全部 12 个变更生产/测试 Python 文件；使用仓库 hook 固定版本。 |
| `uvx pyright --pythonpath .venv/bin/python <changed-python-files>` | pass | 全部 12 个变更 Python 文件，0 错误/警告。 |
| `uv run --extra dev pre-commit run gitleaks --files <changed-files>` | pass | 变更源码、测试、文档及构建产物，无凭据发现。 |
| 浏览器夹具 | pass | 实际弹窗，仅模拟服务：三步流程、auto 无 OV 输入、本地化模型拒绝、同请求重试、BytePlus 手动字段、已提交旧手动任务恢复、Escape/焦点恢复、390×844 布局。临时夹具已移除，未调用云创建。现有交互测试覆盖加载/键盘/IME 及终态行为。 |
| 单独运行 `test_runner_scope_covers_async_worker_events` | fail（历史问题） | 单独运行时，现有 `.env` 初始化日志进入捕获 stdout，导致测试 JSON 解析失败。以临时只读 HEAD 源码快照复现相同失败。广泛套件通过；未修改无关日志/测试。 |
| 真实 OV 创建/Key/就绪验证 | not_run | 需要另行授权的付费隔离资源。读取旧库不证明新库默认模型权益可用。 |
| Codex/sidecar smoke 与覆盖率检查 | not_applicable | 未修改 worker/镜像/harness 协议。 |
| 全仓库 pre-commit / commit / push | not_run | 本次未要求提交；已执行受影响 lint、类型、秘密及独立于真实 Runtime 的检查。 |

AC-1–AC-4 实现及离线验证完成。真实云验收明确待完成：默认模型被拒绝时任务返回可处理错误，不创建方舟接入点、不静默省略 OV。企业版 OV 在失败、取消或 MPA 删除后保留。

### 真实发现及来源修正

首次用户触发的真实请求因模型来源为空明确返回 InvalidParameter，证明不能完全省略 Credentials。[已批准的来源修正](../../../prd-spec/bugfixes/mpa-openviking-source/2026-10-13-model-source.zh.md) 补齐 Source/EndpointID，仅在网络请求中使用现有已解析方舟 Key，并安全恢复完全匹配的已拒绝意图。上面的离线结果仍是初版实现证据，当前验证记录在修正文档中。尚未声称修正后真实建库成功。
