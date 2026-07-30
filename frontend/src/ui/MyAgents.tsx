import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SVGProps } from "react";

import {
  getRuntimes,
  type CloudRuntime,
  type RuntimeScope,
} from "../adk/client";
import { sandboxClient, type SandboxSession } from "../adk/sandbox";
import "./MyAgents.css";

export interface MyAgentCardData {
  id: string;
  appName?: string;
  name: string;
  description: string;
  createdAt: string;
  isMine?: boolean;
  runtime?: {
    runtimeId: string;
    region: string;
    currentVersion?: number | null;
    canDelete: boolean;
  };
}

export type AgentType = "general" | "codex" | "openclaw" | "hermes";
type RuntimeRegion = "cn-beijing" | "cn-shanghai";

const CODEX_TRANSITIONAL_STATUSES = new Set([
  "creating",
  "pending",
  "starting",
  "initializing",
  "provisioning",
]);
const AGENT_TYPES: Array<{ id: AgentType; label: string; createLabel: string }> = [
  { id: "general", label: "通用智能体", createLabel: "添加通用智能体" },
  { id: "codex", label: "Codex 智能体", createLabel: "添加 Codex 智能体" },
  { id: "openclaw", label: "OpenClaw 智能体", createLabel: "添加 OpenClaw 智能体" },
  { id: "hermes", label: "Hermes 智能体", createLabel: "添加 Hermes 智能体" },
];
const RUNTIME_PAGE_SIZE = 24;
const RUNTIME_PAGE_CACHE_TTL_MS = 30_000;
const runtimePageRequests = new Map<
  string,
  Promise<{ runtimes: CloudRuntime[]; nextToken: string }>
>();
const runtimePageCache = new Map<
  string,
  { page: { runtimes: CloudRuntime[]; nextToken: string }; expiresAt: number }
>();
const EMPTY_RUNTIME_IDS = new Set<string>();

export function invalidateRuntimeAgentCache(runtimeIds?: Iterable<string>) {
  if (!runtimeIds) {
    runtimePageRequests.clear();
    runtimePageCache.clear();
    return;
  }
  const targetRuntimeIds = new Set(runtimeIds);
  if (targetRuntimeIds.size === 0) return;
  for (const [key, cached] of runtimePageCache) {
    if (cached.page.runtimes.some((runtime) => targetRuntimeIds.has(runtime.runtimeId))) {
      runtimePageCache.delete(key);
    }
  }
  runtimePageRequests.clear();
}

function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <circle cx="10.8" cy="10.8" r="6.2" stroke="currentColor" strokeWidth="1.7" />
      <path d="m15.4 15.4 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function AddIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="M8 3.25v9.5M3.25 8h9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function ChevronDownIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="m4.25 6.25 3.75 3.5 3.75-3.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="m3.5 8.25 2.75 2.75 6.25-6.25"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function formatCreatedAt(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date).replace(/\//g, "-");
}

function runtimeToAgent(runtime: CloudRuntime): MyAgentCardData {
  return {
    id: runtime.runtimeId,
    name: runtime.name,
    description: runtime.name,
    createdAt: formatCreatedAt(runtime.createdAt ?? ""),
    isMine: runtime.isMine,
    runtime: {
      runtimeId: runtime.runtimeId,
      region: runtime.region,
      currentVersion: runtime.currentVersion,
      canDelete: runtime.canDelete,
    },
  };
}

async function loadRuntimeAgents(
  runtimeScope: RuntimeScope,
  region: RuntimeRegion,
  nextToken: string,
  onList: (agents: MyAgentCardData[]) => void,
): Promise<string> {
  const requestKey = `${runtimeScope}:${region}:${nextToken}`;
  const cached = runtimePageCache.get(requestKey);
  if (cached && cached.expiresAt > Date.now()) {
    onList(cached.page.runtimes.map(runtimeToAgent));
    return cached.page.nextToken;
  }
  if (cached) runtimePageCache.delete(requestKey);
  let request = runtimePageRequests.get(requestKey);
  if (!request) {
    request = getRuntimes({
      scope: runtimeScope,
      region,
      pageSize: RUNTIME_PAGE_SIZE,
      nextToken,
    });
    runtimePageRequests.set(requestKey, request);
    void request.then(
      () => runtimePageRequests.delete(requestKey),
      () => runtimePageRequests.delete(requestKey),
    );
  }
  const page = await request;
  runtimePageCache.set(requestKey, {
    page,
    expiresAt: Date.now() + RUNTIME_PAGE_CACHE_TTL_MS,
  });
  onList(page.runtimes.map(runtimeToAgent));
  return page.nextToken;
}

