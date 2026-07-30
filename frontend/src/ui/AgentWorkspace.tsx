import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  ArrowRight,
  Check,
  CircleAlert,
  CircleCheck,
  CircleX,
  Copy,
  FlaskConical,
  Loader2,
  MessageCircle,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import {
  deleteAgentFeedbackCases,
  getAgentFeedbackCases,
  getRuntimeAgentInfo,
  getRuntimeDetail,
  type AgentFeedbackCase,
  type AgentFeedbackSetSummary,
  type AgentInfo,
  type AgentNode,
  type RuntimeDetail,
} from "../adk/client";
import type { AgentEntry } from "../adk/connections";
import { AgentBuildCanvas } from "../create/AgentBuildCanvas";
import { emptyDraft, type AgentDraft } from "../create/types";
import { BUILTIN_TOOLS } from "../create/veadkCatalog";
import type { DeploymentTaskUpdate } from "./ProjectPreview";
import "./AgentWorkspace.css";

type WorkspaceView = "library" | "evaluation";
type AgentSection = "basic" | "evaluations";
type EvaluationSection = "config" | "history";
type CaseKind = "good" | "bad";

type AgentCase = AgentFeedbackCase & { tag?: string };

interface EvaluationRun {
  id: string;
  createdAt: string;
  score: number;
  status: "completed";
}

interface EvaluationGroup {
  id: string;
  name: string;
  agentIds: string[];
  caseSet: string;
  evaluator: string;
  metrics: string[];
  concurrency: string;
  history: EvaluationRun[];
}

export interface WorkspaceAgentDraft {
  id: string;
  draft: AgentDraft;
  updatedAt: number;
  deploymentTarget?: {
    runtimeId: string;
    name: string;
    region: string;
    currentVersion?: number | null;
  };
}

const DEFAULT_CASES: AgentCase[] = [
  {
    id: "case-1",
    itemKey: "case-1",
    kind: "good",
    input: "总结本周客户反馈，并按优先级归类。",
    output: "覆盖主要问题，给出清晰的优先级与下一步动作。",
    referenceOutput: "覆盖主要问题，给出清晰的优先级与下一步动作。",
    comment: "",
    agentName: "示例 Agent",
    sessionId: "",
    messageId: "",
    runtimeId: "",
    invocationId: "",
    userId: "",
    createdAt: "",
    evaluationSetId: "",
    evaluationSetName: "示例 good case",
    workspaceId: "",
    tag: "总结",
  },
  {
    id: "case-2",
    itemKey: "case-2",
    kind: "good",
    input: "查询最新公开资料并附上来源。",
    output: "调用搜索工具，结论与引用一一对应。",
    referenceOutput: "调用搜索工具，结论与引用一一对应。",
    comment: "",
    agentName: "示例 Agent",
    sessionId: "",
    messageId: "",
    runtimeId: "",
    invocationId: "",
    userId: "",
    createdAt: "",
    evaluationSetId: "",
    evaluationSetName: "示例 good case",
    workspaceId: "",
    tag: "工具调用",
  },
  {
    id: "case-3",
    itemKey: "case-3",
    kind: "bad",
    input: "在信息不足时直接给出确定结论。",
    output: "应明确说明未知，并主动询问缺失信息。",
    referenceOutput: "",
    comment: "",
    agentName: "示例 Agent",
    sessionId: "",
    messageId: "",
    runtimeId: "",
    invocationId: "",
    userId: "",
    createdAt: "",
    evaluationSetId: "",
    evaluationSetName: "示例 bad case",
    workspaceId: "",
    tag: "幻觉",
  },
  {
    id: "case-4",
    itemKey: "case-4",
    kind: "bad",
    input: "连续重复调用相同工具获取同一结果。",
    output: "复用已有结果，避免无意义的重复调用。",
    referenceOutput: "",
    comment: "",
    agentName: "示例 Agent",
    sessionId: "",
    messageId: "",
    runtimeId: "",
    invocationId: "",
    userId: "",
    createdAt: "",
    evaluationSetId: "",
    evaluationSetName: "示例 bad case",
    workspaceId: "",
    tag: "效率",
  },
];

const DEFAULT_EVALUATION_GROUPS: EvaluationGroup[] = [
  {
    id: "eval-regression",
    name: "核心能力回归",
    agentIds: [],
    caseSet: "核心回归集",
    evaluator: "综合质量评估器",
    metrics: ["回答质量", "工具调用"],
    concurrency: "4",
    history: [
      { id: "run-1", createdAt: "今天 10:32", score: 88, status: "completed" },
      { id: "run-2", createdAt: "昨天 16:08", score: 84, status: "completed" },
    ],
  },
  {
    id: "eval-safety",
    name: "安全与幻觉检查",
    agentIds: [],
    caseSet: "安全边界集",
    evaluator: "事实一致性评估器",
    metrics: ["事实准确性", "拒答合理性"],
    concurrency: "2",
    history: [
      { id: "run-3", createdAt: "7 月 25 日 14:20", score: 91, status: "completed" },
    ],
  },
];

const AGENT_SECTIONS: Array<{ id: AgentSection; label: string }> = [
  { id: "basic", label: "基本信息" },
  { id: "evaluations", label: "评测集" },
];

function graphNodeToDraft(node: AgentNode): AgentDraft {
  const runtimeTools = node.tools ?? [];
  const builtinTools = BUILTIN_TOOLS.filter((tool) =>
    tool.toolNames.some((name) => runtimeTools.includes(name)),
  );
  const builtinToolNames = new Set(builtinTools.flatMap((tool) => tool.toolNames));
  return {
    ...emptyDraft(),
    name: node.name,
    description: node.description,
    instruction: node.instruction || emptyDraft().instruction,
    agentType: node.type,
    modelName: node.model,
    tools: runtimeTools.filter((name) => !builtinToolNames.has(name)),
    builtinTools: builtinTools.map((tool) => tool.id),
    skills: (node.skills ?? []).map((skill) => skill.name),
    subAgents: (node.children ?? []).map(graphNodeToDraft),
  };
}

function infoToDraft(info: AgentInfo | null, fallbackName: string): AgentDraft {
  if (info?.draft) return info.draft;
  if (info?.graph) return graphNodeToDraft(info.graph);
  return {
    ...emptyDraft(),
    name: info?.name || fallbackName,
    description: info?.description || "暂无描述",
    agentType: info?.type ?? "llm",
    modelName: info?.model,
    tools: info?.tools ?? [],
    skills: info?.skills?.map((skill) => skill.name) ?? [],
  };
}

function countNodes(node?: AgentNode): number {
  if (!node) return 1;
  return 1 + node.children.reduce((total, child) => total + countNodes(child), 0);
}

function countDraftNodes(draft: AgentDraft): number {
  return 1 + draft.subAgents.reduce(
    (total, child) => total + countDraftNodes(child),
    0,
  );
}

function caseTimeValue(value: string): number {
  if (!value) return 0;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return numeric < 1_000_000_000_000 ? numeric * 1000 : numeric;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatCaseTime(value: string): string {
  const time = caseTimeValue(value);
  if (!time) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(time));
}

function feedbackSetFor(
  sets: AgentFeedbackSetSummary[],
  kind: CaseKind,
): AgentFeedbackSetSummary | undefined {
  return sets.find((set) => set.kind === kind);
}

function canvasDraftKey(draft: AgentDraft): string {
  const visit = (node: AgentDraft): unknown => [
    node.name,
    node.description,
    node.agentType ?? "llm",
    node.modelName ?? "",
    node.tools ?? [],
    node.builtinTools ?? [],
    (node.customTools ?? []).map((tool) => tool.name),
    (node.mcpTools ?? []).map((tool) => tool.name),
    node.skills ?? [],
    (node.selectedSkills ?? []).map((skill) => skill.name),
    (node.subAgents ?? []).map(visit),
  ];
  return JSON.stringify(visit(draft));
}

const DEPLOYMENT_STEPS = [
  { phase: "prepare", label: "准备部署", description: "校验配置并创建部署任务" },
  { phase: "build", label: "构建镜像", description: "生成运行环境与智能体代码" },
  { phase: "deploy", label: "部署服务", description: "创建并启动 AgentKit Runtime" },
  { phase: "publish", label: "发布服务", description: "等待服务就绪并生成访问地址" },
  { phase: "complete", label: "部署完成", description: "智能体已可以正常使用" },
] as const;
const BUILD_STEP_INDEX = DEPLOYMENT_STEPS.findIndex((step) => step.phase === "build");

function deploymentStepIndex(task: DeploymentTaskUpdate): number {
  if (task.status === "success") return DEPLOYMENT_STEPS.length - 1;
  const phase = task.phase ?? ({
    准备部署: "prepare",
    构建镜像: "build",
    部署: "deploy",
    发布: "publish",
    部署完成: "complete",
  } as Record<string, string>)[task.label];
  const index = DEPLOYMENT_STEPS.findIndex((step) => step.phase === phase);
  return index < 0 ? 0 : index;
}

function formatBuildLogTime(updatedAt: number): string {
  if (!updatedAt) return "";
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(updatedAt));
  } catch {
    return "";
  }
}

