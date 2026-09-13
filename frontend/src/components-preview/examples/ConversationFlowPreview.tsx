import { useCallback, useEffect, useRef, useState, type ComponentProps } from "react";
import { ConversationFlow, type ConversationAssistantMessage, type ConversationBlock, type ConversationFeedback, type ConversationMessage, type ConversationStatus } from "../../components/ai-app/ConversationFlow";
import { ConversationSurface } from "../../components/ai-app/ConversationFlow/ConversationSurface";
import { Button } from "../../components/primitives/Button";
import { UnderlineTabs } from "../../components/primitives/UnderlineTabs";
import { FileExplorer, type FileExplorerEntry } from "../../components/composites/FileExplorer";
import { ComponentApi } from "../api/ComponentApi";
import chartImage from "./assets/conversation-media/chart.png";
import trendVideo from "./assets/conversation-media/trend.mp4";
import summaryAudio from "./assets/conversation-media/summary.m4a?url";
import "./ConversationFlowPreview.css";

type AssistantPatch = Partial<Omit<ConversationAssistantMessage, "id" | "role">>;
interface PlaybackPhase { at: number; update: AssistantPatch }

function useConversationPlayback(initialMessages: () => ConversationMessage[]) {
  const [messages, setMessages] = useState(initialMessages);
  const [runningId, setRunningId] = useState<string | null>(null);
  const generation = useRef(0);
  const timers = useRef(new Set<number>());

  const stop = useCallback(() => {
    generation.current += 1;
    timers.current.forEach(timer => window.clearTimeout(timer));
    timers.current.clear();
  }, []);

  useEffect(() => stop, [stop]);

  const play = useCallback((prefix: ConversationMessage[], assistant: ConversationAssistantMessage, phases: readonly PlaybackPhase[]) => {
    stop();
    const currentGeneration = generation.current;
    setMessages([...prefix, assistant]);
    setRunningId(assistant.id);
    phases.forEach(phase => {
      const timer = window.setTimeout(() => {
        timers.current.delete(timer);
        if (generation.current !== currentGeneration) return;
        const finished = phase.update.status === "complete" || phase.update.status === "error" || phase.update.status === "cancelled";
        const endedAt = finished ? Date.now() : undefined;
        setMessages(previous => previous.map(message => message.id === assistant.id && message.role === "assistant"
          ? { ...message, ...phase.update, ...(finished ? { endedAt } : {}) }
          : message));
        if (finished) setRunningId(null);
      }, phase.at);
      timers.current.add(timer);
    });
  }, [stop]);

  const feedback = useCallback((messageId: string, value: ConversationFeedback) => {
    setMessages(previous => previous.map(message => message.id === messageId && message.role === "assistant"
      ? { ...message, feedback: value }
      : message));
  }, []);

  const cancel = useCallback((messageId: string) => {
    if (messageId !== runningId) return;
    stop();
    setRunningId(null);
    const endedAt = Date.now();
    setMessages(previous => previous.map(message => message.id === messageId && message.role === "assistant"
      ? { ...message, status: "cancelled", endedAt, blocks: message.blocks?.map(cancelBlock) }
      : message));
  }, [runningId, stop]);

  return { messages, runningId, play, feedback, cancel };
}

function cancelStatus(status: ConversationStatus | undefined): ConversationStatus | undefined {
  return status === "running" || status === "pending" ? "cancelled" : status;
}

function cancelBlock(block: ConversationBlock): ConversationBlock {
  if (block.type === "handoff") return { ...block, status: cancelStatus(block.status) ?? "complete", steps: block.steps?.map(step => ({ ...step, status: cancelStatus(step.status) })) };
  if (block.type === "reasoning" || block.type === "tool" || block.type === "authorization") return { ...block, status: cancelStatus(block.status) ?? "complete" };
  return block;
}

const defaultPrompt = "分析最近 5 天的调用情况，画出趋势，并给我几条简短建议";
const dailyValues = [128, 154, 141, 178, 196];
const chartSource = JSON.stringify({
  tooltip: { trigger: "axis" },
  xAxis: { type: "category", data: ["周一", "周二", "周三", "周四", "周五"] },
  yAxis: { type: "value", name: "调用次数" },
  series: [{ name: "调用次数", type: "bar", data: dailyValues, barMaxWidth: 24 }],
}, null, 2);
const analysisText = "最近 5 天共完成 **797 次调用**，整体呈上升趋势，周五的调用量最高\n\n- 日均调用量为 159.4 次\n- 周五完成 196 次，较周一增长 53.1%\n- 建议重点观察周五的并发峰值，再决定是否调整配额\n\n下图展示了每天的调用量";
const analysisMarkdown = `${analysisText}\n\n\`\`\`echarts\n${chartSource}\n\`\`\``;
type AnalysisStage = "reasoning" | "query" | "handoff" | "answer" | "complete";

