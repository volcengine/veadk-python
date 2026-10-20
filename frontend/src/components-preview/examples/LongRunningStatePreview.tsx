import { useState } from "react";
import { LongRunningState, type LongRunningStep } from "../../components/composites/LongRunningState";
import { Button } from "../../components/primitives/Button";
import { CodeBlock } from "../../components/composites/CodeBlock";

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

const logs: Record<string, string> = {
  understand: [
    "10:42:01 [INFO] task.start()",
    "  input: 分析调用趋势并整理建议",
    "  sources: 产品文档、知识库",
    "  output: 分析摘要",
    "",
    "正在确认任务范围…",
  ].join("\n"),
  research: [
    "10:42:02 [INFO] search.run()",
    "  query: 调用趋势、并发峰值、配额",
    "  sources: [product_docs, knowledge_base]",
    "",
    "[文档] 正在读取索引",
    "10:42:03 [SUCCESS] 已找到 12 条相关内容",
    "",
    ...Array.from({ length: 12 }, (_, index) => `[匹配] 文档 ${String(index + 1).padStart(2, "0")} · 正在核对相关段落`),
    "",
    "[知识库] 正在匹配关键段落",
    "[校验] 合并重复来源，保留引用位置",
    "[进度] 等待检索完成…",
  ].join("\n"),
  analyze: [
    "10:42:06 [INFO] analysis.summarize()",
    "  documents: 12",
    "  checks:",
    "    - 核对统计周期",
    "    - 合并重复信息",
    "    - 标注结论来源",
    "",
    "正在整理结论与对应依据…",
  ].join("\n"),
  write: [
    "10:42:09 [INFO] report.compose()",
    "  sections:",
    "    - 调用量趋势",
    "    - 峰值与变化",
    "    - 后续建议",
    "",
    "正在检查引用与结论的一致性…",
  ].join("\n"),
};
const completedDetails: Record<string, string> = {
  understand: "已确认分析范围：对照产品文档与知识库，整理调用趋势、并发峰值和配额建议，输出分析摘要",
  research: "已完成检索，共匹配 12 条相关内容，合并重复来源并保留引用位置，供后续分析核对",
  analyze: "已核对统计周期、合并重复信息，并为调用趋势、峰值变化和后续建议整理了对应依据",
  write: "分析摘要已生成，引用与结论检查完成",
};

const completedLogs: Record<string, string> = {
  understand: "10:42:02 [SUCCESS] 任务范围已确认\n  status: completed\n  output: 调用趋势分析摘要",
  research: "10:42:06 [SUCCESS] 检索与校验完成\n  documents: 12\n  status: completed\n  references: 已保留来源位置",
  analyze: "10:42:09 [SUCCESS] 分析与归纳完成\n  status: completed\n  sections: 3\n  citations: 已核对",
  write: "10:42:12 [SUCCESS] 分析摘要已生成\n  status: completed\n  validation: passed",
};

function LongRunningStateExample({ mode }: { mode: "text" | "code" }) {
  const [stepIndex, setStepIndex] = useState(1);
  const completedIds = steps.slice(0, stepIndex).map(step => step.id);
  const previewSteps = steps.map((step, index) => {
    const completed = index < stepIndex;
    const log = completed
      ? `${logs[step.id].split("\n").slice(0, -1).join("\n")}\n${completedLogs[step.id]}`
      : logs[step.id];
    return {
      ...step,
      details: mode === "code"
        ? <CodeBlock title="执行日志" language="log" lines={[log]} showLineNumbers={false} wordWrap />
        : completed ? completedDetails[step.id] : step.details,
    };
  });
  return (
    <div className="long-running-state-preview__example">
      <div className="long-running-state-preview__frame">
        <LongRunningState steps={previewSteps} currentStep={steps[stepIndex]?.id ?? null} completedSteps={completedIds} aria-label="调用趋势分析" />
      </div>
      <div className="long-running-state-preview__controls">
        <div className="long-running-state-preview__buttons">
          <Button variant="secondary" disabled={stepIndex === 0} onClick={() => setStepIndex(0)}>重新开始</Button>
          <Button disabled={stepIndex === steps.length} onClick={() => setStepIndex(index => Math.min(index + 1, steps.length))}>{stepIndex === steps.length ? "任务已完成" : stepIndex === steps.length - 1 ? "完成任务" : "完成当前步骤"}</Button>
        </div>
      </div>
    </div>
  );
}

export function LongRunningStatePreview() {
  return (
    <section className="components-preview-variants" aria-labelledby="component-page-title">
      <section aria-labelledby="long-running-state-preview-title">
        <h2 data-preview-heading tabIndex={-1} id="long-running-state-preview-title" className="component-preview-title">Text</h2>
        <LongRunningStateExample mode="text" />
      </section>
      <section aria-labelledby="long-running-state-preview-code">
        <h2 data-preview-heading tabIndex={-1} id="long-running-state-preview-code" className="component-preview-title">Code</h2>
        <LongRunningStateExample mode="code" />
      </section>
    </section>
  );
}
