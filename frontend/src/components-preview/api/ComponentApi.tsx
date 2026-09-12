import docs from "virtual:component-api";
import "./ComponentApi.css";

const descriptions: Record<string, string> = {
  artworkSrc: "卡片插图地址", onAdd: "添加按钮点击回调", onChat: "Chat 按钮点击回调", onEdit: "Edit 按钮点击回调", status: "状态文案", tailIcon: "尾部图标内容", tailIconLabel: "尾部图标按钮的无障碍名称", onTailIconClick: "尾部图标按钮点击回调",
  children: "组件内容", className: "自定义 CSS 类名", style: "内联样式", id: "元素 ID", title: "标题", description: "描述内容",
  value: "受控值", defaultValue: "非受控初始值", onChange: "值变化回调", disabled: "禁用状态", readOnly: "只读状态",
  label: "显示文案", icon: "图标内容", startIcon: "前置图标", endIcon: "后置图标", variant: "外观变体",
  onClick: "点击回调", onAction: "操作按钮回调", actionLabel: "操作按钮文案", actionIcon: "操作按钮图标", actionDisabled: "禁用操作按钮",
  onClose: "关闭回调", closeLabel: "关闭按钮的无障碍名称", onCancel: "取消回调", onConfirm: "确认回调", cancelLabel: "取消按钮文案", confirmLabel: "确认按钮文案",
  selected: "受控选中状态", defaultSelected: "非受控初始选中状态", onSelectedChange: "选中状态变化回调", onValueChange: "选中值变化回调",
  checked: "受控勾选状态", defaultChecked: "非受控初始勾选状态", items: "选项列表，结构见类型", options: "可选项列表，结构见类型",
  placeholder: "空值提示文字", name: "表单字段名称", required: "必填状态或标签必填标记", htmlFor: "关联控件的 ID",
  counter: "右下角计数内容，不自动限制字数", maxHeight: "拖动时的最大高度，数字单位为 px，支持 CSS 长度；默认不限制",
  open: "受控展开状态", defaultOpen: "非受控初始展开状态", onOpenChange: "展开或收起回调",
  onSend: "发送按钮回调，参数为输入文字", sending: "发送期间禁用发送按钮", sendLabel: "发送按钮的无障碍名称", containerStyle: "外层容器内联样式",
  dismissible: "显示关闭按钮", onDismiss: "关闭按钮回调，是否移除由调用方决定", dismissLabel: "关闭按钮的无障碍名称",
  topGlow: "显示弹窗顶部光效", lines: "代码行或带颜色的 token 行", author: "作者名称", avatar: "头像内容", updatedLabel: "更新时间文案",
  sidebar: "侧栏内容", back: "返回区域内容", header: "页头内容", tabs: "标签栏内容", runtime: "运行区域内容", runtimeLabel: "运行区域标题",
  banner: "横幅内容", filters: "筛选区域内容", actions: "操作区域内容", onZoomIn: "放大回调", onZoomOut: "缩小回调", onFitView: "适配视图回调", onToggleLayout: "切换布局回调",
  iconVariant: "图标变体", skillCount: "技能数量", toolCount: "工具数量", href: "链接地址", target: "链接打开方式",
  type: "原生控件类型", rows: "原生文本区域行数，外框默认高度为 80px", maxLength: "原生最大输入长度", minLength: "原生最小输入长度",
  "aria-label": "无障碍名称", "aria-describedby": "描述元素的 ID", "aria-controls": "关联内容区域的 ID", ref: "底层元素引用",
};

