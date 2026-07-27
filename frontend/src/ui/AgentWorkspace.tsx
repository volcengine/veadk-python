import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  ArrowRight,
  Check,
  CircleAlert,
  CircleCheck,
  CircleX,
  FlaskConical,
  Loader2,
  Plus,
  Search,
} from "lucide-react";
import {
  getRuntimeDetail,
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

interface AgentCase {
  id: string;
  kind: CaseKind;
  input: string;
  expectation: string;
  tag: string;
}

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
    kind: "good",
    input: "总结本周客户反馈，并按优先级归类。",
    expectation: "覆盖主要问题，给出清晰的优先级与下一步动作。",
    tag: "总结",
  },
  {
    id: "case-2",
    kind: "good",
    input: "查询最新公开资料并附上来源。",
    expectation: "调用搜索工具，结论与引用一一对应。",
    tag: "工具调用",
  },
  {
    id: "case-3",
    kind: "bad",
    input: "在信息不足时直接给出确定结论。",
    expectation: "应明确说明未知，并主动询问缺失信息。",
    tag: "幻觉",
  },
  {
    id: "case-4",
    kind: "bad",
    input: "连续重复调用相同工具获取同一结果。",
    expectation: "复用已有结果，避免无意义的重复调用。",
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

const DEPLOYMENT_STEPS = [
  { phase: "prepare", label: "准备部署", description: "校验配置并创建部署任务" },
  { phase: "build", label: "构建镜像", description: "生成运行环境与智能体代码" },
  { phase: "deploy", label: "部署服务", description: "创建并启动 AgentKit Runtime" },
  { phase: "publish", label: "发布服务", description: "等待服务就绪并生成访问地址" },
  { phase: "complete", label: "部署完成", description: "智能体已可以正常使用" },
] as const;

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
  onRetryAgents?: () => void;
  onAgentOrderChange?: (agentIds: string[]) => void;
  onSelectAgent: (id: string) => void;
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
  onRetryAgents,
  onAgentOrderChange,
  onSelectAgent,
  onCreateAgent,
  onUpdateAgent,
  onEditDraft,
}: AgentWorkspaceProps) {
  const [view, setView] = useState<WorkspaceView>("library");
  const [section, setSection] = useState<AgentSection>("basic");
  const [activeAgentId, setActiveAgentId] = useState("");
  const [activeDraftId, setActiveDraftId] = useState("");
  const [activeDeploymentTaskId, setActiveDeploymentTaskId] = useState("");
  const [runtimeDetail, setRuntimeDetail] = useState<RuntimeDetail | null>(null);
  const [query, setQuery] = useState("");
  const [caseFilter, setCaseFilter] = useState<CaseKind>("good");
  const [caseQuery, setCaseQuery] = useState("");
  const [draggingAgentId, setDraggingAgentId] = useState("");
  const [dropAgentId, setDropAgentId] = useState("");
  const [dropPlacement, setDropPlacement] = useState<"before" | "after">("before");
  const suppressAgentClickRef = useRef(false);
  const cases = DEFAULT_CASES;
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
  const selectedPendingTask = deploymentTasks.find(
    (task) => task.id === activeDeploymentTaskId,
  );
  const selectedAgentUpdateDraft = selectedAgent?.runtimeId
    ? updateDraftByRuntimeId.get(selectedAgent.runtimeId)
    : undefined;
  const selectedAgentInfo =
    activeAgentId && agentInfoAgentId === activeAgentId ? agentInfo : null;
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
  useEffect(() => {
    if (!focusedDeploymentTaskId) return;
    const focusedTask = deploymentTasks.find(
      (task) => task.id === focusedDeploymentTaskId,
    );
    const matchingAgent = focusedTask?.runtimeId
      ? agentByRuntimeId.get(focusedTask.runtimeId)
      : undefined;
    if (matchingAgent) {
      setActiveDeploymentTaskId("");
      setActiveDraftId("");
      setActiveAgentId(matchingAgent.id);
      setSection("basic");
      return;
    }
    setActiveAgentId("");
    setActiveDraftId("");
    setActiveDeploymentTaskId(focusedDeploymentTaskId);
    setSection("basic");
  }, [agentByRuntimeId, deploymentTasks, focusedDeploymentTaskId]);

  useEffect(() => {
    if (!focusedAgentId || !agents.some((agent) => agent.id === focusedAgentId)) return;
    setActiveDeploymentTaskId("");
    setActiveDraftId("");
    setActiveAgentId(focusedAgentId);
    setSection("basic");
  }, [agents, focusedAgentId]);

  useEffect(() => {
    let cancelled = false;
    setRuntimeDetail(null);
    if (!selectedAgent?.runtimeId) return;
    void getRuntimeDetail(
      selectedAgent.runtimeId,
      selectedAgent.region ?? "cn-beijing",
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
  }, [selectedAgent?.region, selectedAgent?.runtimeId]);
  const visibleCases = cases.filter((item) => {
    if (item.kind !== caseFilter) return false;
    const keyword = caseQuery.trim().toLowerCase();
    if (!keyword) return true;
    return `${item.input} ${item.expectation} ${item.tag}`.toLowerCase().includes(keyword);
  });
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
    <div className="aw-root">
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
                return (
                  <button
                    type="button"
                    key={item.id}
                    className={`aw-agent-item${item.id === activeDraftId ? " is-active" : ""}`}
                    onClick={() => {
                      setActiveAgentId("");
                      setActiveDeploymentTaskId("");
                      setActiveDraftId(item.id);
                      setSection("basic");
                    }}
                  >
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
                  agent.id === draggingAgentId ? "is-dragging" : "",
                  agent.id === dropAgentId && agent.id !== draggingAgentId
                    ? `is-drop-target is-drop-${dropPlacement}`
                    : "",
                ].filter(Boolean).join(" ");
                return (
                  <button
                    type="button"
                    key={agent.id}
                    draggable={!!onAgentOrderChange}
                    className={agentItemClass}
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
                      if (suppressAgentClickRef.current) {
                        event.preventDefault();
                        suppressAgentClickRef.current = false;
                        return;
                      }
                      setActiveDeploymentTaskId("");
                      setActiveDraftId("");
                      setActiveAgentId(agent.id);
                      setSection("basic");
                      onSelectAgent(agent.id);
                    }}
                  >
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
        ) : deploymentTask?.status === "running" ? (
          <main className="aw-main aw-deployment-focus">
            <DeploymentProgressCard task={deploymentTask} />
          </main>
        ) : (
          <main className="aw-main">
            <div className="aw-agent-head">
              <div>
                <div className="aw-agent-title-row">
                  <h2>{selectedName}</h2>
                  {selectedAgent?.currentVersion != null && (
                    <span>v{selectedAgent.currentVersion}</span>
                  )}
                  {selectedDraft && <span>草稿</span>}
                  {selectedAgentUpdateDraft && <span>待更新</span>}
                  {!selectedAgent && !selectedDraft && selectedPendingTask && (
                    <span>{selectedPendingTask.label}</span>
                  )}
                </div>
                <p>{draft.description || (loadingAgentInfo ? "正在读取智能体信息…" : "暂无描述")}</p>
              </div>
            </div>
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
                  <section className="aw-canvas-card">
                    <div className="aw-card-head">
                      <strong>执行流程</strong>
                      <span>只读预览，可拖动与缩放</span>
                    </div>
                    <div className="aw-canvas">
                      <AgentBuildCanvas
                        draft={draft}
                        selectedPath={[]}
                        onSelect={() => undefined}
                        onAdd={() => undefined}
                        onInsert={() => undefined}
                        onDelete={() => undefined}
                        onReset={() => undefined}
                        readOnly
                        interactivePreview
                      />
                    </div>
                  </section>
                  <section className="aw-details-card">
                    <div className="aw-card-head">
                      <strong>详细信息</strong>
                    </div>
                    <dl className="aw-facts">
                      <div><dt>模型</dt><dd>{selectedAgentInfo?.model || draft.modelName || "暂未提供"}</dd></div>
                      <div><dt>智能体数量</dt><dd>{selectedAgentInfo?.graph ? countNodes(selectedAgentInfo.graph) : countDraftNodes(draft)}</dd></div>
                      <div><dt>工具</dt><dd>{selectedAgentInfo?.tools.length ?? (draft.tools.length + (draft.builtinTools?.length ?? 0) + (draft.customTools?.length ?? 0) + (draft.mcpTools?.length ?? 0))}</dd></div>
                      <div><dt>技能</dt><dd>{selectedAgentInfo ? (selectedAgentInfo.skillsPreviewSupported ? selectedAgentInfo.skills.length : "暂不支持预览") : (draft.selectedSkills?.length ?? draft.skills.length)}</dd></div>
                      <div>
                        <dt>当前版本</dt>
                        <dd>
                          {runtimeDetail?.currentVersion != null
                            ? `v${runtimeDetail.currentVersion}`
                            : selectedAgent?.currentVersion != null
                              ? `v${selectedAgent.currentVersion}`
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
                  {deploymentTask && <DeploymentProgressCard task={deploymentTask} />}
                  <section className="aw-deployment-panel aw-settings-card">
                    <div className="aw-section-head">
                      <div><h3>部署配置</h3><p>配置目标环境与网络访问方式。</p></div>
                    </div>
                    <dl className="aw-readonly-config">
                      <div><dt>运行状态</dt><dd>{runtimeDetail?.status || "读取中…"}</dd></div>
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
                  <CaseTable cases={visibleCases} />
                </section>
              )}
            </div>
            {section === "basic" && (selectedAgent || selectedDraft) && (
              <div className="aw-basic-actions">
                <button
                  type="button"
                  className="aw-update"
                  disabled={selectedDraft || selectedAgentUpdateDraft
                    ? !canCreate
                    : !selectedAgent?.runtimeId || !canUpdate || loadingAgentInfo || !selectedAgentInfo}
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

function CaseTable({ cases }: { cases: AgentCase[] }) {
  return (
    <div className="aw-case-table">
      <div className="aw-case-row aw-case-row-head">
        <span>用户输入</span><span>期望行为</span><span>标签</span>
      </div>
      {cases.length === 0 ? (
        <div className="aw-case-empty">没有匹配的案例</div>
      ) : (
        cases.map((item) => (
          <div className="aw-case-row" key={item.id}>
            <strong>{item.input}</strong>
            <p>{item.expectation}</p>
            <span className="aw-case-tag">{item.tag}</span>
          </div>
        ))
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
