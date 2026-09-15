# Conversation Flow

AI APP 对话流，以 Figma `855:464885` 的折叠过程和 `758:325756` 的消息排版为视觉参考
使用现有明暗主题 Token，复用 Dropdown、Button、Loading、CodeBlock、Table、ScrollArea、ModalButton、Item、InfoCard 和 FileExplorer

用户消息靠右，模型回复靠左，界面不显示头像和发言者名称
同一条用户消息的 Markdown、文件、图片、视频与音频共用一个气泡，不拆成独立消息
消息容器复用固定高度 ScrollArea，默认 600px；组件与示例均不包含 PromptInput

## 用法

```tsx
import { ConversationFlow, type ConversationMessage } from "./components/ai-app";

const messages: ConversationMessage[] = [
  { id: "user-1", role: "user", content: "分析最近五天的调用量" },
  {
    id: "answer-1",
    role: "assistant",
    status: "complete",
    durationMs: 7200,
    ttftMs: 420,
    blocks: [
      { id: "reasoning-1", type: "reasoning", title: "分析过程", content: "读取调用统计并汇总", durationMs: 1200 },
      { id: "tool-1", type: "tool", title: "读取调用量", input: '{"days":5}', output: '{"total":797}' },
      { id: "text-1", type: "markdown", text: "最近五天共完成 **797 次调用**" },
    ],
  },
];

<ConversationFlow
  messages={messages}
  height={600}
  scrollAreaProps={{ "aria-label": "对话消息" }}
  onRetry={retry}
  onFeedback={saveFeedback}
  onStop={stop}
/>;
```

`messages` 与其中的 `blocks` 都按传入顺序展示，稳定的 id 用于保留展开状态
`blocks` 优先于兼容写法 `content` / `steps`；过程可独立折叠，工具的 Input / Output 可分别收起
运行状态、授权结果和反馈由调用方更新，组件不推断过程或请求后端
运行中的整体执行时间与每个步骤独立刷新，不依赖流式内容或新事件触发渲染；TTFT、token 数和模型名称仍由调用方提供

## 容器参数

| 参数 | 类型 | 默认值与行为 |
| --- | --- | --- |
| height | CSSProperties["height"] | 默认 600px；数字单位为 px，也可传入 CSS 长度 |
| scrollAreaProps | Omit<ScrollAreaProps, "children" \| "orientation" \| "ref"> | 配置内部 ScrollArea，例如 onScroll、aria-label、hasMore、onLoadMore；固定纵向滚动 |
| messages | readonly ConversationMessage[] | 按传入顺序显示；用户靠右，模型靠左 |

`scrollAreaProps.onLoadMore` 沿用 ScrollArea 的触底加载行为，收到 AbortSignal 后由调用方加载和追加消息
`name` 保留为消息的无障碍名称，不在界面中显示；消息 API 不提供 avatar

## 内容类型

| type | 内容 |
| --- | --- |
| markdown | 安全 Markdown、GFM 表格、高亮代码、ECharts / Mermaid 代码块 |
| reasoning | 可折叠思考或执行摘要 |
| tool | 可折叠输入、输出、错误和自定义结果组件 |
| handoff | 子智能体移交关系、耗时及嵌套步骤 |
| plan | 按需提供执行计划及状态，当前预览示例未启用 |
| visualization | 图表与源码切换、放大查看，Mermaid 可缩放 |
| media | 图片、视频与音频直接展示；图片可放大，视频音频提供原生播放控制条 |
| files | 文件名、说明、预览与下载回调 |
| authorization | 授权请求、继续、取消与受控执行状态 |
| custom | A2UI 交互卡片、项目交付、领域内容 |

所有消息支持 user / assistant / system
assistant 支持 startedAt、endedAt、durationMs、ttftMs、tokens、model、error、feedback 和任意 React actions
复制默认取 Markdown 原文，可用 copyText 覆盖；actions 为 null 时隐藏内置操作
未传 onRetry / onFeedback / onStop 时不显示对应按钮

## 实时计时

assistant 消息及 reasoning、tool、handoff 步骤共用下列计时字段，嵌套步骤各自计时

