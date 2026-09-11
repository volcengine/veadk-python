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

侧栏可切换明暗模式，默认浅色并保存选择，浅色页面背景为微紫灰 #f8f7fb，侧栏为 #f3f2f7，卡片与输入框保留白色
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

## AI APP

PromptInput（602:44016）为 720 × 150，使用 Didact Gothic、20px 圆角及 CSS 玻璃发送按钮，图标来自原稿 SVG
支持受控和非受控输入、发送回调、禁用及 sending 状态，发送由按钮触发，文本框保留原生换行行为

Item 合集增加 compact 变体（602:44003），尺寸 229.33 × 68，图标 22px，渐变描边透明度 26% → 13%
Tabs 合集增加 GlassTabs（607:220149），原稿双选项尺寸 196 × 36，使用独立样式，支持键盘导航与平滑指示器

SingleLinePromptInput（779:366073）为 652 × 56，92px 圆角，无外框描边和阴影；Century Gothic 16px / 26px，36px 渐变描边发送按钮，20px 原稿箭头

基础组件增加 Divider（855:464899）：397px 宽、0.5px 线条，白色 20% 透明度，中段均匀、两端渐隐
Dropdown（855:464896）为 394 × 28，支持点击及键盘激活展开/收起，160ms 过渡和减少动态效果偏好；children 为内容插槽，预览使用空白区域

Label 增加可关闭变体（788:392375），GitHub 示例 97 × 26，16px 图标与关闭按钮，支持 onDismiss 回调

## 参数表

各组件示例下方提供参数、类型、必填项、默认值和说明，原生属性可展开查看
参数类型与解构默认值由独立预览的 Vite 插件读取 TypeScript 源码，修改组件接口后自动刷新；说明优先使用参数文档注释
Textarea 支持 maxHeight（数字单位 px 或 CSS 长度），限制外框拖动高度，示例为 240px；默认不限制，初始最小高度为 80px

## 滚动、表格与加载

ScrollArea 支持纵向、横向和双向滚动，滚动条随鼠标移入淡入、移出淡出，键盘聚焦时显示，也可通过 hideScrollbar 始终隐藏；预览提供纵向加载与横向滚动示例
通过 hasMore、onLoadMore 和 threshold 开启触底加载；包含加载状态、失败重试、重复请求保护和卸载取消
LoadMoreArea 复用 ScrollArea 的加载逻辑，资源卡片示例初始 6 张、每批追加 6 张
Tabs 复用横向 ScrollArea，隐藏滚动条，保持文字单行；网站侧栏和预览区仅纵向滚动
Table 使用语义化表格，支持列宽、对齐、自定义单元格、空数据内容及窄容器横向滚动；TableStatus 提供 Pass / Fail 图标和文案
浅色主题使用轻微带紫灰色相的中性色；Card、Item 和 DashedZone 提供轻量 hover 过渡
原生滚动回弹由浏览器和操作系统控制，组件不模拟橡皮筋动画

Table 的 overflow 列配置支持 wrap（自动换行并撑高行）或 ellipsis（单行省略），layout=fixed 可保持列宽稳定，layout=auto 由内容参与分配列宽
minWidth 设定横向滚动阈值，maxHeight 限制纵向视口，stickyHeader 控制列标题固定，hideScrollbar 控制滚动条可见性
TableCellText 提供 title + description，truncate 控制标题单行省略，descriptionLines 控制说明最大行数；纯文本省略时保留原生全文提示
Table 的 toolbarStart / toolbarEnd 放置搜索和主操作，两端对齐并位于滚动区外，搜索和按钮行为由调用方提供
列配置 fixed=left / right 可冻结任意列，冻结列偏移按实际列宽计算并随容器变化更新，能与固定表头组合使用
Table 复用 ScrollArea 的横向、双向滚动和滚动条效果，示例固定首列与 Actions 列
列配置 sort 接收 direction（asc / desc / null）和 onChange，filter 接收 value、options 和 onChange；表头复用 Button 与 Select，筛选与排序数据由调用方管理，独立示例演示两者组合
Button 的 iconOnly 提供纯图标按钮，可组合 primary、secondary、ghost 样式，使用 startIcon 和 aria-label；Table 操作列直接复用，不另写按钮样式
Button 的 link 样式支持 endIcon，图标随字号缩放；悬停或键盘聚焦时文字下方虚线与右侧图标同时淡入，移开淡出，并保留图标占位，示例使用 ExternalLinkIcon
InputWithHeaderIcon 复用 InputWithTailIcon 的原生输入逻辑，前置图标可替换或绑定点击回调
SidebarItemWithIcon 的长标题默认尾部渐隐，悬停后缓慢滚到末尾、移开复位；trailing / hoverTrailing 支持尾部图标或按钮组切换，标题宽度自动适配
Radio 按 Figma 740:296852 内的单选控件实现，16 × 16px，未选中白色圆底，选中深色圆底与 6px 白点；使用原生单选输入，同 name 互斥，支持可选标签与受控值
FormField 的 tip 显示控件下方输入规则，error 优先替换为红色提示，并为对应输入框或文本域显示红边；htmlFor 与控件 id 关联标签和描述，校验规则由调用方负责
