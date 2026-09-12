# Studio 工具活动组件契约

- **组件 ID：** `studio-tool-activity`
- **状态：** active
- **修订日期：** 2026-09-12
- **英文版本：** [README.md](README.md)
- **关联 PRD：** [Studio 工具活动可视化设计](../../prd-spec/features/studio-tool-activity-visualization/2026-09-12-studio-tool-activity-visualization-design.zh.md)
- **负责实现：** `frontend/src/blocks.ts`、`frontend/src/ui/Blocks.tsx` 和 `frontend/src/ui/tool-activity/`
- **主要测试：** `frontend/tests/toolActivityModel.test.mjs`、`frontend/tests/toolBlockDefaultOpen.test.mjs` 和 `frontend/tests/codexSandboxProgress.test.mjs`

## 1. 责任

本组件将 ADK function call、function response 和 Codex sandbox progress 转换成 Studio transcript 中有界、可访问的工具活动单元。它负责展示归一化、生命周期关联、安全只读聚合、自适应展开、输出预览和脱敏后的原始数据查看。

它不负责事件传输、Runtime 执行、session 持久化、后端脱敏、授权流程或最终回答生成。已有专用工具 renderer 继续负责自身领域内容。

## 2. 入口与依赖

- `frontend/src/blocks.ts` 中的 `applyEvent()` 和 `eventsToTurns()` 负责实时与历史事件投影。
- `flattenCodexActivityBlocks()` 从嵌套 Codex activity 派生只用于展示的扁平视图，不修改源 blocks。
- `presentToolActivity()` 将工具 block 转换为 `ToolPresentation`。
- `ToolActivityCard` 渲染一个普通活动。
- `ToolExplorationGroup` 渲染一组符合条件的成功只读活动。
- `Blocks` 将普通工具分发给本组件，并保留已有专用 renderer。

组件依赖现有 ADK 事件类型、i18n `conversation` namespace、Studio 语义 CSS 变量和仓库自有 SVG 图标；不新增运行时依赖或服务端契约。

## 3. 契约

### `CON-1` — 保留源数据的展示派生

展示由源 `Block` 派生。聚合和沙箱扁平化不得修改源 block 的顺序或数据。原始 `args` 和 `response` 只能通过有界、脱敏的二级入口访问。

### `CON-2` — 稳定生命周期关联

相同非空 `callId` 的事件表示一个逻辑活动，包括 `exec_command` 与 `commandExecution` 等已知命令别名。partial function response 只更新输出并保持 running；terminal response 才完成或标记失败。同名并发调用没有匹配 ID 时禁止合并。

一个 projector 内重复 event ID 必须忽略，跟踪上限为 2,048 个 ID。先于 call 到达的 result 必须保持可见，并在后续匹配 call 到达时合并。

### `CON-3` — 状态与展开状态

合法状态为 `queued`、`running`、`completed`、`failed`。running 默认展开，completed 默认折叠，failed 默认展开。用户手动切换后，后续生命周期更新不得覆盖用户选择。展开状态只属于本地 UI，不持久化。

### `CON-4` — 类型化展示与通用回退

长期支持的类别为 `command`、`read`、`search`、`file-change`、`mcp`、`authorization`、`generic`。未知或异常工具必须通过 `generic` 保持可见，presenter 异常不得破坏 transcript。已有注册详情 renderer 继续使用专用内容，普通内置工具保留已有本地化动作标题。

### `CON-5` — Sandbox 扁平化

当 `delegate_to_codex_sandbox` 存在结构化子活动时，子 block 在当前 transcript 层级展示，并使用一个轻量 `Codex Sandbox` 来源标记。没有子活动时保留外层工具卡。最终回答保持在工具活动序列之外。

### `CON-6` — 安全探索聚合

只有同来源、相邻、已完成且成功的 `read` 和 `search` 活动可形成探索分组。命令、文件变更、MCP、授权、失败、运行中活动、来源变化、非工具 block 和最终文本都会终止分组。子项保持原顺序并可分别查看。

### `CON-7` — 有界输出

可见文本必须移除 ANSI CSI/OSC、危险控制字符和疑似凭证值。多行输出预览保留前 5 行和后 5 行，并显示省略行数。单行超长输出最多保留前 8,000 和后 8,000 个字符，并显示省略字符数。详情区域独立滚动，不得造成页面级横向溢出。

