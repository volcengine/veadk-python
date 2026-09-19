# Progress（LongRunningState）

整体左对齐，纵向依次展示当前进度名称、循环加载条和具体内容，随父容器宽度收缩

当前名称使用 14px 正常字号与 22px 行高，切换时先向上渐隐，下一名称从下方向上滑入
执行中加载条以 1.1 秒周期快速滑动，不显示未经确认的完成百分比
内容复用无背景、无边框的 ScrollArea，detailsMaxHeight 默认 240px，支持键盘滚动
步骤切换时滚回内容顶部，同一步骤的内容更新保留当前阅读位置
减少动态效果模式下名称直接更新，加载条保持静态，状态文案继续表明任务进度

details 接收文字或 React 内容，代码可直接复用 CodeBlock，背景保持透明

```tsx
<LongRunningState
  aria-label="调用趋势分析"
  currentStep="research"
  completedSteps={["understand"]}
  detailsMaxHeight={240}
  steps={[{
    id: "understand",
    title: "理解任务",
    details: "已确认分析范围与输出要求",
  }, {
    id: "research",
    title: "检索相关资料",
    details: "正在查找相关文档，并核对不同来源的信息",
  }]}
/>
```

全部结束时传 currentStep={null} 与完整的 completedSteps，名称显示「任务已完成」，加载条停止并保留最后一步的内容
暂无执行步骤但存在部分完成记录时显示「等待下一步」，空任务显示「等待任务开始」
重试时更新 currentStep 和 completedSteps，组件会重新显示执行中的状态

组件库以 Text 和 Code 两个二级标题独立展示正文与日志示例，各自提供「重新开始」与「完成当前步骤」
Code 示例包含长日志，用于检查滚动区域；旧链接 #long-running-state 和 #progress 均可访问
