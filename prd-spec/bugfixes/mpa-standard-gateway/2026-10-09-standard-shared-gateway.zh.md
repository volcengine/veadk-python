# 标准型共享 APIG 创建

[English](2026-10-09-standard-shared-gateway.md)

变更 ID：mpa-standard-gateway。创建/修订：2026-10-09。状态：implemented。

## 证据、目标与边界

只读排查确认，历史成功的 MPA 共享网关为标准型，两个 1c2g 节点、small_1 CLB、公私网启用、按流量计费。新账号 Serverless 网关数量已达限额，标准型数量仍有余量。当前托管创建硬编码 serverless，且只准备一个子网。提供方 [CreateGateway 契约](https://docs.volcengine.com/docs/apig/CreateGateway?lang=en)要求至少两个不同可用区的子网。[GetGatewayAvailableZones](https://docs.volcengine.com/docs/apig/GetGatewayAvailableZones-QuerythecurrentRegionAvailabilityZonelist?lang=zh) 提供 APIG 支持的可用区，可能与 ECS 可用区不同。

目标：新建托管网关采用已验证的标准型配置，准备适合的跨可用区网络，并恢复明确的配额拒绝。非目标：修改前端、通用智能体聊天、迁移现有 Runtime、删除资源、切换云账号、复制旧账号资源 ID、升级镜像或自动申请提额。真实创建由用户另行提交。已有标准型/Serverless 登记和显式接管保持兼容。

## 需求与场景

- FR-1：CreateGateway 使用 standard、Replicas=2、InstanceSpecCode=1c2g、CLBSpecCode=small_1、公私网均启用、按 traffic 计费。少于两个或重复子网 ID 在发送前拒绝。
- FR-2：没有登记/接管 ID 的新网关，在现有账号锁内查询 APIG 可用区，准备同一 VPC 内两个不同受支持可用区的可用子网。优先复用合适子网，只创建缺失的伴随子网，CIDR 不重叠。DescribeSubnets 延迟时，计入 GetSubnet 已确认就绪的子网网段。保留 VPC 及所有现有资源。
- FR-3：每个伴随子网有独立的持久化意图/token/发送标记和稳定的范围/可用区名称。超时/取消/未知结果在再次 Create 前必须查询恢复；重试保留载荷和 token。冲突、畸形可用区、归属变化、CIDR 耗尽及 APIG 可用区不足两个均明确失败。已记录的未完成伴随意图保持权威，即使出现其他合适子网也不能跳过。
- FR-4：已有网关复用/接管不要求新可用区查询或网络变更。已有 Runtime 网络载荷保持不变；新 Runtime 载荷使用准备好的网关子网选择。管理注册库记录为事实来源。
- FR-5：网关和 IM 创建的 ExceededQuota 属于提供方明确拒绝，保存 create_requested/im_create_requested=false，修正后允许同智能体重试。超时/内部/未知错误保留防重复保护。历史未知标记不自动清除。一次性恢复只有在共享锁内核实明确拒绝的审计、精确范围/VPC/名称及网关不存在后才可清除该意图；不得删除资源或重置任意意图。
- FR-6：部署 IAM 策略增加只读 apig:GetGatewayAvailableZones。Runtime 角色策略和其他权限不变。凭据及提供方载荷不得进入用户输出、源码或报告。

场景：新共享环境创建两个跨可用区子网和一个标准网关/IM 服务；已记录单子网 VPC 只补齐缺失子网；不同智能体复用同一管理注册库；伴随子网 Create 响应丢失后按精确名称恢复；配额拒绝可恢复；网关未知结果仍阻止重复；已登记网关/Runtime 保留网络。

## 设计与契约影响

`gateway_cloud.py` 负责标准型请求和 APIG 可用区适配。`network.py` 添加网关专用准备方法，复用 entry 锁，并在 gateway_subnet_intents 中按可用区持久化伴随意图。独立 Runtime 调用方的单子网准备保持不变。`service.py` 仅在没有已登记/接管网关时调用伴随准备，独立传递网关子网，仅修改新 Runtime 模板网络。`gateway.py` 识别明确配额拒绝。`frontend_deploy_policy.py` 增加一个只读动作。不修改公开 HTTP/API/CLI 字段、配置或表；JSON 注册记录增加可选伴随意图。所有提供方调用刷新并核验凭据。

归属契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)及 [Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)。同步双语及托管模块 README。前端/浏览器/资源/sidecar 检查为 not_applicable，因其接口/行为未改。隔离测试覆盖真实请求形态、编排及恢复；真实部署单独报告。

