import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { getSessionTrace, type TraceSpan } from "../adk/client";

interface Row {
  span: TraceSpan;
  depth: number;
  left: number; // 0..1 offset of bar start
  width: number; // 0..1 bar width
  durMs: number;
}

const COLORS = ["#5b8def", "#56b87f", "#e0a32e", "#c062d8", "#e06c5e", "#3fb6c4"];
function colorFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return COLORS[h % COLORS.length];
}

/** Build an ordered waterfall: every span on its own row (so nothing is clipped
 *  regardless of how skewed the durations are), with a proportional time bar. */
function buildRows(spans: TraceSpan[]): { rows: Row[]; totalMs: number } {
  if (!spans.length) return { rows: [], totalMs: 0 };
  const min = Math.min(...spans.map((s) => s.start_time));
  const max = Math.max(...spans.map((s) => s.end_time));
  const total = max - min || 1;

  const byId = new Map<number, TraceSpan>();
  for (const s of spans) byId.set(s.span_id, s);
  const depthOf = (s: TraceSpan): number => {
    let d = 0;
    let cur: TraceSpan | undefined = s;
    const seen = new Set<number>();
    while (cur?.parent_span_id != null && byId.has(cur.parent_span_id) && !seen.has(cur.span_id)) {
      seen.add(cur.span_id);
      d++;
      cur = byId.get(cur.parent_span_id);
    }
    return d;
  };

  const rows = spans
    .map((s) => ({
      span: s,
      depth: depthOf(s),
      left: (s.start_time - min) / total,
      width: Math.max((s.end_time - s.start_time) / total, 0.012),
      durMs: (s.end_time - s.start_time) / 1e6,
    }))
    .sort((a, b) => a.span.start_time - b.span.start_time || a.depth - b.depth);

  return { rows, totalMs: total / 1e6 };
}

function attrLines(attrs: Record<string, unknown>): string[] {
  return Object.keys(attrs)
    .filter((k) => typeof attrs[k] !== "object")
    .map((k) => `${k}: ${attrs[k]}`);
}

export interface TraceDrawerProps {
  sessionId: string;
  onClose: () => void;
}

export function TraceDrawer({ sessionId, onClose }: TraceDrawerProps) {
  const [spans, setSpans] = useState<TraceSpan[] | null>(null);
  const [err, setErr] = useState("");
  const [selected, setSelected] = useState<Row | null>(null);

  useEffect(() => {
    setSpans(null);
    setErr("");
    setSelected(null);
    getSessionTrace(sessionId)
      .then(setSpans)
      .catch((e) => setErr(String(e)));
  }, [sessionId]);

  const { rows, totalMs } = buildRows(spans ?? []);

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer">
        <header className="drawer-head">
          <div>
            <div className="drawer-title">Tracing 观测</div>
            <div className="drawer-sub">
              {spans ? `${spans.length} spans · ${totalMs.toFixed(1)} ms` : "加载中"}
            </div>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label="关闭">
            <X className="icon" />
          </button>
        </header>

        <div className="drawer-body scroll">
          {spans == null && !err && (
            <div className="drawer-loading">
              <Loader2 className="icon spin" /> 加载 trace…
            </div>
          )}
          {err && <div className="error">{err}</div>}
          {spans && spans.length === 0 && (
            <div className="drawer-empty">该会话暂无 trace（可能尚未产生调用）。</div>
          )}

          {rows.length > 0 && (
            <div className="waterfall">
              {rows.map((r) => (
                <div
                  key={r.span.span_id}
                  className={`wf-row ${selected?.span.span_id === r.span.span_id ? "active" : ""}`}
                  onClick={() => setSelected((s) => (s?.span.span_id === r.span.span_id ? null : r))}
                >
                  <div className="wf-name" style={{ paddingLeft: r.depth * 14 }} title={r.span.name}>
                    {r.span.name}
                  </div>
                  <div className="wf-track">
                    <div
                      className="wf-bar"
                      style={{
                        left: `${r.left * 100}%`,
                        width: `${r.width * 100}%`,
                        background: colorFor(r.span.name),
                      }}
                    />
                  </div>
                  <div className="wf-dur">{r.durMs.toFixed(1)}ms</div>
                </div>
              ))}
            </div>
          )}

          {selected && (
            <div className="span-detail">
              <div className="span-detail-name">{selected.span.name}</div>
              <div className="span-detail-dur">{selected.durMs.toFixed(2)} ms</div>
              {attrLines(selected.span.attributes).map((a) => (
                <div key={a} className="span-attr">
                  {a}
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
