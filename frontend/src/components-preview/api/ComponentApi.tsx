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
  Button: {
    variant: "primary 主按钮、secondary 次按钮、ghost 透明按钮、link 链接样式按钮",
    iconOnly: "纯图标按钮，28 × 28px；图标通过 startIcon 传入，需提供 aria-label，可组合 primary、secondary 或 ghost 样式",
    endIcon: "右侧图标；link 样式下尺寸跟随字号，悬停或键盘聚焦时与文字下方虚线一起淡入，移开淡出",
  },
  Radio: {
    name: "同一组 Radio 使用相同 name，只能选中一项",
    label: "可选文字标签；未提供时需设置 aria-label 或 aria-labelledby",
    checked: "受控选中状态，与 onChange 配合使用",
    defaultChecked: "非受控初始选中状态",
  },
  Textarea: { className: "外层可拉伸容器的 CSS 类名", style: "原生 textarea 的样式，外框高度上限使用 maxHeight", counter: "右下角计数内容，不自动计数或限制字数" },
  Select: { options: "选项数组：value、label 必填；icon、disabled 可选", defaultValue: "非受控初始值，未设置时选择第一个未禁用选项" },
  PillTabs: { items: "选项数组：value、label 必填；panelId 可选" },
  GlassTabs: { items: "选项数组：value、label 必填；panelId 可选" },
  UnderlineTabs: { items: "选项数组，详见 UnderlineTabItem 类型" },
  FilterTabs: { options: "选项数组，每项包含 value 和 label" },
  CodeBlock: { lines: "字符串数组或 token 数组的数组，token 包含 text 和可选 color" },
  FormLabel: { required: "显示必填星号，实际表单验证需设置控件的 required" },
  FormField: {
    required: "显示必填标签，实际表单验证需设置控件的 required",
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
      const visibleNative = (prop: (typeof doc.props)[number]) => commonNative.has(prop.name) && (!['defaultChecked', 'checked'].includes(prop.name) || ['Switch', 'Checkbox', 'Radio'].includes(name));
      const primary = doc.props.filter(prop => !prop.native || visibleNative(prop)).sort((a, b) => Number(a.native) - Number(b.native));
      const inherited = doc.props.filter(prop => prop.native && !visibleNative(prop));
      const table = (props: typeof primary) => <div className="component-api__scroll"><table>
        <thead><tr><th scope="col">参数 / 属性</th><th scope="col">类型</th><th scope="col">必填</th><th scope="col">默认值</th><th scope="col">说明</th></tr></thead>
        <tbody>{props.map(prop => <tr key={prop.name}>
          <th scope="row">{prop.name}</th><td>{prop.name === "maxHeight" ? "number | string" : prop.type}</td><td>{prop.required ? "是" : "否"}</td><td>{prop.defaultValue}</td>
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
