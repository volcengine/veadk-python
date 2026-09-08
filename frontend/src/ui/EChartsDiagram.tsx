import { memo, useEffect, useRef, useState } from "react";
import type { ECharts, EChartsOption } from "echarts";
import { parseEChartsOption } from "./echartsOption";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation("conversation");
  const containerRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<"invalid" | "render" | "">("");

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
      setError("invalid");
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
        if (!cancelled) setError("render");
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
      aria-label={t("visualization.echartsAria")}
      aria-busy={!ready && !error}
    >
      <div ref={containerRef} className="echarts-diagram__canvas" hidden={Boolean(error)} />
      {!ready && !error ? (
        <div className="echarts-diagram__state" aria-live="polite">
          <TextShimmer duration={2.2} spread={15}>{t("visualization.rendering")}</TextShimmer>
        </div>
      ) : null}
      {error ? (
        <p className="echarts-diagram__error" role="alert">
          {t(error === "invalid" ? "visualization.invalidEcharts" : "visualization.renderFailed")}
        </p>
      ) : null}
    </div>
  );
}

export const EChartsDiagram = memo(EChartsDiagramImpl);