function analysisBlocks(stage: AnalysisStage, prompt: string, text = analysisMarkdown): ConversationBlock[] {
  const queried = stage === "handoff" || stage === "answer" || stage === "complete";
  const analyzed = stage === "answer" || stage === "complete";
  const blocks: ConversationBlock[] = [
    { id: "reasoning", type: "reasoning", title: "思考摘要", status: stage === "reasoning" ? "running" : "complete", durationMs: stage === "reasoning" ? undefined : 1000, content: <p>读取每日调用数据，委派分析智能体计算趋势，再整理图表与建议</p> },
  ];
  if (stage !== "reasoning") blocks.push({
    id: "query-metrics", type: "tool", title: "读取调用统计", status: queried ? "complete" : "running", durationMs: queried ? 1600 : undefined,
    input: JSON.stringify({ request: prompt, range: "last_5_days", groupBy: "day" }, null, 2),
    output: queried ? JSON.stringify({ days: ["Mon", "Tue", "Wed", "Thu", "Fri"], requests: dailyValues, total: 797 }, null, 2) : undefined,
  });
  if (queried) blocks.push({
    id: "analysis-handoff", type: "handoff", title: "分析调用趋势", fromAgent: "主智能体", toAgent: "数据分析智能体", status: analyzed ? "complete" : "running", durationMs: analyzed ? 2000 : undefined,
    content: <p>计算日均调用量、峰值和变化幅度，并将结果交回主智能体</p>,
    steps: [
      { id: "analysis-summary", type: "reasoning", title: "确认统计口径", status: "complete", durationMs: 400, content: "按自然日比较调用次数，使用首日数据作为增长率基准" },
      { id: "aggregate", type: "tool", title: "计算汇总指标", status: analyzed ? "complete" : "running", durationMs: analyzed ? 1600 : undefined,
        input: JSON.stringify({ values: dailyValues }, null, 2),
        output: analyzed ? JSON.stringify({ average: 159.4, peak: { day: "Fri", value: 196 }, growthPercent: 53.1 }, null, 2) : undefined },
    ],
  });
  if (analyzed && text) blocks.push({ id: "answer", type: "markdown", text });
  return blocks;
}

function completedAnalysis(id: string, prompt: string): ConversationAssistantMessage {
  return { id, role: "assistant", status: "complete", blocks: analysisBlocks("complete", prompt), copyText: analysisMarkdown, durationMs: 8000, ttftMs: 4600, tokens: 1248, feedback: null };
}

function initialAnalysisMessages(): ConversationMessage[] {
  return [{ id: "initial-user", role: "user", content: defaultPrompt }, completedAnalysis("initial-assistant", defaultPrompt)];
}

function createAnalysisPlayback(id: string, prompt: string) {
  const assistant: ConversationAssistantMessage = { id, role: "assistant", status: "running", startedAt: Date.now(), blocks: analysisBlocks("reasoning", prompt), feedback: null };
  const phases: PlaybackPhase[] = [
    { at: 1000, update: { blocks: analysisBlocks("query", prompt) } },
    { at: 2600, update: { blocks: analysisBlocks("handoff", prompt) } },
  ];
  for (let frame = 1; frame <= 24; frame += 1) {
    const text = analysisText.slice(0, Math.ceil(analysisText.length * frame / 24));
    phases.push({ at: 4600 + (frame - 1) * 130, update: { blocks: analysisBlocks("answer", prompt, text), copyText: text, ttftMs: 4600 } });
  }
  phases.push({ at: 8000, update: { ...completedAnalysis(id, prompt), durationMs: undefined } });
  return { assistant, phases };
}