| 字段 | 单位 | 行为 |
| --- | --- | --- |
| startedAt | Unix 时间戳，毫秒 | 执行开始时间，running 时持续显示当前时间与 startedAt 的差值 |
| endedAt | Unix 时间戳，毫秒 | 执行结束时间，提供后固定耗时，不继续递增 |
| durationMs | 毫秒 | 完成、失败或取消后的最终耗时优先；运行中无 startedAt 时，作为首次观察到的已耗时基准继续计时 |
| ttftMs | 毫秒 | 仅 assistant 支持，由业务记录首个 token 耗时，不随执行时间递增 |

运行开始时传入 `startedAt: Date.now()`，后续事件只需更新内容和状态，不必重复计算 durationMs
如果未传 startedAt，组件从首次观察到 running 的时间开始累计，并使用可用的 durationMs 作为起始耗时
状态转为 complete、error 或 cancelled 后立即冻结，最终 durationMs 优先，其次使用 startedAt 与 endedAt，未提供结束值时保留停止时的累计耗时
同一 id 重试时传入新的 startedAt，并清除上次 endedAt 与 durationMs，防止上一轮结束数据覆盖新一轮时钟
历史消息若既没有最终耗时，也没有可用的开始与结束时间，则不补造耗时

完整分析示例在工具和移交阶段保留无内容事件的等待时间，执行时间仍持续更新；完成与取消时记录实际 endedAt

## Studio 数据接入

`fromStudioTurns(turns, options)` 将现有 `src/blocks.ts` 的全部消息种类映射成 ConversationMessage
不改变现有事件协议，也不包含火山引擎或 BytePlus 的专用网络配置
工具、思考、移交、计划、附件、产物、交付、技能调用、授权、A2UI 均保留发生顺序
图片、视频与音频附件直接转换为 media 内容块，普通文件保留 files 展示；同组混合附件保持输入顺序

options 提供授权、A2UI action、附件与产物预览/下载、项目下载与部署回调
`resolveArtifactMedia(file, turn)` 可返回已取得的产物 `src` 与可选 `kind / mimeType / alt / poster / caption`，将模型生成的图片、视频与音频直接展示；未提供类型时按文件扩展名识别
Studio 原始 artifact 只有文件名和版本，未解析到地址时保留文件预览与下载入口，不推断不存在的资源地址
`renderBlock(block, turn)` 可覆盖领域内容：返回 undefined 使用默认组件，null 隐藏，其他 React 内容按原位显示
若服务未提供稳定消息标识，适配器以列表序号生成回退标识；需要插入或重排历史时，应先补充 `meta.localId`

`ConversationSurface` 接收 `buildSurfaces` 生成的 SurfaceState
当前目录的 Text / Icon / Row / Column / Card / Divider / Button 通过组件库样式渲染，未实现的节点提供源码回退
未传 onAction 时禁用交互按钮，消息内容不能自行执行网络请求

## 富内容与状态

ConversationMarkdown、ConversationVisualization 与 ConversationMedia 也可单独使用
图表外层复用 InfoCard，标题行 actions 放置展开按钮，InfoCardBody 承载标签页、图表和源码
ECharts 复用 Studio 的安全配置解析器，拒绝可执行函数、原型键和外部资源配置
Mermaid 使用 strict 模式；Markdown 不解析原始 HTML
生成中的不完整图表显示源码和 Infinity Path，源码完成后再渲染
切换主题时更新图表颜色；切换源码或卸载时释放实例和监听器
错误在当前图表内展示，保留源码用于查看

`media` 字段为 `id / type: "media" / kind: "image" | "video" | "audio" / src`
可选 `alt / name / poster / caption`，`poster` 用于视频封面，`caption` 为媒体下方说明
`onPreview / onDownload` 保留附件原始回调；图片放大复用 ModalButton，加载失败复用 ErrorState
视频与音频不自动播放，只预加载元数据；媒体宽度随消息区域收缩，不撑出对话流
`src` 允许相对路径、HTTP(S)、Blob 与对应媒体类型的安全 data URL，不接受脚本 URL 或内联 SVG

预览提供完整分析、富内容、多模态输入、多模态回复、授权与错误五个场景，使用固定高度消息滚动区域，不附带输入框或执行计划示例
参数与数据字段表位于示例下方