function AgentCard({
  agent,
  onUse,
  onViewDetails,
  connecting,
  connected,
  showOwnership,
}: {
  agent: MyAgentCardData;
  onUse?: (agent: MyAgentCardData) => Promise<void>;
  onViewDetails?: (agent: MyAgentCardData) => void;
  connecting?: boolean;
  connected?: boolean;
  showOwnership?: boolean;
}) {
  return (
    <article className="my-agent-card">
      <button
        type="button"
        className="my-agent-card-main"
        disabled={!agent.runtime}
        onClick={() => onViewDetails?.(agent)}
        aria-label={`查看 ${agent.name} 详情`}
      >
        <span className="my-agent-card-copy">
          <span className="my-agent-card-title">
            <h3>{agent.name}</h3>
            {showOwnership && agent.isMine && (
              <span className="runtime-owner-badge">我创建的</span>
            )}
          </span>
          <dl className="my-agent-meta">
            <div className="my-agent-created-at">
              <dt>创建时间</dt>
              <dd>{agent.createdAt}</dd>
            </div>
          </dl>
        </span>
      </button>
      <button
        type="button"
        className={`my-agent-connect${connected ? " is-connected" : ""}`}
        disabled={!agent.runtime || connecting || connected}
        aria-busy={connecting || undefined}
        aria-label={connected ? `${agent.name} 已连接` : `连接 ${agent.name}`}
        title={connected ? "已连接" : "连接智能体"}
        onClick={() => void onUse?.(agent)}
      >
        {connecting ? "连接中" : connected ? "已连接" : "连接"}
      </button>
    </article>
  );
}

function CodexSessionCard({
  session,
  connecting,
  onOpen,
}: {
  session: SandboxSession;
  connecting: boolean;
  onOpen: (session: SandboxSession) => Promise<void>;
}) {
  const ready = session.status.toLowerCase() === "ready";
  const name =
    session.displayName ||
    session.userSessionId ||
    "Codex 智能体";
  const userSessionSubtitle =
    session.displayName && session.userSessionId ? session.userSessionId : "";
  return (
    <button
      type="button"
      className="my-agent-card codex-session-card"
      disabled={!ready || connecting}
      aria-busy={connecting || undefined}
      aria-label={
        ready
          ? `进入 ${name} 对话`
          : `${name} 当前状态 ${session.status}`
      }
      onClick={() => void onOpen(session)}
    >
      <span className="my-agent-card-copy">
        <span className="codex-session-title">
          <h3 title={name}>{name}</h3>
          <span className={`codex-session-status${ready ? " is-ready" : ""}`}>
            {session.status}
          </span>
        </span>
        {userSessionSubtitle && (
          <span
            className="codex-session-user-id"
            title={userSessionSubtitle}
          >
            User Session · {userSessionSubtitle}
          </span>
        )}
        <dl className="my-agent-meta codex-session-meta">
          <div className="my-agent-created-at">
            <dt>创建时间</dt>
            <dd>{formatCreatedAt(session.createdAt)}</dd>
          </div>
          <div className="my-agent-created-at">
            <dt>到期时间</dt>
            <dd>{formatCreatedAt(session.expireAt)}</dd>
          </div>
        </dl>
      </span>
      <span className="codex-session-enter">
        {connecting ? "连接中" : ready ? "进入对话" : "等待就绪"}
      </span>
    </button>
  );
}

export interface MyAgentsProps {
  canCreate: boolean;
  runtimeScope: RuntimeScope;
  activeType: AgentType;
  onActiveTypeChange: (type: AgentType) => void;
  onCreateAgent: (region: RuntimeRegion) => void;
  onCreateCodexAgent: () => void;
  onOpenCodexSession: (session: SandboxSession) => Promise<void>;
  onUseAgent: (agent: MyAgentCardData) => Promise<void>;
  onViewAgentDetails: (agent: MyAgentCardData) => void;
  connectedRuntimeId?: string;
  hiddenRuntimeIds?: ReadonlySet<string>;
  codexRefreshKey?: number;
}

