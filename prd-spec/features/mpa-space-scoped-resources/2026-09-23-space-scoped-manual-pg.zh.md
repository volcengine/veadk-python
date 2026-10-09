# 按 Space 共享 MPA 资源并使用预先创建的 AIDAP PostgreSQL

> 已被[两套 PG Workspace 方案](2026-09-23-two-pg-workspaces.zh.md)取代：一个管理 Workspace、一个按智能体分库的共用业务 Workspace。下文每智能体 Workspace/Space 选择方案仅供历史参考。

[English](2026-09-23-space-scoped-manual-pg.md)

- 变更 ID：`mpa-space-scoped-resources`
- 日期：2026-09-23
- 状态：提案；Space 选择和 PG 凭据引用方式仍待确定。
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)、[MPA Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)。
- 对本创建流程，以此方案替代[自动创建 PG 设计](../mpa-serverless-pg/2026-09-21-deployment-account-pg.zh.md)中自动创建业务 Workspace 的路径。

## 背景与证据

当前 VeADK 以 `account_id + region` 为 `mpa_account_network` 和 `mpa_account_apig` 建立共享记录，并在管理员 PG 主机上为每个 MPA 建一个逻辑数据库。`frontend/server/mpa_creation.py` 只持久化非密钥的 PG 主机/端口，且要求与服务端唯一管理员连接一致。Studio 创建请求没有 Claw Space ID。当前 `agentkit-mpa-agent` 镜像同样按账号和地域查共享 APIG，因此只改 VeADK 无法保证 Space 隔离。

已检查本地 `arkclaw-team/pkg/service/multiplayer_agent/quota.go`：它从 MPA 读取 `SpaceID`，再从该 Space 的 `claw_space_application_conf` 取得 `apig_instance_id`。其创建流程为每个 MPA 记录 PG Workspace ID。旧实现用于确认共享边界；新链路运行时不依赖 ArkClaw 的数据库或服务。

## 目标、非目标与场景

在已核验的账号、地域和逻辑 Space ID 内创建或复用一套 VPC/子网及 APIG/IM Gateway。每个 MPA 的 Runtime、Worker、Skill Space、路由和预先创建的 AIDAP 业务 PG Workspace 保持独立。Studio 共享注册库仍按部署环境共享，不放在单个智能体的业务 Workspace 中。PG 步骤链接到 [AIDAP 控制台](https://console.volcengine.com/aidap/region:aidap+cn-beijing/)。

同一 Space 的两个 MPA 复用 VPC/APIG，但各用不同业务 Workspace。同账号同地域的两个 Space 不得仅因账号相同而获得同一套托管 VPC/APIG。同一 MPA 重试必须沿用原 Space 和 PG Workspace。迁移期间，已有部署仍能解析原网关和数据库。

非目标：创建或删除 AIDAP PG Workspace；导入 ArkClaw 的 `claw_space_application_conf`；改变通用智能体；在测试中创建真实云资源。

## 需求与设计

- **FR-1 — Space 身份：** Studio 创建时选择服务端授权的已有逻辑 Space。云资源变更前，核验 Space 与部署账号和地域的关系。Space 随请求身份、任务和部署记录持久化。Runtime 的 `CLAW_SPACE_ID` 使用选择值，而非账号推导的默认值。重试时改变 Space 必须失败。
- **FR-2 — 共享资源：** 网络/APIG 记录、锁、稳定名称和归属标记按账号、地域、Space 建立。显式采用 VPC/子网/APIG 时校验其属于所选 Space。保留旧账号级记录供已有智能体使用；不得静默转移旧网关或覆盖旧行。
- **FR-3 — Runtime 契约：** 部署的 `agentkit-mpa-agent` 必须查询同一个 Space 范围内的网关。启用新流程前同步修改其查询契约并发布镜像；否则以可操作的兼容性错误阻止创建。本次不扩大 Runtime 对共享注册库的写权限。
- **FR-4 — 手动 PG：** 提交前由操作员为每个 MPA 创建一个 AIDAP 业务 Workspace。服务端根据与该 MPA 绑定的管理员密钥引用解析连接和凭据；浏览器/任务载荷只包含非密钥的 Workspace 身份和主机/端口。核验 Workspace 可连接，且与共享注册库和其他智能体的 Workspace ID 不同。只记录不含密钥的 Workspace ID、主机。重试或失败时不得创建替代 Workspace。
- **FR-5 — 兼容与失败：** 已有智能体固定使用原网络/APIG/PG；打开创建弹窗不触发迁移。资源选择缺失、冲突、变化或不可达时，尽量在有费用的云操作前失败。取消后保留资源及绑定，供同一 ID 重试。错误信息不得包含数据库 URL、密码或云接口原始响应。
- **FR-6 — 页面与文档：** 保持三步弹窗。基础信息展示所选 Space，PG 步骤展示手动创建的 AIDAP Workspace。说明 Space 级共享和每智能体独立 PG；同步中英文文案、运维配置示例、契约与前端构建产物。

## 影响文件与任务

预计涉及 VeADK 的 `veadk/integrations/mpa/managed/{config,registry,database,network,gateway,service,runtime,runner,tasks}.py`、Studio 创建 API/类型/弹窗/国际化、测试、运维说明和构建资源。独立的 `agentkit-mpa-agent` 注册库/客户端契约也需协同修改并发布镜像。

1. 确定 Space 列表与选择方式、服务端每智能体 PG 凭据引用；修改生产代码前审查双语契约及迁移方案。
2. 先写失败测试，覆盖同账号两个 Space、同 Space 两个智能体、PG Workspace 唯一性、重试、旧记录、Runtime 网关查询和安全错误。
3. 在不削弱归属校验的前提下实现配置、API、注册库、编排和 Runtime 对接。
4. 验证定向测试、前端构建及浏览器场景、共享回归和构建资源。仅在另行授权且环境隔离时运行真实云冒烟测试。

## 风险与验收

当前 Runtime 镜像可能重新创建或读取账号级网关；只改 VeADK 不安全。现有共享注册库以账号和地域为主键，需要增量迁移或新表。手动创建的 Workspace 可能只能从另一个 VPC 访问，必须实测连通性。PG 密码不得进入浏览器存储、任务 SQLite、部署记录、源码或日志。

验收：同 Space 智能体恰好共享已核验的 VPC/APIG；不同 Space 不共用；每个新 MPA 使用独立的预建 PG Workspace；共享注册库保持独立；重试保留原绑定；旧智能体可用；失败不静默创建替代资源。2026-09-23 验证状态：AIDAP 弹窗链接测试 `pass`；新架构和真实云检查均 `not_run`，等待设计选择和实现。