### `CON-8` — 原始数据安全

原始数据默认关闭，只在展开后格式化。显示或复制前必须遮罩敏感字段名和字符串内的凭证模式。遍历上限为深度 8、每个集合 50 项、总节点 500 个、单字符串 4,000 字符。循环引用显示 `[circular]`，超过上限显示 `[truncated]`。剪贴板失败必须可见，且不得使 transcript 抛错。

### `CON-9` — 历史兼容

`eventsToTurns()` 继续作为历史重建权威入口。实时与历史事件共享 `applyEvent()` 生命周期逻辑。仅持久化 `functionCall + functionResponse` 时也必须能恢复活动，并继续兼容 camelCase 与 snake_case；缺少 progress 时降级为通用活动。

若 A2A 虚拟 session 只持久化最终文本，则无法恢复临时工具过程；Studio 必须保留最终回答且禁止伪造缺失历史。这是传输持久化限制，不代表允许重新提交任务。

### `CON-10` — 无障碍与响应式

交互式折叠使用原生 button、`aria-expanded`、清晰焦点、文字状态和至少 44px 有效点击区。折叠内容必须 `aria-hidden` 且 inert。窄屏优先隐藏次要摘要，不隐藏标题或状态。动效必须有界，并在 `prefers-reduced-motion` 下关闭。

## 4. 状态与并发

```text
queued -> running -> completed
                  -> failed
```

running 状态允许重复输出 delta。terminal 事件拥有最终状态和权威输出。并发活动按 `callId` 隔离；projector 状态按 active assistant turn 和 session 隔离。session 切换只能重建或选择该 session 自己的 turns，不得共享组件本地展开状态。

## 5. 安全与隔离

工具 payload 是不可信展示数据。组件不得使用原始 HTML 注入。它必须延续后端 allowlist，并在渲染和复制前额外进行基于值的遮罩。不得暴露 Authorization、cookie、password、access key、secret key、token、签名查询凭证或不受限制的环境变量 payload。

## 6. 兼容与演进

- 继续支持 camelCase 与 snake_case 事件字段。
- 新工具类别必须保留 generic fallback，并补中英文标签和 presenter 测试。
- 新增合并别名必须通过生命周期测试证明无歧义。
- 改变持久化或增加可续传工具历史属于独立的 transport/session 契约变更，不属于本组件。

## 7. 失败与诊断

- 异常值回退为可读通用内容和有界原始数据。
- 无法匹配的 response 保持可见，不得丢弃。
- 剪贴板失败显示本地化反馈。
- 本组件不独立发起网络请求、重试、指标或日志；沿用现有 Studio stream 和浏览器诊断面。

## 8. 验证

| 契约 | 验证 | 证据 |
| --- | --- | --- |
| `CON-1`–`CON-9` | `npm --prefix frontend test` | 模型、生命周期、Codex、历史和现有 transcript 回归套件 |
| `CON-10` | 组件 DOM 测试及正常/窄屏真实浏览器检查 | 活动折叠/状态 DOM 与截图 |
| 构建资产 | `npm --prefix frontend run build` 和 `npm --prefix frontend run test:webui-assets` | 生成的 `veadk/webui` 引用完整 |
| 双语标签 | `npm --prefix frontend run check:i18n` | locale namespace 等价 |

## 9. 变更记录

- **2026-09-12：** 由已批准的 Studio 工具活动可视化 PRD 首次建立契约。初始实现覆盖统一工具卡、命令生命周期关联、沙箱扁平化、只读聚合、有界输出、原始数据脱敏和历史安全回退。
- **2026-09-12：** 非终态 A2A `submitted` 和不含消息的 `working` 更新会作为仅含 metadata 的 heartbeat 转发，用于解除首事件截止时间，但不创建 transcript block、不结束 turn，也不重新提交请求。
- **2026-09-12：** 标记为 `adk_thought` 的 A2A 文本 part 投影为 Studio thinking 事件；reasoning 与答案的累计 delta 状态相互隔离，避免一条流抑制或污染另一条流。
- **2026-09-12：** A2A 流在已有答案增量但没有显式最终文本时结束，桥接会将累计答案作为一个完成态 Studio 事件输出一次；纯 reasoning 流仍保持未完成。
