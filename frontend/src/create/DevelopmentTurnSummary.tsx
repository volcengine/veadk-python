import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Popover } from "@base-ui/react/popover";
import type { DevelopmentTurnMetrics } from "../blocks";
import "./DevelopmentTurnSummary.css";

export function DevelopmentTurnSummary({value}: {value: DevelopmentTurnMetrics}) {
  const {t, i18n} = useTranslation("adk");
  const [open, setOpen] = useState(false);
  const format = (n: number | undefined) => n == null ? t("developmentRuns.notReported") : n.toLocaleString(i18n.resolvedLanguage || i18n.language);
  const time = (n: number | undefined) => n == null ? format(n) : `${format(n)} ms`;
  const usage = value.usage;
  const uncached = usage?.inputTokens != null && usage.cachedInputTokens != null && usage.cachedInputTokens <= usage.inputTokens
    ? usage.inputTokens - usage.cachedInputTokens : undefined;
  const hitRate = usage?.inputTokens && usage.cachedInputTokens != null && uncached != null
    ? `${(usage.cachedInputTokens / usage.inputTokens * 100).toFixed(1)}%` : undefined;
  const entries = [
    ["inputTokens", usage?.inputTokens], ["cachedInputTokens", usage?.cachedInputTokens],
    ["uncachedInputTokens", uncached], ["cacheWriteInputTokens", usage?.cacheWriteInputTokens],
    ["outputTokens", usage?.outputTokens], ["reasoningOutputTokens", usage?.reasoningOutputTokens],
  ] as const;
  return <div className="development-turn-summary" data-turn-id={value.turnId}>
    <span>{t(`developmentRuns.turnStatus.${value.status}`)}</span>
    <span>{t("developmentRuns.toolCalls", {count: value.toolCalls})}</span>
    <span>{t("developmentRuns.turnDuration", {duration: time(value.durationMs)})}</span>
    <span title={t("developmentRuns.toolDurationHelp")}>{t(value.toolDurationComplete ? "developmentRuns.toolDuration" : "developmentRuns.toolDurationPartial", {duration: time(value.toolDurationMs)})}</span>
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger className="development-token-trigger" openOnHover delay={150} closeDelay={150} onFocus={event => { if (event.currentTarget.matches(":focus-visible")) setOpen(true); }}>
        Tokens {format(usage?.totalTokens)}{value.usageIncomplete ? ` · ${t("developmentRuns.partial")}` : ""}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="top" align="end" sideOffset={8} className="development-token-positioner">
          <Popover.Popup className="development-token-popup" initialFocus={false} finalFocus={false}>
            <Popover.Title className="development-token-title">{t("developmentRuns.tokenDetails")}</Popover.Title>
            <dl>
              <div><dt>{t("developmentRuns.model")}</dt><dd>{value.model || t("developmentRuns.notReported")}</dd></div>
              <div><dt>{t("developmentRuns.totalTokens")}</dt><dd>{format(usage?.totalTokens)}</dd></div>
              {entries.map(([key, count]) => <div key={key}><dt>{t(`developmentRuns.${key}`)}</dt><dd>{format(count)}</dd></div>)}
              <div><dt>{t("developmentRuns.cacheHitRate")}</dt><dd>{hitRate || t("developmentRuns.notReported")}</dd></div>
            </dl>
            <Popover.Description className="development-token-note">{t("developmentRuns.tokenHelp")}{value.usageIncomplete ? ` ${t("developmentRuns.partialHelp")}` : ""}</Popover.Description>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  </div>;
}
