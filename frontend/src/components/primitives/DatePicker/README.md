# Date Picker

日期选择器参考 HeroUI 的分段输入与日历交互，视觉沿用组件库的 Figma 输入框、菜单和按钮

支持 `day` 日期和 `minute` 日期时间，默认 24 小时制；可通过键盘修改日期字段，日历支持方向键切换、Esc 关闭并返回触发按钮

```tsx
<DatePicker
  aria-label="执行时间"
  granularity="minute"
  value={onceAt}
  onChange={setOnceAt}
  timeZone="Asia/Shanghai"
  required
/>
```

- `value` / `defaultValue`：日期使用 `YYYY-MM-DD`，日期时间使用 `YYYY-MM-DDTHH:mm`；空值为 `""` 或 `null`
- `onChange`：返回相同格式的字符串；清空返回 `""`
- `minValue` / `maxValue`：包含边界；minute 模式下只传日期时，分别按当天 `00:00` / `23:59` 处理
- `timeZone`：IANA 时区，用于计算“今天”；切换时区不会转换输入值，调用方将当地时间和时区一起提交
- `placeholderValue`：空值日历的参考日期；不设置时为今天，默认时间为 `09:00`，只有选定日期才产生值
- `locale`：默认 `zh-CN`，支持 `en-US` 等日期格式及无障碍文案
- `hourCycle`：`24`（默认）或 `12`
- `disabled` / `readOnly` / `required`：禁用、只读、必填
- `open` / `defaultOpen` / `onOpenChange`：面板受控或非受控展开
- `aria-label` / `aria-labelledby`：可访问名称；`aria-describedby` / `aria-invalid` 可与 FormField 配合
- `name`：原生表单值使用 ISO 日期时间，minute 模式的隐藏表单字段可能带 `:00` 秒；定时任务使用 `onChange` 的分钟精度值
- `className` / `style`：默认宽 320px，最大宽度为容器宽度；输入框高度 32px

不接受带 `Z` 或 UTC 偏移的值，避免把定时任务的当地时间隐式转换为其他时区；非法日期、格式和反向范围会抛出 RangeError

日期模式选中后关闭面板；日期时间模式选择日期后可继续编辑时间，点击完成或面板外部后收起

预览入口：`/components-preview/#date-picker`，包含日期、定时任务、范围限制和状态示例，下方展示完整参数表
