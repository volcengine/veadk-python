# BytePlus MPA 创建中的 OpenViking 自动准备

[English](2026-10-14-automatic-creation.md)

变更 ID：`mpa-byteplus-openviking`。创建/修订：2026-10-14。状态：implemented；云端验收待进行。

相关契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。
前置设计：[北京自动 OV](../mpa-openviking-auto/2026-10-13-default-model-creation.zh.md)。

## 背景与证据

用户要求在本 VeADK 仓库为 BytePlus MPA 创建补齐自动准备 OV。目前 `managed/openviking.py`、配置校验和服务编排都明确拒绝火山北京以外的自动 OV。Studio 弹窗也将自动模式限定为火山。BytePlus 已支持手动注入 URL、资源 ID 和 API Key。

用户提供的海外 SOP 描述了使用 Coding Plan 模型凭据创建个人版库，数据面地址为 `https://api.vikingdb.ap-southeast-1.bytepluses.com/openviking`。文档附有库管理 Python 脚本。2026-10-14 下载附件因缺少 `drive:file:download` 权限被拒绝；文档所述本地路径没有该脚本。因此海外控制面地址、签名地域、模型标识、凭据 Source/EndpointID 语义及企业版可用性尚未确认，不能根据数据面地址或国内配置推断。

本地 `agentkit-mpa-agent` 代码的用户注册和取 Key 仍使用北京 OV 管理接口。仅在 VeADK 中创建海外库不能证明 Runtime 记忆可用；该仓库需要单独适配和部署验证。

## 目标与非目标

在部署 Runtime 前创建并绑定海外库，等待就绪、获取数据面 Key，注入已有的四个 OV 环境变量。保留火山北京行为和已提交的手动请求。首期候选范围为 BytePlus `ap-southeast-1`，须以接口核实结果为准。

不包含自动修改 `agentkit-mpa-agent`、云端部署、开发过程中的付费资源创建、凭据发布、无关本地改动、通用智能体创建及 OV 删除。不得静默将按用户隔离替换成共享 default 身份。

## 需求与场景

- FR-1：仅向明确验证过的云厂商/地域组合开放自动 OV；配置、API、编排及 UI 必须一致。不支持的地域在资源变更前报错。
- FR-2：使用部署账号的 BytePlus 凭据签名已核实的控制面调用，适用时刷新 STS。不得复用国内账号凭据或猜测控制面域名。
- FR-3：选择默认值前核实库版本及模型凭据要求。Coding Plan 凭据、普通模型推理凭据和建库返回的库 API Key 是不同类型。缺少前置条件时，在创建资源前给出可操作、脱敏的错误，不采用未经文档确认的回退。
- FR-4：复用部署锁及持久化的非敏感意图/资源绑定。返回 ResourceID 后立即保存。后续失败重试先校验归属和配置，再复用原 ID。创建超时、结果不确定时不盲目重复建库。取消保留绑定并阻止后续步骤。
- FR-5：按已核实的状态值和有界截止时间轮询。就绪后取得 default 用户的库 Key，注入 `OPENVIKING_URL`、`OPENVIKING_RESOURCE_ID`、`OPENVIKING_API_KEY`、`OPENVIKING_USER`。URL 按云厂商区分。Key 不进入注册库、日志、UI 响应或浏览器持久化存储。
- FR-6：新的符合条件的 Studio 请求使用自动模式；已提交的手动任务重试保留原模式及输入。沿用三步弹窗及本地化状态/错误展示，适用时说明模型凭据前置要求及资源保留行为。
- FR-7：国内请求、通用智能体及其他已有 BytePlus 依赖保持契约。Runtime 按用户使用记忆是独立验收边界，不得通过建库测试声称其已验证。

## 拟议设计与契约影响

确认接口契约后，在现有 OV 适配器增加显式的云厂商/地域端点及模型配置选择，保持北京请求语义。复用签名辅助函数、部署账号凭据来源、注册库锁、安全错误和进度阶段。核实海外 Create/Get/Access 响应结构，不假定与北京一致。

统一扩展配置加载、请求校验、服务执行和弹窗的自动可用性标识及检查，并持久化每次请求选择的模式。模型凭据在服务端按明确支持的来源解析，最终选取方式需参考海外脚本；如增加密钥配置，实施前必须明确校验、脱敏、重启及重试语义。

更新 Studio MPA 创建双语契约，记录已核实的云厂商支持矩阵、模型要求及资源保留语义。现有 Runtime OV 环境变量名称保持不变。当前组件规格没有承诺海外自动创建，不得提前将拟议能力标为已生效。

## 任务与涉及文件