function AnalysisDemo() {
  const { messages, runningId, play, feedback, cancel } = useConversationPlayback(initialAnalysisMessages);
  const nextRound = useRef(0);

  function start(prefix: ConversationMessage[], id: string, text: string) {
    const playback = createAnalysisPlayback(id, text);
    play(prefix, playback.assistant, playback.phases);
  }

  function showExample() {
    const round = ++nextRound.current;
    start([{ id: `example-user-${round}`, role: "user", content: defaultPrompt }], `example-assistant-${round}`, defaultPrompt);
  }

  function retry(messageId: string) {
    const index = messages.findIndex(message => message.id === messageId && message.role === "assistant");
    if (index < 0) return;
    const prefix = messages.slice(0, index);
    const request = [...prefix].reverse().find(message => message.role === "user");
    start(prefix, messageId, typeof request?.content === "string" ? request.content : defaultPrompt);
  }

  return <>
    <div className="conversation-flow-preview__toolbar">
      <Button disabled={runningId !== null} onClick={showExample}>演示执行过程</Button>
    </div>
    <ConversationFlow messages={messages} onRetry={retry} onFeedback={feedback} onStop={cancel} />
  </>;
}

const csvContent = "day,requests\nMon,128\nTue,154\nWed,141\nThu,178\nFri,196\n";
const reportContent = "# 调用统计摘要\n\n" + analysisText + "\n";
const previewFiles: readonly FileExplorerEntry[] = [
  { id: "metrics", name: "metrics.csv", type: "file", content: csvContent, language: "plaintext" },
  { id: "report", name: "weekly-report.md", type: "file", content: reportContent },
];

function downloadFile(name: string, content: string) {
  const anchor = document.createElement("a");
  anchor.href = `data:text/plain;charset=utf-8,${encodeURIComponent(content)}`;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
}

const reportSurface: ComponentProps<typeof ConversationSurface>["surface"] = {
  surfaceId: "report-scope", rootId: "root", dataModel: {}, components: {
    root: { id: "root", component: "Card", title: "报告范围", child: "body" },
    body: { id: "body", component: "Column", children: ["text", "buttons"] },
    text: { id: "text", component: "Text", text: "选择需要保留的内容" },
    buttons: { id: "buttons", component: "Row", children: ["full", "summary"] },
    full: { id: "full", component: "Button", variant: "primary", child: "full-label", action: { event: { name: "select_full" } } },
    "full-label": { id: "full-label", component: "Text", text: "完整报告" },
    summary: { id: "summary", component: "Button", variant: "secondary", child: "summary-label", action: { event: { name: "select_summary" } } },
    "summary-label": { id: "summary-label", component: "Text", text: "关键结论" },
  },
};
const richText = "统计结果已整理为表格，并附上可复用的读取方式\n\n| 指标 | 结果 |\n| --- | --- |\n| 总调用量 | 797 次 |\n| 日均调用量 | 159.4 次 |\n| 最高调用量 | 196 次 |\n\n```python\nimport csv\n\nwith open(\"metrics.csv\", newline=\"\") as file:\n    rows = list(csv.DictReader(file))\n    total = sum(int(row[\"requests\"]) for row in rows)\n```";

function RichContentDemo() {
  const [scope, setScope] = useState("");
  const [feedback, setFeedback] = useState<ConversationFeedback>(null);
  const files = [
    { id: "metrics", name: "metrics.csv", description: "5 行调用统计 · CSV", preview: <div className="conversation-flow-preview__file-preview"><FileExplorer entries={previewFiles} defaultSelectedId="metrics" autoFormat={false} /></div>, onDownload: () => downloadFile("metrics.csv", csvContent) },
    { id: "report", name: "weekly-report.md", description: "汇总结论与建议 · Markdown", preview: <div className="conversation-flow-preview__file-preview"><FileExplorer entries={previewFiles} defaultSelectedId="report" autoFormat={false} /></div>, onDownload: () => downloadFile("weekly-report.md", reportContent) },
  ];
  const messages: ConversationMessage[] = [
    { id: "rich-user", role: "user", copyText: "整理这份统计数据，附上分析流程和报告", blocks: [
      { id: "request", type: "markdown", text: "整理这份统计数据，附上分析流程和报告" },
      { id: "attachment", type: "files", files: [files[0]] },
    ] },
    { id: "rich-assistant", role: "assistant", status: "complete", feedback, durationMs: 3200, ttftMs: 650, tokens: 856, copyText: richText, blocks: [
      { id: "result", type: "markdown", text: richText },
      { id: "diagram", type: "visualization", kind: "mermaid", title: "分析流程", source: "flowchart LR\n  A[读取统计数据] --> B[数据分析智能体]\n  B --> C[计算汇总指标]\n  C --> D[生成报告]" },
      { id: "artifacts", type: "files", title: "生成的文件", files },
      { id: "surface", type: "custom", content: <>
        <ConversationSurface surface={reportSurface} onAction={action => {
          if (action?.event?.name === "select_full") setScope("完整报告");
          if (action?.event?.name === "select_summary") setScope("关键结论");
        }} />
        <p className="conversation-flow-preview__choice" role="status">{scope ? `已选择：${scope}` : "尚未选择报告范围"}</p>
      </> },
    ] },
  ];
  return <ConversationFlow messages={messages} onFeedback={(_, value) => setFeedback(value)} />;
}

