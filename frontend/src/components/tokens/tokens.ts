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
    "light": "#f8f7fb",
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
    "light": "#f3f2f7",
    "category": "color"
  },
  {
    "name": "--studio-bg-track",
    "label": "分段控件轨道",
    "dark": "#0c0c0d",
    "light": "#f0eef5",
    "category": "color"
  },
  {
    "name": "--studio-bg-secondary",
    "label": "次级按钮背景",
    "dark": "#262626",
    "light": "#f0eef5",
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
    "light": "#24242b",
    "category": "color"
  },
  {
    "name": "--studio-text-secondary",
    "label": "次要文字",
    "dark": "rgba(219, 222, 231, 0.6)",
    "light": "rgba(36, 36, 43, 0.65)",
    "category": "color"
  },
  {
    "name": "--studio-text-tertiary",
    "label": "辅助文字",
    "dark": "#7a7880",
    "light": "#777580",
    "category": "color"
  },
  {
    "name": "--studio-text-strong",
    "label": "强调文字",
    "dark": "#ffffff",
    "light": "#101013",
    "category": "color"
  },
  {
    "name": "--studio-text-subtle",
    "label": "柔和文字",
    "dark": "#b8b7c3",
    "light": "#666471",
    "category": "color"
  },
  {
    "name": "--studio-action-primary-bg",
    "label": "主要操作背景",
    "dark": "#ffffff",
    "light": "#202026",
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
    "light": "rgba(91, 80, 119, 0.18)",
    "category": "color"
  },
  {
    "name": "--studio-border-subtle",
    "label": "弱边框",
    "dark": "rgba(219, 222, 231, 0.15)",
    "light": "rgba(91, 80, 119, 0.12)",
    "category": "color"
  },
  {
    "name": "--studio-border-input",
    "label": "输入框边框",
    "dark": "rgba(219, 222, 231, 0.21)",
    "light": "rgba(91, 80, 119, 0.2)",
    "category": "color"
  },
  {
    "name": "--studio-fill-subtle",
    "label": "弱填充",
    "dark": "rgba(219, 222, 231, 0.05)",
    "light": "rgba(116, 99, 151, 0.04)",
    "category": "color"
  },
  {
    "name": "--studio-fill-hover",
    "label": "悬停填充",
    "dark": "rgba(255, 255, 255, 0.06)",
    "light": "rgba(116, 99, 151, 0.07)",
    "category": "color"
  },
  {
    "name": "--studio-fill-selected",
    "label": "选中填充",
    "dark": "rgba(170, 163, 225, 0.1)",
    "light": "rgba(116, 99, 151, 0.12)",
    "category": "color"
  },
  {
    "name": "--studio-focus-ring",
    "label": "键盘焦点",
    "dark": "#ffffff",
    "light": "#47414f",
    "category": "color"
  },
  {
    "name": "--studio-warning",
    "label": "警告文字",
    "dark": "#dd6800",
    "light": "#a74600",
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
  { category: "color", label: "颜色", description: "深色取自现有组件，浅色按同一语义适配，色块跟随当前主题" },
  { category: "typography", label: "字体", description: "界面字体、字号、行高与字重" },
  { category: "size", label: "尺寸", description: "图标、控件与布局的基础尺寸" },
  { category: "radius", label: "圆角", description: "从紧凑控件到卡片和胶囊" },
  { category: "spacing", label: "间距", description: "内容、组件和区域之间的距离" },
  { category: "motion", label: "动效", description: "用于反馈与状态切换，减少动态效果时关闭过渡" },
];
