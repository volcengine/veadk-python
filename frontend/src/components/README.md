# Studio 组件库

统一供火山引擎和 BytePlus Studio 使用的 React 组件

## 目录

- `tokens/`：从 Figma 提取的颜色、字体、尺寸、间距等样式定义
- `icons/`：Figma 图标资产及 React 图标组件
- `primitives/`：Button、Input 等原子组件
- `composites/`：卡片、搜索栏等组合组件
- `layouts/`：页面框架、侧边栏和分栏等布局组件
- `index.ts`：统一导出入口

## 实现约定

- Figma 是视觉依据，逐项复现尺寸、颜色、字体、图标、间距和状态
- 未提供的设计信息先确认，不预设样式数值或自行补充设计
- 每个组件使用独立目录，组件、样式与组件导出放在一起
- 组件通过 Props 接收内容和状态，业务请求留在功能页面
- 两个云环境共用组件，品牌差异由明确的配置传入
- 预览示例放在 `../components-preview/examples/`，直接引用这里的组件

已实现的组件及 Figma 示例见 Components Preview，Tabs 统一归入基础组件

- `nodes/`：画布节点组件，包含普通节点和Agent节点的默认、选中状态