1. T-1 / FR-2–3：读取 SOP 附件或等效的权威海外契约，解决以下阻塞问题，完成并评审双语设计和组件契约。
2. T-2 / FR-1–5：先补失败的云厂商/配置/适配器/重试测试，再修改 `veadk/integrations/mpa/managed/openviking.py`、`config.py`、`service.py`，按需调整配置及凭据代码。
3. T-3 / FR-1,6：修改 `frontend/src/ui/mpa-create/MpaCreateDialog.tsx`，按需更新 API/任务处理和本地化文案，覆盖新请求、恢复请求和缺少前置条件的 UI 回归。
4. T-4 / FR-7：执行国内与海外离线回归、浏览器检查并重新构建发布产物，同步操作文档和双语设计/规格。

## 验收与验证

- AC-1：符合条件的新 BytePlus 请求调用已核实的海外控制面，取得绑定库并注入四个变量；测试数据不含真实凭据。
- AC-2：超时、取消、权限拒绝、就绪失败、缺少模型凭据和同请求重试均有明确测试结果，不重复建库、不静默成功。
- AC-3：国内线上请求体和已有手动重试语义保持不变，不影响通用智能体创建。
- AC-4：UI 可用性与后端一致；错误、加载、重试、键盘和窄窗口可用；前端产物与源码一致。
- AC-5：文档明确区分离线建库编排、云端实测和 Runtime 记忆集成。

计划命令：`uv run --extra dev pytest -n 2 tests/integrations/mpa_managed`；受影响的 Studio 服务端路由/任务测试；修改 Python 文件的 Ruff 和 Pyright；`npm --prefix frontend test`；`npm --prefix frontend run build`；`npm --prefix frontend run check:i18n`；`npm --prefix frontend run test:webui-assets`；限定范围密钥扫描。测试使用隔离的模拟服务。真实付费建库/读取记忆冒烟需要单独授权，并明确资源保留或清理方式。

## 风险与阻塞问题

- 海外支持的控制面地址、签名地域、API 版本及请求/响应字段是什么？
- 海外库版本是否支持 MPA 按用户注册和取 Key？SOP 中个人库的 OpenClaw 示例不能证明这一点。
- VLM/Embedding 接受哪些标识及凭据来源？已有模型 Key 能否复用，还是必须单独提供 Coding Plan 凭据？
- 就绪/失败状态及计费、保留约束是什么？未经核实不得将国内计费说明直接用于海外 UI。
- Runtime 就绪不等于 OV 记忆可用；独立的按用户路径需要适配后的 Runtime 镜像。

## 评审、授权与验证记录

用户在 2026-10-14 要求实施本仓库适配，范围已授权；未解决的接口细节阻止设计通过及生产代码/测试修改。直接评审认定库版本兼容性、凭据选择和云端端点核实为阻塞项。没有可用的 `review-spec` 技能，解决后记录完整直接评审。

2026-10-14，基于 `2ffe6e14` 及原有未提交修改：源码检查完成；附件读取 blocked（缺少 `drive:file:download`）；云端验证与运行测试 `not_run`（尚未实施、未授权云操作）；生产代码修改 `not_run`（云端契约未核实）。已有 contracts 迁移、OpenSpec 删除和 lockfile 修改属于其他任务，予以保留。


## 用户提供脚本的评审（2026-10-14）

用户直接提供了附件，已按源码阅读，没有执行或复制进仓库。脚本确认的参数如下：

- 控制面域名 `vikingdb.ap-southeast-1.byteplusapi.com`、签名地域 `ap-southeast-1`、服务 `vikingdb`、版本 `2025-06-09`、POST 路径 `/api/openviking/{Action}`；头包含 `X-Top-Service`、`X-Top-Region`，以及可选 STS `X-Security-Token`。
- 库为 `Version=developer`。Coding Plan 凭据使用顶层 `Source=codeplan`；模型为 `seed-2-0-lite` 和 `skylark-embedding-vision`，coding 模式不带 `ModelVersion` 或 `EndpointID`。endpoint 模式改用 `Source=volcengine`，分别指定两个模型的接入点。
- Create 返回 `ResourceID`；Get 轮询 `READY`/`FAILED`；取 Key 请求体只有 `ResourceID`（不带 `UserID`），返回 default 用户；响应兼容 `Result` 和 `result`。
- 脚本明确说明个人版拒绝用户注册；数据面要求 `Authorization: Bearer` 和 `x-tt-env: pre`。当前 Runtime 代码没有实现此契约。

脚本读取及控制面参数阻塞已解除，但出现影响隔离方式的版本决策：先实施个人库准备、后续适配 Runtime，还是保留企业版按用户隔离、先取得支持的海外企业版契约。已请用户选择，尚未授权回退到 default 共享身份。实现和生产测试等待该决策。阅读脚本或建库成功均不证明 Runtime 兼容性。