function DeploymentBuildLog({ task }: { task: DeploymentTaskUpdate }) {
  const log = task.buildLog;
  const logTextRef = useRef<HTMLPreElement | null>(null);
  const shouldAutoExpand = Boolean(
    log?.status !== "complete"
    && (task.status === "running" || task.status === "error")
    && deploymentStepIndex(task) === BUILD_STEP_INDEX,
  );
  const [expanded, setExpanded] = useState(shouldAutoExpand);
  const [copied, setCopied] = useState(false);
  const hasLogText = Boolean(log?.text || log?.error);
  const text = log?.text || log?.error || "";
  const lines = text.split("\n");
  const visibleText = expanded ? text : lines.slice(-36).join("\n");
  const pendingMessage = log?.pendingMessage || "正在等待构建日志…";

  useEffect(() => {
    if (!log) return;
    setExpanded(shouldAutoExpand);
  }, [task.id, log?.status, shouldAutoExpand]);

  useEffect(() => {
    if (!expanded || !hasLogText) return;
    const node = logTextRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [expanded, hasLogText, visibleText]);

  if (!log || (!log.text && log.status !== "error" && !log.pendingMessage)) return null;

  const updatedAt = formatBuildLogTime(log.updatedAt);
  const statusLabel = log.status === "complete"
    ? "已同步"
    : log.status === "error"
      ? "读取失败"
      : "同步中";
  const truncationLabel = log.omittedEarly
    ? "已省略早期日志"
    : log.snapshotTruncated
      ? "仅显示最近的构建日志"
      : log.truncated
        ? "已省略部分日志"
        : "";
  const meta = [
    statusLabel,
    log.lineCount ? `${log.lineCount} 行` : "",
    truncationLabel,
    updatedAt,
  ].filter(Boolean).join(" · ");

  async function copyLog() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section
      className={`aw-deploy-log is-${log.status}${expanded ? "" : " is-collapsed"}`}
      aria-label="构建日志"
    >
      <header>
        <div>
          <strong>构建日志</strong>
          <span>{meta}</span>
        </div>
        <div className="aw-deploy-log-actions">
          {hasLogText && (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "收起" : "展开"}
            </button>
          )}
          {hasLogText && (
            <button
              type="button"
              onClick={() => void copyLog()}
              aria-label={copied ? "已复制构建日志" : "复制构建日志"}
              title={copied ? "已复制" : "复制构建日志"}
            >
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              <span>{copied ? "已复制" : "复制"}</span>
            </button>
          )}
        </div>
      </header>
      {expanded && (
        hasLogText
          ? <pre ref={logTextRef}>{visibleText}</pre>
          : <div className="aw-deploy-log-empty">{pendingMessage}</div>
      )}
    </section>
  );
}

