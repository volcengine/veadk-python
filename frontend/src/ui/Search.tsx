import { useRef, useState } from "react";
import { ArrowRight, ExternalLink, Globe, Loader2, MessageSquare } from "lucide-react";
import { search, type SearchResult, type SearchSource } from "../adk/search";

/** Hand-drawn "smart search" mark: a magnifier with a small spark. */
function SearchIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="M20 20l-4.6-4.6" />
      <path d="M10.5 7.6v1.4M10.5 12v1.4M7.6 10.5h1.4M12 10.5h1.4" opacity="0.7" />
    </svg>
  );
}

export function SearchButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="new-chat" onClick={onClick}>
      <SearchIcon />
      智能搜索
    </button>
  );
}

const SOURCES: { id: SearchSource; label: string; ready: boolean }[] = [
  { id: "session", label: "会话", ready: true },
  { id: "web", label: "网页", ready: true },
  { id: "knowledge", label: "知识库", ready: false },
  { id: "memory", label: "记忆", ready: false },
];

function fmt(ts?: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export interface SearchViewProps {
  userId: string;
  appId: string;
  /** Map an agent id to a display label for result badges. */
  agentLabel: (id: string) => string;
  onOpenSession: (appId: string, sessionId: string) => void;
}

export function SearchView({ userId, appId, agentLabel, onOpenSession }: SearchViewProps) {
  const [source, setSource] = useState<SearchSource>("session");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [note, setNote] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const reqRef = useRef(0);

  // Search runs only on an explicit trigger (button click or Enter).
  async function doSearch(q: string, src: SearchSource) {
    const qq = q.trim();
    if (!qq) return;
    const id = ++reqRef.current;
    setBusy(true);
    setSearched(true);
    let outcome;
    try {
      outcome = await search(src, qq, { userId, appId });
    } catch (e) {
      outcome = { results: [], note: `搜索失败：${String(e)}` };
    }
    if (id !== reqRef.current) return; // superseded by a newer search
    setResults(outcome.results);
    setNote(outcome.note);
    setBusy(false);
  }

  // Switching source re-runs the last query against the new source.
  function pickSource(src: SearchSource) {
    setSource(src);
    if (searched && query.trim()) void doSearch(query, src);
  }

  const ready = SOURCES.find((s) => s.id === source)?.ready;
  const placeholder = source === "web" ? "联网搜索…" : "搜索当前 Agent 的会话…";

  return (
    <div className="search">
      <div className="search-box">
        <SearchIcon />
        <input
          className="search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void doSearch(query, source);
            }
          }}
          placeholder={placeholder}
          autoFocus
        />
        <button
          className="search-go"
          onClick={() => void doSearch(query, source)}
          disabled={!query.trim() || busy}
          aria-label="搜索"
        >
          {busy ? <Loader2 className="icon spin" /> : <ArrowRight className="icon" />}
        </button>
      </div>

      <div className="search-sources">
        {SOURCES.map((s) => (
          <button
            key={s.id}
            className={`search-tab ${source === s.id ? "active" : ""}`}
            onClick={() => pickSource(s.id)}
            disabled={!s.ready}
            title={s.ready ? undefined : "即将支持"}
          >
            {s.label}
            {!s.ready && <span className="search-soon">敬请期待</span>}
          </button>
        ))}
      </div>

      <div className="search-results">
        {!ready ? (
          <div className="search-empty">该搜索源即将支持。</div>
        ) : !searched ? (
          <div className="search-empty">
            {source === "web"
              ? "输入关键词后回车或点击按钮，让当前 Agent 联网搜索。"
              : "输入关键词后回车或点击按钮，搜索当前 Agent 的会话。"}
          </div>
        ) : busy ? null : note ? (
          <div className="search-empty">{note}</div>
        ) : results.length === 0 && searched ? (
          <div className="search-empty">未找到匹配「{query.trim()}」的结果。</div>
        ) : (
          results.map((r, i) => <ResultRow key={i} result={r} agentLabel={agentLabel} onOpen={onOpenSession} />)
        )}
      </div>
    </div>
  );
}

/** Render one result by its `type`. */
function ResultRow({
  result,
  agentLabel,
  onOpen,
}: {
  result: SearchResult;
  agentLabel: (id: string) => string;
  onOpen: (appId: string, sessionId: string) => void;
}) {
  switch (result.type) {
    case "session":
      return (
        <button className="search-result" onClick={() => onOpen(result.appId, result.sessionId)}>
          <MessageSquare className="search-result-icon" />
          <div className="search-result-body">
            <div className="search-result-head">
              <span className="search-result-title">{result.title}</span>
              <span className="search-result-meta">
                {agentLabel(result.appId)}
                {result.ts ? ` · ${fmt(result.ts)}` : ""}
              </span>
            </div>
            <div className="search-result-snippet">{result.snippet}</div>
          </div>
        </button>
      );
    case "web":
      return (
        <a
          className="search-result"
          href={result.url || undefined}
          target="_blank"
          rel="noreferrer noopener"
        >
          <Globe className="search-result-icon" />
          <div className="search-result-body">
            <div className="search-result-head">
              <span className="search-result-title">{result.title || result.url}</span>
              <span className="search-result-meta">
                {result.siteName}
                {result.url && <ExternalLink className="search-result-ext" />}
              </span>
            </div>
            {result.summary && <div className="search-result-snippet">{result.summary}</div>}
          </div>
        </a>
      );
    default:
      return null;
  }
}
