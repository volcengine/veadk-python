import { useId } from "react";
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

const integerFormat = new Intl.NumberFormat("zh-CN");

function compactTokenCount(value: number): string {
  if (value >= 1_000) {
    return `${Number((value / 1_000).toFixed(1))}K`;
  }
  return integerFormat.format(value);
}

function summaryTokenCount(value: number): string {
  if (value >= 1_000) {
    return `${Number((value / 1_000).toFixed(1))}K`;
  }
  return `${integerFormat.format(value)} Token`;
}

function summaryPercentage(value: number): string {
  return `${Number(value.toFixed(2))}%`;
}

const SEGMENT_LABELS: Record<ContextSegmentKind, string> = {
  system: "系统与工具",
  input: "输入与历史",
  output: "输出与思考",
  remaining: "剩余",
};

export function TokenUsageIndicator({
  cloudProvider,
  modelName,
  usage,
  systemTokenEstimate,
}: TokenUsageIndicatorProps) {
  const tooltipId = useId();
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
  const modelLabel = modelName.trim() || "模型信息未提供";
  const inputSegmentLabel = systemTokenEstimate === null
    ? "提示词（含系统）"
    : SEGMENT_LABELS.input;
  const overflowTokens = composition
    ? Math.max(0, composition.usedTokens - composition.contextWindow)
    : 0;
  const systemAriaLabel = systemTokenEstimate === null
    ? "系统与工具占用未知"
    : `系统与工具约 ${integerFormat.format(composition?.systemTokens ?? 0)} Token`;
  const ariaLabel = composition
    ? `上下文已使用 ${percentageLabel}%，${systemAriaLabel}，${inputSegmentLabel} ${integerFormat.format(composition.inputTokens)} Token，输出与思考 ${integerFormat.format(composition.outputTokens)} Token，剩余 ${integerFormat.format(composition.remainingTokens)} Token`
    : `${modelLabel}，上下文窗口未知，会话累计使用 ${integerFormat.format(usage.cumulative.totalTokenCount)} Token`;
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
              <strong>上下文构成</strong>
              <span>{percentageLabel}% 已用</span>
            </div>
            <div className="token-context-breakdown">
              <div
                className="token-context-grid"
                role="img"
                aria-label="100 格上下文构成图，每格代表上下文窗口的百分之一"
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
                        : SEGMENT_LABELS[item.kind]}
                      {item.kind === "system" && systemTokenEstimate !== null
                        ? <em>估算</em>
                        : null}
                    </dt>
                    <dd>
                      {item.kind === "system" && systemTokenEstimate === null
                        ? "未知"
                        : `${item.kind === "system" ? "≈" : ""}${compactTokenCount(item.tokens)}`}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="token-context-summary">
              <div>
                <strong>{summaryPercentage(ringPercentage)}</strong> 已用，剩余{" "}
                <strong>{summaryPercentage(remainingPercentage)}</strong>
              </div>
              <div>
                <strong>{summaryTokenCount(composition.usedTokens)}</strong> 已用，剩余{" "}
                <strong>{summaryTokenCount(composition.remainingTokens)}</strong>，总计{" "}
                <strong>{summaryTokenCount(composition.contextWindow)}</strong>
              </div>
            </div>
            {overflowTokens > 0 ? (
              <div className="token-usage-tooltip__overflow">
                已超出上下文 {compactTokenCount(overflowTokens)} Token
              </div>
            ) : null}
          </>
        ) : (
          <>
            <div className="token-usage-tooltip__title">上下文用量</div>
            <div className="token-usage-tooltip__unknown">
              {modelName.trim()
                ? "暂未收录该模型的上下文窗口"
                : "当前 Runtime 未提供模型信息"}
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
