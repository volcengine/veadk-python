import { useState } from "react";
import { LongRunningState, type LongRunningStep } from "../../components/composites/LongRunningState";
import { Button } from "../../components/primitives/Button";
import { ComponentApi } from "../api/ComponentApi";
import "./LongRunningStatePreview.css";

const steps: LongRunningStep[] = [
  {
    id: "understand",
    title: "理解任务",
    details: "正在整理你的问题，识别需要检索的信息与最终输出的内容",
  },
  {
    id: "research",
    title: "检索相关资料",
    details: (
      <div className="long-running-state-preview__details">
        <span>正在查找相关文档，并核对不同来源的信息</span>
        <div className="long-running-state-preview__sources">
          <span>产品文档</span><span>已找到 12 条相关内容</span>
          <span>知识库</span><span>正在匹配关键段落</span>
        </div>
      </div>
    ),
  },
  {
    id: "analyze",
    title: "分析与归纳",
    details: "已收集到相关资料，正在对照问题筛选有效信息，梳理结论和对应依据",
  },
  {
    id: "write",
    title: "生成结果",
    details: "正在组织最终内容，并检查引用与结论是否一致",
  },
];

export function LongRunningStatePreview() {
  const [stepIndex, setStepIndex] = useState(1);
  return (
    <section aria-labelledby="long-running-state-preview-title">
      <h2 id="long-running-state-preview-title" className="component-preview-title">Long-running State</h2>
      <div className="long-running-state-preview__example">
        <div className="long-running-state-preview__frame">
          <LongRunningState steps={steps} currentStep={steps[stepIndex].id} aria-label="任务执行进度" />
        </div>
        <div className="long-running-state-preview__controls">
          <span className="long-running-state-preview__position">步骤 {stepIndex + 1} / {steps.length}</span>
          <div className="long-running-state-preview__buttons">
            <Button variant="secondary" disabled={stepIndex === 0} onClick={() => setStepIndex(index => index - 1)}>上一步</Button>
            <Button disabled={stepIndex === steps.length - 1} onClick={() => setStepIndex(index => index + 1)}>下一步</Button>
          </div>
        </div>
      </div>
      <ComponentApi names={["LongRunningState"]} />
    </section>
  );
}
