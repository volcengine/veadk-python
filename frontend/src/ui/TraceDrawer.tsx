import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { ChevronRight, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  getGeneratedAgentTestTrace,
  getSessionTrace,
  type TraceSpan,
} from "../adk/client";

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

type SpanId = TraceSpan["span_id"];
type TraceLoadState = "loading" | "ready" | "collecting" | "disabled" | "forbidden" | "error";

const TRACE_COLLECTING_RETRIES = 2;
const TRACE_COLLECTING_RETRY_MS = 1_500;

function traceErrorState(message: string): Exclude<TraceLoadState, "loading" | "ready"> {
  if (message.includes("HTTP 425") || message.includes("仍在采集中")) return "collecting";
  if (message.includes("HTTP 404") || message.includes("未开启链路观测")) return "disabled";
  if (/HTTP 40[13]/.test(message) || message.includes("无权限读取 APMPlus")) return "forbidden";
  return "error";
}

function buildTree(spans: TraceSpan[]) {
  const byId = new Map<SpanId, TraceSpan>();
  spans.forEach((s) => byId.set(s.span_id, s));
  const kids = new Map<SpanId, TraceSpan[]>();
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

function flatten(roots: TNode[], collapsed: Set<SpanId>): TNode[] {
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

type TraceSource =
  | { appName: string; testRunId?: never }
  | { appName?: never; testRunId: string };

export type TraceDrawerProps = TraceSource & {
  sessionId: string;
  endTimeMs?: number;
  onClose: () => void;
  title?: string;
};

export function TraceDrawer({
  appName,
  testRunId,
  sessionId,
  endTimeMs,
  onClose,
  title,
}: TraceDrawerProps) {
  const { t } = useTranslation("conversation");
  const [spans, setSpans] = useState<TraceSpan[] | null>(null);
  const [loadState, setLoadState] = useState<TraceLoadState>("loading");
  const [loadRevision, setLoadRevision] = useState(0);
  const [collapsed, setCollapsed] = useState<Set<SpanId>>(new Set());
  const [selectedId, setSelectedId] = useState<SpanId | null>(null);
  const collectingRetries = useRef(0);
  const sourceKey = `${appName ?? ""}:${testRunId ?? ""}:${sessionId}:${endTimeMs ?? ""}`;
  const previousSourceKey = useRef(sourceKey);

  useEffect(() => {
    if (previousSourceKey.current !== sourceKey) {
      previousSourceKey.current = sourceKey;
      collectingRetries.current = 0;
    }
    setSpans(null);
    setLoadState("loading");
    let cancelled = false;
    let retryTimer: number | undefined;
    let request: Promise<TraceSpan[]>;
    if (testRunId) {
      request = getGeneratedAgentTestTrace(testRunId, sessionId);
    } else if (appName) {
      request = getSessionTrace(appName, sessionId, endTimeMs);
    } else {
      setLoadState("error");
      return;
    }
    request
      .then((s) => {
        if (cancelled) return;
        setSpans(s);
        setLoadState("ready");
        setSelectedId(s.length ? s.reduce((a, b) => (a.start_time <= b.start_time ? a : b)).span_id : null);
      })
      .catch((e) => {
        if (cancelled) return;
        const state = traceErrorState(e instanceof Error ? e.message : String(e));
        setLoadState(state);
        if (state === "collecting" && collectingRetries.current < TRACE_COLLECTING_RETRIES) {
          collectingRetries.current += 1;
          retryTimer = window.setTimeout(
            () => setLoadRevision((value) => value + 1),
            TRACE_COLLECTING_RETRY_MS,
          );
        }
      });
    return () => {
      cancelled = true;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    };
  }, [appName, endTimeMs, loadRevision, sessionId, sourceKey, testRunId]);

  const retry = () => {
    collectingRetries.current = 0;
    setLoadRevision((value) => value + 1);
  };

  const { rootNodes, min, total } = useMemo(() => buildTree(spans ?? []), [spans]);
  const rows = useMemo(() => flatten(rootNodes, collapsed), [rootNodes, collapsed]);
  const selected = spans?.find((s) => s.span_id === selectedId) ?? null;
  const totalMs = total / 1e6;

  const toggle = (id: SpanId) =>
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
            <div className="drawer-title">{title ?? t("trace.title")}</div>
            <div className="drawer-sub">
              {loadState === "ready" && spans
                ? t("trace.callCount", { count: spans.length, duration: totalMs.toFixed(1) })
                : t(`trace.statuses.${loadState}`)}
            </div>
          </div>
          <button className="drawer-close" onClick={onClose} aria-label={t("trace.close")}>
            <X className="icon" />
          </button>
        </header>

        {loadState === "loading" && (
          <div className="drawer-loading">
            <Loader2 className="icon spin" /> {t("trace.loading")}
          </div>
        )}
        {loadState === "collecting" && (
          <div className="drawer-loading" role="status" aria-live="polite">
            <Loader2 className="icon spin" />
            <span>{t("trace.errors.collecting")}</span>
            <Button type="button" color="secondary" variant="outline" size="sm" pill={false} onClick={retry}>
              {t("trace.retryNow")}
            </Button>
          </div>
        )}
        {(loadState === "disabled" || loadState === "forbidden" || loadState === "error") && (
          <div className="drawer-empty trace-state" role="alert">
            <span>{t(`trace.errors.${loadState}`)}</span>
            {loadState === "error" && (
              <Button type="button" color="secondary" variant="outline" size="sm" pill={false} onClick={retry}>
                {t("trace.reload")}
              </Button>
            )}
          </div>
        )}
        {loadState === "ready" && spans && spans.length === 0 && (
          <div className="drawer-empty">{t("trace.empty")}</div>
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

                  <div className="td-section">{t("trace.attributes")}</div>
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
                <div className="drawer-empty">{t("trace.selectCall")}</div>
              )}
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
