import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { SVGProps } from "react";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { Explore } from "@openai/apps-sdk-ui/components/Icon";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";

import {
  invalidateRuntimeUpdateCapabilityCache,
  prefetchRuntimeUpdateCapability,
  probeRuntimeApps,
  RuntimeProbeError,
  type CloudRuntime,
  type RuntimeScope,
} from "../adk/client";
import {
  getRuntimesWithTimeoutRetry,
  isAbortError,
  runRuntimeCompatibilityChecks,
  withRuntimeCompatibilitySlot,
} from "../adk/runtimeDiscovery";
import {
  cloudRegionOptions,
  defaultCloudRegion,
  isSupportedCloudRegion,
  type CloudRegion,
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
import {
  ResourceCard,
  ResourceCardAction,
  ResourceCardDescription,
  ResourceCardHeader,
  ResourceCardMetadata,
  ResourceCardRevealAction,
  ResourceCreateCard,
  ResourceGrid,
  ResourceIdentityMark,
  ResourceFilterSelect,
  type ResourceFilterOption,
  ResourcePageHeader,
  ResourcePageShell,
  ResourceResults,
  ResourceSearch,
  ResourceTabs,
  ResourceToolbar,
} from "./ResourceCollection";
import { formatResourceSource } from "./resourceMetadata";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import { formatRelativeTimeLabel } from "./relativeTime";
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
  region?: string;
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
  { id: "codex", label: "Codex" },
  { id: "deepseek-harness", label: "DeepSeek" },
  { id: "openclaw", label: "OpenClaw" },
  { id: "hermes", label: "Hermes" },
];
const AGENT_TYPE_OPTIONS: Array<ResourceFilterOption<AgentType>> = AGENT_TYPES.map(({ id, label }) => ({
  value: id,
  label,
}));
const RUNTIME_PAGE_SIZE = 24;
const RUNTIME_PAGE_CACHE_TTL_MS = 30_000;
const RUNTIME_COMPATIBILITY_TIMEOUT_MS = 7_000;
const RUNTIME_COMPATIBILITY_RETRY_TIMEOUT_MS = 20_000;
const UPDATE_CAPABILITY_PREFETCH_LIMIT = 6;
const UPDATE_CAPABILITY_PREFETCH_CONCURRENCY = 2;
const UPDATE_CAPABILITY_PREFETCH_DELAY_MS = 250;
type RuntimeCompatibilityStatus = "checking" | "compatible" | "unsupported" | "error";
interface RuntimeCompatibility {
  status: RuntimeCompatibilityStatus;
  message: string;
}
const RUNTIME_COMPATIBILITY_CHECKING_MESSAGE =
  "正在请求 Runtime /list-apps，以确认该智能体是否支持 Studio 对话。";
const RUNTIME_COMPATIBILITY_EMPTY_MESSAGE =
  "Runtime /list-apps 未返回可用的 Agent，暂时无法连接对话。";
const runtimePageRequests = new Map<
  string,
  Promise<{ runtimes: CloudRuntime[]; nextToken: string }>
>();
const runtimePageCache = new Map<
  string,
  { page: { runtimes: CloudRuntime[]; nextToken: string }; expiresAt: number }
>();
const EMPTY_RUNTIME_IDS = new Set<string>();

function runtimeCompatibilityKey(agent: MyAgentCardData): string {
  const runtime = agent.runtime;
  return runtime
    ? `${runtime.region}:${runtime.runtimeId}:${runtime.currentVersion ?? ""}`
    : "";
}

function runtimeCompatibilityFailure(error: unknown): RuntimeCompatibility {
  const message = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : "Runtime /list-apps 请求失败，未返回可识别的错误信息。";
  return {
    status: error instanceof RuntimeProbeError && error.unsupported
      ? "unsupported"
      : "error",
    message,
  };
}

