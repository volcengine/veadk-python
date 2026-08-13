import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  getGeneratedAgentTestTrace,
  type TraceSpan,
} from "../../adk/client";
import { alignTraceEvidence } from "./traceAlignment";
import { ComparisonDrawer } from "./ComparisonDrawer";

export interface ComparisonTraceTarget {
  id: string;
  name: string;
  runId: string;
  sessionId: string;
}

function stringAttribute(span: TraceSpan, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = span.attributes[key];
    if (typeof value === "string" && value.trim()) return value;
    if (typeof value === "number") return String(value);
  }
  return undefined;
}

function evidenceSpan(span: TraceSpan) {
  return {
    id: String(span.span_id),
    name: span.name,
    invocationId: stringAttribute(span, [
      "gen_ai.invocation.id",
      "invocation_id",
      "invocationId",
    ]),
    toolCallId: stringAttribute(span, [
      "gen_ai.tool.call.id",
      "tool_call_id",
      "toolCallId",
    ]),
    parentId:
      span.parent_span_id === null ? undefined : String(span.parent_span_id),
    startTime: span.start_time,
  };
}

function duration(span: TraceSpan): string {
  const milliseconds = (span.end_time - span.start_time) / 1e6;
  return milliseconds >= 1000
    ? `${(milliseconds / 1000).toFixed(2)} s`
    : `${milliseconds.toFixed(milliseconds < 10 ? 2 : 1)} ms`;
}

export function ComparisonTraceDrawer({
  targets,
  onClose,
}: {
  targets: ComparisonTraceTarget[];
  onClose: () => void;
}) {
  const [spansByTarget, setSpansByTarget] = useState<
    Record<string, TraceSpan[]>
  >({});
  const [errors, setErrors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const targetKey = targets
    .map((target) => `${target.id}:${target.runId}:${target.sessionId}`)
    .join("|");

  useEffect(() => {
    let canceled = false;
    setLoading(true);
    setErrors([]);
    setSpansByTarget({});
    Promise.all(
      targets.map(async (target) => {
        try {
          const spans = await getGeneratedAgentTestTrace(
            target.runId,
            target.sessionId,
          );
          return { target, spans, error: "" };
        } catch (error) {
          return {
            target,
            spans: [] as TraceSpan[],
            error: `${target.name}：${error instanceof Error ? error.message : String(error)}`,
          };
        }
      }),
    ).then((results) => {
      if (canceled) return;
      setSpansByTarget(
        Object.fromEntries(
          results.map((result) => [result.target.id, result.spans]),
        ),
      );
      setErrors(
        results.flatMap((result) => (result.error ? [result.error] : [])),
      );
      setLoading(false);
    });
    return () => {
      canceled = true;
    };
  }, [targetKey]);

  const baseline = targets.find((target) => target.id === "baseline");
  const baselineSpans = baseline ? spansByTarget[baseline.id] ?? [] : [];
  const comparisons = useMemo(
    () =>
      targets
        .filter((target) => target.id !== "baseline")
        .map((target) => {
          const candidateSpans = spansByTarget[target.id] ?? [];
          const alignment = alignTraceEvidence(
            baselineSpans.map(evidenceSpan),
            candidateSpans.map(evidenceSpan),
          );
          const candidateById = new Map(
            candidateSpans.map((span) => [String(span.span_id), span]),
          );
          const matchByBaselineId = new Map(
            alignment.matches.map((match) => [
              match.baselineId,
              match.candidateId,
            ]),
          );
          return {
            target,
            candidateById,
            rows: baselineSpans.map((baselineSpan) => ({
              baselineSpan,
              candidateSpan: candidateById.get(
                matchByBaselineId.get(String(baselineSpan.span_id)) ?? "",
              ),
            })),
            unmatchedCandidateSpans: alignment.unmatchedCandidateIds.flatMap(
              (spanId) => {
                const span = candidateById.get(spanId);
                return span ? [span] : [];
              },
            ),
          };
        }),
    [baselineSpans, spansByTarget, targets],
  );

  return (
    <ComparisonDrawer
      title="多方案调用链路对齐"
      description="优先按精确 invocation ID 或 Tool Call ID 对齐；不同 Run 再按相同调用路径、确定的操作类型与同名节点顺序对齐，不根据名称相似度猜测。"
      width="wide"
      closeLabel="关闭调用链路对齐"
      onClose={onClose}
    >
        {loading ? (
          <div className="drawer-loading">
            <Loader2 className="icon spin" /> 加载各方案调用链路…
          </div>
        ) : (
          <div className="cw-comparison-trace-content">
            {errors.map((error) => (
              <div className="error" key={error}>
                {error}
              </div>
            ))}
            {!baseline ? (
              <div className="drawer-empty">请先完成基线运行后再对齐 Trace。</div>
            ) : comparisons.length === 0 ? (
              <div className="drawer-empty">至少完成一个候选运行后才能对齐。</div>
            ) : (
              comparisons.map((comparison) => (
                <section
                  className="cw-comparison-trace-section"
                  key={comparison.target.id}
                >
                  <h3>基准组 ↔ {comparison.target.name}</h3>
                  <div className="cw-comparison-trace-table" role="table">
                    <div className="cw-comparison-trace-row is-head" role="row">
                      <span role="columnheader">基准组</span>
                      <span role="columnheader">{comparison.target.name}</span>
                    </div>
                    {comparison.rows.map(({ baselineSpan, candidateSpan }) => (
                      <div
                        className="cw-comparison-trace-row"
                        role="row"
                        key={`baseline:${baselineSpan.span_id}`}
                      >
                        <span role="cell">
                          <strong>{baselineSpan.name}</strong>
                          <small>{duration(baselineSpan)}</small>
                        </span>
                        <span role="cell" className={candidateSpan ? "" : "is-unmatched"}>
                          {candidateSpan ? (
                            <>
                              <strong>{candidateSpan.name}</strong>
                              <small>{duration(candidateSpan)}</small>
                            </>
                          ) : (
                            <em>无对应项</em>
                          )}
                        </span>
                      </div>
                    ))}
                    {comparison.unmatchedCandidateSpans.map((candidateSpan) => (
                      <div
                        className="cw-comparison-trace-row"
                        role="row"
                        key={`candidate:${candidateSpan.span_id}`}
                      >
                        <span role="cell" className="is-unmatched">
                          <em>无对应项</em>
                        </span>
                        <span role="cell">
                          <strong>{candidateSpan.name}</strong>
                          <small>{duration(candidateSpan)}</small>
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              ))
            )}
          </div>
        )}
    </ComparisonDrawer>
  );
}