const componentNotes: Record<string, Record<string, string>> = {
  DatePicker: {
    value: "受控日期，day 使用 YYYY-MM-DD，minute 使用 YYYY-MM-DDTHH:mm；空字符串或 null 清空",
    defaultValue: "非受控初始日期，格式与 value 相同",
    onChange: "返回所选日期或日期时间字符串；清空时返回空字符串，不自动转换时区",
    granularity: "day 仅选择日期；minute 同时选择日期和时间，默认 day",
    minValue: "最早可选日期或时间，包含边界",
    maxValue: "最晚可选日期或时间，包含边界",
    timeZone: "IANA 时区，用于计算今天；切换时区保留已输入的当地时间",
    open: "受控日历面板显示状态",
    onOpenChange: "日历打开或关闭时的回调",
  },
  IndexLayout: {
    tabs: "顶部模式切换区域，推荐传入 GlassTabs",
    prompt: "主输入区域，推荐传入 PromptInput",
    shortcuts: "输入区下方快捷入口，推荐传入 compact Item",
    heading: "主标题，默认 How can I help you today?",
    logo: "标题上方标志，默认显示设计稿中的 AK 标志",
  },
  LongRunningState: {
    steps: "按执行顺序排列：id 为稳定唯一标识，title 为步骤名称，details 支持文字或 React 内容",
    currentStep: "当前执行步骤的 id，左侧此步骤显示 Loading，右侧展示对应详情；null 表示暂无执行步骤",
  },
  ModalButton: {
    label: "触发按钮内容，点击后打开复用 ModalLayout 的弹窗",
    buttonProps: "传入 Button 的外观、图标及禁用等属性",
    children: "弹窗 body 内容，默认留空，超长内容复用 ScrollArea",
    closeOnConfirm: "默认 true，确认后关闭；异步操作可设为 false 并通过 open 控制关闭",
    onOpenChange: "入口、关闭按钮、取消、确认、Esc 或点击遮罩时返回新的打开状态",
  },
  Drawer: {
    trigger: "触发入口，传入 Button 等按钮元素；也可通过 open 直接控制",
    children: "内部可滚动内容，复用 ScrollArea",
    footer: "固定在底部的操作区，可传入 Button 等 React 内容",
    width: "面板默认 480px，距屏幕上下与右侧各 16px，窄屏自动限宽",
    surface: "glass 默认毛玻璃，真实模糊后方页面并带轻微高光；solid 使用不透明面板",
  },
  FileUpload: {
    files: "受控已选择文件，结果通过 onFilesChange 提供给业务，不自动发起网络上传",
    onFilesChange: "添加或移除后返回完整 File 数组",
    accept: "允许的扩展名或 MIME，如 .pdf,.txt,image/*；文件选择与拖放都会校验",
    maxSize: "单个文件的字节数上限，不设置则不限制",
    maxFiles: "文件总数上限，multiple=false 时最多一个",
    multiple: "默认 true；false 时选择新文件替换原文件",
    onReject: "校验失败时返回 { file, reason, message } 数组，reason 为 type、size 或 count；重复文件直接忽略",
  },
  Slider: {
    label: "滑轨上方的名称，同时关联原生 range 的无障碍名称",
    onValueChange: "拖动或键盘调整时返回数值",
    step: "默认 1，支持小数；any 允许连续取值",
    showValue: "默认 true，在名称右侧显示当前数值",
    valueFormat: "自定义数值格式，同时用于屏幕阅读器读值",
    className: "最外层容器的 CSS 类名",
    style: "最外层容器的内联样式，可调整组件宽度",
  },
  FileExplorer: {
    entries: "文件和文件夹组成的树，id/name/type 必填；folder 提供 children，file 提供 content（字符串或 CodeBlock 行/token），可选 language 覆盖文件名识别的语言，plaintext 关闭高亮；图标按文件名自动识别",
    selectedId: "受控选中文件的 id，null 表示未选择；右侧复用 CodeBlock 显示文件内容",
    defaultSelectedId: "非受控模式初始选中的文件 id",
    onSelect: "选择文件时返回 id 和完整文件条目",
    expandedIds: "受控展开的文件夹 id 列表",
    defaultExpandedIds: "非受控模式初始展开的文件夹 id 列表",
    onExpandedChange: "展开或收起目录时返回全部展开 id",
    allowEdit: "默认 false；true 时复用代码编辑器，可直接输入，复制图标右侧显示保存按钮，切换文件保留各自草稿",
    onEdit: "每次用户编辑返回 (id, content, file)，不会因自动格式化触发；内容始终是字符串",
    onSave: "点击保存或 Command/Ctrl + S 时返回 (id, content, file)，支持 Promise；失败保留草稿并提示，未配置时保存按钮禁用",
    autoFormat: "默认 true；打开时格式化 JS/TS/JSON/CSS/HTML/YAML/Markdown，源数据不变；其它语言保留原文，语法错误时保留原文并提示，编辑时不自动重排",
    wordWrap: "默认 true；长行自适应面板宽度，续行不增加行号；false 恢复横向滚动",
    style: "容器内联样式，默认高度 480px，可调整宽高",
  },
  DetailPageLayout: {
    children: "详情页主体内容，占满可用宽度，布局内不包含 Sidebar",
  },
  EmptyState: {
    title: "信息区域的标题，支持文字或 React 内容",
    description: "标题下方的详细说明，长文字自动换行；未设置时不占位",
    icon: "40px 圆形背景内的 18px 图标，与标题字号一致；默认空文件夹，自定义仅替换图标，传 null 隐藏图标区域",
    actions: "底部按钮组插槽，支持任意数量的 Button 子元素；8px 间距横排，窄容器自动换行",
    style: "外层容器样式，可调整宽度、内边距或最小高度",
  },
  Loading: {
    variant: "infinity 无限路径（默认 48 × 24px、2 秒循环）；ring 圆环（默认 40 × 40px、1 秒循环）",
    size: "图形宽度，单位 px；infinity 高度为宽度的一半，ring 宽高相同且描边按比例缩放",
    label: "仅供屏幕阅读器读取的加载状态文案，不显示在图标旁",
    decorative: "设为 true 时隐藏无障碍状态，由按钮等外层提供名称和加载状态",
  },
  ErrorState: {
    title: "错误状态标题，支持文字或 React 内容",
    description: "错误详情，长文字自动换行；固定使用红色断链图标，不提供按钮区域",
  },
  Toast: {
    title: "主标题，与 description 至少提供一项；纯展示组件不负责关闭计时",
    action: "自定义操作区域，可传入 Button、链接等 React 内容",
    onDismiss: "提供后显示关闭按钮，组件的移除由调用方处理",
    role: "默认 status；静态展示可使用 presentation，通知管理使用 ToastProvider",
  },
  ToastProvider: {
    children: "需要调用 useToast 的内容；通知面板自动渲染到页面浮层",
    duration: "默认自动关闭时长，单位毫秒；0 为常驻，悬停或键盘聚焦时暂停；最多显示 3 条通知",
    position: "支持顶部或底部的左侧、居中、右侧，默认 top-center；通知之间保持 8px 间距",
  },
  ResourcePageLayout: {
    loading: "首次加载资源时显示 Infinity Path，默认 false；后台刷新已有资源时无需清空内容",
    loadingLabel: "仅供屏幕阅读器读取的加载状态，默认正在加载资源",
  },
  Button: {
    loading: "默认 false；只显示居中的 Ring 图标并自动禁用按钮，设置 aria-busy，保留原宽高与无障碍名称",
    variant: "primary 主按钮、secondary 次按钮、outline 半透明描边按钮，默认高度统一为 32px；ghost 透明按钮、link 链接样式按钮",
    size: "default 保留各变体原始尺寸；large 为 36px，Header 的两个按钮共用；compact 仅用于 iconOnly，20 × 20px 且无内边距，Modal 关闭按钮复用",
    iconOnly: "纯图标按钮，默认 28 × 28px，large 为 36 × 36px；图标通过 startIcon 传入，需提供 aria-label，可组合不同 variant",
    endIcon: "右侧图标；link 样式下尺寸跟随字号，悬停或键盘聚焦时与文字下方虚线一起淡入，移开淡出",
  },
  Radio: {
    name: "同一组 Radio 使用相同 name，只能选中一项",
    label: "可选文字标签；未提供时需设置 aria-label 或 aria-labelledby",
    checked: "受控选中状态，与 onChange 配合使用",
    defaultChecked: "非受控初始选中状态",
  },
  RadioCard: {
    title: "卡片主标题",
    description: "标题下方的副标题",
    icon: "左侧图标，20 × 20px，放在 44 × 44px 的容器内",
    style: "卡片容器样式，默认宽度 472px、最小高度 68px",
    name: "同一组 RadioCard 使用相同 name，只能选中一项",
    checked: "受控选中状态，与 onChange 配合使用",
    defaultChecked: "非受控初始选中状态",
  },
  PromptInput: {
    placeholder: "未设置 placeholders 或列表为空时显示的单条提示",
    placeholders: "输入为空时向上轮播的提示词列表；输入内容后隐藏，清空后恢复，空列表回退到 placeholder",
    placeholderInterval: "提示词切换间隔，单位为毫秒，默认 3000",
  },
  SingleLinePromptInput: {
    placeholder: "未设置 placeholders 或列表为空时显示的单条提示",
    placeholders: "输入为空时向上轮播的提示词列表；输入内容后隐藏，清空后恢复，空列表回退到 placeholder",
    placeholderInterval: "提示词切换间隔，单位为毫秒，默认 3000",
  },
  Textarea: { className: "外层可拉伸容器的 CSS 类名", style: "原生 textarea 的样式，外框高度上限使用 maxHeight", counter: "右下角计数内容，不自动计数或限制字数" },
  Select: { options: "选项数组：value、label 必填；icon、description、disabled 可选；description 在下拉列表中显示为副标题，选中后输入框只显示 label", defaultValue: "非受控初始值，未设置时选择第一个未禁用选项" },
  Menu: {
    label: "触发按钮的文字或 React 内容，右侧显示向下箭头",
    items: "菜单结构，支持普通菜单项、分组和分割线，children 可继续嵌套；字段见下方 MenuEntry 表格",
    onSelect: "末级菜单项选中时调用，参数为 id 和完整 MenuItem；选中后关闭菜单",
    openOnHover: "默认 false，启用后悬停入口即可展开，点击和键盘仍可用",
    align: "优先与按钮的 start 左侧或 end 右侧对齐；靠近窗口边缘时自动切换对齐方式，上下方向也随可用空间调整",
    menuWidth: "每级菜单面板的宽度，单位为 px，默认 220",
    maxHeight: "每级菜单面板的最大高度，单位为 px，默认 280，溢出时复用 ScrollArea 滚动",
    emptyContent: "items 为空时展示的内容，默认暂无菜单项",
    disabled: "禁用触发按钮，无法打开菜单",
  },
  PillTabs: { items: "选项数组：value、label 必填；panelId 可选" },
  GlassTabs: { items: "选项数组：value、label 必填；panelId 可选" },
  UnderlineTabs: { items: "选项数组，详见 UnderlineTabItem 类型" },
  FilterTabs: { options: "选项数组，每项包含 value 和 label" },
  CodeBlock: {
    lines: "字符串数组或 token 数组的数组，token 包含 text 和可选 color；字符串行自动高亮，手动 token 颜色保留",
    language: "默认 auto 自动识别；支持 TypeScript、JavaScript、Python、JSON、HTML、CSS、Markdown 等常用语言，plaintext 关闭高亮，未知语言按纯文本显示",
  },
  Label: {
    variant: "default 基础标签；status 矩形状态标签；pill 描边胶囊标签，Header 的 ACTIVE 状态复用此类型",
    startIcon: "左侧图标内容；pill 类型保留 7px 状态圆点尺寸",
  },
  FormLabel: {
    required: "显示原设计的 6px 必填星号；实际表单验证需设置控件的 required",
    variant: "default 为 13px 次级文字；field 为 14px 主文字且支持换行，两种样式都支持 required",
  },
  FormField: {
    required: "通过 FormLabel 显示必填星号；非必填标签也复用 FormLabel，保留各 Figma 示例的字体样式；实际表单验证需设置控件的 required",
    htmlFor: "对应输入控件的 id，用于关联标签、提示与错误状态",
    tip: "显示在控件下方的输入规则或辅助提示",
    error: "错误时替换 tip，显示红色文字与输入框/文本域边框，并设置 aria-invalid",
  },
  Divider: { role: "固定为 separator", "aria-orientation": "固定为 horizontal" },
  ScrollArea: {
    orientation: "vertical 纵向、horizontal 横向、both 双向滚动，均保留原生滚动行为",
    hideScrollbar: "始终隐藏滚动条；未隐藏时，鼠标移入区域淡入、移出淡出，键盘聚焦时显示",
    maxHeight: "滚动区域最大高度，数字单位为 px，超出后纵向滚动",
  },
  Table: {
    columns: "列定义：key、title、render 必填；width 设置宽度，align 控制对齐，overflow 选择 wrap 换行或 ellipsis 省略，fixed 选择 left / right 冻结列；sort 包含 direction（asc / desc / null）和 onChange，filter 包含 value、options 和 onChange；筛选排序后的 data 由调用方提供，render 可返回下拉框、按钮组等 React 内容",
    maxHeight: "表格滚动区最大高度，数字单位为 px；超出时在区域内纵向滚动",
    minWidth: "表格最小宽度，空间不足时在区域内横向滚动",
    layout: "fixed 按列宽分配空间；auto 根据内容自适应列宽",
    stickyHeader: "设置 maxHeight 后，在纵向滚动时固定表头",
    hideScrollbar: "隐藏滚动条，保留触控板、触屏和键盘滚动",
    toolbarStart: "表格上方左侧区域，可放搜索框或筛选条件",
    toolbarEnd: "表格上方右侧区域，可放主按钮或按钮组",
  },
  TableCellText: {
    title: "主文本，显示在描述上方",
    description: "次级描述，未设置时只显示主文本",
    truncate: "主文本超出列宽时单行省略",
    descriptionLines: "描述的最大行数，超出后省略；未设置时自然换行",
  },
};