export function invalidateRuntimeAgentCache(runtimeIds?: Iterable<string>) {
  if (!runtimeIds) {
    runtimePageRequests.clear();
    runtimePageCache.clear();
    invalidateRuntimeUpdateCapabilityCache();
    return;
  }
  const targetRuntimeIds = new Set(runtimeIds);
  if (targetRuntimeIds.size === 0) return;
  for (const [key, cached] of runtimePageCache) {
    if (cached.page.runtimes.some((runtime) => targetRuntimeIds.has(runtime.runtimeId))) {
      runtimePageCache.delete(key);
    }
  }
  for (const runtimeId of targetRuntimeIds) {
    invalidateRuntimeUpdateCapabilityCache(runtimeId);
  }
  runtimePageRequests.clear();
}

function AddIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="M8 3.25v9.5M3.25 8h9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function AgentUseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M8.313 3.646a.5.5 0 0 1 .707 0l4 4a.5.5 0 0 1 0 .708l-4 4a.5.5 0 1 1-.707-.708L11.46 8.5H3.333a.5.5 0 0 1 0-1h8.127L8.313 4.354a.5.5 0 0 1 0-.708Z"
        fill="currentColor"
      />
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

export function formatCardUpdateLabel(value: string, nowMs = Date.now()): string {
  return formatRelativeTimeLabel(value, nowMs);
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
    createdAt: runtime.createdAt ?? "",
    specificationLabel: "创建人",
    specification: formatResourceSource(runtime.author),
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
    createdAt: session.createdAt,
    specificationLabel: "创建人",
    specification: formatResourceSource(session.createdBy),
    isMine: session.isMine,
    region: session.region,
    sandbox: session,
  };
}

function draftToAgent(item: WorkspaceAgentDraft): MyAgentCardData {
  return {
    id: item.id,
    name: item.draft.name || "未命名 Agent",
    description: item.draft.description?.trim() || "暂无描述",
    createdAt: new Date(item.updatedAt).toISOString(),
    specificationLabel: "存储位置",
    specification: "当前浏览器",
    isMine: true,
    region: item.deploymentTarget?.region,
    draft: item,
  };
}

function runtimeDetailTargetForCard(
  agent: MyAgentCardData,
  runtimeAgents: MyAgentCardData[],
): MyAgentCardData | null {
  if (!agent.draft) return agent;
  const target = agent.draft.deploymentTarget;
  if (!target) return null;
  return runtimeAgents.find((runtimeAgent) =>
    runtimeAgent.runtime?.runtimeId === target.runtimeId &&
    runtimeAgent.runtime.region === target.region,
  ) ?? {
    id: target.runtimeId,
    appName: target.appName,
    name: target.name || agent.name,
    description: agent.description,
    createdAt: agent.createdAt,
    specificationLabel: "地域",
    specification: target.region,
    isMine: true,
    runtime: {
      runtimeId: target.runtimeId,
      region: target.region,
      currentVersion: target.currentVersion,
      canDelete: false,
    },
  };
}

function resolveAgentRegion(
  studioRegion: string,
  cloudProvider: CloudProvider,
): CloudRegion {
  const providerRegions = cloudRegionOptions(cloudProvider);
  if (
    isSupportedCloudRegion(studioRegion) &&
    providerRegions.some((option) => option.value === studioRegion)
  ) {
    return studioRegion;
  }
  return defaultCloudRegion(cloudProvider);
}

