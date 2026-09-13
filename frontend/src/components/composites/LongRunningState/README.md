# Long-running State

居中的双栏任务工作区，最大宽度 1120px，可直接放入全屏居中的容器
左侧集中展示任务标题、完成进度与步骤导航，右侧是独立的执行详情面板
使用系统字体，任务标题 26px，步骤标题 16px，正文与代码均使用 14px 字号、22px 行高
任务标题在窄栏中缩为 24px，步骤以状态图形和无障碍名称表达进度，不在每一行重复状态说明
右侧复用 ScrollArea，detailsMaxHeight 默认 360px，超过后纵向滚动，切换查看步骤时回到顶部
桌面详情面板至少 480px 高，切换长短内容时步骤位置不跳动，窄容器下自动上下排列

详情面板与 Drawer 共用 `tokens/glass-surface.css`，包含半透明底色、背景模糊、边缘高光及阴影，深浅主题使用同一份材质定义
玻璃只用于详情层，左侧步骤保持清晰的实色交互反馈；无额外遮罩，不阻断任务导航

已完成步骤显示绿色圆圈与白色对勾，点击后查看该步骤的 details；尚未开始的步骤不可点击
currentStep 只表示实际执行进度，查看历史不会修改它；点击当前步骤或「返回当前步骤」恢复跟随进度
圆点与完成圆圈共用同一个图形，以无回弹的阻尼过渡连续改变大小，Loading 在同一中心淡入淡出，完成时绘制对勾
状态可在动画中途改变，图形从当前值继续过渡，连接线同步变色；减少动态效果模式直接更新图形
选中背景沿步骤位置平滑移动，进度条跟随实际完成数量增长；这些动效不会移动或缩放步骤文字
状态变化不会重新播放未改动的步骤标题，详情立即替换并在原位短暂淡入，始终只有一层正文，连续切换不会累积日志重影
标题与操作按钮始终保留占位，按下步骤时即时反馈；返回当前步骤后，键盘焦点也回到对应步骤
支持减少透明度与高对比度偏好，自动将玻璃面板切换为清晰的不透明表面

details 接收文字或 React 内容；代码形式直接复用 CodeBlock

```tsx
<LongRunningState
  heading="调用趋势分析"
  currentStep="research"
  completedSteps={["understand"]}
  detailsMaxHeight={360}
  steps={[{
    id: "understand",
    title: "理解任务",
    details: "已确认分析范围与输出要求",
  }, {
    id: "research",
    title: "检索相关资料",
    details: <CodeBlock
      title="执行日志"
      lines={[logText]}
      language="log"
      showLineNumbers={false}
      wordWrap
    />,
  }]}
/>
```

CodeBlock 的 showLineNumbers 默认 true；false 隐藏行号与行号占位，保留代码字体、缩进和复制功能
language="log" 使用现有代码配色高亮时间、日志级别、分类标签、函数、字段名和数字，并适配明暗主题
预览可在正文与代码之间切换，代码示例包含长日志用于检查滚动

completedSteps 不传时，默认将 currentStep 之前的步骤视为已完成；全部结束时传 currentStep={null} 与完整的 completedSteps
selectedStep 可受控指定查看的步骤，null 跟随当前执行步骤，onSelectedStepChange 返回对应 id 或 null
完成记录由调用方保存在每一步的 details 中，组件不会替业务保存数据或重新执行历史任务
预览中的「完成当前步骤」可检查进度切换和动画，已完成步骤展示完成日志与结果摘要