const commonNative = new Set(["children", "className", "style", "id", "value", "defaultValue", "checked", "defaultChecked", "disabled", "readOnly", "onChange", "onClick", "name", "placeholder", "required", "maxLength", "type", "htmlFor", "aria-label"]);

export function ComponentApi({ names }: { names: string[] }) {
  return <div className="component-api">
    {names.map(name => {
      const doc = docs[name];
      if (!doc) return <p key={name} role="alert">{name} 的参数信息未生成</p>;
      const visibleNative = (prop: (typeof doc.props)[number]) => commonNative.has(prop.name) && (!['defaultChecked', 'checked'].includes(prop.name) || ['Switch', 'Checkbox', 'Radio', 'RadioCard'].includes(name));
      const primary = doc.props.filter(prop => !prop.native || visibleNative(prop)).sort((a, b) => Number(a.native) - Number(b.native));
      const inherited = doc.props.filter(prop => prop.native && !visibleNative(prop));
      const table = (props: typeof primary) => <div className="component-api__scroll"><table>
        <thead><tr><th scope="col">参数 / 属性</th><th scope="col">类型</th><th scope="col">必填</th><th scope="col">默认值</th><th scope="col">说明</th></tr></thead>
        <tbody>{props.map(prop => <tr key={prop.name}>
          <th scope="row">{prop.name}</th><td>{prop.name === "maxHeight" && name !== "Menu" ? "number | string" : prop.type}</td><td>{prop.required ? "是" : "否"}</td><td>{prop.defaultValue}</td>
          <td>{componentNotes[name]?.[prop.name] ?? ((!prop.native && prop.description) || descriptions[prop.name]) ?? (prop.native ? (prop.name.startsWith("on") ? "原生事件回调" : "原生 HTML / ARIA 属性") : prop.description || "组件参数，详见类型定义")}</td>
        </tr>)}</tbody>
      </table></div>;
      return <section key={name} aria-label={`${name} 参数与属性`}>
        <h3>{name} 参数与属性</h3>
        {primary.length ? table(primary) : <p>无自定义参数</p>}
        {inherited.length > 0 && <details><summary>其他原生属性（{inherited.length}）</summary>{table(inherited)}</details>}
      </section>;
    })}
  </div>;
}