## 已批准的实施决定

2026-10-14 用户批准本仓库接入个人版自动建库，Runtime 单独适配后再联调。本节替代前文待定的版本决策。仅实施 BytePlus ap-southeast-1，Source=codeplan 并使用脚本给出的模型名；专用 Coding Plan Key 从服务端环境变量 `OV_MODEL_API_KEY` 读取，不使用普通 MPA 模型 Key。缺少或无效时在任何云资源变更前失败。新的 BytePlus Studio 请求开放 auto，已提交的手动请求保持手动。复用现有意图、归属、超时及取消保证。取 default Key 不传 UserID。保留四个已有 Runtime 变量，不添加没有消费者的 Runtime 配置。UI 说明个人版/default 用户、服务端凭据前置条件和 Runtime 独立联调要求，不声称未经确认的海外计费细节。取消/删除后保留库。

BytePlus 专用辅助模块按参考脚本的签名头和路径实现，不修改共享签名工具或北京适配器。用确定性离线测试覆盖规范签名及 STS。按选定请求校验回读字段：BytePlus 不要求 ModelVersion/EndpointID，北京仍要求。仅 BytePlus 接受参考的 Result/result 响应结构，拒绝显式失败及无效资源 ID。Create 结果不确定时不自动重试。

直接设计评审已检查云厂商边界、凭据分离、个人版隔离限制、已有手动恢复、密钥处理、启动延迟导入、错误传播、测试及双语一致性。阻塞决策已解决，状态 approved。本设计不授权云操作、提交或推送。

## 实施与验证（2026-10-14）

已实现批准的仅个人版范围。适配器使用独立且延迟导入的 BytePlus 签名传输、脚本给出的路径/请求头及模型名；北京继续使用现有签名函数和请求结构。配置能力和已有弹窗支持新的 BytePlus 自动请求。模型 Key 仅从服务端环境解析，直接部署在构造云客户端前检查，Studio 则在任务提交前校验。没有增加浏览器密钥字段，也没有让 Runtime 回退到共享身份。四个已有变量供另行适配后的 Runtime 使用。

验证范围：基于 `2ffe6e14` 的本次功能，保留原有 contracts 迁移、OpenSpec 删除及 lockfile 修改。评审覆盖云厂商范围、带/不带 STS 的精确规范签名、小写响应结构、个人库不显式传 UserID、显式失败处理、密钥排除、归属/回读、创建结果不确定、取消重试及旧手动任务。云端调用全部使用模拟。

| 检查 | 结果 | 范围 |
| --- | --- | --- |
| Python 测试先行 | pass | 实施前 7 个新回归失败，覆盖 BytePlus 适配器/配置/重试。 |
| Python 定向测试 | pass | 12 项，包含后续新增的 STS 签名、取消及缺少 Key 不变更资源检查。 |
| 托管创建及启动回归 | pass | 双 worker，987 项。 |
| Studio API/RBAC 回归 | pass | 双 worker，Runtime Profile 路由与 Studio RBAC 共 205 项。 |
| 前端测试 | pass | 1,389 项 Node、96 项 React。首次 UI 命令工作目录错误，随后使用仓库 npm 命令全部通过；新的自动模式用例在修复 UI 前失败。 |
| Ruff 0.11.12 检查/格式及 Pyright | pass | 6 个修改的 Python 源码/测试文件；Pyright 0 错误/警告。 |
| 构建、国际化及发布引用 | pass | 两个前端目标完成构建；2 语言/21 命名空间；113 个打包文件/350 个引用。 |
| 浏览器 | pass | 真实弹窗、模拟 HTTP：海外自动模式、无手动字段、缺少 Key 错误可见、同请求重试、窄屏、Escape、旧手动恢复及北京文案。已移除临时文件及服务器。 |
| Wheel | pass | 本地构建，包含与源码字节一致的新适配器，没有发布。 |
| 限定范围密钥扫描 | pass | 修改/新增的源码、文档、测试及产物，无发现。 |
| 真实云端/Runtime OV 记忆 | not_run | 未授权创建付费资源，个人版 default 用户/Bearer/pre 路由仍属于另一仓库的工作。 |
| 全仓 pytest/pre-commit | not_run | 未要求提交；本次云厂商扩展由定向集成及完整前端检查覆盖，没有修改无关源码。 |
| Harness/sidecar 冒烟 | not_applicable | 未改变 harness、worker 或 sidecar 协议。 |

AC-1–AC-5 已有离线实现证据，真实库响应细节、账号权益和记忆功能仍未验证。用户同意 Runtime 适配作为独立范围。未提交或推送。


凭据决策已由以下设计替代：[API Key + endpoints](2026-10-14-inference-endpoints.zh.md).
