import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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

function logTime(value: string | null | undefined, locale: string): string {
  if (!value) return "";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return "";
  return new Intl.DateTimeFormat(locale, {
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
  const { t, i18n } = useTranslation("ui");
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
      <ol className="studio-build-progress__steps" aria-label={t("studioBuildProgress.steps")}>
        {steps.map((step) => (
          <li key={step.key} className={`is-${step.status}`}>
            <span className="studio-build-progress__step-icon"><StepIcon status={step.status} /></span>
            <span>{step.label}</span>
          </li>
        ))}
      </ol>

      <section className="studio-build-progress__log" aria-label={t("studioBuildProgress.log")}>
        <header>
          <div>
            <strong>{t("studioBuildProgress.log")}</strong>
            <span>
              {loading ? t("studioBuildProgress.syncing") : logError ? t("studioBuildProgress.loadFailed") : t("studioBuildProgress.synced")}
              {logTruncated ? t("studioBuildProgress.recentOnly") : ""}
              {logTime(logUpdatedAt, i18n.resolvedLanguage ?? i18n.language) ? ` · ${logTime(logUpdatedAt, i18n.resolvedLanguage ?? i18n.language)}` : ""}
            </span>
          </div>
          <Button
            type="button"
            color="secondary"
            variant="ghost"
            size="sm"
            disabled={!log}
            onClick={() => void copyLog()}
            aria-label={copied ? t("studioBuildProgress.copiedLog") : t("studioBuildProgress.copyLog")}
          >
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            {copied ? t("studioBuildProgress.copied") : t("studioBuildProgress.copy")}
          </Button>
        </header>
        {log ? (
          <pre
            ref={logRef}
            tabIndex={0}
            aria-label={t("studioBuildProgress.logContent")}
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
            {logError || (loading ? t("studioBuildProgress.waiting") : t("studioBuildProgress.empty"))}
          </div>
        )}
      </section>
    </div>
  );
}
