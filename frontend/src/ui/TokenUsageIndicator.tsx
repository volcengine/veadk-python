import { useId } from "react";
import { Trans, useTranslation } from "react-i18next";
import type { CloudProvider } from "../adk/cloudProvider";
import { contextWindowForModel } from "../adk/modelContextWindows";
import {
  buildContextGrid,
  contextComposition,
  type ContextSegmentKind,
  type SessionTokenUsage,
} from "../adk/tokenUsage";

interface TokenUsageIndicatorProps {
  cloudProvider: CloudProvider;
  modelName: string;
  usage: SessionTokenUsage;
  systemTokenEstimate: number | null;
}

function compactTokenCount(value: number, integerFormat: Intl.NumberFormat): string {
  if (value >= 1_000) {
    return `${Number((value / 1_000).toFixed(1))}K`;
  }
  return integerFormat.format(value);
}

function summaryTokenCount(value: number, integerFormat: Intl.NumberFormat): string {
  if (value >= 1_000) {
    return `${Number((value / 1_000).toFixed(1))}K`;
  }
  return `${integerFormat.format(value)} Token`;
}

function summaryPercentage(value: number): string {
  return `${Number(value.toFixed(2))}%`;
}

export function TokenUsageIndicator({
  cloudProvider,
  modelName,
  usage,
  systemTokenEstimate,
}: TokenUsageIndicatorProps) {
  const { t, i18n } = useTranslation("conversation");
  const tooltipId = useId();
  const integerFormat = new Intl.NumberFormat(i18n.resolvedLanguage ?? i18n.language);
  const segmentLabel = (kind: ContextSegmentKind) => t(`tokenUsage.segments.${kind}`);
  const contextWindow = contextWindowForModel(modelName, cloudProvider);
  const composition = contextWindow
    ? contextComposition({
        usage,
        contextWindow,
        estimatedSystemTokens: systemTokenEstimate,
      })
    : null;
  const currentTokens = composition?.usedTokens ?? usage.current.totalTokenCount;
  const rawPercentage = contextWindow
    ? (currentTokens / contextWindow) * 100
    : null;
  const roundedPercentage = rawPercentage === null
    ? null
    : Math.round(rawPercentage);
  const percentageLabel = rawPercentage !== null && rawPercentage > 0 && rawPercentage < 1
    ? "<1"
    : String(roundedPercentage ?? 0);
  const ringPercentage = rawPercentage === null
    ? 0
    : Math.min(100, Math.max(0, rawPercentage));
  const remainingPercentage = 100 - ringPercentage;
  const modelLabel = modelName.trim() || t("tokenUsage.modelUnavailable");
  const inputSegmentLabel = systemTokenEstimate === null
    ? t("tokenUsage.promptWithSystem")
    : segmentLabel("input");
  const overflowTokens = composition
    ? Math.max(0, composition.usedTokens - composition.contextWindow)
    : 0;
  const systemAriaLabel = systemTokenEstimate === null
    ? t("tokenUsage.systemUnknown")
    : t("tokenUsage.systemApprox", { count: integerFormat.format(composition?.systemTokens ?? 0) });
  const ariaLabel = composition
    ? t("tokenUsage.ariaKnown", {
        percentage: percentageLabel,
        system: systemAriaLabel,
        inputLabel: inputSegmentLabel,
        input: integerFormat.format(composition.inputTokens),
        output: integerFormat.format(composition.outputTokens),
        remaining: integerFormat.format(composition.remainingTokens),
      })
    : t("tokenUsage.ariaUnknown", {
        model: modelLabel,
        count: integerFormat.format(usage.cumulative.totalTokenCount),
      });
  const cells = composition ? buildContextGrid(composition) : [];
  const legend = composition
    ? [
        { kind: "system" as const, tokens: composition.systemTokens },
        { kind: "input" as const, tokens: composition.inputTokens },
        { kind: "output" as const, tokens: composition.outputTokens },
        { kind: "remaining" as const, tokens: composition.remainingTokens },
      ]
    : [];

  return (
    <div
      className="token-usage-indicator"
      tabIndex={0}
      role={contextWindow === null ? "status" : "meter"}
      aria-label={ariaLabel}
      aria-describedby={tooltipId}
      aria-valuemin={contextWindow === null ? undefined : 0}
      aria-valuemax={contextWindow ?? undefined}
      aria-valuenow={
        contextWindow === null
          ? undefined
          : Math.min(currentTokens, contextWindow)
      }
    >
      <svg
        className="token-usage-ring"
        viewBox="0 0 20 20"
        aria-hidden="true"
      >
        <circle className="token-usage-ring__track" cx="10" cy="10" r="7" />
        <circle
          className="token-usage-ring__value"
          cx="10"
          cy="10"
          r="7"
          pathLength="100"
          style={{ strokeDasharray: `${ringPercentage} ${100 - ringPercentage}` }}
        />
      </svg>

      <div id={tooltipId} className="token-usage-tooltip" role="tooltip">
        {composition ? (
          <>
            <div className="token-usage-tooltip__header">
              <strong>{t("tokenUsage.composition")}</strong>
              <span>{t("tokenUsage.percentageUsed", { percentage: percentageLabel })}</span>
            </div>
            <div className="token-context-breakdown">
              <div
                className="token-context-grid"
                role="img"
                aria-label={t("tokenUsage.gridAria")}
              >
                {cells.map((cell) => (
                  <span
                    key={cell.index}
                    className="token-context-cell"
                    aria-hidden="true"
                  >
                    {cell.slices.map((slice) => (
                      <span
                        key={slice.kind}
                        className={`token-context-cell__slice is-${slice.kind}`}
                        style={{ width: `${slice.share * 100}%` }}
                      />
                    ))}
                  </span>
                ))}
              </div>
              <dl className="token-context-legend">
                {legend.map((item) => (
                  <div key={item.kind}>
                    <dt>
                      <span
                        className={`token-context-swatch is-${item.kind}`}
                        aria-hidden="true"
                      />
                      {item.kind === "input"
                        ? inputSegmentLabel
                        : segmentLabel(item.kind)}
                      {item.kind === "system" && systemTokenEstimate !== null
                        ? <em>{t("tokenUsage.estimated")}</em>
                        : null}
                    </dt>
                    <dd>
                      {item.kind === "system" && systemTokenEstimate === null
                        ? t("tokenUsage.unknown")
                        : `${item.kind === "system" ? "≈" : ""}${compactTokenCount(item.tokens, integerFormat)}`}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="token-context-summary">
              <div>
                <Trans
                  t={t}
                  i18nKey="tokenUsage.summaryPercentage"
                  values={{
                    used: summaryPercentage(ringPercentage),
                    remaining: summaryPercentage(remainingPercentage),
                  }}
                  components={{ strong: <strong /> }}
                />
              </div>
              <div>
                <Trans
                  t={t}
                  i18nKey="tokenUsage.summaryTokens"
                  values={{
                    used: summaryTokenCount(composition.usedTokens, integerFormat),
                    remaining: summaryTokenCount(composition.remainingTokens, integerFormat),
                    total: summaryTokenCount(composition.contextWindow, integerFormat),
                  }}
                  components={{ strong: <strong /> }}
                />
              </div>
            </div>
            {overflowTokens > 0 ? (
              <div className="token-usage-tooltip__overflow">
                {t("tokenUsage.overflow", { count: compactTokenCount(overflowTokens, integerFormat) })}
              </div>
            ) : null}
          </>
        ) : (
          <>
            <div className="token-usage-tooltip__title">{t("tokenUsage.title")}</div>
            <div className="token-usage-tooltip__unknown">
              {modelName.trim()
                ? t("tokenUsage.unknownModel")
                : t("tokenUsage.unknownRuntime")}
            </div>
          </>
        )}
        <div className="token-usage-tooltip__model" title={modelLabel}>
          {modelLabel}
        </div>
      </div>
    </div>
  );
}