function MultimodalDemo({ response = false }: { response?: boolean }) {
  const [feedback, setFeedback] = useState<ConversationFeedback>(null);
  const media: ConversationBlock[] = [
    { id: "media-chart", type: "media", kind: "image", src: chartImage, alt: "最近五天调用次数：周一 128、周二 154、周三 141、周四 178、周五 196", name: "调用统计.png" },
    { id: "media-video", type: "media", kind: "video", src: trendVideo, poster: chartImage, name: "调用趋势.mp4" },
    { id: "media-audio", type: "media", kind: "audio", src: summaryAudio, name: "语音说明.m4a" },
  ];
  const messages: ConversationMessage[] = [
    { id: "media-user", role: "user", blocks: [
      { id: "media-request", type: "markdown", text: response ? "把最近 5 天的调用数据做成统计图和趋势视频，再给我一段语音说明" : "结合这张统计图、趋势视频和语音说明，总结最近 5 天的调用情况" },
      ...(response ? [] : media),
    ] },
    { id: "media-assistant", role: "assistant", status: "complete", feedback, durationMs: 4200, ttftMs: 820, tokens: 328, blocks: [
      { id: "media-result", type: "markdown", text: response ? "统计图、趋势视频和语音说明已整理好，可以直接查看或下载" : "三份资料的数据一致：最近 5 天共完成 **797 次调用**，日均 **159.4 次**\n\n- 周三略有回落，周四开始继续增长\n- 周五达到峰值 **196 次**，比周一增加 **53.1%**\n- 建议关注高峰时段的并发量和响应时间，再判断是否需要调整配额" },
      ...(response ? media : []),
    ] },
  ];
  return <ConversationFlow messages={messages} onFeedback={(_, value) => setFeedback(value)} />;
}

type AuthorizationPhase = "pending" | "authorizing" | "checking" | "error" | "complete" | "cancelled";
interface AuthorizationTiming {
  startedAt?: number;
  endedAt?: number;
  toolStartedAt?: number;
  toolEndedAt?: number;
}

