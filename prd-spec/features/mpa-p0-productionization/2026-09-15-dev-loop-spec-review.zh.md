# MPA AgentKit P0 Dev Loop Spec 评审

- Change ID：`mpa-p0-productionization`
- 日期：2026-09-15
- English：[2026-09-15-dev-loop-spec-review.md](2026-09-15-dev-loop-spec-review.md)
- 被评审 PRD：[MPA AgentKit P0 功能迁移与落地](2026-09-15-mpa-p0-productionization-design.zh.md)

## 1. 总体结论

- 可行性：整改后为中高；实施规模为跨 VeADK、agentkit-mpa-agent、AgentKit OpenTOP/Runtime 和 worker 协议的 XL 级交付。
- 最大风险：身份与真实写链路、跨外部系统幂等、PostgreSQL 并发恢复、创建 operation 刷新恢复。
- 推荐方向：按 M0、S1 至 S5 串行垂直切片交付，每个切片独立验证、合入和回滚，不以单个 PR 一次性实现。
- 门禁结论：下列 P0/P1 已写回 PRD 与组件契约；本地 M0 contract 是进入 S1 的门禁，仅部署后可验证的身份/Profile 项保留为发布门禁。

## 2. 问题与整改记录

| 原级别 | 问题 | 整改 | 状态 |
| --- | --- | --- | --- |
| P0 | 首次 Profile apply 同时要求 `If-Match` 与 `If-None-Match` | 改为互斥前置条件，补 `400/428` 与强 ETag | resolved |
| P0 | 异步 apply/run/continue 缺少幂等与状态持久化 | 新增最小 `runtime_operations`；pending Profile 不切 current | resolved |
| P0 | continuation 对外部 A2A TaskStore 承诺不可实现的 ACID | 改为 Runtime 事务 + dispatch outbox + 幂等 dispatcher | resolved |
| P0 | REST JWT 与 A2A TIP 身份语义分裂 | 定义统一 `RuntimePrincipal v1`、同 issuer/JWKS、claim 映射和迁移矩阵 | resolved；M0 live gate |
| P0 | 旧方案错误依赖 Managed Agent CRUD/version | 从 P0 删除该产品依赖；Studio AgentDraft 直接规范化为 MPA Profile 并应用到 Runtime | 已按范围决策解决 |
| P0 | 显式升级 Session 缺少 API | 新增 `profile-upgrade`，定义 ETag、幂等、活动 Turn、降级和未 applied 错误 | resolved |
| P0 | 创建状态仅在浏览器内存，刷新不可恢复 | 新增 TOS CAS creation operation 与 reconcile/retry API | resolved |
| P0 | AgentKit Session 与 runtime Session 双权威 | P0 明确只使用 mpa-agent 业务 Session/Turn；AgentKit Managed Agent Session 不进入主链路 | resolved |
| P0 | 云 E2E 和 PostgreSQL 语义不可执行 | 补 live 环境清单、真实 PostgreSQL 双连接 lane、fault injection 与跨仓 manifest | resolved；执行时硬门禁 |
| P1 | A2A execution 版本无 wire contract | 定义 `urn:veadk:mpa:execution:v1` 与 metadata/hash/兼容行为 | resolved |
| P1 | SSE cursor 未知时静默全量重放 | 指定持久 ADK events + inbox fence；未知 cursor 返回 `410` | resolved |
| P1 | 明文 Secret 与“只保存引用”冲突 | AgentKit mode 禁止新明文写，定义转换、清空和兼容删除窗口 | resolved |
| P1 | 性能指标无测量口径 | 补 warm-up、样本、并发、数据规模和统计边界 | resolved |
| P1 | 页面复用边界不明确 | 增加 MPA intent/view-model，禁止复用 GitHub version/generic draft/evaluation 逻辑 | resolved |
| P1 | Runtime 门禁和跨仓兼容不明确 | 固定 `make test/coverage`、跨仓 manifest 和兼容矩阵 | resolved |
| P1 | runtime operation 覆盖范围/查询接口不闭合 | 限定 Profile/run/upgrade/continue，补通用 operation GET；配置与控制各用自己的 CAS store | resolved |
| P1 | create/update 首次响应丢失与更新恢复不闭合 | 两类写操作统一 `202 + operationId`、客户端幂等键、active list、reconcile/retry | resolved |
| P1 | Session upgrade 未定义 override 重算 | 目标 Profile 作新 base，保留 override/clear，inherit 跟随新默认，失效资源原子拒绝 | resolved |
| P1 | MPA detail 缺少可实现数据契约 | 增加 `MpaAgentView` 与 0/1/N Runtime binding/orphan 语义 | resolved |
| P1 | Runtime A2A capability 与 Worker protocol 混淆 | 兼容矩阵拆列，固定当前 Worker REST 静态基线 | resolved |
| P1 | smoke 依赖模型自主调用工具 | 拆成 tool-disabled 模型探针与 Runtime 直接调用现有 CodexWorkerClient 探针 | resolved |

## 3. 16 维检查结论

上下文、范围、术语、模型理解、SDD/TDD、最小实现、兼容、存量影响、运行风险、可行性、扩展性、过度设计、最小变更、代码边界、架构一致性和可验收性均已检查。关键收敛包括：不迁移 ArkClaw 数据；不建设模板/专家/version；只新增必要 Runtime 持久模型；Session 单一权威；外部系统使用 adapter/outbox/reconcile，不宣称分布式事务。

## 4. 落地顺序

1. M0：Profile client contract、principal 基座、PostgreSQL、fault injection、跨仓 manifest；仅部署后可验证的身份/Profile 证据移至 S5。
2. S1：创建、持久 operation、Profile、确定性 smoke、首轮对话。
3. S2：Session execution-config 与显式版本升级。
4. S3：Run 幂等、outbox 与持久事件重放。
5. S4：多 worker pause/resume/continuation。
6. S5：详情/版本、Runtime 生命周期、Debug/Trace、CLI 和兼容收口。

## 5. 门禁

范围修正后的评审无 P0/P1；本地 M0 contract 与 PostgreSQL 基座已通过，可进入 S1，实现完成后必须通过部署环境 identity/Profile 发布门禁。
