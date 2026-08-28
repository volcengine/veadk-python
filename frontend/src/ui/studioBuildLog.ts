import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";

hljs.registerLanguage("bash", bash);

export const BUILD_LOG_FOLLOW_THRESHOLD_PX = 48;

interface BuildLogScrollMetrics {
  scrollHeight: number;
  scrollTop: number;
  clientHeight: number;
}

export function shouldFollowBuildLog(
  metrics: BuildLogScrollMetrics,
  threshold = BUILD_LOG_FOLLOW_THRESHOLD_PX,
): boolean {
  return metrics.scrollHeight - metrics.scrollTop - metrics.clientHeight <= threshold;
}

export function highlightBashLog(log: string): string {
  return hljs.highlight(log, {
    language: "bash",
    ignoreIllegals: true,
  }).value;
}
