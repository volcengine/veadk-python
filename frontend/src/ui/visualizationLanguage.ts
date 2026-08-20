export type VisualizationLanguage = "mermaid" | "echarts";

export function normalizeVisualizationLanguage(
  language: string | undefined,
): VisualizationLanguage | undefined {
  const normalized = language?.trim().toLowerCase();
  if (normalized === "mermaid") return "mermaid";
  if (normalized === "echart" || normalized === "echarts") return "echarts";
  return undefined;
}
