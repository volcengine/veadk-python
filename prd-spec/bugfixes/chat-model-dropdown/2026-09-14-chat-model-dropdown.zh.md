# 聊天模型下拉菜单可见性修复

- **变更 ID：** `chat-model-dropdown`
- **创建日期：** 2026-09-14
- **状态：** 已实施
- **英文版本：** [2026-09-14-chat-model-dropdown.md](2026-09-14-chat-model-dropdown.md)
- **相关规格：** [Studio MPA 控制面](../../../specs/studio-mpa-control-plane/README.zh.md)

## 背景与证据

Studio 活跃聊天中的 Turn 模型选择器使用 `NewChatCompactSelect`。共享 compact select 菜单默认向触发器下方展开。Composer 模型选择器通过 `bottom: calc(100% + 6px)` 覆盖为向上展开，但没有重置继承的 `top` 定位，导致菜单同时受上下定位约束；用户只能看到搜索框，完整选项列表不可用或被裁切。

该问题影响聊天过程中切换模型；不影响模型列表获取，也不改变 Turn 模型快照不可变契约。

## 目标

- 让聊天 Composer 模型下拉菜单同时显示搜索输入和选项列表。
- 长模型列表必须限制在视口内，并在菜单内部滚动。
- 保持 Agent、Skill 和视频等其他 compact select 的现有行为不变。

## 非目标

- 不修改 Sandbox 会话的模型加载方式。
- 不修改已选模型持久化或 Turn 快照语义。
- 不重设计 `NewChatCompactSelect`。

## 需求

- `FR-1`：Composer 模型菜单必须从模型触发器向上展开，且不再同时受到冲突的 `top` 和 `bottom` 定位约束。
- `FR-2`：Composer 模型选项列表必须有明确的高度上限，长模型目录可以在菜单内滚动查看。
- `FR-3`：Composer 之外的共享 compact select 菜单必须保持默认向下展开行为。

## 设计

为 `.composer-model-select .new-chat-compact-select__menu` 和 `.composer-model-select .new-chat-compact-select__list` 增加局部 CSS 覆盖。菜单显式设置 `top: auto`，保留既有右对齐、向上展开定位。列表增加基于视口的 `max-height`，使完整模型目录通过菜单内部滚动查看，而不是被裁切。

无需修改组件契约。该修复仅影响展示层，复用现有 DOM、键盘交互、搜索 placeholder 文案和 listbox 语义。

## 任务

- `T-1`：更新 Composer 范围内的 compact select CSS。
- `T-2`：为向上菜单定位和列表高度上限增加源码级回归断言。
- `T-3`：执行定向前端测试、构建 Studio 资源，并验证打包资源引用。

## 验证与验收

| 需求 | 任务 | 验收标准 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-2` | Composer 模型菜单重置继承的 `top`，从触发器向上展开。 | `node --test frontend/tests/newChatComposerLayout.test.mjs frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs` | pass |
| `FR-2` | `T-1`, `T-2` | Composer 模型选项使用视口感知的最大高度，并在菜单内滚动。 | `node --test frontend/tests/newChatComposerLayout.test.mjs frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs` | pass |
| `FR-3` | `T-1` | 覆盖仅限 `.composer-model-select`；共享 compact select 默认行为不变。 | `node --test frontend/tests/newChatComposerLayout.test.mjs frontend/tests/newChatAgentPicker.test.mjs frontend/tests/myAgents.test.mjs` | pass |
| 全部 | `T-3` | 构建后的 Studio 资源包含 UI 修复，并通过资源引用校验。 | `npm --prefix frontend run build -- --mode development`; `npm --prefix frontend run test:webui-assets`; `git diff --check` | pass |

## 风险

仍需真实浏览器确认用户当前聊天视口下的实际展示效果。CSS 修改已限定在 Composer 模型选择器内；如果视觉验证发现额外的层级或裁切父容器，可继续小范围调整。
