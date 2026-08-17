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
  defaultCloudRegion,
  formatCloudRegion,
  type CloudProvider,
} from "../adk/cloudProvider";
import {
  sandboxClient,
  sandboxStatusLabel,
  type SandboxAgentResource,
  type SandboxAgentKind,
} from "../adk/sandbox";
import { formatRequestError } from "../adk/requestError";
import type { WorkspaceAgentDraft } from "../create/agentDraftStorage";
import { AgentFaceIcon } from "./AgentFaceIcon";
import { SandboxAgentIcon } from "./icons/SandboxAgentIcons";
import type { DeploymentTaskUpdate } from "./ProjectPreview";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import "./MyAgents.css";

export interface MyAgentCardData {
  id: string;
  appName?: string;
  name: string;
  description: string;
  createdAt: string;
  specificationLabel: string;
  specification: string;
  isMine?: boolean;
  runtime?: {
    runtimeId: string;
    region: string;
    currentVersion?: number | null;
    canDelete: boolean;
  };
  sandbox?: SandboxAgentResource;
  draft?: WorkspaceAgentDraft;
}

export type AgentType =
  | "general"
  | "codex"
  | "deepseek-harness"
  | "openclaw"
  | "hermes";

const AGENT_TYPES: Array<{ id: AgentType; label: string }> = [
  { id: "general", label: "通用智能体" },
  { id: "codex", label: "Codex 智能体" },
  { id: "deepseek-harness", label: "DeepSeek Harness" },
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

function HandoffIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M2.75 5.25h8.75m0 0-2-2m2 2-2 2M13.25 10.75H4.5m0 0 2 2m-2-2 2-2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AgentTypeIcon({ type }: { type: AgentType }) {
  if (type === "general") return <AgentFaceIcon />;
  return <SandboxAgentIcon kind={type} />;
}

function formatCreatedAt(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date).replace(/\//g, "-");
}

export function formatSandboxRemainingTime(
  expireAt: string,
  nowMs = Date.now(),
): string {
  const expireTime = Date.parse(expireAt);
  if (!Number.isFinite(expireTime) || expireTime - nowMs < 60_000) {
    return "即将清空";
  }
  const remainingMinutes = Math.ceil((expireTime - nowMs) / 60_000);
  const hours = Math.floor(remainingMinutes / 60);
  const minutes = remainingMinutes % 60;
  return `${hours} 小时 ${minutes} 分钟`;
}

function runtimeToAgent(runtime: CloudRuntime): MyAgentCardData {
  return {
    id: runtime.runtimeId,
    name: runtime.name,
    description: runtime.description?.trim() || "暂无描述",
    createdAt: formatCreatedAt(runtime.createdAt ?? ""),
    specificationLabel: "创建人",
    specification: runtime.author || "—",
    isMine: runtime.isMine,
    runtime: {
      runtimeId: runtime.runtimeId,
      region: runtime.region,
      currentVersion: runtime.currentVersion,
      canDelete: runtime.canDelete,
    },
  };
}

function sandboxToAgent(session: SandboxAgentResource): MyAgentCardData {
  return {
    id: session.id,
    name: session.displayName || `${session.toolName} 智能体`,
    description: sandboxStatusLabel(session.status),
    createdAt: formatCreatedAt(session.createdAt),
    specificationLabel: "创建人",
    specification: session.createdBy || "—",
    sandbox: session,
  };
}

function draftToAgent(item: WorkspaceAgentDraft): MyAgentCardData {
  return {
    id: item.id,
    name: item.draft.name || "未命名 Agent",
    description: item.draft.description?.trim() || "暂无描述",
    createdAt: formatCreatedAt(new Date(item.updatedAt).toISOString()),
    specificationLabel: "存储位置",
    specification: "当前浏览器",
    draft: item,
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
  cloudProvider,
  onUse,
  onViewDetails,
  connecting,
  connected,
  showOwnership,
  deploymentTask,
  nowMs,
  onViewDeploymentTask,
  onEditDraft,
  onDeleteDraft,
}: {
  agent: MyAgentCardData;
  cloudProvider: CloudProvider;
  onUse?: (agent: MyAgentCardData) => Promise<void>;
  onViewDetails?: (agent: MyAgentCardData) => void;
  connecting?: boolean;
  connected?: boolean;
  showOwnership?: boolean;
  deploymentTask?: DeploymentTaskUpdate;
  nowMs: number;
  onViewDeploymentTask?: (task: DeploymentTaskUpdate) => void;
  onEditDraft?: (draft: WorkspaceAgentDraft) => void;
  onDeleteDraft?: (draft: WorkspaceAgentDraft) => void;
}) {
  const sandboxStatus = agent.sandbox?.status.toLowerCase();
  const wakeable = agent.sandbox?.resourceType === "snapshot";
  const actionable = Boolean(
    agent.runtime || sandboxStatus === "ready" || sandboxStatus === "wakeable",
  );
  const sandboxResourceId = agent.sandbox?.resourceType === "snapshot"
    ? agent.sandbox.sourceSessionId || agent.sandbox.snapshotId
    : agent.sandbox?.id;
  return (
    <article className="my-agent-card">
      <div className="my-agent-card-content">
        <div className="my-agent-card-title">
          <div className="my-agent-card-title-copy">
            <h3>{agent.name}</h3>
            {agent.sandbox ? (
              <span className="my-agent-session-id" title={sandboxResourceId}>
                {sandboxResourceId}
              </span>
            ) : null}
          </div>
          {agent.draft ? (
            <span className="my-agent-draft-badge">
              {deploymentTask ? "部署中" : "草稿"}
            </span>
          ) : agent.sandbox ? (
            <span
              className="my-agent-status-label"
              data-ready={agent.sandbox.status.toLowerCase() === "ready" || undefined}
              data-wakeable={wakeable || undefined}
            >
              {agent.description}
            </span>
          ) : agent.runtime ? (
            <div className="my-agent-card-badges">
              {deploymentTask ? (
                <span className="my-agent-deploying-badge">部署中</span>
              ) : null}
              <span className="my-agent-region-badge">
                {formatCloudRegion(agent.runtime.region, cloudProvider)}
              </span>
              {showOwnership && agent.isMine ? (
                <span className="runtime-owner-badge">我创建的</span>
              ) : null}
            </div>
          ) : null}
        </div>
        {!agent.sandbox ? (
          <p className="my-agent-description">{agent.description}</p>
        ) : null}
        <dl className="my-agent-meta">
          <div className="my-agent-created-at">
            <dt>{agent.draft ? "更新时间" : "创建时间"}</dt>
            <dd>{agent.createdAt}</dd>
          </div>
          <div className="my-agent-region">
            <dt>{agent.specificationLabel}</dt>
            <dd>{agent.specification}</dd>
          </div>
          {agent.sandbox ? (
            <div
              className={`my-agent-expiry${
                agent.sandbox.resourceType === "session" && agent.sandbox.persistent
                  ? ""
                  : " is-expiring"
              }`}
            >
              <dt>剩余时间</dt>
              <dd>
                {agent.sandbox.resourceType === "snapshot"
                  ? "可唤醒"
                  : agent.sandbox.persistent
                  ? "永不过期"
                  : formatSandboxRemainingTime(agent.sandbox.expireAt, nowMs)}
              </dd>
            </div>
          ) : null}
        </dl>
      </div>
      <footer className="my-agent-actions">
        {agent.draft ? (
          <>
            <button
              type="button"
              className="my-agent-details"
              aria-label={deploymentTask
                ? `查看 ${agent.name} 部署进度`
                : `编辑草稿 ${agent.name}`}
              onClick={() => deploymentTask
                ? onViewDeploymentTask?.(deploymentTask)
                : onEditDraft?.(agent.draft!)}
            >
              {deploymentTask ? "查看进度" : "编辑"}
            </button>
            <button
              type="button"
              className="my-agent-delete"
              aria-label={`删除草稿 ${agent.name}`}
              onClick={() => onDeleteDraft?.(agent.draft!)}
            >
              删除
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className="my-agent-details"
              disabled={!actionable}
              aria-label={deploymentTask
                ? `查看 ${agent.name} 部署进度`
                : `查看 ${agent.name} 详情`}
              onClick={() => deploymentTask
                ? onViewDeploymentTask?.(deploymentTask)
                : onViewDetails?.(agent)}
            >
              {deploymentTask ? "查看进度" : "查看详情"}
            </button>
            <button
              type="button"
              className={`my-agent-use${connected ? " is-connected" : ""}`}
              disabled={!actionable || connecting || connected}
              aria-busy={connecting || undefined}
              aria-label={connected
                ? `${agent.name} 已连接`
                : wakeable
                  ? `唤醒 ${agent.name}`
                  : `使用 ${agent.name}`}
              onClick={() => void onUse?.(agent)}
            >
              {connecting ? (
                <>
                  <span className="my-agent-use-spinner" aria-hidden="true" />
                  <span>{wakeable ? "唤醒中" : "连接中"}</span>
                </>
              ) : connected ? "已连接" : wakeable ? "唤醒" : "使用"}
            </button>
          </>
        )}
      </footer>
    </article>
  );
}

export interface MyAgentsProps {
  cloudProvider: CloudProvider;
  canCreate: boolean;
  runtimeScope: RuntimeScope;
  onCreateAgent: (region: string) => void;
  onOpenCodexProjectUpload?: () => void;
  onUseAgent: (agent: MyAgentCardData) => Promise<void>;
  onViewAgentDetails: (agent: MyAgentCardData) => void;
  onCreateSandboxAgent: (kind: "codex" | SandboxAgentKind) => void;
  onUseSandboxAgent: (session: SandboxAgentResource) => Promise<void>;
  onViewSandboxAgentDetails: (session: SandboxAgentResource) => void;
  sandboxRefreshKey?: number;
  connectedRuntimeId?: string;
  hiddenRuntimeIds?: ReadonlySet<string>;
  drafts?: WorkspaceAgentDraft[];
  deploymentTasks?: DeploymentTaskUpdate[];
  draftDeploymentTaskIds?: Readonly<Record<string, string>>;
  onViewDeploymentTask?: (task: DeploymentTaskUpdate) => void;
  onEditDraft?: (draft: WorkspaceAgentDraft) => void;
  onDeleteDraft?: (draft: WorkspaceAgentDraft) => void;
}

export function MyAgents({
  cloudProvider,
  canCreate,
  runtimeScope,
  onCreateAgent,
  onOpenCodexProjectUpload,
  onUseAgent,
  onViewAgentDetails,
  onCreateSandboxAgent,
  onUseSandboxAgent,
  onViewSandboxAgentDetails,
  sandboxRefreshKey = 0,
  connectedRuntimeId = "",
  hiddenRuntimeIds = EMPTY_RUNTIME_IDS,
  drafts = [],
  deploymentTasks = [],
  draftDeploymentTaskIds = {},
  onViewDeploymentTask,
  onEditDraft,
  onDeleteDraft,
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
  const [draftToDelete, setDraftToDelete] = useState<WorkspaceAgentDraft | null>(null);
  const [remainingTimeNow, setRemainingTimeNow] = useState(() => Date.now());
  const hasExpiringSandboxAgents = sandboxAgents.some(
    (agent) =>
      agent.sandbox?.resourceType === "session" && agent.sandbox.persistent === false,
  );

  useEffect(() => {
    if (!hasExpiringSandboxAgents) return;
    setRemainingTimeNow(Date.now());
    const timer = window.setInterval(() => setRemainingTimeNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, [hasExpiringSandboxAgents]);

  const draftAgents = useMemo(() => drafts.map(draftToAgent), [drafts]);
  const activeDeploymentTasks = useMemo(() => {
    const byId = new Map<string, DeploymentTaskUpdate>();
    const byRuntimeId = new Map<string, DeploymentTaskUpdate>();
    for (const task of deploymentTasks) {
      if (task.status !== "running") continue;
      byId.set(task.id, task);
      if (!task.runtimeId) continue;
      const previous = byRuntimeId.get(task.runtimeId);
      if (!previous || task.startedAt > previous.startedAt) {
        byRuntimeId.set(task.runtimeId, task);
      }
    }
    return { byId, byRuntimeId };
  }, [deploymentTasks]);

  const deploymentTaskForAgent = useCallback((agent: MyAgentCardData) => {
    if (agent.draft) {
      const taskId = draftDeploymentTaskIds[agent.draft.id];
      return taskId ? activeDeploymentTasks.byId.get(taskId) : undefined;
    }
    const runtimeId = agent.runtime?.runtimeId;
    return runtimeId
      ? activeDeploymentTasks.byRuntimeId.get(runtimeId)
      : undefined;
  }, [activeDeploymentTasks, draftDeploymentTaskIds]);

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
        setRuntimeError(formatRequestError(cause, "加载通用智能体", "GET /web/runtimes"));
      })
      .finally(() => {
        if (runtimeRequestRef.current === requestId) setLoadingRuntimes(false);
      });
  }, [runtimeScope]);

  useEffect(() => {
    if (activeType !== "general") return;
    setRuntimeAgents([]);
    setRuntimeNextToken("");
    void fetchRuntimePage("", true);
    return () => {
      runtimeRequestRef.current += 1;
    };
  }, [activeType, fetchRuntimePage]);

  const fetchSandboxAgents = useCallback(async (type: Exclude<AgentType, "general">) => {
    sandboxAbortRef.current?.abort();
    const controller = new AbortController();
    sandboxAbortRef.current = controller;
    const requestId = ++sandboxRequestRef.current;
    setLoadingSandboxAgents(true);
    setSandboxError("");
    setSandboxAgents([]);
    try {
      const sessions = type === "codex"
        ? await sandboxClient.listSessions({ signal: controller.signal })
        : await sandboxClient.listAgentSessions(type, { signal: controller.signal });
      if (sandboxRequestRef.current !== requestId) return;
      setSandboxAgents(sessions.map(sandboxToAgent));
    } catch (cause) {
      if ((cause as Error)?.name === "AbortError") return;
      if (sandboxRequestRef.current !== requestId) return;
      setSandboxError(formatRequestError(
        cause,
        `加载 ${AGENT_TYPES.find((item) => item.id === type)?.label ?? type}`,
        `GET /web/${type === "codex" ? "sandbox" : type}/sessions`,
      ));
    } finally {
      if (sandboxAbortRef.current === controller) sandboxAbortRef.current = null;
      if (sandboxRequestRef.current === requestId) {
        setLoadingSandboxAgents(false);
      }
    }
  }, []);

  function selectAgentType(type: AgentType) {
    if (type === activeType) return;
    if (type === "general") {
      runtimeRequestRef.current += 1;
      setRuntimeAgents([]);
      setRuntimeNextToken("");
      setRuntimeError("");
      setLoadingRuntimes(true);
    } else {
      sandboxAbortRef.current?.abort();
      sandboxAbortRef.current = null;
      sandboxRequestRef.current += 1;
      setSandboxAgents([]);
      setSandboxError("");
      setLoadingSandboxAgents(true);
    }
    setActiveType(type);
  }

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
    const source = activeType === "general"
      ? [...draftAgents, ...runtimeAgents]
      : sandboxAgents;
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
    draftAgents,
    hiddenRuntimeIds,
    query,
    runtimeAgents,
    sandboxAgents,
  ]);

  const activeTypeInfo = AGENT_TYPES.find((type) => type.id === activeType);
  const activeLabel = activeTypeInfo?.label ?? "智能体";
  const showInitialLoading = activeType === "general"
    ? loadingRuntimes && runtimeAgents.length === 0 && draftAgents.length === 0
    : loadingSandboxAgents && sandboxAgents.length === 0;
  const showEmpty = !showInitialLoading && visibleAgents.length === 0;
  const createAgent = canCreate
    ? activeType === "general"
      ? () => onCreateAgent(defaultCloudRegion(cloudProvider))
      : () => onCreateSandboxAgent(activeType)
    : undefined;
  const showCodexProjectUpload =
    activeType === "codex" && canCreate && Boolean(onOpenCodexProjectUpload);
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
              onClick={() => selectAgentType(type.id)}
            >
              {type.label}
            </button>
          ))}
        </nav>
        <div className="my-agent-type-actions">
          {showCodexProjectUpload ? (
            <button
              type="button"
              className="my-agent-create-secondary"
              onClick={onOpenCodexProjectUpload}
            >
              <HandoffIcon />
              <span>接力</span>
            </button>
          ) : null}
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
        ) : (activeType === "general" ? runtimeError : sandboxError) && visibleAgents.length === 0 ? (
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
                <EmptyMessage.Title className="my-agent-sandbox-empty-title">
                  暂无 {activeLabel}
                </EmptyMessage.Title>
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
                      onClick={() => onCreateAgent(defaultCloudRegion(cloudProvider))}
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
          <>
            {activeType === "general" && runtimeError ? (
              <div className="my-agent-inline-error" role="alert">
                <span>{runtimeError}</span>
                <button type="button" onClick={() => void fetchRuntimePage("", true)}>
                  重新加载
                </button>
              </div>
            ) : null}
            <div className="my-agent-grid">
              {visibleAgents.map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={agent}
                  cloudProvider={cloudProvider}
                  deploymentTask={deploymentTaskForAgent(agent)}
                  nowMs={remainingTimeNow}
                  onViewDeploymentTask={onViewDeploymentTask}
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
                  onEditDraft={onEditDraft}
                  onDeleteDraft={setDraftToDelete}
                />
              ))}
            </div>
          </>
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
      {draftToDelete ? (
        <StudioConfirmDialog
          title="删除草稿？"
          description={`删除后将无法恢复“${draftToDelete.draft.name || "未命名 Agent"}”。`}
          confirmLabel="删除草稿"
          variant="danger"
          onCancel={() => setDraftToDelete(null)}
          onConfirm={() => {
            onDeleteDraft?.(draftToDelete);
            setDraftToDelete(null);
          }}
        />
      ) : null}
    </div>
  );
}
