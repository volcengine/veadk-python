import { useEffect, useRef, useState } from "react";
import { ExternalLink, Globe, Loader2, MessageSquare } from "lucide-react";
import { search, type SearchResult, type SearchSource } from "../adk/search";
import type { AgentInfo } from "../adk/client";

/** A deliberately quiet, hand-drawn search mark shared by navigation and submit. */
function SearchGlyph({ className = "icon" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M16.4 10.7a5.7 5.7 0 1 1-1.67-4.03" />
      <path d="M15.25 15.25 19.6 19.6" />
    </svg>
  );
}

function SourceChevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`search-source-chevron ${open ? "open" : ""}`}
      viewBox="0 0 12 12"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m3.25 4.75 2.75 2.5 2.75-2.5" />
    </svg>
  );
}

export function SearchButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="new-chat" onClick={onClick} aria-label="智能搜索" title="智能搜索">
      <SearchGlyph />
      <span className="sidebar-nav-label">智能搜索</span>
    </button>
  );
}

interface SourceOption {
  id: SearchSource;
  label: string;
  ready: boolean;
  description?: string;
  unavailableLabel?: string;
}

function sourceOptions(
  appId: string,
  agentInfo: AgentInfo | null,
  capabilitiesLoading: boolean,
): SourceOption[] {
  const hasAgent = Boolean(appId);
  const mounted = new Set(agentInfo?.searchSources ?? []);
  const unavailable = (label: string) => !hasAgent
    ? "请选择 Agent"
    : capabilitiesLoading
      ? "正在检测 Agent 能力"
      : `当前 Agent 未挂载${label}`;
  return [
    { id: "session", label: "会话", ready: hasAgent, unavailableLabel: "请选择 Agent" },
    {
      id: "web",
      label: "网络",
      ready: hasAgent && mounted.has("web"),
      description: "通过 web_search 工具检索",
      unavailableLabel: unavailable(" web_search 工具"),
    },
    {
      id: "knowledge",
      label: "知识库",
      ready: hasAgent && mounted.has("knowledge"),
      unavailableLabel: unavailable("知识库"),
    },
    {
      id: "memory",
      label: "长期记忆",
      ready: hasAgent && mounted.has("memory"),
      unavailableLabel: unavailable("长期记忆"),
    },
  ];
}

function searchBackendLabel(backend: string): string {
  const labels: Record<string, string> = {
    context_search: "Context Search",
    local: "本地",
    mem0: "Mem0",
    milvus: "Milvus",
    opensearch: "OpenSearch",
    openviking: "OpenViking",
    redis: "Redis",
    tos_vector: "TOS Vector",
    viking: "VikingDB",
  };
  return labels[backend.toLowerCase()] ?? backend;
}

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
  agentInfo: AgentInfo | null;
  capabilitiesLoading: boolean;
  /** Map an agent id to a display label for result badges. */
  agentLabel: (id: string) => string;
  onOpenSession: (appId: string, sessionId: string) => void;
}