export function MyAgents({
  canCreate,
  runtimeScope,
  activeType,
  onActiveTypeChange,
  onCreateAgent,
  onCreateCodexAgent,
  onOpenCodexSession,
  onUseAgent,
  onViewAgentDetails,
  connectedRuntimeId = "",
  hiddenRuntimeIds = EMPTY_RUNTIME_IDS,
  codexRefreshKey = 0,
}: MyAgentsProps) {
  const resultsRef = useRef<HTMLElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const runtimeRequestRef = useRef(0);
  const codexRequestRef = useRef(0);
  const codexAbortRef = useRef<AbortController | null>(null);
  const [region, setRegion] = useState<RuntimeRegion>("cn-beijing");
  const [regionMenuOpen, setRegionMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [runtimeAgents, setRuntimeAgents] = useState<MyAgentCardData[]>([]);
  const [runtimeNextToken, setRuntimeNextToken] = useState("");
  const [loadingRuntimes, setLoadingRuntimes] = useState(true);
  const [runtimeError, setRuntimeError] = useState("");
  const [connectingAgentId, setConnectingAgentId] = useState("");
  const [codexSessions, setCodexSessions] = useState<SandboxSession[]>([]);
  const [codexLoading, setCodexLoading] = useState(false);
  const [codexError, setCodexError] = useState("");
  const [connectingCodexSessionId, setConnectingCodexSessionId] = useState("");

  const fetchRuntimePage = useCallback((token: string, reset: boolean) => {
    const requestId = ++runtimeRequestRef.current;
    setLoadingRuntimes(true);
    setRuntimeError("");
    return loadRuntimeAgents(runtimeScope, region, token, (agents) => {
      if (runtimeRequestRef.current !== requestId) return;
      setRuntimeAgents((current) => reset ? agents : [...current, ...agents]);
    })
      .then((nextToken) => {
        if (runtimeRequestRef.current === requestId) setRuntimeNextToken(nextToken);
      })
      .catch((cause) => {
        if (runtimeRequestRef.current !== requestId) return;
        setRuntimeError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (runtimeRequestRef.current === requestId) setLoadingRuntimes(false);
      });
  }, [region, runtimeScope]);

  useEffect(() => {
    if (activeType !== "general") return;
    setRuntimeAgents([]);
    setRuntimeNextToken("");
    void fetchRuntimePage("", true);
    return () => {
      runtimeRequestRef.current += 1;
    };
  }, [activeType, fetchRuntimePage]);

  const fetchCodexSessions = useCallback(() => {
    const requestId = ++codexRequestRef.current;
    codexAbortRef.current?.abort();
    const controller = new AbortController();
    codexAbortRef.current = controller;
    setCodexLoading(true);
    setCodexError("");
    return sandboxClient
      .listSessions({ signal: controller.signal })
      .then((sessions) => {
        if (codexRequestRef.current === requestId) setCodexSessions(sessions);
      })
      .catch((cause) => {
        if ((cause as Error)?.name === "AbortError") return;
        if (codexRequestRef.current !== requestId) return;
        setCodexError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (codexRequestRef.current === requestId) {
          setCodexLoading(false);
          codexAbortRef.current = null;
        }
      });
  }, []);

  useEffect(() => {
    if (activeType !== "codex") {
      codexAbortRef.current?.abort();
      return;
    }
    void fetchCodexSessions();
    return () => {
      codexRequestRef.current += 1;
      codexAbortRef.current?.abort();
    };
  }, [activeType, codexRefreshKey, fetchCodexSessions]);

  useEffect(() => {
    if (
      activeType !== "codex" ||
      codexLoading ||
      !codexSessions.some((session) =>
        CODEX_TRANSITIONAL_STATUSES.has(session.status.toLowerCase()),
      )
    ) {
      return;
    }
    const timer = window.setTimeout(() => {
      void fetchCodexSessions();
    }, 3_000);
    return () => window.clearTimeout(timer);
  }, [activeType, codexLoading, codexSessions, fetchCodexSessions]);

  useEffect(() => {
    const target = loadMoreRef.current;
    const root = resultsRef.current;
    if (!target || !root || activeType !== "general" || !runtimeNextToken || loadingRuntimes) {
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) void fetchRuntimePage(runtimeNextToken, false);
      },
      { root, rootMargin: "180px 0px", threshold: 0.01 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [activeType, fetchRuntimePage, loadingRuntimes, runtimeNextToken]);

  const useAgent = useCallback(async (agent: MyAgentCardData) => {
    if (connectingAgentId) return;
    setConnectingAgentId(agent.id);
    try {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      await onUseAgent(agent);
    } finally {
      setConnectingAgentId("");
    }
  }, [connectingAgentId, onUseAgent]);

  const openCodexSession = useCallback(async (session: SandboxSession) => {
    if (connectingCodexSessionId || session.status.toLowerCase() !== "ready") return;
    setConnectingCodexSessionId(session.id);
    setCodexError("");
    try {
      await onOpenCodexSession(session);
    } catch (cause) {
      setCodexError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setConnectingCodexSessionId("");
    }
  }, [connectingCodexSessionId, onOpenCodexSession]);

  const visibleAgents = useMemo(() => {
    if (activeType !== "general") return [];
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const matchingAgents = normalizedQuery
      ? runtimeAgents.filter((agent) =>
          agent.name.toLocaleLowerCase().includes(normalizedQuery),
        )
      : runtimeAgents;
    const availableAgents = hiddenRuntimeIds.size > 0
      ? matchingAgents.filter((agent) =>
          !agent.runtime || !hiddenRuntimeIds.has(agent.runtime.runtimeId),
        )
      : matchingAgents;
    const connectedIndex = availableAgents.findIndex(
      (agent) => agent.runtime?.runtimeId === connectedRuntimeId,
    );
    if (connectedIndex <= 0) return availableAgents;
    return [
      availableAgents[connectedIndex],
      ...availableAgents.slice(0, connectedIndex),
      ...availableAgents.slice(connectedIndex + 1),
    ];
  }, [activeType, connectedRuntimeId, hiddenRuntimeIds, query, runtimeAgents]);

  const visibleCodexSessions = useMemo(() => {
    if (activeType !== "codex") return [];
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) return codexSessions;
    return codexSessions.filter((session) =>
      [session.displayName, session.userSessionId, session.status]
        .some((value) => value.toLocaleLowerCase().includes(normalizedQuery)),
    );
  }, [activeType, codexSessions, query]);

  const activeTypeInfo = AGENT_TYPES.find((type) => type.id === activeType);
  const activeLabel = activeTypeInfo?.label ?? "智能体";
  const createLabel = activeTypeInfo?.createLabel ?? "添加智能体";
  const showInitialLoading =
    (activeType === "general" && loadingRuntimes && runtimeAgents.length === 0) ||
    (activeType === "codex" && codexLoading && codexSessions.length === 0);
  const visibleCount =
    activeType === "general"
      ? visibleAgents.length
      : activeType === "codex"
        ? visibleCodexSessions.length
        : 0;
  const showEmpty = !showInitialLoading && visibleCount === 0;
  const emptyMessage = activeType === "openclaw" || activeType === "hermes"
    ? "暂未开放"
    : query.trim() ? "没有匹配的智能体" : `${activeLabel}暂无内容`;
  const createAgent = canCreate && activeType === "general"
    ? () => onCreateAgent(region)
    : canCreate && activeType === "codex" ? onCreateCodexAgent : undefined;

  return (
    <div className="my-agents-page">
      <header className="my-agents-header">
        <div className="my-agents-heading">
          <div className="my-agents-title-row">
            <h1>智能体</h1>
            {activeType === "general" && (
              <div
                className="my-agents-region-picker"
                onKeyDown={(event) => {
                  if (event.key === "Escape") setRegionMenuOpen(false);
                }}
              >
                <button
                  type="button"
                  className="my-agents-region"
                  aria-label="Runtime 地域"
                  aria-haspopup="listbox"
                  aria-expanded={regionMenuOpen}
                  onClick={() => setRegionMenuOpen((open) => !open)}
                >
                  <span>{region === "cn-beijing" ? "北京" : "上海"}</span>
                  <ChevronDownIcon
                    className={`my-agents-region-chevron${regionMenuOpen ? " is-open" : ""}`}
                  />
                </button>
                {regionMenuOpen && (
                  <>
                    <div className="menu-scrim" onClick={() => setRegionMenuOpen(false)} />
                    <div className="my-agents-region-menu" role="listbox" aria-label="Runtime 地域">
                      {[
                        { value: "cn-beijing", label: "北京" },
                        { value: "cn-shanghai", label: "上海" },
                      ].map((item) => {
                        const selected = item.value === region;
                        return (
                          <button
                            key={item.value}
                            type="button"
                            role="option"
                            aria-selected={selected}
                            className={`my-agents-region-option${selected ? " is-selected" : ""}`}
                            onClick={() => {
                              setRegion(item.value as RuntimeRegion);
                              setRegionMenuOpen(false);
                            }}
                          >
                            <span>{item.label}</span>
                            {selected && <CheckIcon />}
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
          <p>
            {runtimeScope === "all"
              ? "在此处浏览所有智能体"
              : "在此处浏览您的所有智能体"}
          </p>
        </div>
        <label className="my-agent-search">
          <SearchIcon />
          <input
            type="search"
            aria-label="搜索智能体"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索所有类型智能体名称"
          />
        </label>
      </header>

      <div className="my-agent-type-bar">
        <nav className="my-agent-type-pills" aria-label="智能体类型">
          {AGENT_TYPES.map((type) => (
            <button
              type="button"
              key={type.id}
              className={`my-agent-type-pill${activeType === type.id ? " is-active" : ""}`}
              aria-pressed={activeType === type.id}
              onClick={() => onActiveTypeChange(type.id)}
            >
              {type.label}
            </button>
          ))}
        </nav>
        {canCreate && (
          <button
            type="button"
            className="my-agent-add"
            disabled={!createAgent}
            onClick={() => createAgent?.()}
          >
            <AddIcon />
            {createLabel}
          </button>
        )}
      </div>

      <section
        className="my-agent-results"
        ref={resultsRef}
        aria-label={`${activeLabel}列表`}
      >
        {showInitialLoading ? (
          <div className="my-agent-initial-loading" role="status" aria-live="polite">
            <span className="my-agent-loading-mark" aria-hidden="true" />
            <span>
              {activeType === "codex" ? "正在加载 Codex 智能体" : "正在加载智能体"}
            </span>
          </div>
        ) : (runtimeError && activeType === "general") ||
          (codexError && activeType === "codex" && codexSessions.length === 0) ? (
          <div className="my-agent-empty" role="alert">
            <p>{activeType === "codex" ? codexError : runtimeError}</p>
            <button
              type="button"
              onClick={() => {
                if (activeType === "codex") void fetchCodexSessions();
                else void fetchRuntimePage("", true);
              }}
            >
              重新加载
            </button>
          </div>
        ) : showEmpty ? (
          <div className="my-agent-empty">
            {!query.trim() && activeType === "general" && canCreate ? (
              <p>
                暂无智能体，
                <button
                  type="button"
                  className="my-agent-empty-create"
                  onClick={() => onCreateAgent(region)}
                >
                  点此创建
                </button>
              </p>
            ) : (
              <p>{emptyMessage}</p>
            )}
            {query.trim() && activeType !== "openclaw" && activeType !== "hermes" && (
              <span>请尝试搜索其他名称</span>
            )}
          </div>
        ) : (
          <>
            {codexError && activeType === "codex" && (
              <div className="my-agent-inline-error" role="alert">
                <span>{codexError}</span>
                <button type="button" onClick={() => void fetchCodexSessions()}>
                  重试
                </button>
              </div>
            )}
            <div className="my-agent-grid">
              {activeType === "general"
                ? visibleAgents.map((agent) => (
                    <AgentCard
                      key={agent.id}
                      agent={agent}
                      onUse={useAgent}
                      onViewDetails={onViewAgentDetails}
                      connecting={agent.id === connectingAgentId}
                      connected={agent.runtime?.runtimeId === connectedRuntimeId}
                      showOwnership={runtimeScope === "all"}
                    />
                  ))
                : visibleCodexSessions.map((session) => (
                    <CodexSessionCard
                      key={session.id}
                      session={session}
                      connecting={session.id === connectingCodexSessionId}
                      onOpen={openCodexSession}
                    />
                  ))}
            </div>
          </>
        )}

        {activeType === "general" && visibleAgents.length > 0 && (
          <div className="my-agent-load-more" ref={loadMoreRef} aria-live="polite">
            {loadingRuntimes ? (
              <>
                <span className="my-agent-loading-mark" aria-hidden="true" />
                <span>正在加载更多智能体</span>
              </>
            ) : runtimeNextToken ? (
              <span>继续滚动加载更多</span>
            ) : (
              <span>已加载全部智能体</span>
            )}
          </div>
        )}
        {activeType === "codex" && visibleCodexSessions.length > 0 && codexLoading && (
          <div className="my-agent-load-more" role="status" aria-live="polite">
            <span className="my-agent-loading-mark" aria-hidden="true" />
            <span>正在刷新 Codex 智能体</span>
          </div>
        )}
      </section>
    </div>
  );
}
