import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SandboxTokenUsage } from "../adk/sandbox";
import type { TurnActivity } from "../blocks";
import { InsightIcon } from "./icons/InsightIcon";
import "./SandboxSession.css";

export interface SandboxEntryButtonProps {
  variant: "composer" | "header";
  active?: boolean;
  onClick: () => void;
}

export function SandboxEntryButton({
  variant,
  active = false,
  onClick,
}: SandboxEntryButtonProps) {
  const { t } = useTranslation("sandbox");
  return (
    <button
      type="button"
      className={`sandbox-entry sandbox-entry--${variant}${active ? " is-active" : ""}`}
      onClick={onClick}
      disabled={active}
      aria-label={active ? t("session.activeAria") : t("session.openAria")}
    >
      <InsightIcon />
      <span>{active ? t("session.active") : t("session.entry")}</span>
    </button>
  );
}

export function SandboxSessionWarning({
  agentName,
  expireAt,
  exitLabel,
  onExit,
}: {
  agentName: string;
  expireAt?: string;
  exitLabel?: string;
  onExit: () => void;
}) {
  const { t, i18n } = useTranslation("sandbox");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!expireAt) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, [expireAt]);
  const expiry = expireAt ? Date.parse(expireAt) : Number.NaN;
  const remainingMinutes = Number.isFinite(expiry)
    ? Math.max(0, Math.ceil((expiry - now) / 60_000))
    : null;
  const remaining = remainingMinutes === null
    ? ""
    : remainingMinutes === 0
      ? t("session.expired")
      : remainingMinutes >= 60
        ? t("session.remainingHours", {
            hours: Math.floor(remainingMinutes / 60),
            minutes: remainingMinutes % 60,
          })
        : t("session.remainingMinutes", { minutes: remainingMinutes });
  const expiryLabel = Number.isFinite(expiry)
    ? new Date(expiry).toLocaleString(
        i18n.resolvedLanguage ?? i18n.language,
        {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        },
      )
    : "";
  return (
    <div
      className={`sandbox-session-warning${expireAt ? " is-expiring" : ""}`}
      role="status"
    >
      <span className="sandbox-session-warning-dot" aria-hidden="true" />
      <span className="sandbox-session-warning-copy">
        {expiryLabel
          ? t("session.expiryWarning", { expiry: expiryLabel, remaining })
          : t("session.usingAgent", { agent: agentName })}
      </span>
      <button type="button" onClick={onExit}>
        {exitLabel ?? t("session.exit")}
      </button>
    </div>
  );
}

export function SandboxActivityRecord({
  activity,
  time,
}: {
  activity: TurnActivity;
  time?: string;
}) {
  const { t } = useTranslation("sandbox");
  return (
    <aside
      className="sandbox-activity-record"
      role="status"
      aria-label={t("session.activityAria")}
    >
      <div className="sandbox-activity-summary">
        <span className="sandbox-activity-dot" aria-hidden="true" />
        <span className="sandbox-activity-label">{t("session.activity")}</span>
        <strong>{activity.title}</strong>
        {time ? <time>{time}</time> : null}
      </div>
      {activity.details?.length ? (
        <dl className="sandbox-activity-details">
          {activity.details.map((detail) => (
            <div key={`${detail.label}:${detail.value}`}>
              <dt>{detail.label}</dt>
              <dd title={detail.value}>
                {detail.code ? <code>{detail.value}</code> : detail.value}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </aside>
  );
}

function compactTokenCount(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  }
  return String(value);
}

export function SandboxTokenUsageRow({ usage }: { usage: SandboxTokenUsage }) {
  const { t, i18n } = useTranslation("sandbox");
  const entries = [
    ["total", t("session.tokenLabels.total"), usage.totalTokens],
    ["input", t("session.tokenLabels.input"), usage.inputTokens],
    ...(usage.cachedInputTokens > 0
      ? [["cachedInput", t("session.tokenLabels.cachedInput"), usage.cachedInputTokens] as const]
      : []),
    ["output", t("session.tokenLabels.output"), usage.outputTokens],
    ...(usage.reasoningOutputTokens > 0
      ? [["reasoningOutput", t("session.tokenLabels.reasoningOutput"), usage.reasoningOutputTokens] as const]
      : []),
  ] as const;
  const locale = i18n.resolvedLanguage ?? i18n.language;
  return (
    <div className="sandbox-token-usage" aria-label={t("session.tokenUsageAria")}>
      {entries.map(([key, label, value]) => (
        <span
          key={key}
          title={t("session.tokens", { label, value: value.toLocaleString(locale) })}
        >
          <small>{label}</small>
          <strong>{compactTokenCount(value)}</strong>
        </span>
      ))}
    </div>
  );
}