export function SearchView({
  userId,
  appId,
  agentInfo,
  capabilitiesLoading,
  agentLabel,
  onOpenSession,
}: SearchViewProps) {
  const [source, setSource] = useState<SearchSource>("session");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [note, setNote] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const [sourceMenuOpen, setSourceMenuOpen] = useState(false);
  const reqRef = useRef(0);
  const sourcePickerRef = useRef<HTMLDivElement>(null);
  const sources = sourceOptions(appId, agentInfo, capabilitiesLoading);
  const selectedSource = sources.find((item) => item.id === source);
  const retrievalComponent =
    source === "knowledge"
      ? agentInfo?.components?.find(
          (component) =>
            component.source === "knowledgebase" || component.kind === "knowledgebase",
        )
      : source === "memory"
        ? agentInfo?.components?.find(
            (component) =>
              component.source === "long_term_memory" || component.kind === "memory",
          )
        : undefined;

  useEffect(() => {
    reqRef.current += 1;
    setSource("session");
    setResults([]);
    setNote(undefined);
    setSearched(false);
    setBusy(false);
    setSourceMenuOpen(false);
  }, [appId]);

  useEffect(() => {
    if (!sourceMenuOpen) return;
    function closeOutside(event: PointerEvent) {
      if (!sourcePickerRef.current?.contains(event.target as Node)) {
        setSourceMenuOpen(false);
      }
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [sourceMenuOpen]);

  // Search runs only on an explicit trigger (button click or Enter).
  async function doSearch(q: string, src: SearchSource) {
    const qq = q.trim();
    if (!qq || !sources.find((item) => item.id === src)?.ready) return;
    const id = ++reqRef.current;
    setBusy(true);
    setSearched(true);
    let outcome;
    try {
      outcome = await search(src, qq, { userId, appId });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      outcome = { results: [], note: `搜索失败：${message}` };
    }
    if (id !== reqRef.current) return; // superseded by a newer search
    setResults(outcome.results);
    setNote(outcome.note);
    setBusy(false);
  }

  function updateQuery(value: string) {
    reqRef.current += 1;
    setQuery(value);
    setResults([]);
    setNote(undefined);
    setSearched(false);
    setBusy(false);
  }

  // A source change waits for an explicit search instead of reusing stale results.
  function pickSource(src: SearchSource) {
    reqRef.current += 1;
    setSource(src);
    setSourceMenuOpen(false);
    setResults([]);
    setNote(undefined);
    setSearched(false);
    setBusy(false);
  }

  const ready = Boolean(selectedSource?.ready);
  const placeholder = !appId
    ? "请先选择 Agent"
    : source === "web"
      ? "在网络中检索"
      : source === "knowledge"
        ? `在 ${retrievalComponent?.name ?? "当前 Agent 的知识库"} 中检索`
        : source === "memory"
          ? `在 ${retrievalComponent?.name ?? "当前用户的长期记忆"} 中检索`
          : "在当前 Agent 的会话中检索";
  const selectedBackend = retrievalComponent?.backend
    ? searchBackendLabel(retrievalComponent.backend)
    : "";

  return (
    <div className="search">
      <div className="search-box">
        <div className="search-source-picker-wrap" ref={sourcePickerRef}>
          <button
            className="search-source-picker"
            type="button"
            aria-label={`搜索类型：${selectedSource?.label ?? "未选择"}`}
            aria-haspopup="listbox"
            aria-expanded={sourceMenuOpen}
            onClick={() => setSourceMenuOpen((open) => !open)}
          >
            <span>{selectedSource?.label ?? "搜索类型"}</span>
            {selectedBackend && <small>{selectedBackend}</small>}
            <SourceChevron open={sourceMenuOpen} />
          </button>
          {sourceMenuOpen && (
            <div className="search-source-menu" role="listbox" aria-label="选择搜索类型">
              {sources.map((option) => {
                const component =
                  option.id === "knowledge"
                    ? agentInfo?.components?.find(
                        (item) =>
                          item.source === "knowledgebase" || item.kind === "knowledgebase",
                      )
                    : option.id === "memory"
                      ? agentInfo?.components?.find(
                          (item) =>
                            item.source === "long_term_memory" || item.kind === "memory",
                        )
                      : undefined;
                const detail = component
                  ? [
                      component.name,
                      component.backend ? searchBackendLabel(component.backend) : "",
                    ]
                      .filter(Boolean)
                      .join(" · ")
                  : option.ready
                    ? option.description
                    : option.unavailableLabel;
                return (
                  <button
                    key={option.id}
                    type="button"
                    role="option"
                    aria-selected={source === option.id}
                    disabled={!option.ready}
                    onClick={() => pickSource(option.id)}
                  >
                    <span>{option.label}</span>
                    {detail && <small>{detail}</small>}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <span className="search-box-divider" aria-hidden />
        <input
          className="search-input"
          value={query}
          onChange={(e) => updateQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void doSearch(query, source);
            }
          }}
          placeholder={placeholder}
          disabled={!ready}
          autoFocus
        />
        <button
          className="search-go"
          onClick={() => void doSearch(query, source)}
          disabled={!query.trim() || busy}
          aria-label="搜索"
        >
          {busy ? <Loader2 className="icon spin" /> : <SearchGlyph className="icon" />}
        </button>
      </div>

      <div className="search-results">
        {!ready ? (
          <div className="search-empty">
            {!appId
              ? "选择一个 Agent 后，即可检索会话、网络及其挂载的数据源。"
              : capabilitiesLoading
                ? "正在读取当前 Agent 的检索能力…"
                : (selectedSource?.unavailableLabel ?? "当前 Agent 未挂载该数据源")}
          </div>
        ) : !searched ? (
          <div className="search-empty">
            {source === "web"
              ? "输入关键词后回车或点击按钮，通过 web_search 工具检索。"
              : source === "knowledge"
                ? "输入问题，检索当前 Agent 挂载的知识库。"
                : source === "memory"
                  ? "输入线索，检索当前用户跨会话保存的长期记忆。"
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
    case "knowledge":
      return (
        <div className="search-result search-result-static">
          <RetrievalResultIcon source="knowledge" />
          <div className="search-result-body">
            <div className="search-result-head">
              <span className="search-result-title">知识片段 {result.index + 1}</span>
              <span className="search-result-meta">
                {result.sourceName}
                {result.sourceType ? ` · ${searchBackendLabel(result.sourceType)}` : ""}
              </span>
            </div>
            <div className="search-result-snippet search-result-snippet-expanded">
              {result.content}
            </div>
          </div>
        </div>
      );
    case "memory":
      return (
        <div className="search-result search-result-static">
          <RetrievalResultIcon source="memory" />
          <div className="search-result-body">
            <div className="search-result-head">
              <span className="search-result-title">记忆片段 {result.index + 1}</span>
              <span className="search-result-meta">
                {result.sourceName}
                {result.sourceType ? ` · ${searchBackendLabel(result.sourceType)}` : ""}
                {result.ts ? ` · ${fmt(result.ts)}` : ""}
              </span>
            </div>
            <div className="search-result-snippet search-result-snippet-expanded">
              {result.content}
            </div>
          </div>
        </div>
      );
    default:
      return null;
  }
}

function RetrievalResultIcon({
  source,
  className = "search-result-icon",
}: {
  source: "knowledge" | "memory";
  className?: string;
}) {
  return source === "knowledge" ? (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M5 5.5h10.5A3.5 3.5 0 0 1 19 9v9.5H8.5A3.5 3.5 0 0 1 5 15V5.5Z" />
      <path d="M8.25 9h7.5M8.25 12.25h6" />
    </svg>
  ) : (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 4.5a7.5 7.5 0 1 0 7.5 7.5" />
      <path d="M12 8a4 4 0 1 0 4 4M12 11.3a.7.7 0 1 0 0 1.4.7.7 0 0 0 0-1.4Z" />
    </svg>
  );
}
