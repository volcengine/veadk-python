import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Circle, CircleX, Copy, Loader2 } from "lucide-react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import type { EnvironmentBuildStep } from "../adk/client";
import { highlightBashLog, shouldFollowBuildLog } from "./studioBuildLog";
import "./StudioBuildProgress.css";

export interface StudioBuildProgressProps {
  steps: EnvironmentBuildStep[];
  log: string;
  logError?: string;
  logTruncated?: boolean;
  logUpdatedAt?: string | null;
  loading?: boolean;
}

function StepIcon({ status }: { status: EnvironmentBuildStep["status"] }) {
  if (status === "succeeded") return <Check aria-hidden />;
  if (status === "failed") return <CircleX aria-hidden />;
  if (status === "running") return <Loader2 className="studio-build-progress__spinner" aria-hidden />;
  return <Circle aria-hidden />;
}

function logTime(value?: string | null): string {
  if (!value) return "";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(timestamp);
}

export function StudioBuildProgress({
  steps,
  log,
  logError = "",
  logTruncated = false,
  logUpdatedAt,
  loading = false,
}: StudioBuildProgressProps) {
  const logRef = useRef<HTMLPreElement>(null);
  const followLogRef = useRef(true);
  const [copied, setCopied] = useState(false);
  const highlightedLog = useMemo(() => highlightBashLog(log), [log]);

  useEffect(() => {
    const node = logRef.current;
    if (node && log && followLogRef.current) node.scrollTop = node.scrollHeight;
  }, [log]);

  const copyLog = async () => {
    try {
      await navigator.clipboard.writeText(log);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="studio-build-progress">
      <ol className="studio-build-progress__steps" aria-label="构建步骤">
        {steps.map((step) => (
          <li key={step.key} className={`is-${step.status}`}>
            <span className="studio-build-progress__step-icon"><StepIcon status={step.status} /></span>
            <span>{step.label}</span>
          </li>
        ))}
      </ol>

      <section className="studio-build-progress__log" aria-label="构建日志">
        <header>
          <div>
            <strong>构建日志</strong>
            <span>
              {loading ? "同步中" : logError ? "读取失败" : "已同步"}
              {logTruncated ? " · 仅显示最近日志" : ""}
              {logTime(logUpdatedAt) ? ` · ${logTime(logUpdatedAt)}` : ""}
            </span>
          </div>
          <Button
            type="button"
            color="secondary"
            variant="ghost"
            size="sm"
            disabled={!log}
            onClick={() => void copyLog()}
            aria-label={copied ? "已复制构建日志" : "复制构建日志"}
          >
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? "已复制" : "复制"}
          </Button>
        </header>
        {log ? (
          <pre
            ref={logRef}
            tabIndex={0}
            aria-label="构建日志内容"
            onScroll={(event) => {
              followLogRef.current = shouldFollowBuildLog(event.currentTarget);
            }}
          >
            <code
              className="hljs language-bash"
              dangerouslySetInnerHTML={{ __html: highlightedLog }}
            />
          </pre>
        ) : (
          <div className={`studio-build-progress__log-empty${logError ? " is-error" : ""}`}>
            {logError || (loading ? "正在等待 CodePipeline 输出日志…" : "暂无构建日志")}
          </div>
        )}
      </section>
    </div>
  );
}
