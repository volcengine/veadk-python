export type StudioTokenCategory = "color" | "typography" | "size" | "radius" | "spacing" | "motion";
export type StudioToken = {
  name: string;
  label: string;
  category: StudioTokenCategory;
  value?: string;
  dark?: string;
  light?: string;
};

export const studioTokens: readonly StudioToken[] = [
  {
    "name": "--studio-bg-canvas",
    "label": "画布背景",
    "dark": "#101013",
    "light": "#f8f9fb",
    "category": "color"
  },
  {
    "name": "--studio-bg-panel",
    "label": "卡片背景",
    "dark": "#111111",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-bg-elevated",
    "label": "输入与浮层背景",
    "dark": "#1c1c1e",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-bg-sidebar",
    "label": "侧栏背景",
    "dark": "#18181b",
    "light": "#f3f4f7",
    "category": "color"
  },
  {
    "name": "--studio-bg-track",
    "label": "分段控件轨道",
    "dark": "#0c0c0d",
    "light": "#eceff4",
    "category": "color"
  },
  {
    "name": "--studio-bg-secondary",
    "label": "次级按钮背景",
    "dark": "#262626",
    "light": "#edf0f5",
    "category": "color"
  },
  {
    "name": "--studio-bg-promo",
    "label": "广告卡片背景",
    "dark": "#030303",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-text-primary",
    "label": "主要文字",
    "dark": "#dbdee7",
    "light": "#252934",
    "category": "color"
  },
  {
    "name": "--studio-text-secondary",
    "label": "次要文字",
    "dark": "rgba(219, 222, 231, 0.6)",
    "light": "#596171",
    "category": "color"
  },
  {
    "name": "--studio-text-tertiary",
    "label": "辅助文字",
    "dark": "#7a7880",
    "light": "#646d7c",
    "category": "color"
  },
  {
    "name": "--studio-text-strong",
    "label": "强调文字",
    "dark": "#ffffff",
    "light": "#171b24",
    "category": "color"
  },
  {
    "name": "--studio-text-subtle",
    "label": "柔和文字",
    "dark": "#b8b7c3",
    "light": "#58606f",
    "category": "color"
  },
  {
    "name": "--studio-action-primary-bg",
    "label": "主要操作背景",
    "dark": "#ffffff",
    "light": "#282d3a",
    "category": "color"
  },
  {
    "name": "--studio-action-primary-text",
    "label": "主要操作文字",
    "dark": "#101013",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-border-default",
    "label": "常规边框",
    "dark": "rgba(255, 255, 255, 0.2)",
    "light": "#d8dde6",
    "category": "color"
  },
  {
    "name": "--studio-border-subtle",
    "label": "弱边框",
    "dark": "rgba(219, 222, 231, 0.15)",
    "light": "#e3e7ee",
    "category": "color"
  },
  {
    "name": "--studio-border-input",
    "label": "输入框边框",
    "dark": "rgba(219, 222, 231, 0.21)",
    "light": "#cbd2de",
    "category": "color"
  },
  {
    "name": "--studio-fill-subtle",
    "label": "弱填充",
    "dark": "rgba(219, 222, 231, 0.05)",
    "light": "rgba(66, 84, 122, 0.035)",
    "category": "color"
  },
  {
    "name": "--studio-fill-hover",
    "label": "悬停填充",
    "dark": "rgba(255, 255, 255, 0.06)",
    "light": "rgba(66, 84, 122, 0.065)",
    "category": "color"
  },
  {
    "name": "--studio-fill-selected",
    "label": "选中填充",
    "dark": "rgba(170, 163, 225, 0.1)",
    "light": "rgba(85, 99, 149, 0.1)",
    "category": "color"
  },
  {
    "name": "--studio-focus-ring",
    "label": "键盘焦点",
    "dark": "#ffffff",
    "light": "#626c8a",
    "category": "color"
  },
  {
    "name": "--studio-warning",
    "label": "警告文字",
    "dark": "#dd6800",
    "light": "#a75008",
    "category": "color"
  },
  {
    "name": "--studio-success",
    "label": "成功状态",
    "dark": "#8cdbab",
    "light": "#287b49",
    "category": "color"
  },
  {
    "name": "--studio-danger",
    "label": "错误状态",
    "dark": "#ed9696",
    "light": "#b34444",
    "category": "color"
  },
  {
    "name": "--studio-scrollbar-thumb",
    "label": "滚动条滑块",
    "dark": "rgba(219, 222, 231, .22)",
    "light": "rgba(63, 78, 106, .24)",
    "category": "color"
  },
  {
    "name": "--studio-scrollbar-thumb-hover",
    "label": "滚动条滑块悬停",
    "dark": "rgba(219, 222, 231, .38)",
    "light": "rgba(63, 78, 106, .4)",
    "category": "color"
  },
  {
    "name": "--studio-surface-input",
    "label": "输入控件表面",
    "dark": "#111112",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-text-input",
    "label": "输入内容",
    "dark": "#c2c5cc",
    "light": "#252934",
    "category": "color"
  },
  {
    "name": "--studio-text-preview",
    "label": "预览说明",
    "dark": "#a1a1aa",
    "light": "#596171",
    "category": "color"
  },
  {
    "name": "--studio-text-counter",
    "label": "字数提示",
    "dark": "#737a87",
    "light": "#646d7c",
    "category": "color"
  },
  {
    "name": "--studio-text-muted",
    "label": "弱化辅助文字",
    "dark": "rgba(219,222,231,.4)",
    "light": "#646d7c",
    "category": "color"
  },
  {
    "name": "--studio-text-dim",
    "label": "次要标签",
    "dark": "rgba(219,222,231,.5)",
    "light": "#596171",
    "category": "color"
  },
  {
    "name": "--studio-text-count",
    "label": "数量标签",
    "dark": "rgba(255,255,255,.6)",
    "light": "#596171",
    "category": "color"
  },
  {
    "name": "--studio-surface-page",
    "label": "页面底色",
    "dark": "#0c0c0c",
    "light": "#f8f9fb",
    "category": "color"
  },
  {
    "name": "--studio-surface-modal",
    "label": "弹窗表面",
    "dark": "#1a1a1d",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-surface-metric",
    "label": "信息卡片表面",
    "dark": "rgba(32,33,36,.39)",
    "light": "#f1f3f7",
    "category": "color"
  },
  {
    "name": "--studio-surface-node",
    "label": "节点表面",
    "dark": "rgba(38,38,46,.37)",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-surface-node-selected",
    "label": "选中节点表面",
    "dark": "rgba(38,38,46,.45)",
    "light": "#f6f7fc",
    "category": "color"
  },
  {
    "name": "--studio-surface-node-body",
    "label": "节点内容表面",
    "dark": "rgba(37,37,42,.48)",
    "light": "#f7f8fb",
    "category": "color"
  },
  {
    "name": "--studio-surface-node-body-selected",
    "label": "选中节点内容",
    "dark": "rgba(69,70,83,.29)",
    "light": "#edf0f8",
    "category": "color"
  },
  {
    "name": "--studio-surface-count",
    "label": "数量标签表面",
    "dark": "rgba(17,17,17,.54)",
    "light": "#e9edf3",
    "category": "color"
  },
  {
    "name": "--studio-surface-dashed",
    "label": "虚线区域表面",
    "dark": "rgba(255,255,255,.03)",
    "light": "#fdfdfe",
    "category": "color"
  },
  {
    "name": "--studio-border-dashed",
    "label": "虚线边框",
    "dark": "rgba(255,255,255,.15)",
    "light": "#cbd2de",
    "category": "color"
  },
  {
    "name": "--studio-border-control",
    "label": "选择控件边框",
    "dark": "rgba(219,222,231,.2)",
    "light": "#bcc5d3",
    "category": "color"
  },
  {
    "name": "--studio-border-emphasis",
    "label": "强调边框",
    "dark": "rgba(219,222,231,.7)",
    "light": "#69738b",
    "category": "color"
  },
  {
    "name": "--studio-surface-checkbox",
    "label": "选择控件表面",
    "dark": "rgba(17,17,18,.7)",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-surface-status",
    "label": "状态标签表面",
    "dark": "rgba(235,235,245,.1)",
    "light": "#ecf0f5",
    "category": "color"
  },
  {
    "name": "--studio-surface-item",
    "label": "列表项表面",
    "dark": "rgba(229,229,229,.06)",
    "light": "#ffffff",
    "category": "color"
  },
  {
    "name": "--studio-surface-item-icon",
    "label": "列表项图标底色",
    "dark": "rgba(0,0,0,.31)",
    "light": "#edf0f5",
    "category": "color"
  },
  {
    "name": "--studio-surface-glass-group",
    "label": "玻璃按钮组表面",
    "dark": "rgba(28,28,30,.2)",
    "light": "rgba(255, 255, 255, .82)",
    "category": "color"
  },
  {
    "name": "--studio-surface-glass-button",
    "label": "玻璃按钮表面",
    "dark": "rgba(45,45,45,.2)",
    "light": "rgba(255, 255, 255, .88)",
    "category": "color"
  },
  {
    "name": "--studio-surface-sidebar-overlay",
    "label": "侧栏叠加表面",
    "dark": "rgba(255,255,255,.02)",
    "light": "#f3f4f7",
    "category": "color"
  },
  {
    "name": "--studio-surface-update",
    "label": "更新按钮表面",
    "dark": "rgba(255,255,255,.25)",
    "light": "rgba(46, 57, 78, .09)",
    "category": "color"
  },
  {
    "name": "--studio-code-text",
    "label": "代码正文",
    "dark": "#abb2bf",
    "light": "#343b4a",
    "category": "color"
  },
  {
    "name": "--studio-code-line-number",
    "label": "代码行号",
    "dark": "#5c6370",
    "light": "#6b7584",
    "category": "color"
  },
  {
    "name": "--studio-code-comment",
    "label": "代码注释",
    "dark": "#7f848e",
    "light": "#6b7584",
    "category": "color"
  },
  {
    "name": "--studio-code-keyword",
    "label": "代码关键字",
    "dark": "#c678dd",
    "light": "#87529c",
    "category": "color"
  },
  {
    "name": "--studio-code-string",
    "label": "代码字符串",
    "dark": "#98c379",
    "light": "#42714a",
    "category": "color"
  },
  {
    "name": "--studio-code-function",
    "label": "代码函数",
    "dark": "#61afef",
    "light": "#2f6393",
    "category": "color"
  },
  {
    "name": "--studio-code-number",
    "label": "代码数字",
    "dark": "#d19a66",
    "light": "#a2582e",
    "category": "color"
  },
  {
    "name": "--studio-code-variable",
    "label": "代码变量",
    "dark": "#e06c75",
    "light": "#a64f63",
    "category": "color"
  },
  {
    "name": "--studio-code-constant",
    "label": "代码常量",
    "dark": "#e5c07b",
    "light": "#90621e",
    "category": "color"
  },
  {
    "name": "--studio-action-hover",
    "label": "主按钮悬停",
    "dark": "#e9e9ec",
    "light": "#3a4152",
    "category": "color"
  },
  {
    "name": "--studio-action-active",
    "label": "主按钮按下",
    "dark": "#dbdee7",
    "light": "#1b202c",
    "category": "color"
  },
  {
    "name": "--studio-secondary-hover",
    "label": "次级按钮悬停",
    "dark": "#323234",
    "light": "#e3e8f0",
    "category": "color"
  },
  {
    "name": "--studio-secondary-active",
    "label": "次级按钮按下",
    "dark": "#3b3b3e",
    "light": "#d8dfeb",
    "category": "color"
  },
  {
    "name": "--studio-font-family-ui",
    "label": "界面字体",
    "value": "\"Century Gothic\", sans-serif",
    "category": "typography"
  },
  {
    "name": "--studio-font-family-code",
    "label": "代码字体",
    "value": "\"JetBrains Mono\", monospace",
    "category": "typography"
  },
  {
    "name": "--studio-font-size-xs",
    "label": "辅助字号",
    "value": "12px",
    "category": "typography"
  },
  {
    "name": "--studio-font-size-sm",
    "label": "紧凑字号",
    "value": "13px",
    "category": "typography"
  },
  {
    "name": "--studio-font-size-md",
    "label": "正文字号",
    "value": "14px",
    "category": "typography"
  },
  {
    "name": "--studio-font-size-lg",
    "label": "卡片标题",
    "value": "16px",
    "category": "typography"
  },
  {
    "name": "--studio-font-size-xl",
    "label": "预览标题",
    "value": "20px",
    "category": "typography"
  },
  {
    "name": "--studio-font-size-2xl",
    "label": "页面标题",
    "value": "24px",
    "category": "typography"
  },
  {
    "name": "--studio-line-height-xs",
    "label": "辅助行高",
    "value": "18px",
    "category": "typography"
  },
  {
    "name": "--studio-line-height-sm",
    "label": "紧凑行高",
    "value": "20px",
    "category": "typography"
  },
  {
    "name": "--studio-line-height-md",
    "label": "正文行高",
    "value": "22px",
    "category": "typography"
  },
  {
    "name": "--studio-line-height-lg",
    "label": "卡片标题行高",
    "value": "24px",
    "category": "typography"
  },
  {
    "name": "--studio-font-weight-regular",
    "label": "常规字重",
    "value": "400",
    "category": "typography"
  },
  {
    "name": "--studio-font-weight-bold",
    "label": "加粗字重",
    "value": "700",
    "category": "typography"
  },
  {
    "name": "--studio-size-icon-xs",
    "label": "小图标",
    "value": "10px",
    "category": "size"
  },
  {
    "name": "--studio-size-icon-sm",
    "label": "紧凑图标",
    "value": "14px",
    "category": "size"
  },
  {
    "name": "--studio-size-icon-md",
    "label": "标准图标",
    "value": "16px",
    "category": "size"
  },
  {
    "name": "--studio-size-icon-lg",
    "label": "大图标",
    "value": "20px",
    "category": "size"
  },
  {
    "name": "--studio-size-control-xs",
    "label": "标签高度",
    "value": "26px",
    "category": "size"
  },
  {
    "name": "--studio-size-control-sm",
    "label": "紧凑控件高度",
    "value": "32px",
    "category": "size"
  },
  {
    "name": "--studio-size-control-md",
    "label": "标准控件高度",
    "value": "36px",
    "category": "size"
  },
  {
    "name": "--studio-size-control-lg",
    "label": "大控件高度",
    "value": "40px",
    "category": "size"
  },
  {
    "name": "--studio-size-sidebar",
    "label": "侧栏宽度",
    "value": "240px",
    "category": "size"
  },
  {
    "name": "--studio-size-resource-card",
    "label": "资源卡片宽度",
    "value": "336px",
    "category": "size"
  },
  {
    "name": "--studio-radius-sm",
    "label": "小圆角",
    "value": "6px",
    "category": "radius"
  },
  {
    "name": "--studio-radius-md",
    "label": "控件圆角",
    "value": "8px",
    "category": "radius"
  },
  {
    "name": "--studio-radius-lg",
    "label": "中圆角",
    "value": "12px",
    "category": "radius"
  },
  {
    "name": "--studio-radius-xl",
    "label": "卡片圆角",
    "value": "16px",
    "category": "radius"
  },
  {
    "name": "--studio-radius-2xl",
    "label": "大圆角",
    "value": "20px",
    "category": "radius"
  },
  {
    "name": "--studio-radius-pill",
    "label": "胶囊圆角",
    "value": "999px",
    "category": "radius"
  },
  {
    "name": "--studio-space-1",
    "label": "最小间距",
    "value": "2px",
    "category": "spacing"
  },
  {
    "name": "--studio-space-2",
    "label": "紧密间距",
    "value": "4px",
    "category": "spacing"
  },
  {
    "name": "--studio-space-3",
    "label": "小间距",
    "value": "8px",
    "category": "spacing"
  },
  {
    "name": "--studio-space-4",
    "label": "控件间距",
    "value": "12px",
    "category": "spacing"
  },
  {
    "name": "--studio-space-5",
    "label": "组件间距",
    "value": "16px",
    "category": "spacing"
  },
  {
    "name": "--studio-space-6",
    "label": "区域内间距",
    "value": "20px",
    "category": "spacing"
  },
  {
    "name": "--studio-space-7",
    "label": "分组间距",
    "value": "24px",
    "category": "spacing"
  },
  {
    "name": "--studio-space-8",
    "label": "区域间距",
    "value": "32px",
    "category": "spacing"
  },
  {
    "name": "--studio-motion-duration-fast",
    "label": "即时反馈",
    "value": "140ms",
    "category": "motion"
  },
  {
    "name": "--studio-motion-duration-normal",
    "label": "状态切换",
    "value": "160ms",
    "category": "motion"
  },
  {
    "name": "--studio-motion-duration-slow",
    "label": "区域展开",
    "value": "240ms",
    "category": "motion"
  },
  {
    "name": "--studio-motion-easing-standard",
    "label": "标准曲线",
    "value": "cubic-bezier(0.2, 0, 0, 1)",
    "category": "motion"
  },
  {
    "name": "--studio-motion-easing-enter",
    "label": "进入曲线",
    "value": "cubic-bezier(0, 0, 0.2, 1)",
    "category": "motion"
  }
];

export const studioTokenGroups: readonly { category: StudioTokenCategory; label: string; description: string }[] = [
  { category: "color", label: "颜色", description: "深色保留 Figma 数值，浅色以冷灰底色、白色表面和清晰文字建立层次，色块跟随当前主题" },
  { category: "typography", label: "字体", description: "界面字体、字号、行高与字重" },
  { category: "size", label: "尺寸", description: "图标、控件与布局的基础尺寸" },
  { category: "radius", label: "圆角", description: "从紧凑控件到卡片和胶囊" },
  { category: "spacing", label: "间距", description: "内容、组件和区域之间的距离" },
  { category: "motion", label: "动效", description: "用于反馈与状态切换，减少动态效果时关闭过渡" },
];
