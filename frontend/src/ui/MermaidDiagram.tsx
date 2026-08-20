import { memo, useEffect, useRef, useState } from "react";
import { TextShimmer } from "./text-shimmer/TextShimmer";

type MermaidApi = (typeof import("mermaid"))["default"];
type BindFunctions = (element: Element) => void;

interface RenderedDiagram {
  svg: string;
  bindFunctions?: BindFunctions;
}

interface MermaidDiagramProps {
  source: string;
}

let mermaidPromise: Promise<MermaidApi> | undefined;
let renderQueue = Promise.resolve();
let diagramSequence = 0;

function loadMermaid(): Promise<MermaidApi> {
  mermaidPromise ??= import("mermaid").then(({ default: mermaid }) => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      suppressErrorRendering: true,
      theme: "neutral",
    });
    return mermaid;
  });
  return mermaidPromise;
}

function renderMermaid(source: string): Promise<RenderedDiagram> {
  const task = renderQueue.then(async () => {
    const mermaid = await loadMermaid();
    const id = `mermaid-diagram-${diagramSequence += 1}`;
    return mermaid.render(id, source);
  });
  renderQueue = task.then(() => undefined, () => undefined);
  return task;
}

function MermaidDiagramImpl({ source }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [rendered, setRendered] = useState<RenderedDiagram | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRendered(null);
    setFailed(false);
    void renderMermaid(source)
      .then((result) => {
        if (cancelled) return;
        setRendered(result);
      })
      .catch(() => {
        if (cancelled) return;
        setFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [source]);

  useEffect(() => {
    if (!rendered?.bindFunctions || !containerRef.current) return;
    rendered.bindFunctions(containerRef.current);
  }, [rendered]);

  if (failed) {
    return (
      <div className="mermaid-diagram mermaid-diagram--error">
        <p className="mermaid-diagram__error" role="alert">
          图表暂时无法渲染，请切换到代码查看 Mermaid 内容。
        </p>
      </div>
    );
  }

  if (!rendered) {
    return (
      <div className="mermaid-diagram mermaid-diagram--loading" aria-live="polite">
        <TextShimmer duration={2.2} spread={15}>正在渲染图表…</TextShimmer>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="mermaid-diagram"
      role="img"
      aria-label="Mermaid 图表预览"
      dangerouslySetInnerHTML={{ __html: rendered.svg }}
    />
  );
}

export const MermaidDiagram = memo(MermaidDiagramImpl);
