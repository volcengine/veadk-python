# IndexLayout

首页内容布局，参考 Figma `602:43991`，只包含右侧区域，不含产品 Sidebar

通过 `tabs`、`prompt`、`shortcuts` 插槽组合已有组件，推荐分别使用 GlassTabs、PromptInput 和三个 `variant="compact"` 的 Item

预览与 PromptInput 示例共享提示词列表，传入 `placeholders` 后复用组件的每 3 秒上滑和淡入淡出动画；输入文字时隐藏提示词，清空后恢复

桌面参考尺寸为 1200 × 900px，内容宽 720px，Prompt Input 高 150px，快捷入口间距为 16px；窄容器下内容自适应并将快捷入口排列成单列

`heading` 和 `logo` 可替换，布局不负责发送请求、模式数据或快捷入口的业务行为，由传入组件的回调处理

顶部光效使用设计稿中独立的装饰图片层 `602:43993`，保留其裁切比例；Logo 与快捷入口图标来自同一画板的原始 SVG，上传代码图标直接复用 Item 内置图标