function AuthorizationDemo() {
  const [phase, setPhase] = useState<AuthorizationPhase>("pending");
  const [authorized, setAuthorized] = useState(false);
  const [feedback, setFeedback] = useState<ConversationFeedback>(null);
  const [timing, setTiming] = useState<AuthorizationTiming>({});
  const timers = useRef(new Set<number>());
  const version = useRef(0);
  const clear = useCallback(() => {
    version.current += 1;
    timers.current.forEach(timer => window.clearTimeout(timer));
    timers.current.clear();
  }, []);
  useEffect(() => clear, [clear]);

  function later(delay: number, action: () => void) {
    const current = version.current;
    const timer = window.setTimeout(() => {
      timers.current.delete(timer);
      if (current === version.current) action();
    }, delay);
    timers.current.add(timer);
  }

  function authorize() {
    clear();
    setTiming({ startedAt: Date.now() });
    setPhase("authorizing");
    later(1000, () => {
      const toolStartedAt = Date.now();
      setTiming(previous => ({ ...previous, toolStartedAt }));
      setAuthorized(true);
      setPhase("checking");
    });
    later(2500, () => finish("error"));
  }
  function finish(nextPhase: "error" | "complete" | "cancelled") {
    const endedAt = Date.now();
    setTiming(previous => ({ ...previous, endedAt, toolEndedAt: previous.toolStartedAt === undefined ? undefined : endedAt }));
    setPhase(nextPhase);
  }
  function cancel() { clear(); finish("cancelled"); }
  function retry() {
    clear();
    setFeedback(null);
    if (!authorized) { setTiming({}); setPhase("pending"); return; }
    const startedAt = Date.now();
    setTiming({ startedAt, toolStartedAt: startedAt });
    setPhase("checking");
    later(1600, () => finish("complete"));
  }
  function reset() { clear(); setTiming({}); setPhase("pending"); setAuthorized(false); setFeedback(null); }
  function showError() {
    clear();
    const endedAt = Date.now();
    setTiming({ startedAt: endedAt - 2500, endedAt, toolStartedAt: endedAt - 1500, toolEndedAt: endedAt });
    setAuthorized(true);
    setPhase("error");
    setFeedback(null);
  }

  const running = phase === "authorizing" || phase === "checking";
  const status: ConversationStatus = running ? "running" : phase === "pending" ? "pending" : phase;
  const authorizationStatus: ConversationStatus = authorized ? "complete" : phase === "authorizing" ? "running" : phase === "cancelled" ? "cancelled" : "pending";
  const blocks: ConversationBlock[] = [{ id: "permission", type: "authorization", title: "授权读取私有数据源", description: "仅允许本次读取调用统计，不修改数据源", status: authorizationStatus, onAuthorize: authorize, onCancel: cancel }];
  if (authorized) blocks.push({
    id: "private-data", type: "tool", title: "读取私有调用统计", status: phase === "error" ? "error" : phase === "complete" ? "complete" : phase === "cancelled" ? "cancelled" : "running", defaultOpen: phase === "error",
    input: JSON.stringify({ source: "private-analytics", range: "last_5_days" }, null, 2),
    output: phase === "complete" ? JSON.stringify({ total: 797, days: 5 }, null, 2) : undefined,
    error: phase === "error" ? "数据源暂时不可用，请重试" : undefined,
    startedAt: timing.toolStartedAt,
    endedAt: timing.toolEndedAt,
  });
  const result = phase === "complete" ? "已读取调用统计，最近 5 天共完成 **797 次调用**" : phase === "cancelled" ? "本次请求已取消" : "";
  if (result) blocks.push({ id: "result", type: "markdown", text: result });

  return <>
    <div className="conversation-flow-preview__toolbar">
      <Button variant="secondary" onClick={reset}>重置授权</Button>
      <Button variant="secondary" onClick={showError}>失败示例</Button>
    </div>
    <ConversationFlow messages={[
      { id: "permission-user", role: "user", content: "读取私有数据源，汇总最近 5 天的调用量" },
      { id: "permission-assistant", role: "assistant", status, blocks, feedback, error: phase === "error" ? "读取未完成，你可以重新尝试" : undefined, copyText: result || undefined, startedAt: timing.startedAt, endedAt: timing.endedAt, ttftMs: phase === "complete" && timing.startedAt !== undefined && timing.endedAt !== undefined ? timing.endedAt - timing.startedAt : undefined, tokens: phase === "complete" ? 256 : undefined },
    ]} onRetry={retry} onStop={cancel} onFeedback={(_, value) => setFeedback(value)} />
  </>;
}

const scenes = [
  { value: "analysis", label: "完整分析", id: "conversation-analysis-tab", panelId: "conversation-analysis-panel" },
  { value: "rich", label: "富内容", id: "conversation-rich-tab", panelId: "conversation-rich-panel" },
  { value: "multimodal", label: "多模态输入", id: "conversation-multimodal-tab", panelId: "conversation-multimodal-panel" },
  { value: "multimodal-response", label: "多模态回复", id: "conversation-multimodal-response-tab", panelId: "conversation-multimodal-response-panel" },
  { value: "authorization", label: "授权与错误", id: "conversation-authorization-tab", panelId: "conversation-authorization-panel" },
] as const;

export function ConversationFlowPreview() {
  const [scene, setScene] = useState("analysis");
  return <section className="conversation-flow-preview" aria-labelledby="conversation-flow-preview-title">
    <h2 className="component-preview-title" id="conversation-flow-preview-title">Conversation Flow</h2>
    <UnderlineTabs items={scenes} value={scene} onValueChange={setScene} aria-label="对话流场景" />
    <div key={scene} className="conversation-flow-preview__panel" id={`conversation-${scene}-panel`} role="tabpanel" aria-labelledby={`conversation-${scene}-tab`}>
      {scene === "analysis" ? <AnalysisDemo /> : scene === "rich" ? <RichContentDemo /> : scene === "multimodal" ? <MultimodalDemo /> : scene === "multimodal-response" ? <MultimodalDemo response /> : <AuthorizationDemo />}
    </div>
    <ComponentApi names={["ConversationFlow", "ConversationMarkdown", "ConversationVisualization", "ConversationSurface"]} />
  </section>;
}
