import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Loader2, X } from "lucide-react";
import { getSessionTrace, type TraceSpan } from "../adk/client";

// Softer, cohesive palette that sits better on the neutral UI than the old
// saturated primaries.
const COLORS = [
  "#6366f1", // indigo
  "#0ea5e9", // sky
  "#10b981", // emerald
  "#f59e0b", // amber
  "#f43f5e", // rose
  "#a855f7", // violet
  "#14b8a6", // teal
  "#f472b6", // pink
];
function colorFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return COLORS[h % COLORS.length];
}

interface TNode {
  span: TraceSpan;
  depth: number;
  children: TNode[];
}

function buildTree(spans: TraceSpan[]) {
  const byId = new Map<number, TraceSpan>();
  spans.forEach((s) => byId.set(s.span_id, s));
  const kids = new Map<number, TraceSpan[]>();
  const roots: TraceSpan[] = [];
  for (const s of spans) {
    if (s.parent_span_id != null && byId.has(s.parent_span_id)) {
      (kids.get(s.parent_span_id) ?? kids.set(s.parent_span_id, []).get(s.parent_span_id)!).push(s);
    } else {
      roots.push(s);
    }
  }
  const byStart = (a: TraceSpan, b: TraceSpan) => a.start_time - b.start_time;
  const make = (s: TraceSpan, depth: number): TNode => ({
    span: s,
    depth,
    children: (kids.get(s.span_id) ?? []).sort(byStart).map((c) => make(c, depth + 1)),
  });
  const rootNodes = roots.sort(byStart).map((s) => make(s, 0));
  const min = spans.length ? Math.min(...spans.map((s) => s.start_time)) : 0;
  const max = spans.length ? Math.max(...spans.map((s) => s.end_time)) : 1;
  return { rootNodes, min, total: max - min || 1 };
}

function flatten(roots: TNode[], collapsed: Set<number>): TNode[] {
  const out: TNode[] = [];
  const walk = (n: TNode) => {
    out.push(n);
    if (!collapsed.has(n.span.span_id)) n.children.forEach(walk);
  };
  roots.forEach(walk);
  return out;
}

function fmtMs(ns: number): string {
  const ms = ns / 1e6;
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  return `${ms.toFixed(ms < 10 ? 2 : 1)} ms`;
}

const shortKey = (k: string) => k.replace(/^(gen_ai|a2ui|adk)\./, "");

interface Attr {
  key: string;
  value: string;
  long: boolean;
}
function attrs(span: TraceSpan): Attr[] {
  return Object.entries(span.attributes)
    .filter(([, v]) => v != null && typeof v !== "object")
    .map(([k, v]) => {
      const value = String(v);
      return { key: shortKey(k), value, long: value.length > 80 || value.includes("\n") };
    })
    .sort((a, b) => Number(a.long) - Number(b.long)); // short props first
}

export interface TraceDrawerProps {
  appName: string;
  sessionId: string;
  onClose: () => void;
}

export function TraceDrawer({ appName, sessionId, onClose }: TraceDrawerProps) {
  const [spans, setSpans] = useState<TraceSpan[] | null>(null);
  const [err, setErr] = useState("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    setSpans(null);
    setErr("");
    getSessionTrace(appName, sessionId)
      .then((s) => {
        setSpans(s);
        setSelectedId(s.length ? s.reduce((a, b) => (a.start_time <= b.start_time ? a : b)).span_id : null);
      })
      .catch((e) => setErr(String(e)));
  }, [appName, sessionId]);

  const { rootNodes, min, total } = useMemo(() => buildTree(spans ?? []), [spans]);
  const rows = useMemo(() => flatten(rootNodes, collapsed), [rootNodes, collapsed]);
  const selected = spans?.find((s) => s.span_id === selectedId) ?? null;
  const totalMs = total / 1e6;

  const toggle = (id: number) =>
    setCollapsed((c) => {
      const n = new Set(c);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });

  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer drawer--trace">
        <header className="drawer-head">
          <div>
            <div className="drawer-title">调用链路观测</div>
            <div className="drawer-sub">
              {spans ? `${spans.length} 个调用 · ${totalMs.toFixed(1)} ms` : "加载中"}
            </div>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label="关闭">
            <X className="icon" />
          </button>
        </header>

        {spans == null && !err && (
          <div className="drawer-loading">
            <Loader2 className="icon spin" /> 加载调用链路…
          </div>
        )}
        {err && <div className="error">{err}</div>}
        {spans && spans.length === 0 && (
          <div className="drawer-empty">该会话暂无调用链路（可能尚未产生调用）。</div>
        )}

        {rows.length > 0 && (
          <div className="trace-split">
            {/* left: span tree + timeline */}
            <div className="trace-tree scroll">
              {rows.map((n) => {
                const s = n.span;
                const left = ((s.start_time - min) / total) * 100;
                const width = Math.max(((s.end_time - s.start_time) / total) * 100, 0.6);
                const hasKids = n.children.length > 0;
                return (
                  <button
                    key={s.span_id}
                    className={`trace-row ${selectedId === s.span_id ? "active" : ""}`}
                    onClick={() => setSelectedId(s.span_id)}
                  >
                    <span className="trace-label" style={{ paddingLeft: n.depth * 14 }}>
                      <span
                        className={`trace-caret ${hasKids ? "" : "hidden"} ${collapsed.has(s.span_id) ? "" : "open"}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (hasKids) toggle(s.span_id);
                        }}
                      >
                        <ChevronRight className="chev" />
                      </span>
                      <span className="trace-dot" style={{ background: colorFor(s.name) }} />
                      <span className="trace-name" title={s.name}>
                        {s.name}
                      </span>
                    </span>
                    <span className="trace-dur">{fmtMs(s.end_time - s.start_time)}</span>
                    <span className="trace-track">
                      <span
                        className="trace-bar"
                        style={{ left: `${left}%`, width: `${width}%`, background: colorFor(s.name) }}
                      />
                    </span>
                  </button>
                );
              })}
            </div>

            {/* right: selected span detail */}
            <div className="trace-detail scroll">
              {selected ? (
                <>
                  <div className="td-title">{selected.name}</div>
                  <div className="td-dur">
                    <span className="td-dot" style={{ background: colorFor(selected.name) }} />
                    {fmtMs(selected.end_time - selected.start_time)}
                  </div>

                  <div className="td-section">属性</div>
                  <div className="td-props">
                    {attrs(selected)
                      .filter((a) => !a.long)
                      .map((a) => (
                        <div key={a.key} className="td-prop">
                          <span className="td-key">{a.key}</span>
                          <span className="td-val">{a.value}</span>
                        </div>
                      ))}
                  </div>

                  {attrs(selected)
                    .filter((a) => a.long)
                    .map((a) => (
                      <div key={a.key} className="td-block">
                        <div className="td-section">{a.key}</div>
                        <pre className="td-pre">{a.value}</pre>
                      </div>
                    ))}
                </>
              ) : (
                <div className="drawer-empty">选择左侧的一个调用查看详情</div>
              )}
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
