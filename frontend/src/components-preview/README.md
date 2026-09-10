# Components Preview

独立组件库预览入口，不依赖后端，适用于火山引擎和 BytePlus 环境

## 启动

在 `frontend` 目录执行：

```sh
npm ci
npm run dev:components
```

打开 http://127.0.0.1:5186/components-preview/
此入口独立于 Studio 生产构建，不替换现有业务页面

## 内容与使用

组件实现在 `src/components/`，预览示例位于本目录的 `examples/`，示例直接使用真实组件

- 设计规范：颜色、字体、尺寸、间距、圆角和动效 Tokens
- 基础组件：Button、Tabs、Label、FormLabel、InputWithTailIcon、Textarea、Select、Switch、Checkbox、PillTag
- 复合组件：Sidebar、Item、卡片、Header、FormField、FormLabelRow、DashedZone、CodeBlock 和玻璃按钮组
- 布局：CardLayout、ModalLayout、ResourcePageLayout、DetailPageLayout
- 节点组件：BasicNode、AgentNode、CanvasBackground

Button、Tabs 和 Card 的变体集中展示，旧预览链接仍可访问
示例按 Figma 画布尺寸展示；示例数据和页面导航不属于组件 API
ModalLayout 提供 header、空白 body 插槽和 footer，实际遮罩与焦点管理由使用方提供
FormLabel 的 required 表示必填标记，表单控件需要同时设置原生 required 属性
Textarea 的 counter 为独立插槽，预览保留原稿计数

## 主题与动效

侧栏可切换明暗模式，默认浅色并保存选择，浅色基础背景为纯白
主题定义位于 `components/tokens/theme.css` 和 `component-themes.css`，通过根元素 `data-theme` 切换
深色以提供的 Figma 节点为基准，浅色为同风格适配，保留尺寸、字体和品牌资产
按钮、Tabs、Switch、Checkbox 和 Select 带轻量交互过渡，并支持减少动态效果偏好
Select 提供同宽矩形下拉面板，支持方向键、Enter、Escape、输入匹配和原生表单值

## 字体

预览包含 Geist Mono、JetBrains Mono 和 Noto Sans SC 示例字体，许可证位于 `fonts/`
布局资产中的 Didact Gothic 和 Fragment Mono 附带各自的 OFL 许可证
Century Gothic 不随仓库分发，优先使用本机已安装字体；拥有授权的用户可将 regular 和 bold 字体放到 `frontend/.local-fonts/gothic.woff` 与 `gothic-bold.ttf`
该本地目录已忽略，无这些字体时使用字体栈回退，文字度量可能与设计稿不同

## 设计说明

组件来源为提供的 Figma 设计；部分深色输入和表单颜色依据对应截图校准，因为设计变量返回浅色值
Switch 关闭状态沿用开启状态尺寸移动圆点；Checkbox 选中图标取自同一设计文件
玻璃按钮使用 CSS 透明背景、backdrop-filter 和边缘高光，独立 SVG 仅用于图标；CSS 对 Figma GLASS 折射效果为近似实现
ModalLayout 顶部光效和 CanvasBackground 点阵使用 CSS 实现
Select 展开样式、浅色主题与动效属于基于现有设计的交互扩展
