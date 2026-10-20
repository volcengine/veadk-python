import { Children, isValidElement, memo, useEffect, useId, useMemo, useRef, useState, type ReactNode, type RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ECharts } from "echarts";
import { CodeBlock } from "../../composites/CodeBlock";
import { InfoCard, InfoCardBody } from "../../composites/InfoCard";
import { ModalButton } from "../../composites/ModalButton";
import { Button } from "../../primitives/Button";
import { ErrorState } from "../../primitives/ErrorState";
import { Loading } from "../../primitives/Loading";
import { ScrollArea } from "../../primitives/ScrollArea";
import { Table } from "../../primitives/Table";
import { UnderlineTabs } from "../../primitives/UnderlineTabs";
import { parseEChartsOption } from "../../../ui/echartsOption";
import { normalizeVisualizationLanguage } from "../../../ui/visualizationLanguage";
import "./ConversationRichContent.css";

export interface ConversationMarkdownProps {
  /** 最终回复或过程中的 Markdown，支持 GFM 表格与代码块 */
  text: string;
  /** 流式生成时，未闭合的图表代码先展示源码 */
  streaming?: boolean;
}

export interface ConversationVisualizationProps {
  kind: "echarts" | "mermaid";
  /** ECharts 使用安全的数据对象语法，Mermaid 使用图表定义 */
  source: string;
  title?: string;
  /** 等待完整定义后再渲染，避免半段配置报错或图表闪动 */
  streaming?: boolean;
}

type ChartApi = typeof import("echarts");
type MermaidApi = (typeof import("mermaid"))["default"];
type RenderedMermaid = Awaited<ReturnType<MermaidApi["render"]>>;

interface VisualizationTheme {
  text: string;
  secondary: string;
  tertiary: string;
  subtle: string;
  border: string;
  panel: string;
  fill: string;
  font: string;
  dark: boolean;
  reducedMotion: boolean;
}

let chartsPromise: Promise<ChartApi> | undefined;
let mermaidPromise: Promise<MermaidApi> | undefined;
let mermaidQueue = Promise.resolve();
let mermaidSequence = 0;

function loadCharts() {
  chartsPromise ??= import("echarts").catch(error => {
    chartsPromise = undefined;
    throw error;
  });
  return chartsPromise;
}

function loadMermaid() {
  mermaidPromise ??= import("mermaid").then(module => module.default).catch(error => {
    mermaidPromise = undefined;
    throw error;
  });
  return mermaidPromise;
}

function renderMermaid(source: string, theme: VisualizationTheme): Promise<RenderedMermaid> {
  const task = mermaidQueue.then(async () => {
    if (source.length > 50_000) throw new Error("Diagram exceeds the supported size");
    const mermaid = await loadMermaid();
    // Configuration and rendering share a queue because Mermaid keeps global configuration
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      suppressErrorRendering: true,
      maxTextSize: 50_000,
      theme: "base",
      fontFamily: theme.font,
      secure: ["secure", "securityLevel", "startOnLoad", "maxTextSize", "suppressErrorRendering", "theme", "themeVariables", "themeCSS", "fontFamily"],
      themeVariables: {
        darkMode: theme.dark,
        fontFamily: theme.font,
        fontSize: "14px",
        background: theme.panel,
        primaryColor: theme.fill,
        primaryTextColor: theme.text,
        primaryBorderColor: theme.border,
        secondaryColor: theme.panel,
        secondaryTextColor: theme.text,
        secondaryBorderColor: theme.border,
        tertiaryColor: theme.fill,
        tertiaryTextColor: theme.text,
        tertiaryBorderColor: theme.border,
        lineColor: theme.secondary,
        textColor: theme.text,
        mainBkg: theme.fill,
        nodeBorder: theme.border,
        clusterBkg: theme.panel,
        clusterBorder: theme.border,
        edgeLabelBackground: theme.panel,
        titleColor: theme.text,
        actorBkg: theme.fill,
        actorTextColor: theme.text,
        actorBorder: theme.border,
        actorLineColor: theme.border,
        signalColor: theme.secondary,
        signalTextColor: theme.text,
        noteBkgColor: theme.fill,
        noteTextColor: theme.text,
        noteBorderColor: theme.border,
      },
    });
    return mermaid.render(`studio-conversation-diagram-${++mermaidSequence}`, source);
  });
  mermaidQueue = task.then(() => undefined, () => undefined);
  return task;
}

