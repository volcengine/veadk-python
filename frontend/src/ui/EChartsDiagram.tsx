import { memo, useEffect, useRef, useState } from "react";
import type { ECharts, EChartsOption } from "echarts";
import { parseEChartsOption } from "./echartsOption";
import { TextShimmer } from "./text-shimmer/TextShimmer";

type EChartsApi = typeof import("echarts");

interface EChartsDiagramProps {
  source: string;
}

let echartsPromise: Promise<EChartsApi> | undefined;

function loadECharts(): Promise<EChartsApi> {
  echartsPromise ??= import("echarts").catch((error) => {
    echartsPromise = undefined;
    throw error;
  });
  return echartsPromise;
}

function EChartsDiagramImpl({ source }: EChartsDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let chart: ECharts | undefined;
    let resizeObserver: ResizeObserver | undefined;
    let option: EChartsOption;

    setReady(false);
    try {
      option = parseEChartsOption(
        source,
        window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      );
      setError("");
    } catch {
      setError("ECharts 配置不是有效且安全的数据对象，请切换到代码检查内容。");
      return;
    }

    void loadECharts()
      .then((echarts) => {
        const container = containerRef.current;
        if (cancelled || !container) return;
        chart = echarts.init(container, undefined, { renderer: "svg" });
        chart.setOption(option, { notMerge: true });
        if (typeof ResizeObserver !== "undefined") {
          resizeObserver = new ResizeObserver(() => chart?.resize());
          resizeObserver.observe(container);
        }
        setReady(true);
      })
      .catch(() => {
        chart?.dispose();
        chart = undefined;
        if (!cancelled) setError("图表暂时无法渲染，请切换到代码检查内容。");
      });

    return () => {
      cancelled = true;
      resizeObserver?.disconnect();
      chart?.dispose();
    };
  }, [source]);

  return (
    <div
      className={`echarts-diagram${error ? " echarts-diagram--error" : ""}`}
      role="img"
      aria-label="ECharts 图表预览"
      aria-busy={!ready && !error}
    >
      <div ref={containerRef} className="echarts-diagram__canvas" hidden={Boolean(error)} />
      {!ready && !error ? (
        <div className="echarts-diagram__state" aria-live="polite">
          <TextShimmer duration={2.2} spread={15}>正在渲染图表…</TextShimmer>
        </div>
      ) : null}
      {error ? (
        <p className="echarts-diagram__error" role="alert">{error}</p>
      ) : null}
    </div>
  );
}

export const EChartsDiagram = memo(EChartsDiagramImpl);