async function loadRuntimeAgents(
  runtimeScope: RuntimeScope,
  region: CloudRegion,
  nextToken: string,
  onList: (agents: MyAgentCardData[]) => void,
  signal?: AbortSignal,
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
    request = getRuntimesWithTimeoutRetry({
      scope: runtimeScope,
      region,
      pageSize: RUNTIME_PAGE_SIZE,
      nextToken,
      signal,
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
  onPrepareUpdate,
  compatibility,
  onRetryCompatibility,
  connecting,
  connected,
  deploymentTask,
  nowMs,
  onViewDeploymentTask,
  onEditDraft,
  onDeleteDraft,
}: {
  agent: MyAgentCardData;
  onUse?: (agent: MyAgentCardData) => Promise<void>;
  onViewDetails?: (agent: MyAgentCardData) => void;
  onPrepareUpdate?: (agent: MyAgentCardData) => void;
  compatibility?: RuntimeCompatibility;
  onRetryCompatibility?: (agent: MyAgentCardData) => void;
  connecting?: boolean;
  connected?: boolean;
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
  const checkingCompatibility = compatibility?.status === "checking";
  const incompatible = compatibility?.status === "unsupported";
  const compatibilityFailed = compatibility?.status === "error";
  const sandboxResourceId = agent.sandbox?.resourceType === "snapshot"
    ? agent.sandbox.sourceSessionId || agent.sandbox.snapshotId
    : agent.sandbox?.id;
  const openCard = () => {
    if (agent.draft) {
      if (deploymentTask) onViewDeploymentTask?.(deploymentTask);
      else onViewDetails?.(agent);
      return;
    }
    if (!actionable) return;
    if (deploymentTask) onViewDeploymentTask?.(deploymentTask);
    else onViewDetails?.(agent);
  };
  const cardTargetEnabled = agent.draft
    ? Boolean(deploymentTask ? onViewDeploymentTask : onViewDetails)
    : actionable && Boolean(deploymentTask ? onViewDeploymentTask : onViewDetails);
  const cardTargetLabel = agent.draft
    ? deploymentTask
      ? `查看 ${agent.name} 部署进度`
      : `查看 ${agent.name} Runtime 详情`
    : deploymentTask
      ? `查看 ${agent.name} 部署进度`
      : `查看 ${agent.name} 详情`;
  return (
    <ResourceCard
      className={connecting ? "my-agent-card is-connecting" : "my-agent-card"}
      activateLabel={cardTargetEnabled ? cardTargetLabel : undefined}
      onActivate={cardTargetEnabled ? openCard : undefined}
      onPointerEnter={() => onPrepareUpdate?.(agent)}
      onFocusCapture={() => onPrepareUpdate?.(agent)}
      footer={(
        <ResourceCardMetadata
          className="my-agent-meta"
          items={[
            {
              label: agent.specificationLabel,
              value: agent.specification,
              hideLabel: true,
              className: "my-agent-region",
            },
            {
              label: "时间",
              value: formatCardUpdateLabel(agent.createdAt, nowMs),
              hideLabel: true,
              className: "my-agent-created-at",
            },
            ...(agent.sandbox ? [{
              label: "剩余时间",
              value: agent.sandbox.resourceType === "snapshot"
                ? "可唤醒"
                : agent.sandbox.persistent
                  ? "永不过期"
                  : formatSandboxRemainingTime(agent.sandbox.expireAt, nowMs),
              className: `my-agent-expiry${
                agent.sandbox.resourceType === "session" && agent.sandbox.persistent
                  ? ""
                  : " is-expiring"
              }`,
            }] : []),
          ]}
        />
      )}
      actions={agent.draft ? (
        <>
          <ResourceCardAction
            aria-label={deploymentTask
              ? `查看 ${agent.name} 部署进度`
              : `编辑草稿 ${agent.name}`}
            onClick={() => deploymentTask
              ? onViewDeploymentTask?.(deploymentTask)
              : onEditDraft?.(agent.draft!)}
          >
            {deploymentTask ? "查看进度" : "编辑"}
          </ResourceCardAction>
          <ResourceCardAction
            tone="danger"
            aria-label={`删除草稿 ${agent.name}`}
            onClick={() => onDeleteDraft?.(agent.draft!)}
          >
            删除
          </ResourceCardAction>
        </>
      ) : compatibilityFailed || incompatible ? (
        <ResourceCardAction
          className="my-agent-compatibility-retry"
          aria-label={`重新检测 ${agent.name} 的对话兼容性`}
          onClick={() => onRetryCompatibility?.(agent)}
        >
          重试
        </ResourceCardAction>
      ) : (
        <ResourceCardRevealAction
          className={connected ? "my-agent-use is-connected" : "my-agent-use"}
          disabled={!actionable || checkingCompatibility || incompatible || connecting || connected}
          aria-busy={connecting || undefined}
          label={connected
            ? `${agent.name} 已连接`
            : wakeable
              ? `唤醒 ${agent.name} 并开始对话`
              : `与 ${agent.name} 对话`}
          onClick={() => void onUse?.(agent)}
        >
          {connecting ? (
            <>
              <span className="my-agent-use-spinner" aria-hidden="true" />
              <span className="sr-only">{wakeable ? "唤醒中" : "连接中"}</span>
            </>
          ) : (
            <AgentUseIcon />
          )}
        </ResourceCardRevealAction>
      )}
    >
      <ResourceCardHeader
        leading={(
          <ResourceIdentityMark seed={agent.name} />
        )}
        title={agent.name}
        subtitle={agent.sandbox ? (
          <span className="my-agent-session-id" title={sandboxResourceId}>
            {sandboxResourceId}
          </span>
        ) : undefined}
        status={agent.draft ? (
          deploymentTask ? (
            <span className="my-agent-deploying-badge">部署中</span>
          ) : (
            <span className="my-agent-draft-badge">草稿</span>
          )
          ) : agent.sandbox ? (
            <span
              className="my-agent-status-label"
              data-ready={agent.sandbox.status.toLowerCase() === "ready" || undefined}
              data-wakeable={wakeable || undefined}
            >
              {agent.description}
            </span>
          ) : agent.runtime && deploymentTask ? (
            <span className="my-agent-deploying-badge">部署中</span>
          ) : checkingCompatibility ? (
            <Tooltip
              content={compatibility?.message}
              contentClassName="my-agent-compatibility-tooltip"
              maxWidth={360}
              align="end"
              interactive
              preventUnintentionalClickToClose
            >
              <span className="my-agent-compatibility-trigger" tabIndex={0}>
                <Badge
                  className="my-agent-compatibility-status"
                  color="secondary"
                  variant="soft"
                  size="sm"
                  pill
                >
                  <span className="my-agent-compatibility-spinner" aria-hidden="true" />
                  <span>检测中</span>
                </Badge>
              </span>
            </Tooltip>
          ) : incompatible ? (
            <Tooltip
              content={compatibility?.message}
              contentClassName="my-agent-compatibility-tooltip"
              maxWidth={360}
              align="end"
              interactive
              preventUnintentionalClickToClose
            >
              <span className="my-agent-compatibility-trigger" tabIndex={0}>
                <Badge
                  className="my-agent-compatibility-status"
                  color="warning"
                  variant="soft"
                  size="sm"
                  pill
                >
                  不支持对话
                </Badge>
              </span>
            </Tooltip>
          ) : compatibilityFailed ? (
            <Tooltip
              content={compatibility?.message}
              contentClassName="my-agent-compatibility-tooltip"
              maxWidth={360}
              align="end"
              interactive
              preventUnintentionalClickToClose
            >
              <span className="my-agent-compatibility-trigger" tabIndex={0}>
                <Badge
                  className="my-agent-compatibility-status"
                  color="danger"
                  variant="soft"
                  size="sm"
                  pill
                >
                  检测失败
                </Badge>
              </span>
            </Tooltip>
          ) : null}
      />
      {!agent.sandbox ? (
        <ResourceCardDescription>{agent.description}</ResourceCardDescription>
      ) : null}
    </ResourceCard>
  );
}

export interface MyAgentsProps {
  cloudProvider: CloudProvider;
  studioRegion: string;
  canCreate: boolean;
  canUpdate: boolean;
  runtimeScope: RuntimeScope;
  onCreateAgent: (region: string) => void;
  onOpenCodexProjectUpload?: () => void;
  onUseAgent: (agent: MyAgentCardData) => Promise<void>;
  onViewAgentDetails: (agent: MyAgentCardData) => void;
  onCreateSandboxAgent: (kind: "codex" | SandboxAgentKind) => void;
  onUseSandboxAgent: (session: SandboxAgentResource) => Promise<void>;
  onViewSandboxAgentDetails: (session: SandboxAgentResource) => void;
  activeType: AgentType;
  onActiveTypeChange: (type: AgentType) => void;
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
  studioRegion,
  canCreate,
  canUpdate,
  runtimeScope,
  onCreateAgent,
  onOpenCodexProjectUpload,
  onUseAgent,
  onViewAgentDetails,
  onCreateSandboxAgent,
  onUseSandboxAgent,
  onViewSandboxAgentDetails,
  activeType,
  onActiveTypeChange,
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
  const runtimeListAbortRef = useRef<AbortController | null>(null);
  const sandboxRequestRef = useRef(0);
  const sandboxAbortRef = useRef<AbortController | null>(null);
  const runtimeCompatibilityAbortRef = useRef<Map<string, AbortController>>(new Map());
  const configuredRegion = resolveAgentRegion(studioRegion, cloudProvider);
  const [query, setQuery] = useState("");
  const [ownership, setOwnership] = useState<RuntimeScope>(
    runtimeScope === "mine" ? "mine" : "all",
  );
  const [region, setRegion] = useState<CloudRegion>(configuredRegion);
  const [runtimeAgents, setRuntimeAgents] = useState<MyAgentCardData[]>([]);
  const [runtimeNextToken, setRuntimeNextToken] = useState("");
  const [loadingRuntimes, setLoadingRuntimes] = useState(true);
  const [runtimeError, setRuntimeError] = useState("");
  const [sandboxAgents, setSandboxAgents] = useState<MyAgentCardData[]>([]);
  const [loadingSandboxAgents, setLoadingSandboxAgents] = useState(false);
  const [sandboxError, setSandboxError] = useState("");
  const [connectingAgentId, setConnectingAgentId] = useState("");
  const [runtimeCompatibility, setRuntimeCompatibility] = useState<
    Record<string, RuntimeCompatibility>
  >({});
  const [draftToDelete, setDraftToDelete] = useState<WorkspaceAgentDraft | null>(null);
  const [remainingTimeNow, setRemainingTimeNow] = useState(() => Date.now());
  const regionFilterOptions = useMemo<Array<ResourceFilterOption<CloudRegion>>>(
    () => cloudRegionOptions(cloudProvider),
    [cloudProvider],
  );

  useEffect(() => {
    if (runtimeScope === "mine") setOwnership("mine");
  }, [runtimeScope]);

  useEffect(() => {
    setRegion(configuredRegion);
  }, [configuredRegion]);

  useEffect(() => {
    setRemainingTimeNow(Date.now());
    const timer = window.setInterval(() => setRemainingTimeNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

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
    runtimeListAbortRef.current?.abort();
    runtimePageRequests.clear();
    const controller = new AbortController();
    runtimeListAbortRef.current = controller;
    const requestId = ++runtimeRequestRef.current;
    setLoadingRuntimes(true);
    setRuntimeError("");
    return loadRuntimeAgents(ownership, region, token, (agents) => {
      if (runtimeRequestRef.current !== requestId) return;
      setRuntimeAgents((current) => reset ? agents : [...current, ...agents]);
    }, controller.signal)
      .then((nextToken) => {
        if (runtimeRequestRef.current === requestId) setRuntimeNextToken(nextToken);
      })
      .catch((cause) => {
        if (runtimeRequestRef.current !== requestId) return;
        if (isAbortError(cause)) return;
        setRuntimeError(formatRequestError(cause, "加载通用智能体", "GET /web/runtimes"));
      })
      .finally(() => {
        if (runtimeRequestRef.current === requestId) setLoadingRuntimes(false);
        if (runtimeListAbortRef.current === controller) {
          runtimeListAbortRef.current = null;
        }
      });
  }, [ownership, region]);

  useEffect(() => {
    if (activeType !== "general") return;
    setRuntimeAgents([]);
    setRuntimeNextToken("");
    void fetchRuntimePage("", true);
    return () => {
      runtimeListAbortRef.current?.abort();
      runtimeListAbortRef.current = null;
      runtimePageRequests.clear();
      runtimeRequestRef.current += 1;
    };
  }, [activeType, fetchRuntimePage]);

  useEffect(() => {
    if (activeType !== "general") {
      for (const controller of runtimeCompatibilityAbortRef.current.values()) {
        controller.abort();
      }
      runtimeCompatibilityAbortRef.current.clear();
      return;
    }

    const liveKeys = new Set(runtimeAgents
      .filter((agent) =>
        agent.runtime?.runtimeId !== connectedRuntimeId &&
        agent.runtime?.region === region,
      )
      .map(runtimeCompatibilityKey)
      .filter(Boolean));
    for (const [key, controller] of runtimeCompatibilityAbortRef.current) {
      if (!liveKeys.has(key)) {
        controller.abort();
        runtimeCompatibilityAbortRef.current.delete(key);
      }
    }
    const pendingAgents = runtimeAgents.filter((agent) => {
      const runtimeId = agent.runtime?.runtimeId;
      if (
        !runtimeId ||
        runtimeId === connectedRuntimeId ||
        agent.runtime?.region !== region
      ) return false;
      const key = runtimeCompatibilityKey(agent);
      const status = runtimeCompatibility[key]?.status;
      return !runtimeCompatibilityAbortRef.current.has(key) &&
        (!status || status === "checking");
    });

    for (const agent of pendingAgents) {
      runtimeCompatibilityAbortRef.current.set(
        runtimeCompatibilityKey(agent),
        new AbortController(),
      );
    }

    setRuntimeCompatibility((current) => {
      let changed = false;
      const next = { ...current };
      for (const agent of runtimeAgents) {
        const key = runtimeCompatibilityKey(agent);
        if (!key) continue;
        const connected = agent.runtime?.runtimeId === connectedRuntimeId;
        if (connected && next[key]?.status !== "compatible") {
          next[key] = { status: "compatible", message: "Runtime 支持 Studio 对话。" };
          changed = true;
        } else if (!connected && !next[key]) {
          next[key] = {
            status: "checking",
            message: RUNTIME_COMPATIBILITY_CHECKING_MESSAGE,
          };
          changed = true;
        }
      }
      return changed ? next : current;
    });

    void runRuntimeCompatibilityChecks(pendingAgents, async (agent) => {
      const runtime = agent.runtime;
      if (!runtime) return;
      const key = runtimeCompatibilityKey(agent);
      const controller = runtimeCompatibilityAbortRef.current.get(key);
      if (!controller) return;
      try {
        const apps = await probeRuntimeApps(runtime.runtimeId, runtime.region, {
          signal: controller.signal,
          preferCached: true,
          timeoutMs: RUNTIME_COMPATIBILITY_TIMEOUT_MS,
          currentVersion: runtime.currentVersion,
        });
        if (controller.signal.aborted) return;
        setRuntimeCompatibility((current) => ({
          ...current,
          [key]: apps && apps.length > 0
            ? { status: "compatible", message: "Runtime 支持 Studio 对话。" }
            : { status: "unsupported", message: RUNTIME_COMPATIBILITY_EMPTY_MESSAGE },
        }));
      } catch (error) {
        if (controller.signal.aborted || (error as Error)?.name === "AbortError") return;
        setRuntimeCompatibility((current) => ({
          ...current,
          [key]: runtimeCompatibilityFailure(error),
        }));
      } finally {
        if (runtimeCompatibilityAbortRef.current.get(key) === controller) {
          runtimeCompatibilityAbortRef.current.delete(key);
        }
      }
    });
  }, [activeType, connectedRuntimeId, region, runtimeAgents]);

  useEffect(() => () => {
    runtimeListAbortRef.current?.abort();
    for (const controller of runtimeCompatibilityAbortRef.current.values()) {
      controller.abort();
    }
    runtimeCompatibilityAbortRef.current.clear();
  }, []);

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
        ? await sandboxClient.listSessions({
            signal: controller.signal,
            autoResumeSnapshots: true,
          })
        : await sandboxClient.listAgentSessions(type, {
            signal: controller.signal,
            autoResumeSnapshots: true,
          });
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
    onActiveTypeChange(type);
  }

  function resetRuntimePagination() {
    if (activeType !== "general") return;
    runtimeRequestRef.current += 1;
    setRuntimeAgents([]);
    setRuntimeNextToken("");
    setRuntimeError("");
    setLoadingRuntimes(true);
  }

  function selectOwnership(nextOwnership: RuntimeScope) {
    if (nextOwnership === ownership) return;
    resetRuntimePagination();
    setOwnership(nextOwnership);
  }

  function selectRegion(nextRegion: CloudRegion) {
    if (nextRegion === region) return;
    resetRuntimePagination();
    setRegion(nextRegion);
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

  const retryRuntimeCompatibility = useCallback(async (agent: MyAgentCardData) => {
    const runtime = agent.runtime;
    if (!runtime) return;
    const key = runtimeCompatibilityKey(agent);
    setRuntimeCompatibility((current) => ({
      ...current,
      [key]: {
        status: "checking",
        message: RUNTIME_COMPATIBILITY_CHECKING_MESSAGE,
      },
    }));
    runtimeCompatibilityAbortRef.current.get(key)?.abort();
    const controller = new AbortController();
    runtimeCompatibilityAbortRef.current.set(key, controller);
    try {
      const apps = await withRuntimeCompatibilitySlot(() =>
        probeRuntimeApps(runtime.runtimeId, runtime.region, {
          retryProbe: true,
          signal: controller.signal,
          timeoutMs: RUNTIME_COMPATIBILITY_RETRY_TIMEOUT_MS,
          currentVersion: runtime.currentVersion,
        }),
      );
      if (controller.signal.aborted) return;
      setRuntimeCompatibility((current) => ({
        ...current,
        [key]: apps && apps.length > 0
          ? { status: "compatible", message: "Runtime 支持 Studio 对话。" }
          : { status: "unsupported", message: RUNTIME_COMPATIBILITY_EMPTY_MESSAGE },
      }));
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) return;
      setRuntimeCompatibility((current) => ({
        ...current,
        [key]: runtimeCompatibilityFailure(error),
      }));
    } finally {
      if (runtimeCompatibilityAbortRef.current.get(key) === controller) {
        runtimeCompatibilityAbortRef.current.delete(key);
      }
    }
  }, []);

  const prepareRuntimeUpdate = useCallback((agent: MyAgentCardData) => {
    const runtime = agent.runtime;
    if (!canUpdate || !runtime || deploymentTaskForAgent(agent)) return;
    void prefetchRuntimeUpdateCapability({
      runtimeId: runtime.runtimeId,
      region: runtime.region,
      appName: agent.appName,
      currentVersion: runtime.currentVersion,
    });
  }, [canUpdate, deploymentTaskForAgent]);

  const visibleAgents = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const source = activeType === "general"
      ? [...draftAgents, ...runtimeAgents]
      : sandboxAgents;
    const matchingOwnership = ownership === "mine"
      ? source.filter((agent) => agent.isMine)
      : source;
    const matchingRegion = matchingOwnership.filter((agent) => {
      const agentRegion = agent.runtime?.region ?? agent.region;
      return !agentRegion || agentRegion === region;
    });
    const matchingAgents = normalizedQuery
      ? matchingRegion.filter((agent) =>
          agent.name.toLocaleLowerCase().includes(normalizedQuery),
        )
      : matchingRegion;
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
    ownership,
    region,
    runtimeAgents,
    sandboxAgents,
  ]);

  useEffect(() => {
    if (!canUpdate || activeType !== "general") return;
    const targets = visibleAgents
      .filter((agent) => Boolean(agent.runtime))
      .filter((agent) => !deploymentTaskForAgent(agent))
      .slice(0, UPDATE_CAPABILITY_PREFETCH_LIMIT);
    if (targets.length === 0) return;

    let cancelled = false;
    let nextIndex = 0;
    const runWorker = async () => {
      while (!cancelled) {
        const target = targets[nextIndex];
        nextIndex += 1;
        if (!target?.runtime) return;
        await prefetchRuntimeUpdateCapability({
          runtimeId: target.runtime.runtimeId,
          region: target.runtime.region,
          appName: target.appName,
          currentVersion: target.runtime.currentVersion,
        });
        if (cancelled) return;
      }
    };
    const timer = window.setTimeout(() => {
      for (let index = 0; index < UPDATE_CAPABILITY_PREFETCH_CONCURRENCY; index += 1) {
        void runWorker();
      }
    }, UPDATE_CAPABILITY_PREFETCH_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeType, canUpdate, deploymentTaskForAgent, visibleAgents]);

  const activeTypeInfo = AGENT_TYPES.find((type) => type.id === activeType);
  const activeLabel = activeTypeInfo?.label ?? "智能体";
  const showInitialLoading = activeType === "general"
    ? loadingRuntimes && runtimeAgents.length === 0 && draftAgents.length === 0
    : loadingSandboxAgents && sandboxAgents.length === 0;
  const showEmpty = !showInitialLoading && visibleAgents.length === 0;
  const createAgent = canCreate
    ? activeType === "general"
      ? () => onCreateAgent(region)
      : () => onCreateSandboxAgent(activeType)
    : undefined;
  const showCodexProjectUpload =
    activeType === "codex" && canCreate && Boolean(onOpenCodexProjectUpload);

  return (
    <ResourcePageShell className="my-agents-page" aria-label="智能体">
      <ResourcePageHeader title="智能体" className="my-agents-header" />

      <ResourceToolbar className="my-agent-toolbar">
        <ResourceTabs
          idPrefix="my-agent-ownership"
          ariaLabel="创建人筛选"
          value={ownership}
          items={[
            { id: "all", label: "全部", disabled: runtimeScope === "mine" },
            { id: "mine", label: "我创建的" },
          ]}
          onChange={selectOwnership}
        />
        <div className="resource-toolbar__actions">
          <ResourceFilterSelect
            id="my-agent-type-filter"
            ariaLabel="智能体类型"
            value={activeType}
            options={AGENT_TYPE_OPTIONS}
            onChange={selectAgentType}
          />
          <ResourceFilterSelect
            id="my-agent-region-filter"
            ariaLabel="区域"
            value={region}
            options={regionFilterOptions}
            onChange={selectRegion}
          />
          <ResourceSearch
            className="my-agent-search"
            aria-label="搜索智能体"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索"
          />
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
        </div>
      </ResourceToolbar>

      <ResourceResults
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
        ) : showEmpty && !createAgent ? (
          query.trim() || ownership === "mine" || region !== configuredRegion ? (
            <div className="my-agent-empty-message">
              <EmptyMessage fill="none">
                <EmptyMessage.Icon>
                  <Explore />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>没有匹配的智能体</EmptyMessage.Title>
                <EmptyMessage.Description>请尝试调整搜索或筛选条件</EmptyMessage.Description>
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
            <ResourceGrid className="my-agent-grid">
              {createAgent ? (
                <ResourceCreateCard
                  className="my-agent-create-card"
                  aria-label={`创建${activeLabel}`}
                  onClick={createAgent}
                  icon={<AddIcon />}
                >
                  创建智能体
                </ResourceCreateCard>
              ) : null}
              {visibleAgents.map((agent) => {
                const detailTarget = runtimeDetailTargetForCard(agent, runtimeAgents);
                return (
                  <AgentCard
                    key={agent.id}
                    agent={agent}
                    deploymentTask={deploymentTaskForAgent(agent)}
                    nowMs={remainingTimeNow}
                    onViewDeploymentTask={onViewDeploymentTask}
                    onUse={useAgent}
                    compatibility={agent.runtime
                      ? runtimeCompatibility[runtimeCompatibilityKey(agent)] ?? {
                          status: "checking",
                          message: RUNTIME_COMPATIBILITY_CHECKING_MESSAGE,
                        }
                      : undefined}
                    onRetryCompatibility={retryRuntimeCompatibility}
                    onPrepareUpdate={prepareRuntimeUpdate}
                    onViewDetails={detailTarget ? () => {
                      if (detailTarget.sandbox) {
                        onViewSandboxAgentDetails(detailTarget.sandbox);
                      } else {
                        onViewAgentDetails(detailTarget);
                      }
                    } : undefined}
                    connecting={agent.id === connectingAgentId}
                    connected={agent.runtime?.runtimeId === connectedRuntimeId}
                    onEditDraft={onEditDraft}
                    onDeleteDraft={setDraftToDelete}
                  />
                );
              })}
            </ResourceGrid>
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
      </ResourceResults>
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
    </ResourcePageShell>
  );
}
