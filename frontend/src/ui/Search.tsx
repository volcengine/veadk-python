import { useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { ExternalLink, Globe, Loader2, MessageSquare } from "lucide-react";
import { search, type SearchResult, type SearchSource } from "../adk/search";
import type { AgentInfo } from "../adk/client";
import { SidebarSearchIcon } from "./icons/SidebarIcons";

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

export function SearchButton({
  active = false,
  onClick,
}: {
  active?: boolean;
  onClick: () => void;
}) {
  const { t } = useTranslation("workspaceTools");
  return (
    <button
      className={`new-chat${active ? " is-active" : ""}`}
      onClick={onClick}
      aria-label={t("search.nav")}
      aria-current={active ? "page" : undefined}
      title={t("search.nav")}
    >
      <SidebarSearchIcon className="icon" />
      <span className="sidebar-nav-label">{t("search.nav")}</span>
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
  t: TFunction,
): SourceOption[] {
  const hasAgent = Boolean(appId);
  const mounted = new Set(agentInfo?.searchSources ?? []);
  const unavailable = (label: string) => !hasAgent
    ? t("search.selectAgent")
    : capabilitiesLoading
      ? t("search.checkingCapabilities")
      : t("search.notMounted", { label });
  return [
    {
      id: "session",
      label: t("search.sources.session"),
      ready: hasAgent,
      unavailableLabel: t("search.selectAgent"),
    },
    {
      id: "web",
      label: t("search.sources.web"),
      ready: hasAgent && mounted.has("web"),
      description: t("search.webDescription"),
      unavailableLabel: unavailable(" web_search"),
    },
    {
      id: "knowledge",
      label: t("search.sources.knowledge"),
      ready: hasAgent && mounted.has("knowledge"),
      unavailableLabel: unavailable(t("search.sources.knowledge")),
    },
    {
      id: "memory",
      label: t("search.sources.memory"),
      ready: hasAgent && mounted.has("memory"),
      unavailableLabel: unavailable(t("search.sources.memory")),
    },
  ];
}

function searchBackendLabel(backend: string, t: TFunction): string {
  const labels: Record<string, string> = {
    context_search: "Context Search",
    local: t("search.backendLocal"),
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

function fmt(ts: number | undefined, locale: string): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(locale, {
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
  const { t, i18n } = useTranslation("workspaceTools");
  const locale = i18n.resolvedLanguage || i18n.language;
  const [source, setSource] = useState<SearchSource>("session");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [note, setNote] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);
  const [sourceMenuOpen, setSourceMenuOpen] = useState(false);
  const reqRef = useRef(0);
  const sourcePickerRef = useRef<HTMLDivElement>(null);
  const sources = sourceOptions(appId, agentInfo, capabilitiesLoading, t);
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
      outcome = { results: [], note: t("search.failed", { message }) };
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
    ? t("search.placeholder.selectAgent")
    : source === "web"
      ? t("search.placeholder.web")
      : source === "knowledge"
        ? t("search.placeholder.knowledge", {
            name: retrievalComponent?.name ?? t("search.placeholder.knowledgeFallback"),
          })
        : source === "memory"
          ? t("search.placeholder.memory", {
              name: retrievalComponent?.name ?? t("search.placeholder.memoryFallback"),
            })
          : t("search.placeholder.session");
  const selectedBackend = retrievalComponent?.backend
    ? searchBackendLabel(retrievalComponent.backend, t)
    : "";

  return (
    <div className="search">
      <div className="search-box">
        <div className="search-source-picker-wrap" ref={sourcePickerRef}>
          <button
            className="search-source-picker"
            type="button"
            aria-label={t("search.sourceTypeAria", {
              label: selectedSource?.label ?? t("search.notSelected"),
            })}
            aria-haspopup="listbox"
            aria-expanded={sourceMenuOpen}
            onClick={() => setSourceMenuOpen((open) => !open)}
          >
            <span>{selectedSource?.label ?? t("search.sourceType")}</span>
            {selectedBackend && <small>{selectedBackend}</small>}
            <SourceChevron open={sourceMenuOpen} />
          </button>
          {sourceMenuOpen && (
            <div className="search-source-menu" role="listbox" aria-label={t("search.selectSource")}>
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
                      component.backend ? searchBackendLabel(component.backend, t) : "",
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
          aria-label={t("search.nav")}
        >
          {busy ? <Loader2 className="icon spin" /> : <SearchGlyph className="icon" />}
        </button>
      </div>

      <div className="search-results">
        {!ready ? (
          <div className="search-empty">
            {!appId
              ? t("search.noAgentHint")
              : capabilitiesLoading
                ? t("search.loadingCapabilities")
                : (selectedSource?.unavailableLabel ?? t("search.sourceUnavailable"))}
          </div>
        ) : !searched ? (
          <div className="search-empty">
            {source === "web"
              ? t("search.instructions.web")
              : source === "knowledge"
                ? t("search.instructions.knowledge")
                : source === "memory"
                  ? t("search.instructions.memory")
                  : t("search.instructions.session")}
          </div>
        ) : busy ? null : note ? (
          <div className="search-empty">{note}</div>
        ) : results.length === 0 && searched ? (
          <div className="search-empty">{t("search.noResults", { query: query.trim() })}</div>
        ) : (
          results.map((r, index) => (
            <ResultRow
              key={index}
              result={r}
              agentLabel={agentLabel}
              onOpen={onOpenSession}
              locale={locale}
            />
          ))
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
  locale,
}: {
  result: SearchResult;
  agentLabel: (id: string) => string;
  onOpen: (appId: string, sessionId: string) => void;
  locale: string;
}) {
  const { t } = useTranslation("workspaceTools");
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
                {result.ts ? ` · ${fmt(result.ts, locale)}` : ""}
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
              <span className="search-result-title">{t("search.knowledgeFragment", { index: result.index + 1 })}</span>
              <span className="search-result-meta">
                {result.sourceName}
                {result.sourceType ? ` · ${searchBackendLabel(result.sourceType, t)}` : ""}
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
              <span className="search-result-title">{t("search.memoryFragment", { index: result.index + 1 })}</span>
              <span className="search-result-meta">
                {result.sourceName}
                {result.sourceType ? ` · ${searchBackendLabel(result.sourceType, t)}` : ""}
                {result.ts ? ` · ${fmt(result.ts, locale)}` : ""}
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