function DeploymentProgressCard({ task }: { task: DeploymentTaskUpdate }) {
  const currentIndex = deploymentStepIndex(task);
  const progress = task.status === "success"
    ? 100
    : Math.max(6, Math.min(100, task.pct ?? 6));
  const title = task.status === "running"
    ? "正在部署"
    : task.status === "success"
      ? "部署完成"
      : task.status === "error"
        ? "部署失败"
        : "部署已取消";

  return (
    <section
      className={`aw-deploy-progress-card is-${task.status}`}
      aria-live="polite"
    >
      <div className="aw-deploy-progress-head">
        <div>
          <span className="aw-deploy-progress-icon" aria-hidden>
            {task.status === "running" ? (
              <Loader2 className="spin" />
            ) : task.status === "success" ? (
              <CircleCheck />
            ) : task.status === "error" ? (
              <CircleAlert />
            ) : (
              <CircleX />
            )}
          </span>
          <div>
            <h3>{title}</h3>
            <p>{task.runtimeName}</p>
          </div>
        </div>
        <strong>{task.status === "running" ? `${Math.round(progress)}%` : task.label}</strong>
      </div>

      <div
        className="aw-deploy-progress-track"
        role="progressbar"
        aria-label="部署进度"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress)}
      >
        <span style={{ width: `${progress}%` }} />
      </div>

      <ol className="aw-deploy-steps">
        {DEPLOYMENT_STEPS.map((step, index) => {
          const status = task.status === "success" || index < currentIndex
            ? "done"
            : index === currentIndex
              ? task.status === "running" ? "active" : "failed"
              : "pending";
          const message = index === currentIndex ? task.message : undefined;
          return (
            <li key={step.phase} className={`is-${status}`}>
              <span className="aw-deploy-step-marker" aria-hidden>
                {status === "done" ? (
                  <Check />
                ) : status === "active" ? (
                  <Loader2 className="spin" />
                ) : status === "failed" ? (
                  <CircleX />
                ) : (
                  index + 1
                )}
              </span>
              <div className="aw-deploy-step-copy">
                <strong>{step.label}</strong>
                <p>{message || step.description}</p>
                {step.phase === "build" && task.buildLog && (
                  <div className="aw-deploy-step-log">
                    <DeploymentBuildLog task={task} />
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export interface AgentWorkspaceProps {
  agents: AgentEntry[];
  drafts?: WorkspaceAgentDraft[];
  agentOrder?: string[];
  selectedAgentId: string;
  agentInfo: AgentInfo | null;
  agentInfoAgentId: string;
  loadingAgentInfo: boolean;
  canCreate: boolean;
  canUpdate: boolean;
  loadingAgents?: boolean;
  agentsError?: string;
  deploymentTasks?: DeploymentTaskUpdate[];
  focusedDeploymentTaskId?: string;
  focusedAgentId?: string;
  focusedAgentSection?: AgentSection;
  focusedCaseKind?: CaseKind;
  detailOnly?: boolean;
  onRetryAgents?: () => void;
  onAgentOrderChange?: (agentIds: string[]) => void;
  onDeleteAgents?: (agents: AgentEntry[]) => Promise<void>;
  onDeleteDrafts?: (drafts: WorkspaceAgentDraft[]) => void;
  onSelectAgent: (id: string) => void;
  onTalkAgent?: (id: string) => void;
  onOpenFeedbackCase?: (item: AgentFeedbackCase) => void | Promise<void>;
  onFeedbackCasesDeleted?: (items: AgentFeedbackCase[]) => void;
  onCreateAgent: () => void;
  onUpdateAgent: (draft: AgentDraft) => void;
  onEditDraft?: (draft: WorkspaceAgentDraft) => void;
}

export function AgentWorkspace({
  agents,
  drafts = [],
  agentOrder = [],
  agentInfo,
  agentInfoAgentId,
  loadingAgentInfo,
  canCreate,
  canUpdate,
  loadingAgents = false,
  agentsError = "",
  deploymentTasks = [],
  focusedDeploymentTaskId = "",
  focusedAgentId = "",
  focusedAgentSection = "basic",
  focusedCaseKind = "good",
  detailOnly = false,
  onRetryAgents,
  onAgentOrderChange,
  onDeleteAgents,
  onDeleteDrafts,
  onSelectAgent,
  onTalkAgent,
  onOpenFeedbackCase,
  onFeedbackCasesDeleted,
  onCreateAgent,
  onUpdateAgent,
  onEditDraft,
}: AgentWorkspaceProps) {
  const [view, setView] = useState<WorkspaceView>("library");
  const [section, setSection] = useState<AgentSection>("basic");
  const [activeAgentId, setActiveAgentId] = useState("");
  const [activeDraftId, setActiveDraftId] = useState("");
  const [runtimeDetail, setRuntimeDetail] = useState<RuntimeDetail | null>(null);
  const [detailAgentInfo, setDetailAgentInfo] = useState<AgentInfo | null>(null);
  const [detailAgentInfoResolved, setDetailAgentInfoResolved] = useState(false);
  const [query, setQuery] = useState("");
  const [caseFilter, setCaseFilter] = useState<CaseKind>("good");
  const [caseQuery, setCaseQuery] = useState("");
  const [draggingAgentId, setDraggingAgentId] = useState("");
  const [dropAgentId, setDropAgentId] = useState("");
  const [dropPlacement, setDropPlacement] = useState<"before" | "after">("before");
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(() => new Set());
  const [selectedDraftIds, setSelectedDraftIds] = useState<Set<string>>(() => new Set());
  const [deletingAgents, setDeletingAgents] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [feedbackCases, setFeedbackCases] = useState<AgentCase[]>([]);
  const [feedbackSets, setFeedbackSets] = useState<AgentFeedbackSetSummary[]>([]);
  const [feedbackCasesLoading, setFeedbackCasesLoading] = useState(false);
  const [feedbackCasesError, setFeedbackCasesError] = useState("");
  const [feedbackReloadToken, setFeedbackReloadToken] = useState(0);
  const [caseSelectionMode, setCaseSelectionMode] = useState(false);
  const [selectedCaseIds, setSelectedCaseIds] = useState<Set<string>>(() => new Set());
  const [deletingCases, setDeletingCases] = useState(false);
  const [caseDeleteError, setCaseDeleteError] = useState("");
  const [focusedCaseId, setFocusedCaseId] = useState("");
  const [expandedCaseIds, setExpandedCaseIds] = useState<Set<string>>(() => new Set());
  const suppressAgentClickRef = useRef(false);
  const appliedFocusKeyRef = useRef("");
  const caseTableRef = useRef<HTMLDivElement | null>(null);
  const [evaluationGroups, setEvaluationGroups] = useState(DEFAULT_EVALUATION_GROUPS);
  const [activeEvaluationGroupId, setActiveEvaluationGroupId] = useState("");

  useEffect(() => {
    if (agents.length === 0) return;
    setEvaluationGroups((current) =>
      current.map((group, index) =>
        index === 0 && group.agentIds.length === 0
          ? { ...group, agentIds: agents.slice(0, 2).map((agent) => agent.id) }
          : group,
      ),
    );
  }, [agents]);

  const agentByRuntimeId = useMemo(() => {
    const next = new Map<string, AgentEntry>();
    for (const agent of agents) {
      if (agent.runtimeId) next.set(agent.runtimeId, agent);
    }
    return next;
  }, [agents]);
  const updateDraftByRuntimeId = useMemo(() => {
    const next = new Map<string, WorkspaceAgentDraft>();
    for (const item of drafts) {
      const runtimeId = item.deploymentTarget?.runtimeId;
      if (!runtimeId || !agentByRuntimeId.has(runtimeId)) continue;
      const previous = next.get(runtimeId);
      if (!previous || item.updatedAt > previous.updatedAt) next.set(runtimeId, item);
    }
    return next;
  }, [agentByRuntimeId, drafts]);
  const latestTaskByRuntimeId = useMemo(() => {
    const next = new Map<string, DeploymentTaskUpdate>();
    for (const task of deploymentTasks) {
      if (!task.runtimeId) continue;
      const previous = next.get(task.runtimeId);
      if (!previous || task.startedAt > previous.startedAt) {
        next.set(task.runtimeId, task);
      }
    }
    return next;
  }, [deploymentTasks]);

  const filteredAgents = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return agents;
    return agents.filter((agent) => {
      const updateDraft = agent.runtimeId
        ? updateDraftByRuntimeId.get(agent.runtimeId)
        : undefined;
      const deploymentTask = agent.runtimeId
        ? latestTaskByRuntimeId.get(agent.runtimeId)
        : undefined;
      return [
        agent.label,
        agent.app,
        agent.host ?? "",
        updateDraft?.draft.name ?? "",
        updateDraft?.draft.description ?? "",
        deploymentTask?.runtimeName ?? "",
      ].join(" ").toLowerCase().includes(keyword);
    });
  }, [agents, latestTaskByRuntimeId, query, updateDraftByRuntimeId]);
  const filteredDrafts = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return drafts.filter((item) => {
      const runtimeId = item.deploymentTarget?.runtimeId;
      if (runtimeId && agentByRuntimeId.has(runtimeId)) return false;
      if (!keyword) return true;
      return `${item.draft.name} ${item.draft.description}`.toLowerCase().includes(keyword);
    });
  }, [agentByRuntimeId, drafts, query]);
  const standaloneDraftCount = useMemo(
    () =>
      drafts.filter((item) => {
        const runtimeId = item.deploymentTarget?.runtimeId;
        return !runtimeId || !agentByRuntimeId.has(runtimeId);
      }).length,
    [agentByRuntimeId, drafts],
  );
  const filteredEvaluationGroups = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return evaluationGroups;
    return evaluationGroups.filter((group) =>
      group.name.toLowerCase().includes(keyword),
    );
  }, [evaluationGroups, query]);

  const selectedAgent = agents.find((agent) => agent.id === activeAgentId);
  const selectedDraft = drafts.find((item) => item.id === activeDraftId);
  const selectedPendingTask = focusedDeploymentTaskId
    ? deploymentTasks.find((task) => task.id === focusedDeploymentTaskId)
    : undefined;
  const selectedAgentUpdateDraft = selectedAgent?.runtimeId
    ? updateDraftByRuntimeId.get(selectedAgent.runtimeId)
    : undefined;
  const selectedAgentInfo = detailOnly
    ? detailAgentInfo
    : activeAgentId && agentInfoAgentId === activeAgentId
      ? agentInfo
      : null;
  const listedAgents = useMemo(() => {
    const originalOrder = new Map(agents.map((agent, index) => [agent.id, index]));
    const savedOrder = new Map(agentOrder.map((id, index) => [id, index]));
    return [...filteredAgents].sort((left, right) => {
      const leftTask = left.runtimeId
        ? latestTaskByRuntimeId.get(left.runtimeId)
        : undefined;
      const rightTask = right.runtimeId
        ? latestTaskByRuntimeId.get(right.runtimeId)
        : undefined;
      const leftStartedAt = leftTask?.status === "running" ? leftTask.startedAt : 0;
      const rightStartedAt = rightTask?.status === "running" ? rightTask.startedAt : 0;
      if (leftStartedAt !== rightStartedAt) return rightStartedAt - leftStartedAt;
      const leftOrder = savedOrder.get(left.id);
      const rightOrder = savedOrder.get(right.id);
      if (leftOrder != null && rightOrder != null) return leftOrder - rightOrder;
      if (leftOrder != null) return -1;
      if (rightOrder != null) return 1;
      return (originalOrder.get(left.id) ?? 0) - (originalOrder.get(right.id) ?? 0);
    });
  }, [agentOrder, agents, filteredAgents, latestTaskByRuntimeId]);
  const selectedName =
    selectedAgent?.label ||
    selectedAgentInfo?.name ||
    selectedDraft?.draft.name ||
    selectedPendingTask?.runtimeName ||
    "未选择智能体";
  const selectedEvaluationGroup = evaluationGroups.find(
    (group) => group.id === activeEvaluationGroupId,
  );
  const deletableListedAgents = listedAgents.filter((agent) => agent.canDelete === true);
  const selectedDeletableAgents = listedAgents.filter(
    (agent) => selectedAgentIds.has(agent.id) && agent.canDelete === true,
  );
  const selectedDeletableDrafts = filteredDrafts.filter((item) =>
    selectedDraftIds.has(item.id),
  );
  const deletableItemCount = deletableListedAgents.length + filteredDrafts.length;
  const selectedDeleteCount =
    selectedDeletableAgents.length + selectedDeletableDrafts.length;
  const draft = useMemo(
    () =>
      selectedPendingTask?.agentDraft ??
      selectedDraft?.draft ??
      selectedAgentUpdateDraft?.draft ??
      infoToDraft(selectedAgentInfo, selectedAgent?.label ?? "agent"),
    [
      selectedAgentInfo,
      selectedAgent?.label,
      selectedAgentUpdateDraft?.draft,
      selectedDraft?.draft,
      selectedPendingTask?.agentDraft,
    ],
  );
  const toolNames = useMemo(() => {
    if (selectedAgentInfo) return selectedAgentInfo.tools;
    const builtinNames = (draft.builtinTools ?? []).map(
      (id) => BUILTIN_TOOLS.find((tool) => tool.id === id)?.label ?? id,
    );
    return Array.from(new Set([
      ...draft.tools,
      ...builtinNames,
      ...(draft.customTools ?? []).map((tool) => tool.name),
      ...(draft.mcpTools ?? []).map((tool) => tool.name),
    ].filter(Boolean)));
  }, [draft, selectedAgentInfo]);
  const skillNames = useMemo(() => {
    if (selectedAgentInfo) {
      return selectedAgentInfo.skillsPreviewSupported
        ? selectedAgentInfo.skills.map((skill) => skill.name)
        : null;
    }
    return Array.from(new Set([
      ...(draft.selectedSkills ?? []).map((skill) => skill.name),
      ...draft.skills,
    ].filter(Boolean)));
  }, [draft, selectedAgentInfo]);
  const deploymentTask = useMemo(() => {
    if (selectedPendingTask) return selectedPendingTask;
    if (selectedDraft) {
      return deploymentTasks
        .filter(
          (task) =>
            task.agentDraft?.name === selectedDraft.draft.name ||
            task.runtimeName === selectedDraft.draft.name ||
            (!!selectedDraft.deploymentTarget?.runtimeId &&
              task.runtimeId === selectedDraft.deploymentTarget.runtimeId),
        )
        .sort((left, right) => right.startedAt - left.startedAt)[0];
    }
    if (!selectedAgent) return undefined;
    return deploymentTasks
      .filter(
        (task) =>
          (!!selectedAgent.runtimeId && task.runtimeId === selectedAgent.runtimeId) ||
          task.runtimeName === selectedAgent.label,
      )
      .sort((left, right) => right.startedAt - left.startedAt)[0];
  }, [deploymentTasks, selectedAgent, selectedDraft, selectedPendingTask]);
  const focusedDeploymentTaskActive = Boolean(
    focusedDeploymentTaskId
    && deploymentTask
    && deploymentTask.id === focusedDeploymentTaskId,
  );
  const shouldShowDeploymentTask = Boolean(
    deploymentTask && (
      deploymentTask.status !== "success"
      || focusedDeploymentTaskActive
    ),
  );
  const draftFlowKey = useMemo(() => canvasDraftKey(draft), [draft]);
  const displayCurrentVersion =
    selectedAgent?.currentVersion ?? runtimeDetail?.currentVersion ?? null;
  const runtimeVersionKey =
    displayCurrentVersion ?? selectedPendingTask?.startedAt ?? "unknown";
  const executionFlowKey = selectedAgentInfo
    ? `runtime:${selectedAgent?.runtimeId ?? selectedAgentInfo.name}:v${runtimeVersionKey}:${draftFlowKey}`
    : `draft:${selectedPendingTask?.id ?? selectedDraft?.id ?? selectedAgent?.id ?? selectedName}:${draftFlowKey}`;
  const loadingExecutionFlow = Boolean(
    detailOnly && selectedAgent?.runtimeId && !detailAgentInfoResolved,
  );
  useEffect(() => {
    if (!focusedDeploymentTaskId) return;
    const focusedTask = deploymentTasks.find(
      (task) => task.id === focusedDeploymentTaskId,
    );
    const matchingAgent = focusedTask?.runtimeId
      ? agentByRuntimeId.get(focusedTask.runtimeId)
      : undefined;
    if (matchingAgent) {
      setActiveDraftId("");
      setActiveAgentId(matchingAgent.id);
      setSection("basic");
      return;
    }
    setActiveAgentId("");
    setActiveDraftId("");
    setSection("basic");
  }, [agentByRuntimeId, deploymentTasks, focusedDeploymentTaskId]);

  useEffect(() => {
    if (!focusedAgentId) {
      appliedFocusKeyRef.current = "";
      return;
    }
    const focusKey = `${focusedAgentId}:${focusedAgentSection}:${focusedCaseKind}`;
    if (appliedFocusKeyRef.current === focusKey) return;
    if (!agents.some((agent) => agent.id === focusedAgentId)) return;
    appliedFocusKeyRef.current = focusKey;
    setActiveDraftId("");
    setActiveAgentId(focusedAgentId);
    setSection(focusedAgentSection);
    if (focusedAgentSection === "evaluations") {
      setCaseFilter(focusedCaseKind);
      setCaseQuery("");
    }
  }, [agents, focusedAgentId, focusedAgentSection, focusedCaseKind]);

  useEffect(() => {
    let cancelled = false;
    setDetailAgentInfo(null);
    setDetailAgentInfoResolved(
      !detailOnly || !selectedAgent?.runtimeId || !selectedAgent.region,
    );
    if (!detailOnly || !selectedAgent?.runtimeId || !selectedAgent.region) return;
    void getRuntimeAgentInfo(
      selectedAgent.runtimeId,
      selectedAgent.region,
      selectedAgent.runtimeApp,
    )
      .then((info) => {
        if (!cancelled) setDetailAgentInfo(info);
      })
      .catch(() => {
        if (!cancelled) setDetailAgentInfo(null);
      })
      .finally(() => {
        if (!cancelled) setDetailAgentInfoResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [
    detailOnly,
    selectedAgent?.currentVersion,
    selectedAgent?.region,
    selectedAgent?.runtimeApp,
    selectedAgent?.runtimeId,
  ]);

  useEffect(() => {
    let cancelled = false;
    setRuntimeDetail(null);
    if (!selectedAgent?.runtimeId || !selectedAgent.region) return;
    void getRuntimeDetail(
      selectedAgent.runtimeId,
      selectedAgent.region,
    )
      .then((detail) => {
        if (!cancelled) setRuntimeDetail(detail);
      })
      .catch(() => {
        if (!cancelled) setRuntimeDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [
    selectedAgent?.currentVersion,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
  ]);

  useEffect(() => {
    let cancelled = false;
    setFeedbackCases([]);
    setFeedbackSets([]);
    setFeedbackCasesError("");
    if (section !== "evaluations" || !selectedAgent?.runtimeId || !selectedAgent.region) {
      setFeedbackCasesLoading(false);
      return;
    }
    setFeedbackCasesLoading(true);
    void getAgentFeedbackCases({
      runtimeId: selectedAgent.runtimeId,
      region: selectedAgent.region,
      appName: selectedAgent.app,
      pageSize: 100,
    })
      .then((response) => {
        if (cancelled) return;
        setFeedbackSets(response.sets);
        setFeedbackCases(
          response.items
            .map((item) => ({
              ...item,
              tag: item.kind === "good" ? "Good case" : "Bad case",
            }))
            .sort((left, right) => (
              caseTimeValue(right.createdAt) - caseTimeValue(left.createdAt)
            )),
        );
      })
      .catch((cause) => {
        if (!cancelled) {
          setFeedbackCasesError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!cancelled) setFeedbackCasesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    feedbackReloadToken,
    section,
    selectedAgent?.app,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
  ]);

  useEffect(() => {
    const caseIds = new Set(feedbackCases.map((item) => item.id));
    setSelectedCaseIds((current) => {
      const next = new Set([...current].filter((id) => caseIds.has(id)));
      return next.size === current.size ? current : next;
    });
    setExpandedCaseIds((current) => {
      const next = new Set([...current].filter((id) => caseIds.has(id)));
      return next.size === current.size ? current : next;
    });
    if (focusedCaseId && !caseIds.has(focusedCaseId)) setFocusedCaseId("");
  }, [feedbackCases, focusedCaseId]);

  useEffect(() => {
    setCaseSelectionMode(false);
    setSelectedCaseIds(new Set());
    setExpandedCaseIds(new Set());
    setCaseDeleteError("");
    setFocusedCaseId("");
  }, [selectedAgent?.runtimeId]);

  useEffect(() => {
    const selectableIds = new Set(
      listedAgents
        .filter((agent) => agent.canDelete === true)
        .map((agent) => agent.id),
    );
    setSelectedAgentIds((current) => {
      const next = new Set([...current].filter((id) => selectableIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [listedAgents]);

  useEffect(() => {
    const selectableIds = new Set(filteredDrafts.map((item) => item.id));
    setSelectedDraftIds((current) => {
      const next = new Set([...current].filter((id) => selectableIds.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [filteredDrafts]);

  const cases = selectedAgent?.runtimeId ? feedbackCases : DEFAULT_CASES;
  const visibleCases = cases.filter((item) => {
    if (item.kind !== caseFilter) return false;
    const keyword = caseQuery.trim().toLowerCase();
    if (!keyword) return true;
    return [
      item.input,
      item.output,
      item.referenceOutput,
      item.comment,
      item.tag ?? "",
      item.sessionId,
      item.messageId,
      item.userId,
      item.evaluationSetName,
    ].join(" ").toLowerCase().includes(keyword);
  });
  const selectedVisibleCases = visibleCases.filter((item) => selectedCaseIds.has(item.id));
  const canManageCases = Boolean(selectedAgent?.runtimeId);

  const focusCaseKind = (kind: CaseKind) => {
    setCaseFilter(kind);
    setCaseQuery("");
    setCaseDeleteError("");
    const firstCase = cases.find((item) => item.kind === kind);
    setFocusedCaseId(firstCase?.id ?? "");
    window.setTimeout(() => {
      caseTableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  };

  const toggleCaseSelection = (item: AgentCase) => {
    setCaseDeleteError("");
    setSelectedCaseIds((current) => {
      const next = new Set(current);
      if (next.has(item.id)) {
        next.delete(item.id);
      } else {
        next.add(item.id);
      }
      return next;
    });
  };

  const selectAllVisibleCases = () => {
    setCaseDeleteError("");
    setSelectedCaseIds(new Set(visibleCases.map((item) => item.id)));
  };

  const clearCaseSelection = () => {
    setCaseDeleteError("");
    setSelectedCaseIds(new Set());
    setCaseSelectionMode(false);
  };

  const toggleCaseExpansion = (caseId: string) => {
    setExpandedCaseIds((current) => {
      const next = new Set(current);
      if (next.has(caseId)) {
        next.delete(caseId);
      } else {
        next.add(caseId);
      }
      return next;
    });
  };

  const openFeedbackCase = (item: AgentCase) => {
    setFocusedCaseId(item.id);
    setCaseDeleteError("");
    if (!item.sessionId || !item.messageId) return;
    void onOpenFeedbackCase?.(item);
  };

  const deleteCases = async (items: AgentCase[]) => {
    if (
      !selectedAgent?.runtimeId ||
      !selectedAgent.region ||
      deletingCases ||
      items.length === 0
    ) return;
    const confirmText = items.length === 1
      ? "确定删除这条反馈案例？原始聊天记录不会被删除。"
      : `确定删除选中的 ${items.length} 条反馈案例？原始聊天记录不会被删除。`;
    if (!window.confirm(confirmText)) return;
    const ids = items.map((item) => item.id);
    const idSet = new Set(ids);
    setDeletingCases(true);
    setCaseDeleteError("");
    try {
      await deleteAgentFeedbackCases({
        runtimeId: selectedAgent.runtimeId,
        region: selectedAgent.region,
        appName: selectedAgent.app,
        itemIds: ids,
      });
      const deletedByKind = new Map<CaseKind, number>();
      for (const item of items) {
        deletedByKind.set(item.kind, (deletedByKind.get(item.kind) ?? 0) + 1);
      }
      setFeedbackCases((current) => current.filter((item) => !idSet.has(item.id)));
      setFeedbackSets((current) =>
        current.map((set) => ({
          ...set,
          itemCount: Math.max(0, set.itemCount - (deletedByKind.get(set.kind) ?? 0)),
        })),
      );
      setSelectedCaseIds((current) =>
        new Set([...current].filter((id) => !idSet.has(id))),
      );
      setExpandedCaseIds((current) =>
        new Set([...current].filter((id) => !idSet.has(id))),
      );
      if (focusedCaseId && idSet.has(focusedCaseId)) setFocusedCaseId("");
      if (items.length > 1) setCaseSelectionMode(false);
      onFeedbackCasesDeleted?.(items);
    } catch (cause) {
      setCaseDeleteError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setDeletingCases(false);
    }
  };

  const updateEvaluationGroup = (nextGroup: EvaluationGroup) => {
    setEvaluationGroups((current) =>
      current.map((group) => (group.id === nextGroup.id ? nextGroup : group)),
    );
  };

  const orderedAgentIds = () => {
    const currentIds = new Set(agents.map((agent) => agent.id));
    const savedIds = agentOrder.filter((id) => currentIds.has(id));
    const saved = new Set(savedIds);
    return [
      ...savedIds,
      ...agents.filter((agent) => !saved.has(agent.id)).map((agent) => agent.id),
    ];
  };

  const moveAgentNear = (
    agentId: string,
    targetAgentId: string,
    placement: "before" | "after",
  ) => {
    if (!onAgentOrderChange || agentId === targetAgentId) return;
    const next = orderedAgentIds().filter((id) => id !== agentId);
    const targetIndex = next.indexOf(targetAgentId);
    const insertIndex = targetIndex < 0
      ? next.length
      : placement === "after"
        ? targetIndex + 1
        : targetIndex;
    next.splice(insertIndex, 0, agentId);
    onAgentOrderChange(next);
  };

  const updateDropPlacement = (
    event: DragEvent<HTMLButtonElement>,
    agentId: string,
  ) => {
    if (!draggingAgentId || draggingAgentId === agentId) return;
    const rect = event.currentTarget.getBoundingClientRect();
    setDropAgentId(agentId);
    setDropPlacement(event.clientY > rect.top + rect.height / 2 ? "after" : "before");
  };

  const moveAgentByOffset = (agentId: string, offset: number) => {
    if (!onAgentOrderChange) return;
    const next = orderedAgentIds();
    const index = next.indexOf(agentId);
    const targetIndex = Math.max(0, Math.min(next.length - 1, index + offset));
    if (index < 0 || index === targetIndex) return;
    next.splice(index, 1);
    next.splice(targetIndex, 0, agentId);
    onAgentOrderChange(next);
  };

  const toggleAgentSelection = (agent: AgentEntry) => {
    if (agent.canDelete !== true) return;
    setDeleteError("");
    setSelectedAgentIds((current) => {
      const next = new Set(current);
      if (next.has(agent.id)) {
        next.delete(agent.id);
      } else {
        next.add(agent.id);
      }
      return next;
    });
  };

  const toggleDraftSelection = (draftItem: WorkspaceAgentDraft) => {
    setDeleteError("");
    setSelectedDraftIds((current) => {
      const next = new Set(current);
      if (next.has(draftItem.id)) {
        next.delete(draftItem.id);
      } else {
        next.add(draftItem.id);
      }
      return next;
    });
  };

  const selectAllListedAgents = () => {
    setDeleteError("");
    setSelectedAgentIds(new Set(deletableListedAgents.map((agent) => agent.id)));
    setSelectedDraftIds(new Set(filteredDrafts.map((item) => item.id)));
  };

  const clearAgentSelection = () => {
    setDeleteError("");
    setSelectedAgentIds(new Set());
    setSelectedDraftIds(new Set());
    setSelectionMode(false);
  };

  const deleteSelectedItems = async () => {
    if (selectedDeleteCount === 0 || deletingAgents) return;
    const runtimeCount = selectedDeletableAgents.length;
    const draftCount = selectedDeletableDrafts.length;
    const confirmText = runtimeCount === 1 && draftCount === 0
      ? `确定删除 Agent "${selectedDeletableAgents[0].label}"？该 Runtime 将被永久删除。`
      : runtimeCount === 0 && draftCount === 1
        ? `确定删除草稿 "${selectedDeletableDrafts[0].draft.name || "未命名 Agent"}"？`
        : `确定删除选中的 ${selectedDeleteCount} 个项目？${runtimeCount > 0 ? `${runtimeCount} 个 Runtime 将被永久删除。` : ""}`;
    if (!window.confirm(confirmText)) return;
    setDeletingAgents(true);
    setDeleteError("");
    try {
      if (selectedDeletableAgents.length > 0) {
        if (!onDeleteAgents) throw new Error("当前页面不支持删除已部署 Agent。");
        await onDeleteAgents(selectedDeletableAgents);
      }
      if (selectedDeletableDrafts.length > 0) {
        onDeleteDrafts?.(selectedDeletableDrafts);
      }
      setSelectedAgentIds(new Set());
      setSelectedDraftIds(new Set());
      setSelectionMode(false);
      if (selectedDeletableAgents.some((agent) => agent.id === activeAgentId)) {
        setActiveAgentId("");
      }
      if (selectedDeletableDrafts.some((item) => item.id === activeDraftId)) {
        setActiveDraftId("");
      }
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setDeletingAgents(false);
    }
  };

  const deleteSingleAgent = async (agent: AgentEntry) => {
    if (!onDeleteAgents || agent.canDelete !== true || deletingAgents) return;
    if (!window.confirm(`确定删除 Agent "${agent.label}"？该 Runtime 将被永久删除。`)) {
      return;
    }
    setDeletingAgents(true);
    setDeleteError("");
    try {
      await onDeleteAgents([agent]);
      if (activeAgentId === agent.id) setActiveAgentId("");
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setDeletingAgents(false);
    }
  };

  const deleteSingleDraft = (draftItem: WorkspaceAgentDraft) => {
    if (!onDeleteDrafts || deletingAgents) return;
    const name = draftItem.draft.name || "未命名 Agent";
    if (!window.confirm(`确定删除草稿 "${name}"？`)) return;
    setDeleteError("");
    onDeleteDrafts([draftItem]);
    if (activeDraftId === draftItem.id) setActiveDraftId("");
  };

  const createEvaluationGroup = () => {
    const id = `eval-${Date.now()}`;
    const nextGroup: EvaluationGroup = {
      id,
      name: `新评测组 ${evaluationGroups.length + 1}`,
      agentIds: [],
      caseSet: "核心回归集",
      evaluator: "综合质量评估器",
      metrics: ["回答质量"],
      concurrency: "4",
      history: [],
    };
    setEvaluationGroups((current) => [nextGroup, ...current]);
    setActiveEvaluationGroupId(id);
  };

  const runEvaluation = (group: EvaluationGroup) => {
    updateEvaluationGroup({
      ...group,
      history: [
        {
          id: `run-${Date.now()}`,
          createdAt: "刚刚",
          score: 86 + (group.history.length % 7),
          status: "completed",
        },
        ...group.history,
      ],
    });
  };

  return (
    <div className={`aw-root${detailOnly ? " is-detail-only" : ""}`}>
      <nav className="aw-view-tabs" aria-label="智能体工作台">
        <button
          type="button"
          className={view === "library" ? "is-active" : ""}
          aria-pressed={view === "library"}
          onClick={() => {
            setView("library");
            setQuery("");
          }}
        >
          智能体库
        </button>
        <button
          type="button"
          className={view === "evaluation" ? "is-active" : ""}
          aria-pressed={view === "evaluation"}
          onClick={() => {
            setView("evaluation");
            setQuery("");
          }}
        >
          评测
        </button>
      </nav>

      <div className="aw-workspace-frame">
        <div
          className="aw-workspace"
          aria-hidden={view === "evaluation" || undefined}
          ref={(node) => node?.toggleAttribute("inert", view === "evaluation")}
        >
        <aside className="aw-sidebar" aria-label={view === "library" ? "智能体列表" : "评测组列表"}>
          <label className="aw-search">
            <Search aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder={view === "library" ? "搜索智能体" : "搜索评测组"}
              aria-label={view === "library" ? "搜索智能体" : "搜索评测组"}
            />
          </label>
          <button
            type="button"
            className="aw-create-card"
            onClick={view === "library" ? onCreateAgent : createEvaluationGroup}
            disabled={view === "library" && !canCreate}
          >
            <Plus aria-hidden />
            <span>{view === "library" ? "新建 Agent" : "新建评测组"}</span>
          </button>
          {view === "library" && (onDeleteAgents || onDeleteDrafts) && (
            <div className={`aw-selection-toolbar${selectionMode ? " is-active" : ""}`}>
              {selectionMode ? (
                <>
                  <span className="aw-selection-count">
                    已选 {selectedDeleteCount} 个
                  </span>
                  <button
                    type="button"
                    onClick={selectAllListedAgents}
                    disabled={deletableItemCount === 0 || deletingAgents}
                  >
                    全选
                  </button>
                  <button
                    type="button"
                    className="aw-selection-danger"
                    onClick={() => void deleteSelectedItems()}
                    disabled={selectedDeleteCount === 0 || deletingAgents}
                  >
                    {deletingAgents ? "删除中…" : "删除所选"}
                  </button>
                  <button
                    type="button"
                    onClick={clearAgentSelection}
                    disabled={deletingAgents}
                  >
                    取消
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setDeleteError("");
                    setSelectionMode(true);
                  }}
                  disabled={deletableItemCount === 0}
                >
                  选择
                </button>
              )}
            </div>
          )}
          {view === "library" && deleteError && (
            <div className="aw-delete-error" role="alert">{deleteError}</div>
          )}
          <div className="aw-agent-list">
            {view === "evaluation" ? (
              filteredEvaluationGroups.length === 0 ? (
                <div className="aw-list-empty">没有匹配的评测组</div>
              ) : (
                filteredEvaluationGroups.map((group) => (
                  <button
                    type="button"
                    key={group.id}
                    className={`aw-agent-item${group.id === activeEvaluationGroupId ? " is-active" : ""}`}
                    onClick={() => setActiveEvaluationGroupId(group.id)}
                  >
                    <span className="aw-agent-copy aw-eval-group-copy">
                      <strong>{group.name}</strong>
                      <small>{group.agentIds.length} 个智能体 · {group.history.length} 次运行</small>
                    </span>
                    <ArrowRight aria-hidden />
                  </button>
                ))
              )
            ) : loadingAgents && listedAgents.length === 0 && filteredDrafts.length === 0 ? (
              <div className="aw-list-empty">正在读取云端智能体…</div>
            ) : agentsError && listedAgents.length === 0 && filteredDrafts.length === 0 ? (
              <div className="aw-list-empty aw-list-error">
                <span>{agentsError}</span>
                {onRetryAgents && (
                  <button type="button" onClick={onRetryAgents}>重试</button>
                )}
              </div>
            ) : listedAgents.length === 0 && filteredDrafts.length === 0 ? (
              <div className="aw-list-empty">没有匹配的智能体</div>
            ) : (
              <>
                {filteredDrafts.map((item) => {
                  const task = deploymentTasks
                    .filter(
                      (candidate) =>
                        candidate.agentDraft?.name === item.draft.name ||
                        candidate.runtimeName === item.draft.name ||
                        (!!item.deploymentTarget?.runtimeId &&
                          candidate.runtimeId === item.deploymentTarget.runtimeId),
                    )
                    .sort((left, right) => right.startedAt - left.startedAt)[0];
                  const isSelectedForDelete = selectedDraftIds.has(item.id);
                  return (
                    <button
                      type="button"
                      key={item.id}
                      className={[
                        "aw-agent-item",
                        selectionMode ? "is-selecting" : "",
                        isSelectedForDelete ? "is-selected-for-delete" : "",
                        item.id === activeDraftId ? "is-active" : "",
                      ].filter(Boolean).join(" ")}
                      aria-pressed={selectionMode ? isSelectedForDelete : undefined}
                      onClick={() => {
                        if (selectionMode) {
                          toggleDraftSelection(item);
                          return;
                        }
                        setActiveAgentId("");
                        setActiveDraftId(item.id);
                        setSection("basic");
                      }}
                    >
                      {selectionMode && (
                        <span
                          className={`aw-select-marker${isSelectedForDelete ? " is-checked" : ""}`}
                          aria-hidden="true"
                        />
                      )}
                      <span className="aw-agent-copy">
                        <span className="aw-agent-name-row">
                          <strong>{item.draft.name || "未命名 Agent"}</strong>
                          <span className={`aw-draft-badge${task?.status === "running" ? " is-deploying" : ""}`}>
                            {task?.status === "running" ? "部署中" : "草稿"}
                          </span>
                        </span>
                        <small>{item.deploymentTarget ? "待更新" : "尚未发布"}</small>
                      </span>
                      <ArrowRight aria-hidden />
                    </button>
                  );
                })}
                {listedAgents.map((agent) => {
                  const runtimeTask = agent.runtimeId
                    ? latestTaskByRuntimeId.get(agent.runtimeId)
                    : undefined;
                  const updateDraft = agent.runtimeId
                    ? updateDraftByRuntimeId.get(agent.runtimeId)
                    : undefined;
                  const isSelectedForDelete = selectedAgentIds.has(agent.id);
                  const canDeleteAgent = agent.canDelete === true;
                  const statusBadge =
                    runtimeTask?.status === "running"
                      ? { label: "部署中", className: " is-deploying" }
                    : runtimeTask?.status === "error"
                      ? { label: "失败", className: " is-error" }
                      : runtimeTask?.status === "cancelled"
                        ? { label: "已取消", className: " is-muted" }
                        : updateDraft
                          ? { label: "待更新", className: "" }
                          : null;
                const metaText = runtimeTask?.status === "running"
                  ? "正在更新部署"
                  : updateDraft
                    ? "待更新"
                    : agent.remote
                      ? agent.host || "远程智能体"
                      : "本地智能体";
                const agentItemClass = [
                  "aw-agent-item",
                  "aw-agent-item--sortable",
                  agent.id === activeAgentId ? "is-active" : "",
                  selectionMode ? "is-selecting" : "",
                  isSelectedForDelete ? "is-selected-for-delete" : "",
                  selectionMode && !canDeleteAgent ? "is-selection-disabled" : "",
                  agent.id === draggingAgentId ? "is-dragging" : "",
                  agent.id === dropAgentId && agent.id !== draggingAgentId
                    ? `is-drop-target is-drop-${dropPlacement}`
                    : "",
                ].filter(Boolean).join(" ");
                return (
                  <button
                    type="button"
                    key={agent.id}
                    draggable={!!onAgentOrderChange && !selectionMode}
                    className={agentItemClass}
                    aria-pressed={selectionMode ? isSelectedForDelete : undefined}
                    aria-keyshortcuts={onAgentOrderChange ? "Alt+ArrowUp Alt+ArrowDown" : undefined}
                    onDragStart={(event) => {
                      if (!onAgentOrderChange) return;
                      suppressAgentClickRef.current = true;
                      setDraggingAgentId(agent.id);
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", agent.id);
                    }}
                    onDragEnter={(event) => {
                      updateDropPlacement(event, agent.id);
                    }}
                    onDragOver={(event) => {
                      if (!draggingAgentId || draggingAgentId === agent.id) return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                      updateDropPlacement(event, agent.id);
                    }}
                    onDragLeave={(event) => {
                      const nextTarget = event.relatedTarget;
                      if (
                        nextTarget instanceof Node &&
                        event.currentTarget.contains(nextTarget)
                      ) return;
                      if (dropAgentId === agent.id) setDropAgentId("");
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      const draggedId =
                        event.dataTransfer.getData("text/plain") || draggingAgentId;
                      moveAgentNear(draggedId, agent.id, dropPlacement);
                      setDraggingAgentId("");
                      setDropAgentId("");
                      setDropPlacement("before");
                    }}
                    onDragEnd={() => {
                      setDraggingAgentId("");
                      setDropAgentId("");
                      setDropPlacement("before");
                      window.setTimeout(() => {
                        suppressAgentClickRef.current = false;
                      }, 0);
                    }}
                    onKeyDown={(event) => {
                      if (!event.altKey) return;
                      if (event.key === "ArrowUp") {
                        event.preventDefault();
                        moveAgentByOffset(agent.id, -1);
                      } else if (event.key === "ArrowDown") {
                        event.preventDefault();
                        moveAgentByOffset(agent.id, 1);
                      }
                    }}
                    onClick={(event) => {
                      if (selectionMode) {
                        event.preventDefault();
                        toggleAgentSelection(agent);
                        return;
                      }
                      if (suppressAgentClickRef.current) {
                        event.preventDefault();
                        suppressAgentClickRef.current = false;
                        return;
                      }
                      setActiveDraftId("");
                      setActiveAgentId(agent.id);
                      setSection("basic");
                      onSelectAgent(agent.id);
                    }}
                  >
                    {selectionMode && (
                      <span
                        className={`aw-select-marker${isSelectedForDelete ? " is-checked" : ""}`}
                        aria-hidden="true"
                      />
                    )}
                    <span className="aw-agent-copy">
                      <span className="aw-agent-name-row">
                        <strong>{agent.label}</strong>
                        {agent.currentVersion != null && (
                          <span className="aw-version-badge">
                            v{agent.currentVersion}
                          </span>
                        )}
                        {statusBadge && (
                          <span className={`aw-draft-badge${statusBadge.className}`}>
                            {statusBadge.label}
                          </span>
                        )}
                      </span>
                      <small>{metaText}</small>
                    </span>
                    <ArrowRight aria-hidden />
                  </button>
                );
              })}
              </>
            )}
          </div>
          <div className="aw-list-count">
            共 {view === "library" ? agents.length + standaloneDraftCount : evaluationGroups.length} 个
          </div>
        </aside>

        {view === "evaluation" && selectedEvaluationGroup ? (
          <EvaluationWorkspace
            group={selectedEvaluationGroup}
            agents={agents}
            cases={cases}
            onChange={updateEvaluationGroup}
            onRun={runEvaluation}
          />
        ) : view === "evaluation" ? (
          <main className="aw-main aw-empty-selection">
            <p>未选择评测组</p>
          </main>
        ) : !selectedAgent && !selectedDraft && !selectedPendingTask ? (
          <main className="aw-main aw-empty-selection">
            <p>未选择智能体</p>
          </main>
        ) : (
          <main className="aw-main">
            {selectedAgent && !selectedAgentInfo && loadingAgentInfo && (
              <div className="aw-detail-loading" role="status" aria-live="polite">
                <div className="aw-detail-loading-card">
                  <span className="loading-gap-spinner" aria-hidden="true" />
                  <span>
                    <strong>正在加载智能体</strong>
                    <small>正在读取配置与运行信息…</small>
                  </span>
                </div>
              </div>
            )}
            <div className="aw-agent-head">
              <div>
                <div className="aw-agent-title-row">
                  <h2>{selectedName}</h2>
                  {displayCurrentVersion != null && (
                    <span>v{displayCurrentVersion}</span>
                  )}
                  {selectedDraft && <span>草稿</span>}
                  {selectedAgentUpdateDraft && <span>待更新</span>}
                  {!selectedAgent && !selectedDraft && selectedPendingTask && (
                    <span>{selectedPendingTask.label}</span>
                  )}
                </div>
                <p>{draft.description || (loadingAgentInfo || (detailOnly && !detailAgentInfoResolved) ? "正在读取智能体信息…" : "暂无描述")}</p>
              </div>
              {(selectedDraft || selectedAgentUpdateDraft) && (
                <div className="aw-head-actions">
                  {(selectedDraft || selectedAgentUpdateDraft) && (
                    <button
                      type="button"
                      className="aw-head-delete aw-head-delete--draft"
                      onClick={() => {
                        const draftToDelete = selectedDraft ?? selectedAgentUpdateDraft;
                        if (draftToDelete) deleteSingleDraft(draftToDelete);
                      }}
                      disabled={deletingAgents}
                      aria-label="删除草稿"
                      title="删除草稿"
                    >
                      <Trash2 aria-hidden />
                      <span>删除草稿</span>
                    </button>
                  )}
                </div>
              )}
            </div>
            {deploymentTask && shouldShowDeploymentTask && (
              <div className="aw-detail-deployment">
                <DeploymentProgressCard task={deploymentTask} />
              </div>
            )}
            <nav className="aw-agent-tabs" aria-label="智能体详情">
              {AGENT_SECTIONS.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={section === item.id ? "is-active" : ""}
                  aria-pressed={section === item.id}
                  onClick={() => setSection(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </nav>

            <div className="aw-content">
              {section === "basic" && (
                <div className="aw-basic-stack">
                  <section className="aw-deployment-panel aw-settings-card">
                    <div className="aw-section-head">
                      <div><h3>部署配置</h3><p>配置目标环境与网络访问方式。</p></div>
                    </div>
                    <dl className="aw-readonly-config">
                      <div>
                        <dt>运行状态</dt>
                        <dd className={runtimeDetail?.status.toLowerCase() === "ready" ? "is-ready" : undefined}>
                          {runtimeDetail?.status.toLowerCase() === "ready" && <span className="aw-status-dot" />}
                          {runtimeDetail?.status || "读取中…"}
                        </dd>
                      </div>
                      <div>
                        <dt>部署区域</dt>
                        <dd>{runtimeDetail?.region || selectedAgent?.region || deploymentTask?.region || "暂未提供"}</dd>
                      </div>
                      <div>
                        <dt>网络访问</dt>
                        <dd>
                          {runtimeDetail?.networkTypes.length
                            ? runtimeDetail.networkTypes.join(" / ")
                            : "暂未提供"}
                        </dd>
                      </div>
                    </dl>
                  </section>
                  <section className="aw-canvas-card">
                    <div className="aw-card-head">
                      <strong>执行流程</strong>
                    </div>
                    <div className="aw-canvas">
                      {loadingExecutionFlow ? (
                        <div className="aw-canvas-loading" role="status" aria-live="polite">
                          <span className="loading-gap-spinner" aria-hidden="true" />
                          <span>正在加载执行流程</span>
                        </div>
                      ) : (
                        <AgentBuildCanvas
                          key={executionFlowKey}
                          draft={draft}
                          direction="horizontal"
                          selectedPath={[]}
                          onSelect={() => undefined}
                          onAdd={() => undefined}
                          onInsert={() => undefined}
                          onDelete={() => undefined}
                          readOnly
                          interactivePreview
                        />
                      )}
                    </div>
                  </section>
                  <section className="aw-details-card">
                    <div className="aw-card-head">
                      <strong>详细信息</strong>
                    </div>
                    <dl className="aw-facts">
                      <div><dt>模型</dt><dd>{selectedAgentInfo?.model || draft.modelName || "暂未提供"}</dd></div>
                      <div><dt>智能体数量</dt><dd>{selectedAgentInfo?.graph ? countNodes(selectedAgentInfo.graph) : countDraftNodes(draft)}</dd></div>
                      <div>
                        <dt>工具</dt>
                        <dd className="aw-fact-badges">
                          {toolNames.length ? toolNames.map((name) => <span key={name}>{name}</span>) : "暂无"}
                        </dd>
                      </div>
                      <div>
                        <dt>技能</dt>
                        <dd className="aw-fact-badges">
                          {skillNames === null
                            ? "暂不支持预览"
                            : skillNames.length
                              ? skillNames.map((name) => <span key={name}>{name}</span>)
                              : "暂无"}
                        </dd>
                      </div>
                      <div>
                        <dt>当前版本</dt>
                        <dd>
                          {displayCurrentVersion != null
                            ? `v${displayCurrentVersion}`
                            : "暂未提供"}
                        </dd>
                      </div>
                      <div>
                        <dt>状态</dt>
                        <dd>
                          {selectedDraft
                            ? "草稿"
                            : deploymentTask?.status === "error"
                              ? "部署失败"
                              : deploymentTask?.status === "cancelled"
                                ? "已取消"
                                : selectedAgentUpdateDraft
                                  ? "待更新"
                                  : <><span className="aw-status-dot" />可用</>}
                        </dd>
                      </div>
                    </dl>
                  </section>
                  <section className="aw-option-panel aw-settings-card">
                    <div className="aw-section-head">
                      <div><h3>优化项</h3><p>针对运行质量开启专项优化策略。</p></div>
                    </div>
                    <div className="aw-option-content">
                      <div className="aw-option-list" aria-disabled="true">
                        {[
                          ["上下文优化", "压缩冗余信息，保留对当前任务最有价值的上下文。"],
                          ["幻觉抑制", "在证据不足时降低确定性表达并主动请求补充信息。"],
                          ["工具调用优化", "减少重复调用，并优先复用已经获得的结果。"],
                        ].map(([title, description]) => (
                          <label key={title}>
                            <input type="checkbox" disabled />
                            <span><strong>{title}</strong><small>{description}</small></span>
                          </label>
                        ))}
                      </div>
                      <div className="aw-option-glass" role="status">
                        <span>暂未开放</span>
                      </div>
                    </div>
                  </section>
                </div>
              )}

              {section === "evaluations" && (
                <section className="aw-cases">
                  {selectedAgent?.runtimeId ? (
                    <div className="aw-case-summary">
                      {(["good", "bad"] as const).map((kind) => {
                        const set = feedbackSetFor(feedbackSets, kind);
                        const count = set?.itemCount ??
                          feedbackCases.filter((item) => item.kind === kind).length;
                        return (
                          <button
                            type="button"
                            key={kind}
                            onClick={() => focusCaseKind(kind)}
                          >
                            <strong>{count}</strong>
                            <span>{kind === "good" ? "Good cases" : "Bad cases"}</span>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="aw-case-note">
                      只有已部署到 AgentKit Runtime 的 Agent 会同步展示用户反馈评测集。
                    </div>
                  )}
                  <div className="aw-case-filters">
                    {(["good", "bad"] as const).map((filter) => (
                      <button
                        type="button"
                        key={filter}
                        className={caseFilter === filter ? "is-active" : ""}
                        aria-pressed={caseFilter === filter}
                        onClick={() => setCaseFilter(filter)}
                      >
                        {filter === "good" ? "Good case" : "Bad case"}
                      </button>
                    ))}
                  </div>
                  <label className="aw-case-search">
                    <Search aria-hidden />
                    <input
                      type="search"
                      value={caseQuery}
                      onChange={(event) => setCaseQuery(event.currentTarget.value)}
                      placeholder="搜索用户输入、期望行为或标签"
                      aria-label="搜索评测案例"
                    />
                  </label>
                  {canManageCases && (
                    <div className={`aw-case-toolbar${caseSelectionMode ? " is-active" : ""}`}>
                      {caseSelectionMode ? (
                        <>
                          <span className="aw-selection-count">
                            已选 {selectedVisibleCases.length} 条
                          </span>
                          <button
                            type="button"
                            onClick={selectAllVisibleCases}
                            disabled={visibleCases.length === 0 || deletingCases}
                          >
                            全选当前
                          </button>
                          <button
                            type="button"
                            className="aw-selection-danger"
                            onClick={() => void deleteCases(selectedVisibleCases)}
                            disabled={selectedVisibleCases.length === 0 || deletingCases}
                          >
                            {deletingCases ? "删除中…" : "删除所选"}
                          </button>
                          <button
                            type="button"
                            onClick={clearCaseSelection}
                            disabled={deletingCases}
                          >
                            取消
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            setCaseDeleteError("");
                            setCaseSelectionMode(true);
                          }}
                          disabled={visibleCases.length === 0 || deletingCases}
                        >
                          选择案例
                        </button>
                      )}
                    </div>
                  )}
                  {caseDeleteError && (
                    <div className="aw-delete-error" role="alert">{caseDeleteError}</div>
                  )}
                  <div ref={caseTableRef}>
                    <CaseTable
                      cases={visibleCases}
                      loading={feedbackCasesLoading}
                      error={feedbackCasesError}
                      runtimeBacked={Boolean(selectedAgent?.runtimeId)}
                      selectionMode={caseSelectionMode}
                      selectedCaseIds={selectedCaseIds}
                      focusedCaseId={focusedCaseId}
                      expandedCaseIds={expandedCaseIds}
                      deleting={deletingCases}
                      canDelete={canManageCases}
                      onOpenCase={openFeedbackCase}
                      onToggleCase={toggleCaseSelection}
                      onToggleExpanded={toggleCaseExpansion}
                      onDeleteCase={(item) => void deleteCases([item])}
                      onRetry={() => setFeedbackReloadToken((value) => value + 1)}
                    />
                  </div>
                </section>
              )}
            </div>
            {section === "basic" && (selectedAgent || selectedDraft) && (
              <div className="aw-basic-actions">
                {selectedAgent && (
                  <button
                    type="button"
                    className="aw-talk studio-update-action"
                    onClick={() => onTalkAgent?.(selectedAgent.id)}
                  >
                    <MessageCircle aria-hidden />
                    <span>去对话</span>
                  </button>
                )}
                <button
                  type="button"
                  className="aw-update studio-update-action"
                  disabled={selectedDraft || selectedAgentUpdateDraft
                    ? !canCreate
                    : !selectedAgent?.runtimeId || !canUpdate || (!loadingAgentInfo && !selectedAgentInfo)}
                  onClick={() =>
                    selectedDraft
                      ? onEditDraft?.(selectedDraft)
                      : selectedAgentUpdateDraft
                        ? onEditDraft?.(selectedAgentUpdateDraft)
                        : onUpdateAgent(draft)
                  }
                >
                  {selectedDraft || selectedAgentUpdateDraft ? "继续编辑" : "更新"}
                </button>
                {(selectedDraft || selectedAgentUpdateDraft) && (
                  <button
                    type="button"
                    className="aw-head-delete studio-update-action"
                    onClick={() => {
                      const draftToDelete = selectedDraft ?? selectedAgentUpdateDraft;
                      if (draftToDelete) deleteSingleDraft(draftToDelete);
                    }}
                    disabled={deletingAgents}
                    aria-label="删除草稿"
                    title="删除草稿"
                  >
                    <Trash2 aria-hidden />
                    <span>删除草稿</span>
                  </button>
                )}
                {selectedAgent?.canDelete && (
                  <button
                    type="button"
                    className="aw-head-delete studio-update-action"
                    onClick={() => void deleteSingleAgent(selectedAgent)}
                    disabled={deletingAgents}
                    aria-label="删除 Agent"
                    title="删除 Agent"
                  >
                    <Trash2 aria-hidden />
                    <span>{deletingAgents ? "删除中…" : "删除 Agent"}</span>
                  </button>
                )}
              </div>
            )}
          </main>
        )}
        </div>
        {view === "evaluation" && (
          <div className="aw-evaluation-glass" role="status">
            <span>敬请期待</span>
          </div>
        )}
      </div>
    </div>
  );
}

function CaseTable({
  cases,
  loading = false,
  error = "",
  runtimeBacked = false,
  selectionMode = false,
  selectedCaseIds,
  focusedCaseId = "",
  expandedCaseIds,
  deleting = false,
  canDelete = false,
  onOpenCase,
  onToggleCase,
  onToggleExpanded,
  onDeleteCase,
  onRetry,
}: {
  cases: AgentCase[];
  loading?: boolean;
  error?: string;
  runtimeBacked?: boolean;
  selectionMode?: boolean;
  selectedCaseIds?: Set<string>;
  focusedCaseId?: string;
  expandedCaseIds?: Set<string>;
  deleting?: boolean;
  canDelete?: boolean;
  onOpenCase?: (item: AgentCase) => void;
  onToggleCase?: (item: AgentCase) => void;
  onToggleExpanded?: (caseId: string) => void;
  onDeleteCase?: (item: AgentCase) => void;
  onRetry?: () => void;
}) {
  return (
    <div className="aw-case-table">
      <div className="aw-case-row aw-case-row-head">
        <span>用户输入</span><span>Agent 输出</span><span>来源</span>
      </div>
      {loading ? (
        <div className="aw-case-empty">正在读取 AgentKit 评测集…</div>
      ) : error ? (
        <div className="aw-case-empty aw-case-error">
          <span>{error}</span>
          {onRetry && <button type="button" onClick={onRetry}>重试</button>}
        </div>
      ) : cases.length === 0 ? (
        <div className="aw-case-empty">
          {runtimeBacked ? "暂无用户反馈案例" : "没有匹配的案例"}
        </div>
      ) : (
        cases.map((item) => {
          const isSelected = selectedCaseIds?.has(item.id) ?? false;
          const isExpanded = expandedCaseIds?.has(item.id) ?? false;
          const outputLength =
            item.output.length + item.referenceOutput.length;
          const canExpand = outputLength > 220;
          return (
            <div
              className={[
                "aw-case-row",
                focusedCaseId === item.id ? "is-focused" : "",
                selectionMode ? "is-selecting" : "",
                isSelected ? "is-selected-for-delete" : "",
              ].filter(Boolean).join(" ")}
              key={item.id}
              role="row"
              tabIndex={0}
              aria-selected={selectionMode ? isSelected : undefined}
              onClick={() => {
                if (selectionMode) {
                  onToggleCase?.(item);
                  return;
                }
                onOpenCase?.(item);
              }}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                if (selectionMode) {
                  onToggleCase?.(item);
                } else {
                  onOpenCase?.(item);
                }
              }}
            >
              <div className="aw-case-text">
                <span className="aw-case-title-line">
                  {selectionMode && (
                    <span
                      className={`aw-select-marker${isSelected ? " is-checked" : ""}`}
                      aria-hidden="true"
                    />
                  )}
                  <strong title={item.input}>{item.input || "无用户输入"}</strong>
                </span>
                {item.comment && <small title={item.comment}>备注：{item.comment}</small>}
              </div>
              <div className={`aw-case-output${isExpanded ? " is-expanded" : ""}`}>
                <p className="aw-case-output-preview" title={item.output}>
                  {item.output || "无可见回复"}
                </p>
                {item.referenceOutput && (
                  <small
                    className="aw-case-output-preview"
                    title={item.referenceOutput}
                  >
                    Reference: {item.referenceOutput}
                  </small>
                )}
                {canExpand && (
                  <button
                    type="button"
                    className="aw-case-expand"
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggleExpanded?.(item.id);
                    }}
                  >
                    {isExpanded ? "收起" : "展开"}
                  </button>
                )}
              </div>
              <div className="aw-case-meta">
                <span className="aw-case-meta-top">
                  <span className={`aw-case-tag is-${item.kind}`}>
                    {item.kind === "good" ? "Good case" : "Bad case"}
                  </span>
                  {canDelete && (
                    <button
                      type="button"
                      className="aw-case-delete"
                      onClick={(event) => {
                        event.stopPropagation();
                        onDeleteCase?.(item);
                      }}
                      disabled={deleting}
                      title="删除反馈案例"
                      aria-label="删除反馈案例"
                    >
                      <Trash2 aria-hidden />
                    </button>
                  )}
                </span>
                <small>{formatCaseTime(item.createdAt)}</small>
                {(item.userId || item.sessionId) && (
                  <small title={[item.userId, item.sessionId].filter(Boolean).join(" · ")}>
                    {[item.userId, item.sessionId].filter(Boolean).join(" · ")}
                  </small>
                )}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

function EvaluationWorkspace({
  group,
  agents,
  cases,
  onChange,
  onRun,
}: {
  group: EvaluationGroup;
  agents: AgentEntry[];
  cases: AgentCase[];
  onChange: (group: EvaluationGroup) => void;
  onRun: (group: EvaluationGroup) => void;
}) {
  const [section, setSection] = useState<EvaluationSection>("config");
  const selectedAgents = group.agentIds
    .map((id) => agents.find((agent) => agent.id === id))
    .filter((agent): agent is AgentEntry => Boolean(agent));
  const metrics = ["回答质量", "事实准确性", "工具调用", "响应效率"];

  useEffect(() => setSection("config"), [group.id]);

  const toggleAgent = (id: string) => {
    onChange({
      ...group,
      agentIds: group.agentIds.includes(id)
        ? group.agentIds.filter((agentId) => agentId !== id)
        : [...group.agentIds, id],
    });
  };

  const toggleMetric = (metric: string) => {
    onChange({
      ...group,
      metrics: group.metrics.includes(metric)
        ? group.metrics.filter((item) => item !== metric)
        : [...group.metrics, metric],
    });
  };

  return (
    <main className="aw-main">
      <div className="aw-eval-head">
        <div>
          <div className="aw-agent-title-row"><h2>{group.name}</h2><span>评测组</span></div>
          <p>{selectedAgents.length} 个参评智能体 · {group.caseSet} · {group.history.length} 次运行</p>
        </div>
        <button type="button" className="aw-run" onClick={() => onRun(group)} disabled>
          <FlaskConical aria-hidden />开始评测
        </button>
      </div>
      <nav className="aw-agent-tabs" aria-label="评测组详情">
        <button type="button" className={section === "config" ? "is-active" : ""} aria-pressed={section === "config"} onClick={() => setSection("config")} disabled>评测配置</button>
        <button type="button" className={section === "history" ? "is-active" : ""} aria-pressed={section === "history"} onClick={() => setSection("history")} disabled>历史结果</button>
      </nav>
      <div className="aw-content">
        {section === "config" ? (
          <div className="aw-eval-setup">
            <section className="aw-eval-block">
              <div className="aw-card-head"><strong>参评智能体</strong><span>已选择 {selectedAgents.length} 个</span></div>
              <div className="aw-eval-agent-grid">
                {agents.map((agent) => (
                  <label key={agent.id}>
                    <input type="checkbox" checked={group.agentIds.includes(agent.id)} onChange={() => toggleAgent(agent.id)} />
                    <span><strong>{agent.label}</strong><small>{agent.remote ? "远程" : "本地"}</small></span>
                  </label>
                ))}
              </div>
            </section>
            <div className="aw-eval-setting-grid">
              <section className="aw-eval-block">
                <div className="aw-card-head"><strong>评测资源</strong></div>
                <div className="aw-eval-fields">
                  <label><span>评测集</span><select value={group.caseSet} onChange={(event) => onChange({ ...group, caseSet: event.currentTarget.value })}><option>核心回归集</option><option>安全边界集</option><option>工具调用集</option></select><small>{cases.length} 条案例</small></label>
                  <label><span>评估器</span><select value={group.evaluator} onChange={(event) => onChange({ ...group, evaluator: event.currentTarget.value })}><option>综合质量评估器</option><option>事实一致性评估器</option><option>工具调用评估器</option></select></label>
                  <label><span>并发数</span><select value={group.concurrency} onChange={(event) => onChange({ ...group, concurrency: event.currentTarget.value })}><option value="2">2</option><option value="4">4</option><option value="8">8</option></select></label>
                </div>
              </section>
              <section className="aw-eval-block">
                <div className="aw-card-head"><strong>评测指标</strong><span>已选择 {group.metrics.length} 项</span></div>
                <div className="aw-metric-list">
                  {metrics.map((metric) => (
                    <label key={metric}><input type="checkbox" checked={group.metrics.includes(metric)} onChange={() => toggleMetric(metric)} /><span>{metric}</span></label>
                  ))}
                </div>
              </section>
            </div>
          </div>
        ) : (
          <section className="aw-eval-history">
            <div className="aw-section-head"><div><h3>历史结果</h3><p>查看该评测组历次运行的总体表现。</p></div></div>
            {group.history.length === 0 ? (
              <div className="aw-results-empty"><strong>暂无历史结果</strong><span>完成首次评测后，结果会出现在这里。</span></div>
            ) : (
              <div className="aw-history-list">
                {group.history.map((run, index) => (
                  <button type="button" key={run.id}>
                    <span><strong>评测运行 #{group.history.length - index}</strong><small>{run.createdAt} · {selectedAgents.length} 个智能体</small></span>
                    <span className="aw-history-score"><strong>{run.score}</strong><small>综合得分</small></span>
                    <span className="aw-complete"><Check />已完成</span>
                    <ArrowRight aria-hidden />
                  </button>
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