## 任务与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1、FR-6 | T-1：先失败的适配器/策略回归，再标准型请求/可用区 | AC-1：标准型载荷和最少 ID、严格可用区、部署权限 |
| FR-2–4 | T-2：先失败的伴随/复用/取消测试，再持久准备及入口接线 | AC-2：新环境/单子网恢复/多智能体，无现有 Runtime 变更或重复创建 |
| FR-5 | T-3：先失败的配额恢复测试，再明确错误处理 | AC-3：网关/IM 配额允许重试，未知结果仍阻止 |
| FR-1–6 | T-4：文档、专项/回归及审查 | AC-4：相关测试、Ruff/Pyright、密钥/差异/双语/链接通过 |

命令：`uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q`；修改文件的 Ruff/Pyright/pre-commit。验证不包含提交、推送、部署、破坏性清理或真实创建。

## 审查、批准与风险

review-spec 不可用，直接审查：范围归属、跨可用区要求、独立意图、锁、部分失败、Runtime 兼容不变、权限及双语等价均已审查。用户以“帮我改”批准标准型网关/双可用区/IM/注册库/重试方案。新只读动作需要部署权限；可用区为空/查询失败时不静默替换为 ECS 结果。新标准型资源按提供方计费；配额/资源不足仍可能发生，并保留明确失败。历史未完成标记在审计确认的操作恢复前保持保守。无设计阻塞项。

## 验证与交付

2026-10-09，测试范围为 ef0ad519 工作区加本次未提交网关修复及此前已批准的账号/IAM/网络修复；保留无关用户修改。隔离实现验证满足 T-1–T-4、AC-1–AC-4。

- pass：先运行适配器/配额基线（13 个预期失败、14 个通过）、伴随子网/策略基线（12 个预期失败、64 个通过）及列表延迟 CIDR 回归（一个预期失败），然后实现。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short`：578 个通过，五条已有依赖弃用警告。覆盖标准型载荷、APIG 不同可用区、多智能体复用、取消/响应丢失恢复、未完成意图权威性、归属/可用区/账号变化、CIDR 耗尽及列表延迟、配额恢复和已有 Runtime 网络不变。
- pass：12 个相关 Python 源码/测试文件执行 `uvx --from ruff==0.11.12 ruff check`、`ruff format --check`；gateway_cloud.py、gateway.py、network.py、service.py、frontend_deploy_policy.py 执行 `uvx pyright --pythonpath .venv/bin/python`，零错误。
- pass：`uv run --extra dev pre-commit run --files <affected source/tests/docs>` 的 Ruff 检查/格式及硬编码密钥扫描。具体 YAML 密钥检查 not_applicable（没有 YAML 修改）。
- pass：双语配对、相对路径/引用、差异空白检查；直接实现审查无剩余阻塞项。保留范围、注册库锁和 Runtime 网络兼容；取消不回滚资源。
- pass（仅真实数据修复）：在共享账号/地域锁内，重新核验部署 STS 身份、本地失败任务/无运行中创建、精确的 ExceededQuota 提供方审计及范围内网关不存在；仅清除这次明确拒绝的 create_requested 标记并回读核验。未创建/删除云资源，未修改其他记录。历史未知意图没有自动绕过。
- not_run：真实标准网关/IM/Runtime 创建；用户需重启本地 Studio（云端重新部署）后提交。提供方配额、资源及权限仍需实际检查。
- not_run：全仓库并行回归及全文件提交检查；本次覆盖相关创建/部署/CLI 回归。此前全量运行的无关 SDK 依赖/收集失败已记录在 IAM 设计中。未收到提交请求。
- not_applicable：前端/浏览器/构建/资源/sidecar 检查，没有前端或事件/聊天接口变化。
