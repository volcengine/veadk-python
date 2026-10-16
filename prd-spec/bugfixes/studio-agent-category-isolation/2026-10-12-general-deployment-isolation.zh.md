# 通用部署与 MPA 隔离

## 背景和范围

在 `812faadf` 中，ProjectPreview 把所有 AgentDraft 当成 MPA，CustomCreate 固定提交 `agentCategory: mpa` 并在所有结构化部署后应用 Profile，MyAgents 在两个类型列表都加入全部草稿。这会误标通用 Runtime，并调用不支持的 MPA 接口。恢复引入 MPA 前的通用构建、部署、发布流程，保留现有实例配置、评测和 GitHub 选项。保留独立 MPA 创建与明确的 MPA 编辑。

## 需求、设计和验收

- R1：新的结构化/YAML 创建默认 general。存在草稿、名称、模型、技能、委派和快捷/传统界面都不能推断 MPA。
- R2：已有目标从选中 Runtime 或明确 MPA 入口保存 `agentCategory`。明确类型优先；旧 `mpaProfileOnly: true` 仍为 MPA，否则默认 general。只有实例 ID 不足以判断。
- R3：向 ProjectPreview 传递类型，并限制 CustomCreate 两条部署路径。仅 MPA 执行 Profile/smoke，并在初始、成功、失败和重试任务状态报告这些阶段。保留通用部署、取消和错误行为。
- R4：合并服务端已筛选 Runtime 前，按同样规则筛选本地草稿。保留归属、地域和搜索筛选，包括恢复草稿后。
- R5：MpaCreateDialog 与托管创建 API 不变。不修改聊天，不自动迁移已有云端标签。

通用部署须发送 general，不调用 Profile/smoke 即可完成，失败和重试后仍为 general。明确 MPA 保留对应流程。无类型旧草稿归通用；旧 Profile-only 草稿归 MPA。不做无关清理或云资源变更。

## 文件和任务

1. 增加类型解析函数及 agentDraftStorage/App 目标持久化。
2. 限制 CustomCreate 和 ProjectPreview 流程、请求及任务标记。
3. 筛选 MyAgents 草稿。
4. 实现前先编写失败的类型/存储和部署回归测试；纠正要求所有草稿为 MPA 的旧测试。
5. 执行前端测试、构建、国际化、产物和隔离浏览器检查；同步发布产物并记录结果。

## 评审和风险

参见[组件契约](../../../specs/studio-mpa-control-plane/README.zh.md)。2026-10-12 直接设计评审覆盖边界、错误/重试、安全、兼容性、可测试性和双语等价性；review-spec 不可用。用户于 2026-10-12 同意实施，要求保持原通用流程，MPA 作为额外流程。复用现有 UI，不做视觉重设计。后端 API 不变。

已有误标 Runtime 在单独核实修正前仍误标。旧标识无法可靠还原意图，无类型草稿默认通用。预览与快捷部署两条路径必须使用相同类型规则。保留无关群权限修改及 package-lock 修改。

## 验证

范围：`812faadf` 上本次修复，2026-10-12。云部署：not_run（未授权变更）。Python 检查：not_applicable（前端范围）。提交检查：not_run（未要求提交）。

### 结果和实现评审

- pass：先写回归测试复现通用任务被标为 MPA，包括失败部署。修复后类型、存储和源代码契约的定向用例通过 24 项。
- pass：`npm --prefix frontend test`：1,379 项 Node 测试和 74 项组件测试；覆盖真实 React 处理函数的普通预览部署、快捷创建、带旧实例 ID 的更新、重试、取消、状态不确定、明确 MPA Profile 失败、列表切换及独立 MPA 创建回归。
- pass：`npm --prefix frontend run build`（TypeScript 和两套产物）、`npm --prefix frontend run check:i18n`、`npm --prefix frontend run test:webui-assets` 和 `git diff --check`。发布产物包含既有群权限修改。现有 Vite 警告不是新增失败。
- pass：使用真实 ProjectPreview/MyAgents 组件、模拟 API 的隔离浏览器验证：通用成功部署不含 MPA 阶段，失败/重试仍为通用，Escape 取消确认，类型切换隔离草稿，390×844 下中文搜索和空结果正常。未使用云凭据或变更云资源。临时测试页和服务已移除。
- not_run：真实云部署、浏览器慢网络时序及原生输入法组合输入；未授权云操作，且未修改输入/加载实现。取消及状态不确定行为由组件测试覆盖。
- not_applicable：Python、harness-sidecar 覆盖率和文档站门禁；其实现/契约没有变化。
- not_run：pre-commit、rebase、提交、推送；未要求提交。

最终评审：按 Runtime ID/地域匹配类型，随部署目标保存，并用于预览、快捷创建、任务恢复和列表筛选。独立 MPA 创建 API 未改动。已评审差异无阻塞项；已有云端误标需单独修复。约定前端范围内的实现任务均已完成。
