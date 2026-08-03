import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SVGProps } from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { Explore } from "@openai/apps-sdk-ui/components/Icon";

import {
  getRuntimes,
  type CloudRuntime,
  type RuntimeScope,
} from "../adk/client";
import {
  sandboxClient,
  type SandboxAgentKind,
  type SandboxSession,
} from "../adk/sandbox";
import { AgentFaceIcon } from "./AgentFaceIcon";
import "./MyAgents.css";

export interface MyAgentCardData {
  id: string;
  appName?: string;
  name: string;
  description: string;
  createdAt: string;
  specification: string;
  isMine?: boolean;
  runtime?: {
    runtimeId: string;
    region: string;
    currentVersion?: number | null;
    canDelete: boolean;
  };
  sandbox?: SandboxSession;
}

export type AgentType = "general" | "codex" | "openclaw" | "hermes";
type RuntimeRegion = "cn-beijing" | "cn-shanghai";
const DEFAULT_CREATE_REGION: RuntimeRegion = "cn-beijing";

const AGENT_TYPES: Array<{ id: AgentType; label: string }> = [
  { id: "general", label: "通用智能体" },
  { id: "codex", label: "Codex 智能体" },
  { id: "openclaw", label: "OpenClaw 智能体" },
  { id: "hermes", label: "Hermes 智能体" },
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

function AgentTypeIcon({ type }: { type: AgentType }) {
  if (type === "general") return <AgentFaceIcon />;
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {type === "codex" ? (
        <>
          <path d="m12 3 7 4v8l-7 4-7-4V7l7-4Z" />
          <path d="m8 9 4-2.3L16 9v4.5L12 16l-4-2.5V9Z" />
        </>
      ) : type === "openclaw" ? (
        <>
          <path d="M7 19c-2-2.5-2.5-5.5-.8-8.2M17 19c2-2.5 2.5-5.5.8-8.2" />
          <path d="m6.2 10.8-2.7-2M17.8 10.8l2.7-2M9.2 8 7.5 4M14.8 8 16.5 4" />
          <path d="M8.5 18.5h7" />
        </>
      ) : (
        <>
          <path d="M5 18.5V9l7-4 7 4v9.5" />
          <path d="M8.5 13h7M9 18.5v-2.8h6v2.8" />
        </>
      )}
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

function formatRuntimeRegion(region?: string): string {
  if (region === "cn-shanghai") return "上海";
  if (region === "cn-beijing") return "北京";
  return "—";
}

function runtimeToAgent(runtime: CloudRuntime): MyAgentCardData {
  return {
    id: runtime.runtimeId,
    name: runtime.name,
    description: runtime.description?.trim() || "暂无描述",
    createdAt: formatCreatedAt(runtime.createdAt ?? ""),
    specification: formatRuntimeRegion(runtime.region),
    isMine: runtime.isMine,
    runtime: {
      runtimeId: runtime.runtimeId,
      region: runtime.region,
      currentVersion: runtime.currentVersion,
      canDelete: runtime.canDelete,
    },
  };
}

function sandboxToAgent(session: SandboxSession): MyAgentCardData {
  const status = session.status || "Unknown";
  return {
    id: session.id,
    name: session.displayName || `${session.toolName} 智能体`,
    description: `AgentKit Session · ${status}`,
    createdAt: formatCreatedAt(session.createdAt),
    specification: formatRuntimeRegion(session.region),
    sandbox: session,
  };
}

async function loadRuntimeAgents(
  runtimeScope: RuntimeScope,
  nextToken: string,
  onList: (agents: MyAgentCardData[]) => void,
): Promise<string> {
  const requestKey = `${runtimeScope}:all:${nextToken}`;
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
      region: "all",
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
  const actionable = Boolean(agent.runtime || agent.sandbox);
  return (
    <article className="my-agent-card">
      <div className="my-agent-card-content">
        <div className="my-agent-card-title">
          <h3>{agent.name}</h3>
          {showOwnership && agent.isMine && (
            <span className="runtime-owner-badge">我创建的</span>
          )}
        </div>
        <p className="my-agent-description">{agent.description}</p>
        <dl className="my-agent-meta">
          <div className="my-agent-created-at">
            <dt>创建时间</dt>
            <dd>{agent.createdAt}</dd>
          </div>
          <div className="my-agent-region">
            <dt>地域</dt>
            <dd>{agent.specification}</dd>
          </div>
        </dl>
      </div>
      <footer className="my-agent-actions">
        <button
          type="button"
          className="my-agent-details"
          disabled={!actionable}
          aria-label={`查看 ${agent.name} 详情`}
          onClick={() => onViewDetails?.(agent)}
        >
          查看详情
        </button>
        <button
          type="button"
          className={`my-agent-use${connected ? " is-connected" : ""}`}
          disabled={!actionable || connecting || connected}
          aria-busy={connecting || undefined}
          aria-label={connected ? `${agent.name} 已连接` : `使用 ${agent.name}`}
          onClick={() => void onUse?.(agent)}
        >
          {connecting ? (
            <>
              <span className="my-agent-use-spinner" aria-hidden="true" />
              <span>连接中</span>
            </>
          ) : connected ? "已连接" : "使用"}
        </button>
      </footer>
    </article>
  );
}

export interface MyAgentsProps {
  canCreate: boolean;
  runtimeScope: RuntimeScope;
  onCreateAgent: (region: RuntimeRegion) => void;
  onUseAgent: (agent: MyAgentCardData) => Promise<void>;
  onViewAgentDetails: (agent: MyAgentCardData) => void;
  onCreateSandboxAgent: (kind: "codex" | SandboxAgentKind) => void;
  onUseSandboxAgent: (session: SandboxSession) => Promise<void>;
  onViewSandboxAgentDetails: (session: SandboxSession) => void;
  sandboxRefreshKey?: number;
  connectedRuntimeId?: string;
  hiddenRuntimeIds?: ReadonlySet<string>;
}

export function MyAgents({
  canCreate,
  runtimeScope,
  onCreateAgent,
  onUseAgent,
  onViewAgentDetails,
  onCreateSandboxAgent,
  onUseSandboxAgent,
  onViewSandboxAgentDetails,
  sandboxRefreshKey = 0,
  connectedRuntimeId = "",
  hiddenRuntimeIds = EMPTY_RUNTIME_IDS,
}: MyAgentsProps) {
  const resultsRef = useRef<HTMLElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const runtimeRequestRef = useRef(0);
  const sandboxRequestRef = useRef(0);
  const sandboxAbortRef = useRef<AbortController | null>(null);
  const [activeType, setActiveType] = useState<AgentType>("general");
  const [query, setQuery] = useState("");
  const [runtimeAgents, setRuntimeAgents] = useState<MyAgentCardData[]>([]);
  const [runtimeNextToken, setRuntimeNextToken] = useState("");
  const [loadingRuntimes, setLoadingRuntimes] = useState(true);
  const [runtimeError, setRuntimeError] = useState("");
  const [sandboxAgents, setSandboxAgents] = useState<MyAgentCardData[]>([]);
  const [loadingSandboxAgents, setLoadingSandboxAgents] = useState(false);
  const [sandboxError, setSandboxError] = useState("");
  const [connectingAgentId, setConnectingAgentId] = useState("");

  const fetchRuntimePage = useCallback((token: string, reset: boolean) => {
    const requestId = ++runtimeRequestRef.current;
    setLoadingRuntimes(true);
    setRuntimeError("");
    return loadRuntimeAgents(runtimeScope, token, (agents) => {
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
  }, [runtimeScope]);

  useEffect(() => {
    setRuntimeAgents([]);
    setRuntimeNextToken("");
    void fetchRuntimePage("", true);
    return () => {
      runtimeRequestRef.current += 1;
    };
  }, [fetchRuntimePage]);

  const fetchSandboxAgents = useCallback(async (type: Exclude<AgentType, "general">) => {
    sandboxAbortRef.current?.abort();
    const controller = new AbortController();
    sandboxAbortRef.current = controller;
    const requestId = ++sandboxRequestRef.current;
    setLoadingSandboxAgents(true);
    setSandboxError("");
    try {
      const sessions = type === "codex"
        ? await sandboxClient.listSessions({ signal: controller.signal })
        : await sandboxClient.listAgentSessions(type, { signal: controller.signal });
      if (sandboxRequestRef.current !== requestId) return;
      setSandboxAgents(sessions.map(sandboxToAgent));
    } catch (cause) {
      if ((cause as Error)?.name === "AbortError") return;
      if (sandboxRequestRef.current !== requestId) return;
      setSandboxError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (sandboxAbortRef.current === controller) sandboxAbortRef.current = null;
      if (sandboxRequestRef.current === requestId) {
        setLoadingSandboxAgents(false);
      }
    }
  }, []);

  useEffect(() => {
    if (activeType === "general") {
      sandboxAbortRef.current?.abort();
      sandboxAbortRef.current = null;
      sandboxRequestRef.current += 1;
      return;
    }
    void fetchSandboxAgents(activeType);
    return () => {
      sandboxAbortRef.current?.abort();
      sandboxAbortRef.current = null;
      sandboxRequestRef.current += 1;
    };
  }, [activeType, fetchSandboxAgents, sandboxRefreshKey]);

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
      { root, rootMargin: "240px 0px", threshold: 0.01 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [activeType, fetchRuntimePage, loadingRuntimes, runtimeNextToken]);

  const useAgent = useCallback(async (agent: MyAgentCardData) => {
    if (connectingAgentId) return;
    setConnectingAgentId(agent.id);
    try {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      if (agent.sandbox) {
        await onUseSandboxAgent(agent.sandbox);
      } else {
        await onUseAgent(agent);
      }
    } finally {
      setConnectingAgentId("");
    }
  }, [connectingAgentId, onUseAgent, onUseSandboxAgent]);

  const visibleAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const source = activeType === "general" ? runtimeAgents : sandboxAgents;
    const matchingAgents = normalizedQuery
      ? source.filter((agent) =>
          agent.name.toLocaleLowerCase().includes(normalizedQuery),
        )
      : source;
    if (activeType !== "general") return matchingAgents;
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
  }, [
    activeType,
    connectedRuntimeId,
    hiddenRuntimeIds,
    query,
    runtimeAgents,
    sandboxAgents,
  ]);

  const activeTypeInfo = AGENT_TYPES.find((type) => type.id === activeType);
  const activeLabel = activeTypeInfo?.label ?? "智能体";
  const showInitialLoading = activeType === "general"
    ? loadingRuntimes && runtimeAgents.length === 0
    : loadingSandboxAgents && sandboxAgents.length === 0;
  const showEmpty = !showInitialLoading && visibleAgents.length === 0;
  const createAgent = canCreate
    ? activeType === "general"
      ? () => onCreateAgent(DEFAULT_CREATE_REGION)
      : () => onCreateSandboxAgent(activeType)
    : undefined;
  const createDisabledReason = !canCreate
    ? "当前账号没有创建智能体权限"
    : undefined;

  return (
    <div className="my-agents-page">
      <header className="my-agents-header">
        <div className="my-agents-heading">
          <div className="my-agents-title-row">
            <h1>智能体</h1>
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
              onClick={() => setActiveType(type.id)}
            >
              {type.label}
            </button>
          ))}
        </nav>
        <button
          type="button"
          className="my-agent-create-primary"
          disabled={!createAgent}
          title={createDisabledReason}
          onClick={() => createAgent?.()}
        >
          <AddIcon />
          <span>创建智能体</span>
        </button>
      </div>

      <section
        className="my-agent-results"
        ref={resultsRef}
        aria-label={`${activeLabel}列表`}
      >
        {showInitialLoading ? (
          <div className="my-agent-initial-loading" role="status" aria-live="polite">
            <span className="my-agent-loading-mark" aria-hidden="true" />
            <span>正在加载智能体</span>
          </div>
        ) : (activeType === "general" ? runtimeError : sandboxError) ? (
          <div className="my-agent-empty" role="alert">
            <p>{activeType === "general" ? runtimeError : sandboxError}</p>
            <button
              type="button"
              onClick={() => {
                if (activeType === "general") {
                  void fetchRuntimePage("", true);
                } else {
                  void fetchSandboxAgents(activeType);
                }
              }}
            >
              重新加载
            </button>
          </div>
        ) : showEmpty ? (
          query.trim() ? (
            <div className="my-agent-empty-message">
              <EmptyMessage fill="none">
                <EmptyMessage.Icon>
                  <Explore />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>没有匹配的智能体</EmptyMessage.Title>
                <EmptyMessage.Description>请尝试搜索其他名称</EmptyMessage.Description>
              </EmptyMessage>
            </div>
          ) : activeType !== "general" ? (
            <div className="my-agent-empty-message">
              <EmptyMessage fill="none">
                <EmptyMessage.Icon>
                  <AgentTypeIcon type={activeType} />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>暂无{activeLabel}</EmptyMessage.Title>
                <EmptyMessage.Description>
                  创建一个{activeLabel}，开始使用 AgentKit Session
                </EmptyMessage.Description>
                {canCreate ? (
                  <EmptyMessage.ActionRow>
                    <Button
                      color="primary"
                      size="lg"
                      onClick={() => onCreateSandboxAgent(activeType)}
                    >
                      <AddIcon />
                      创建智能体
                    </Button>
                  </EmptyMessage.ActionRow>
                ) : null}
              </EmptyMessage>
            </div>
          ) : (
            <div className="my-agent-empty-message">
              <EmptyMessage fill="none">
                <EmptyMessage.Icon>
                  <AgentFaceIcon />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>暂无通用智能体</EmptyMessage.Title>
                <EmptyMessage.Description>
                  创建一个通用智能体，开始构建和对话
                </EmptyMessage.Description>
                {canCreate ? (
                  <EmptyMessage.ActionRow>
                    <Button
                      color="primary"
                      size="lg"
                      onClick={() => onCreateAgent(DEFAULT_CREATE_REGION)}
                    >
                      <AddIcon />
                      创建智能体
                    </Button>
                  </EmptyMessage.ActionRow>
                ) : null}
              </EmptyMessage>
            </div>
          )
        ) : (
          <div className="my-agent-grid">
            {visibleAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onUse={useAgent}
                onViewDetails={(agent) => {
                  if (agent.sandbox) {
                    onViewSandboxAgentDetails(agent.sandbox);
                  } else {
                    onViewAgentDetails(agent);
                  }
                }}
                connecting={agent.id === connectingAgentId}
                connected={agent.runtime?.runtimeId === connectedRuntimeId}
                showOwnership={runtimeScope === "all"}
              />
            ))}
          </div>
        )}

        {activeType === "general" && !runtimeError && !showInitialLoading &&
          (visibleAgents.length > 0 || Boolean(runtimeNextToken)) && (
          <div className="my-agent-load-more" ref={loadMoreRef} aria-live="polite">
            {loadingRuntimes ? (
              <>
                <span className="my-agent-loading-mark" aria-hidden="true" />
                <span>正在加载更多智能体</span>
              </>
            ) : runtimeNextToken ? (
              <span>继续下滑加载更多</span>
            ) : (
              <span>已加载全部智能体</span>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