function useVisualizationTheme(element: RefObject<HTMLElement | null>) {
  const [theme, setTheme] = useState<VisualizationTheme | null>(null);
  useEffect(() => {
    const node = element.current;
    if (!node) return;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    function update() {
      const style = getComputedStyle(node!);
      const token = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
      const next: VisualizationTheme = {
        text: token("--studio-text-primary", style.color),
        secondary: token("--studio-text-secondary", style.color),
        tertiary: token("--studio-text-tertiary", style.color),
        subtle: token("--studio-text-subtle", style.color),
        border: token("--studio-border-subtle", style.color),
        panel: token("--studio-bg-panel", style.backgroundColor),
        fill: token("--studio-bg-secondary", style.backgroundColor),
        font: token("--studio-font-family-ui", style.fontFamily),
        dark: node!.closest("[data-theme]")?.getAttribute("data-theme") !== "light",
        reducedMotion: motion.matches,
      };
      setTheme(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    }
    update();
    const observer = new MutationObserver(update);
    for (let ancestor: HTMLElement | null = node; ancestor; ancestor = ancestor.parentElement) {
      observer.observe(ancestor, { attributes: true, attributeFilter: ["data-theme", "class", "style"] });
    }
    motion.addEventListener("change", update);
    return () => {
      observer.disconnect();
      motion.removeEventListener("change", update);
    };
  }, [element]);
  return theme;
}

function chartTheme(theme: VisualizationTheme) {
  const axis = {
    axisLine: { lineStyle: { color: theme.border } },
    axisTick: { lineStyle: { color: theme.border } },
    axisLabel: { color: theme.secondary, fontFamily: theme.font, fontSize: 12 },
    nameTextStyle: { color: theme.secondary, fontFamily: theme.font, fontSize: 12 },
    splitLine: { lineStyle: { color: theme.border } },
    splitArea: { areaStyle: { color: ["transparent", theme.fill] } },
  };
  return {
    color: [theme.text, theme.tertiary, theme.subtle, theme.secondary],
    backgroundColor: "transparent",
    textStyle: { color: theme.text, fontFamily: theme.font, fontSize: 12 },
    title: { textStyle: { color: theme.text, fontSize: 14, fontWeight: 400 }, subtextStyle: { color: theme.secondary } },
    legend: { textStyle: { color: theme.secondary, fontFamily: theme.font, fontSize: 12 } },
    tooltip: { backgroundColor: theme.panel, borderColor: theme.border, textStyle: { color: theme.text, fontFamily: theme.font, fontSize: 12 } },
    categoryAxis: axis,
    valueAxis: axis,
    timeAxis: axis,
    logAxis: axis,
    radar: { axisLine: axis.axisLine, splitLine: axis.splitLine, splitArea: axis.splitArea, axisName: { color: theme.secondary } },
    line: { symbolSize: 5 },
    graph: { color: [theme.text, theme.tertiary, theme.subtle] },
  };
}

function VisualizationError({ invalid = false }: { invalid?: boolean }) {
  return <div role="alert" className="studio-conversation-rich-visual__error">
    <ErrorState title={invalid ? "图表定义无法解析" : "图表暂时无法显示"} description="可以切换到源码查看完整内容" />
  </div>;
}

function EChartsPreview({ source, title, theme }: { source: string; title: string; theme: VisualizationTheme }) {
  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "invalid" | "error">("loading");
  useEffect(() => {
    let cancelled = false;
    let chart: ECharts | undefined;
    let observer: ResizeObserver | undefined;
    const resize = () => chart?.resize();
    setStatus("loading");
    let option;
    try {
      option = parseEChartsOption(source, theme.reducedMotion);
    } catch {
      setStatus("invalid");
      return;
    }
    const presentation = chartTheme(theme);
    void loadCharts().then(echarts => {
      if (cancelled || !container.current) return;
      chart = echarts.init(container.current, presentation, { renderer: "svg" });
      chart.setOption({
        ...option,
        color: option.color ?? presentation.color,
        backgroundColor: "transparent",
        textStyle: { ...option.textStyle, ...presentation.textStyle },
        animation: !theme.reducedMotion && option.animation !== false,
        animationDuration: theme.reducedMotion ? 0 : 240,
        animationDurationUpdate: theme.reducedMotion ? 0 : 160,
      }, { notMerge: true });
      if (typeof ResizeObserver !== "undefined") {
        observer = new ResizeObserver(resize);
        observer.observe(container.current);
      } else {
        window.addEventListener("resize", resize);
      }
      setStatus("ready");
    }).catch(() => {
      chart?.dispose();
      chart = undefined;
      if (!cancelled) setStatus("error");
    });
    return () => {
      cancelled = true;
      observer?.disconnect();
      window.removeEventListener("resize", resize);
      chart?.dispose();
    };
  }, [source, theme]);
  const failed = status === "invalid" || status === "error";
  return <div className="studio-conversation-rich-visual__chart" aria-busy={status === "loading"}>
    <div ref={container} className="studio-conversation-rich-visual__canvas" role="img" aria-label={title} hidden={failed} />
    {status === "loading" && <div className="studio-conversation-rich-visual__loading"><Loading size={24} label="正在渲染图表" /></div>}
    {failed && <VisualizationError invalid={status === "invalid"} />}
  </div>;
}

function VisualIcon({ kind }: { kind: "expand" | "minus" | "plus" | "reset" }) {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {kind === "expand" ? <path d="M6 2.5H2.5V6m7.5-3.5h3.5V6m0 4v3.5H10M6 13.5H2.5V10" />
      : kind === "minus" ? <path d="M3.5 8h9" />
        : kind === "plus" ? <path d="M3.5 8h9M8 3.5v9" />
          : <><path d="M3 5.5A5.1 5.1 0 1 1 3 10M3 2.5v3H6" /></>}
  </svg>;
}

function MermaidPreview({ source, title, theme }: { source: string; title: string; theme: VisualizationTheme }) {
  const container = useRef<HTMLDivElement>(null);
  const [rendered, setRendered] = useState<RenderedMermaid | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(1);
  useEffect(() => {
    let cancelled = false;
    setRendered(null);
    setFailed(false);
    void renderMermaid(source, theme).then(result => {
      if (!cancelled) setRendered(result);
    }).catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => { cancelled = true; };
  }, [source, theme]);
  useEffect(() => {
    if (container.current) rendered?.bindFunctions?.(container.current);
  }, [rendered]);
  if (failed) return <VisualizationError invalid />;
  if (!rendered) return <div className="studio-conversation-rich-visual__placeholder"><Loading size={24} label="正在渲染图表" /></div>;
  return <>
    <ScrollArea orientation="both" maxHeight={440} className="studio-conversation-rich-visual__diagram-scroll" tabIndex={0} role="region" aria-label={`${title}图表滚动区域`}>
      <div className="studio-conversation-rich-visual__diagram-size" style={{ width: `${zoom * 100}%` }}>
        <div ref={container} className="studio-conversation-rich-visual__mermaid" role="img" aria-label={title} dangerouslySetInnerHTML={{ __html: rendered.svg }} />
      </div>
    </ScrollArea>
    <div className="studio-conversation-rich-visual__zoom" role="group" aria-label="图表缩放">
      <Button variant="ghost" iconOnly size="compact" aria-label="缩小图表" disabled={zoom <= .5} startIcon={<VisualIcon kind="minus" />} onClick={() => setZoom(current => Math.max(.5, current - .25))} />
      <span aria-live="polite">{Math.round(zoom * 100)}%</span>
      <Button variant="ghost" iconOnly size="compact" aria-label="放大图表" disabled={zoom >= 2.5} startIcon={<VisualIcon kind="plus" />} onClick={() => setZoom(current => Math.min(2.5, current + .25))} />
      <Button variant="ghost" iconOnly size="compact" aria-label="重置图表缩放" startIcon={<VisualIcon kind="reset" />} onClick={() => setZoom(1)} />
    </div>
  </>;
}

function VisualizationFrame({ kind, source, title = kind === "echarts" ? "数据图表" : "流程图", streaming = false, expanded = false }: ConversationVisualizationProps & { expanded?: boolean }) {
  const id = useId();
  const ref = useRef<HTMLElement>(null);
  const theme = useVisualizationTheme(ref);
  const [selectedTab, setSelectedTab] = useState("preview");
  const view = streaming ? "source" : selectedTab;
  return <InfoCard ref={ref} title={title} className="studio-conversation-rich-visual" data-kind={kind} data-expanded={expanded || undefined} actions={
    streaming ? <Loading size={24} label="正在生成图表定义" />
      : !expanded ? <ModalButton label={`展开${title}`} title={title} topGlow={false} closeLabel="关闭图表" data-theme={theme ? theme.dark ? "dark" : "light" : undefined} className="studio-conversation-rich-visual__modal" buttonProps={{ variant: "ghost", iconOnly: true, startIcon: <VisualIcon kind="expand" />, "aria-label": `展开${title}` }}>
        <VisualizationFrame kind={kind} source={source} title={title} expanded />
      </ModalButton> : undefined
  }>
    <InfoCardBody className="studio-conversation-rich-visual__body">
      {!streaming && <UnderlineTabs aria-label={`${title}展示方式`} value={view} onValueChange={setSelectedTab} items={[
        { value: "preview", label: "预览", id: `${id}-preview-tab`, panelId: `${id}-preview` },
        { value: "source", label: "源码", id: `${id}-source-tab`, panelId: `${id}-source` },
      ]} />}
      <div id={`${id}-${view}`} role={streaming ? undefined : "tabpanel"} aria-labelledby={streaming ? undefined : `${id}-${view}-tab`} className="studio-conversation-rich-visual__panel">
        {view === "source" ? <CodeBlock title={kind === "echarts" ? "ECharts option" : "Mermaid"} language={kind === "echarts" ? "javascript" : "plaintext"} lines={source.split("\n")} scrollAreaProps={{ orientation: "both", maxHeight: expanded ? 600 : 320 }} />
          : theme ? kind === "echarts" ? <EChartsPreview source={source} title={title} theme={theme} /> : <MermaidPreview source={source} title={title} theme={theme} />
            : <div className="studio-conversation-rich-visual__placeholder"><Loading size={24} label="正在渲染图表" /></div>}
      </div>
    </InfoCardBody>
  </InfoCard>;
}

/** 安全的图表预览，复用组件库的卡片、标签页、代码块、弹窗和加载状态 */
export const ConversationVisualization = memo(function ConversationVisualization(props: ConversationVisualizationProps) {
  return <VisualizationFrame {...props} />;
});

type MarkdownElementProps = { children?: ReactNode; className?: string; style?: { textAlign?: "left" | "center" | "right" } };
function elements(children: ReactNode) {
  return Children.toArray(children).filter(isValidElement<MarkdownElementProps>);
}

function MarkdownTable({ children }: { children?: ReactNode }) {
  const sections = elements(children);
  const header = sections.find(section => section.type === "thead");
  const body = sections.find(section => section.type === "tbody");
  const firstRow = header ? elements(header.props.children)[0] : undefined;
  const headings = firstRow ? elements(firstRow.props.children) : [];
  const rows = body ? elements(body.props.children).map((row, index) => ({ id: index, cells: elements(row.props.children).map(cell => cell.props.children) })) : [];
  return <Table
    aria-label="回复中的表格"
    className="studio-conversation-rich-markdown__table"
    columns={headings.map((cell, index) => ({ key: String(index), title: cell.props.children, align: cell.props.style?.textAlign, render: (row: typeof rows[number]) => row.cells[index] }))}
    data={rows}
    rowKey={row => row.id}
    layout="auto"
    minWidth={Math.max(320, headings.length * 112)}
    maxHeight={360}
    hideScrollbar={false}
  />;
}

function isClosedFence(source: string) {
  const lines = source.trimEnd().split("\n");
  const opening = lines[0]?.match(/^\s{0,3}(`{3,}|~{3,})/);
  if (!opening || lines.length < 2) return false;
  const closing = lines[lines.length - 1]?.trim();
  return new RegExp(`^${opening[1][0]}{${opening[1].length},}$`).test(closing);
}

/** 普通代码、图表和表格均复用现有组件，不解析原始 HTML */
export const ConversationMarkdown = memo(function ConversationMarkdown({ text, streaming = false }: ConversationMarkdownProps) {
  const plugins = useMemo(() => [remarkGfm], []);
  return <div className="studio-conversation-rich-markdown" data-streaming={streaming || undefined}>
    <ReactMarkdown remarkPlugins={plugins} skipHtml components={{
      pre({ children, node }) {
        const code = elements(children)[0];
        const content = typeof code?.props.children === "string" ? code.props.children.replace(/\n$/, "") : String(code?.props.children ?? "");
        const language = code?.props.className?.match(/language-([^\s]+)/)?.[1]?.toLowerCase() ?? "plaintext";
        const visualization = normalizeVisualizationLanguage(language);
        if (visualization) {
          const start = node?.position?.start.offset;
          const end = node?.position?.end.offset;
          const pending = streaming && (start == null || end == null || !isClosedFence(text.slice(start, end)));
          return <ConversationVisualization kind={visualization} source={content} streaming={pending} />;
        }
        return <CodeBlock title={language === "plaintext" ? "代码" : language} language={language} lines={content.split("\n")} scrollAreaProps={{ orientation: "both", maxHeight: 360 }} />;
      },
      table: MarkdownTable,
      a({ children, href, title }) {
        const external = href ? /^https?:\/\//i.test(href) : false;
        return <a href={href} title={title} target={external ? "_blank" : undefined} rel={external ? "noopener noreferrer" : undefined}>{children}</a>;
      },
      img({ src, alt, title }) {
        return <img src={src} alt={alt ?? ""} title={title} loading="lazy" />;
      },
    }}>{text}</ReactMarkdown>
  </div>;
});
