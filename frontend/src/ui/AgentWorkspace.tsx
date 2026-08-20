import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";
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
  getCachedAgentFeedbackCases,
  getCachedRuntimeAgentInfo,
  getCachedRuntimeDetail,
  getAgentUsage,
  getAgentFeedbackCases,
  getAgentOptimizations,
  getRuntimeAgentInfo,
  getRuntimeDetail,
  getRuntimeUpdateCapability,
  probeRuntimeA2a,
  probeRuntimeApps,
  prefetchRuntimeAgentInfo,
  prefetchRuntimeDetail,
  revealRuntimeApiKey,
  type AgentFeedbackCasesResponse,
  type AgentFeedbackCase,
  type AgentFeedbackSource,
  type AgentFeedbackSetSummary,
  type AgentInfo,
  type AgentNode,
  type AgentOptimizationGroup,
  type AgentOptimizationModule,
  type AgentOptimizationPriority,
  type AgentUsageResponse,
  type RuntimeA2aIntegration,
  RuntimeProbeError,
  type RuntimeDetail,
  type RuntimeUpdateCapability,
} from "../adk/client";
import type { AgentEntry } from "../adk/connections";
import { AgentBuildCanvas } from "../create/AgentBuildCanvas";
import {
  modelNameFromRuntime,
  runtimeAgentDraftFromCloud,
} from "../create/runtimeModelName";
import {
  HARNESS_SIDECAR_OPTION_IDS,
  harnessIntentFromRuntimeEnvs,
  harnessSidecarOptionLabel,
  harnessSidecarProfileLabel,
} from "../create/harnessSidecarOptions";
import type { AgentDraft } from "../create/types";
import type { WorkspaceAgentDraft } from "../create/agentDraftStorage";
import { BUILTIN_TOOLS } from "../create/veadkCatalog";
import type { DeploymentTaskUpdate } from "./ProjectPreview";
import { Markdown } from "./Markdown";
import { PageBackButton } from "./PageBackButton";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./AgentWorkspace.css";

type WorkspaceView = "library" | "evaluation";
type AgentSection = "basic" | "usage" | "evaluations" | "optimizations" | "integrations";
type IntegrationProtocol = "api-server" | "a2a";
type EvaluationSection = "config" | "history";
type CaseKind = "good" | "bad";
type OptimizationPriority = AgentOptimizationPriority;
type OptimizationModule = AgentOptimizationModule;

type AgentCase = AgentFeedbackCase & { tag?: string };
type OptimizationGroup = AgentOptimizationGroup;
type DeleteConfirmTarget =
  | {
      kind: "selection";
      title: string;
      description: string;
      confirmLabel: string;
      agents: AgentEntry[];
      drafts: WorkspaceAgentDraft[];
    }
  | {
      kind: "agent";
      title: string;
      description: string;
      confirmLabel: string;
      agent: AgentEntry;
    }
  | {
      kind: "draft";
      title: string;
      description: string;
      confirmLabel: string;
      draft: WorkspaceAgentDraft;
    };

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
    createdAt: "2026-08-05T09:12:00+08:00",
    evaluationSetId: "",
    evaluationSetName: "示例 good case",
    workspaceId: "",
    tag: "总结",
    source: "auto",
    score: 0.92,
    reason: "任务完整覆盖了用户目标，输出结构清晰，并给出了可执行的下一步动作。",
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
    createdAt: "2026-08-05T08:47:00+08:00",
    evaluationSetId: "",
    evaluationSetName: "示例 good case",
    workspaceId: "",
    tag: "工具调用",
    source: "user",
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
    createdAt: "2026-08-05T07:35:00+08:00",
    evaluationSetId: "",
    evaluationSetName: "示例 bad case",
    workspaceId: "",
    tag: "幻觉",
    source: "auto",
    score: 0.28,
    reason: "信息不足时仍给出了确定结论，缺少必要的澄清步骤与不确定性说明。",
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
    createdAt: "2026-08-05T06:58:00+08:00",
    evaluationSetId: "",
    evaluationSetName: "示例 bad case",
    workspaceId: "",
    tag: "效率",
    source: "user",
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
  { id: "usage", label: "用量统计" },
  { id: "evaluations", label: "评测集" },
  { id: "optimizations", label: "优化项" },
  { id: "integrations", label: "接入方法" },
];

const AGENT_USAGE_PAGE_SIZE = 20;
const AGENT_USAGE_DATE_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatAgentUsageTime(value: string): string {
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp)
    ? "暂未提供"
    : AGENT_USAGE_DATE_FORMATTER.format(timestamp);
}

const INTEGRATION_PROTOCOLS: Array<{
  id: IntegrationProtocol;
  label: string;
}> = [
  { id: "api-server", label: "API Server" },
  { id: "a2a", label: "A2A" },
];

interface IntegrationProbeResult {
  requestKey: string;
  apiApps: string[] | null;
  a2a: RuntimeA2aIntegration | null;
}

interface RevealedApiKey {
  requestKey: string;
  value: string;
}

function endpointPath(endpoint: string, path: string): string {
  return endpoint ? `${endpoint.replace(/\/+$/, "")}${path}` : "";
}

function normalizeRuntimeA2aEndpoint(
  endpoint: string,
  runtimeEndpoint: string,
): string {
  const value = endpoint.trim();
  if (!value || !runtimeEndpoint) return value;
  try {
    const agentUrl = new URL(value);
    const hostname = agentUrl.hostname.replace(/^\[|\]$/g, "").toLowerCase();
    if (!["localhost", "127.0.0.1", "::1"].includes(hostname)) return value;
    const publicUrl = new URL(runtimeEndpoint);
    agentUrl.protocol = publicUrl.protocol;
    agentUrl.hostname = publicUrl.hostname;
    agentUrl.port = publicUrl.port;
    return agentUrl.toString();
  } catch {
    return value;
  }
}

function authTypeLabel(authType?: RuntimeDetail["authType"]): string {
  if (authType === "key_auth") return "API Key";
  if (authType === "custom_jwt") return "OAuth / JWT";
  if (authType === "none") return "无需鉴权";
  return "暂无";
}

function pythonString(value: string): string {
  return JSON.stringify(value);
}

function pythonAuthSetup(authType?: RuntimeDetail["authType"]): string {
  if (authType === "key_auth") {
    return `API_KEY = "<API_KEY>"\nHEADERS = {"Authorization": f"Bearer {API_KEY}"}`;
  }
  if (authType === "custom_jwt") {
    return `ACCESS_TOKEN = "<ACCESS_TOKEN>"\nHEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}`;
  }
  if (authType === "none") return "HEADERS = {}";
  return `AUTH_TOKEN = "<AUTH_TOKEN>"\nHEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}`;
}

function apiServerPythonExample(
  endpoint: string,
  appName: string,
  authType?: RuntimeDetail["authType"],
): string {
  const baseUrl = endpoint.replace(/\/+$/, "");
  return `\`\`\`python
import uuid

import requests

BASE_URL = ${pythonString(baseUrl)}
APP_NAME = ${pythonString(appName)}
USER_ID = "demo-user"
SESSION_ID = str(uuid.uuid4())
${pythonAuthSetup(authType)}

session_response = requests.post(
    f"{BASE_URL}/apps/{APP_NAME}/users/{USER_ID}/sessions/{SESSION_ID}",
    headers=HEADERS,
    json={},
    timeout=30,
)
session_response.raise_for_status()

with requests.post(
    f"{BASE_URL}/run_sse",
    headers=HEADERS,
    json={
        "app_name": APP_NAME,
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "new_message": {
            "role": "user",
            "parts": [{"text": "你好，请介绍一下自己"}],
        },
        "streaming": True,
    },
    stream=True,
    timeout=120,
) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if line:
            print(line.decode("utf-8"))
\`\`\``;
}

function a2aPythonExample(
  endpoint: string,
  authType?: RuntimeDetail["authType"],
): string {
  return `\`\`\`python
import uuid

import requests

AGENT_URL = ${pythonString(endpoint)}
${pythonAuthSetup(authType)}

response = requests.post(
    AGENT_URL,
    headers=HEADERS,
    json={
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": "你好，请介绍一下自己"}],
            }
        },
    },
    timeout=120,
)
response.raise_for_status()
print(response.json())
\`\`\``;
}

function SecretVisibilityIcon({ visible }: { visible: boolean }) {
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
      <path d="M2.8 12s3.3-5.4 9.2-5.4 9.2 5.4 9.2 5.4-3.3 5.4-9.2 5.4S2.8 12 2.8 12Z" />
      <circle cx="12" cy="12" r="2.4" />
      {!visible && <path d="m4.2 4.2 15.6 15.6" />}
    </svg>
  );
}

function IntegrationApiKey({
  available,
  authType,
  value,
  visible,
  loading,
  error,
  onToggle,
}: {
  available: boolean;
  authType?: RuntimeDetail["authType"];
  value: string;
  visible: boolean;
  loading: boolean;
  error: string;
  onToggle: () => void;
}) {
  if (!available) return "暂无";
  if (authType === "none") return "无需 API Key";
  if (authType === "custom_jwt") return "使用 OAuth / JWT";
  if (authType !== "key_auth") return "暂无";
  return (
    <span className="aw-integration-secret">
      <span className="aw-integration-secret-value" aria-live="polite">
        {visible && value ? value : "****"}
      </span>
      <button
        type="button"
        className="aw-integration-secret-toggle"
        aria-label={visible ? "隐藏 API Key" : "显示 API Key"}
        title={visible ? "隐藏 API Key" : "显示 API Key"}
        disabled={loading}
        onClick={onToggle}
      >
        {loading ? (
          <span className="loading-gap-spinner" aria-hidden="true" />
        ) : (
          <SecretVisibilityIcon visible={visible} />
        )}
      </button>
      {error && <span className="aw-integration-secret-error" role="alert">{error}</span>}
    </span>
  );
}

function IntegrationPanel({
  protocol,
  title,
  available,
  fields,
  example,
}: {
  protocol: IntegrationProtocol;
  title: string;
  available: boolean;
  fields: Array<{ label: string; value: ReactNode }>;
  example: string;
}) {
  return (
    <section
      className={`aw-integration-panel${available && example ? " has-example" : ""}`}
      id={`integration-${protocol}-panel`}
      role="tabpanel"
      aria-labelledby={`integration-${protocol}-tab`}
    >
      <header>
        <h3>{title}</h3>
      </header>
      <dl>
        {fields.map((field) => (
          <div key={field.label}>
            <dt>{field.label}</dt>
            <dd>{field.value || "暂无"}</dd>
          </div>
        ))}
      </dl>
      {available && example && (
        <section className="aw-integration-example">
          <h4>Python 示例</h4>
          <Markdown
            text={example}
            className="aw-integration-example-code"
            allowRawHtml={false}
          />
        </section>
      )}
    </section>
  );
}

function infoToDraft(
  info: AgentInfo | null,
  fallbackName: string,
  cloudProvider: "volcengine" | "byteplus",
): AgentDraft {
  return runtimeAgentDraftFromCloud(
    {
      appName: info?.appName?.trim() || fallbackName,
      name: info?.name,
      description: info?.description,
      type: info?.type,
      model: info?.model,
      tools: info?.tools,
      skills: info?.skills,
      graph: info?.graph,
      draft: info?.draft,
    },
    cloudProvider,
  );
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

function formatCaseScore(item: AgentCase): string {
  if (typeof item.score !== "number") return "—";
  if (!Number.isFinite(item.score)) return "—";
  return `${Math.round(item.score * 100)} 分`;
}

function optimizationPriorityLabel(priority: OptimizationPriority): string {
  if (priority === "high") return "高";
  if (priority === "medium") return "中";
  return "低";
}

const OPTIMIZATION_MODULE_LABELS: Record<OptimizationModule, string> = {
  agent_structure: "Agent 结构",
  prompt: "提示词",
  tool: "工具",
  knowledge: "知识库",
  memory: "记忆",
  workflow: "工作流",
  other: "其他",
};

function optimizationModuleLabel(group: OptimizationGroup): string {
  if (group.module === "other") return group.customModule?.trim() || "其他";
  return OPTIMIZATION_MODULE_LABELS[group.module];
}

function feedbackSetFor(
  sets: AgentFeedbackSetSummary[],
  kind: CaseKind,
): AgentFeedbackSetSummary | undefined {
  return sets.find((set) => set.kind === kind);
}

function feedbackCasesFromResponse(
  response: AgentFeedbackCasesResponse,
): AgentCase[] {
  return response.items
    .map((item) => ({
      ...item,
      tag: item.kind === "good" ? "Good case" : "Bad case",
    }))
    .sort((left, right) => (
      caseTimeValue(right.createdAt) - caseTimeValue(left.createdAt)
    ));
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
const EVALUATION_SET_STEP = {
  phase: "evaluation",
  label: "创建评测集",
  description: "自动创建 Good Case 和 Bad Case 评测集",
} as const;
function instanceUpdateStep(range: { min: number; max: number }) {
  return {
    phase: "update",
    label: "更新实例配置",
    description: `将 Runtime 实例数调整为 ${range.min}～${range.max}`,
  } as const;
}
const BUILD_STEP_INDEX = DEPLOYMENT_STEPS.findIndex((step) => step.phase === "build");

function deploymentSteps(task: DeploymentTaskUpdate) {
  const steps = task.instanceRange
    ? [
        ...DEPLOYMENT_STEPS.slice(0, -1),
        instanceUpdateStep(task.instanceRange),
        DEPLOYMENT_STEPS[DEPLOYMENT_STEPS.length - 1],
      ]
    : DEPLOYMENT_STEPS;
  return task.createEvaluationSets
    ? [
        ...steps.slice(0, -1),
        EVALUATION_SET_STEP,
        steps[steps.length - 1],
      ]
    : steps;
}

function deploymentStepIndex(task: DeploymentTaskUpdate): number {
  const steps = deploymentSteps(task);
  if (task.status === "success") return steps.length - 1;
  const phase = task.phase ?? ({
    准备部署: "prepare",
    构建镜像: "build",
    部署: "deploy",
    发布: "publish",
    创建评测集: "evaluation",
    部署完成: "complete",
  } as Record<string, string>)[task.label];
  const index = steps.findIndex((step) => step.phase === phase);
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

function DeploymentProgressCard({
  task,
  onReturnToEdit,
}: {
  task: DeploymentTaskUpdate;
  onReturnToEdit?: () => void;
}) {
  const steps = deploymentSteps(task);
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
        {steps.map((step, index) => {
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
      {(task.status === "error" || task.status === "cancelled") && onReturnToEdit && (
        <div className="aw-deploy-progress-actions">
          <button
            type="button"
            className="studio-update-action"
            onClick={onReturnToEdit}
          >返回编辑</button>
        </div>
      )}
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
  canViewUsage?: boolean;
  loadingAgents?: boolean;
  agentsError?: string;
  deploymentTasks?: DeploymentTaskUpdate[];
  focusedDeploymentTaskId?: string;
  focusedAgentId?: string;
  focusedAgentSection?: AgentSection;
  focusedCaseKind?: CaseKind;
  feedbackCasePreview?: AgentFeedbackCase | null;
  detailOnly?: boolean;
  onBack?: () => void;
  onRetryAgents?: () => void;
  onAgentOrderChange?: (agentIds: string[]) => void;
  onDeleteAgents?: (agents: AgentEntry[]) => Promise<void>;
  onDeleteDrafts?: (drafts: WorkspaceAgentDraft[]) => void;
  onSelectAgent: (id: string) => void;
  onTalkAgent?: (agent: AgentEntry) => void;
  onOpenFeedbackCase?: (item: AgentFeedbackCase) => void | Promise<void>;
  onFeedbackCasesDeleted?: (items: AgentFeedbackCase[]) => void;
  onCreateAgent: () => void;
  onUpdateAgent: (capability: RuntimeUpdateCapability) => void;
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
  canViewUsage = false,
  loadingAgents = false,
  agentsError = "",
  deploymentTasks = [],
  focusedDeploymentTaskId = "",
  focusedAgentId = "",
  focusedAgentSection = "basic",
  focusedCaseKind = "good",
  feedbackCasePreview = null,
  detailOnly = false,
  onBack,
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
  const [integrationProbe, setIntegrationProbe] =
    useState<IntegrationProbeResult | null>(null);
  const [integrationLoading, setIntegrationLoading] = useState(false);
  const [integrationError, setIntegrationError] = useState("");
  const [integrationReloadToken, setIntegrationReloadToken] = useState(0);
  const [integrationProtocol, setIntegrationProtocol] =
    useState<IntegrationProtocol>("api-server");
  const [revealedApiKey, setRevealedApiKey] =
    useState<RevealedApiKey | null>(null);
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [apiKeyLoading, setApiKeyLoading] = useState(false);
  const [apiKeyError, setApiKeyError] = useState("");
  const [updateCapability, setUpdateCapability] = useState<{
    requestKey: string;
    value: RuntimeUpdateCapability;
  } | null>(null);
  const [updateCapabilityLoading, setUpdateCapabilityLoading] = useState(false);
  const [updateCapabilityError, setUpdateCapabilityError] = useState("");
  const [detailAgentInfo, setDetailAgentInfo] = useState<AgentInfo | null>(null);
  const [detailAgentInfoResolved, setDetailAgentInfoResolved] = useState(false);
  const [query, setQuery] = useState("");
  const [caseFilter, setCaseFilter] = useState<CaseKind>("good");
  const [caseQuery, setCaseQuery] = useState("");
  const [caseSourceFilter, setCaseSourceFilter] =
    useState<AgentFeedbackSource>("auto");
  const [draggingAgentId, setDraggingAgentId] = useState("");
  const [dropAgentId, setDropAgentId] = useState("");
  const [dropPlacement, setDropPlacement] = useState<"before" | "after">("before");
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<string>>(() => new Set());
  const [selectedDraftIds, setSelectedDraftIds] = useState<Set<string>>(() => new Set());
  const [deletingAgents, setDeletingAgents] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleteConfirmTarget, setDeleteConfirmTarget] =
    useState<DeleteConfirmTarget | null>(null);
  const [feedbackCases, setFeedbackCases] = useState<AgentCase[]>([]);
  const [feedbackSets, setFeedbackSets] = useState<AgentFeedbackSetSummary[]>([]);
  const [feedbackCasesLoading, setFeedbackCasesLoading] = useState(false);
  const [feedbackCasesError, setFeedbackCasesError] = useState("");
  const [feedbackCasesUnsupported, setFeedbackCasesUnsupported] = useState("");
  const [feedbackReloadToken, setFeedbackReloadToken] = useState(0);
  const [optimizationGroups, setOptimizationGroups] = useState<OptimizationGroup[]>([]);
  const [optimizationsLoading, setOptimizationsLoading] = useState(false);
  const [optimizationsError, setOptimizationsError] = useState("");
  const [optimizationsReloadToken, setOptimizationsReloadToken] = useState(0);
  const [agentUsage, setAgentUsage] = useState<{
    requestKey: string;
    value: AgentUsageResponse;
  } | null>(null);
  const [agentUsagePage, setAgentUsagePage] = useState(1);
  const [agentUsageLoading, setAgentUsageLoading] = useState(false);
  const [agentUsageError, setAgentUsageError] = useState("");
  const [agentUsageReloadToken, setAgentUsageReloadToken] = useState(0);
  const [caseSelectionMode, setCaseSelectionMode] = useState(false);
  const [selectedCaseIds, setSelectedCaseIds] = useState<Set<string>>(() => new Set());
  const [deletingCases, setDeletingCases] = useState(false);
  const [caseDeleteError, setCaseDeleteError] = useState("");
  const [focusedCaseId, setFocusedCaseId] = useState("");
  const [expandedCaseIds, setExpandedCaseIds] = useState<Set<string>>(() => new Set());
  const suppressAgentClickRef = useRef(false);
  const appliedFocusKeyRef = useRef("");
  const caseTableRef = useRef<HTMLDivElement | null>(null);
  const updateCapabilityRequestRef = useRef(0);
  const apiKeyRequestRef = useRef(0);
  const agentUsageRequestRef = useRef(0);
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
  const selectedAgentAppName =
    selectedAgentInfo?.appName || selectedAgent?.runtimeApp || selectedAgent?.app || "";
  const visibleAgentSections = canViewUsage && selectedAgent?.runtimeId
    ? AGENT_SECTIONS
    : AGENT_SECTIONS.filter((item) => item.id !== "usage");
  const agentUsageRequestKey = JSON.stringify([
    selectedAgent?.runtimeId ?? "",
    selectedAgent?.region ?? "cn-beijing",
    selectedAgentAppName,
    agentUsagePage,
  ]);
  const selectedAgentUsage = agentUsage?.requestKey === agentUsageRequestKey
    ? agentUsage.value
    : null;
  const integrationRequestKey = `${selectedAgent?.region ?? "cn-beijing"}:${selectedAgent?.runtimeId ?? ""}`;
  const selectedRevealedApiKey =
    revealedApiKey?.requestKey === integrationRequestKey
      ? revealedApiKey.value
      : "";
  const selectedIntegrationProbe =
    integrationProbe?.requestKey === integrationRequestKey
      ? integrationProbe
      : null;
  const apiIntegrationAvailable = Boolean(selectedIntegrationProbe?.apiApps?.length);
  const a2aIntegrationAvailable = Boolean(selectedIntegrationProbe?.a2a);
  const apiIntegrationAppName =
    selectedIntegrationProbe?.apiApps?.[0] ?? selectedAgentAppName;
  const runtimeEndpoint = runtimeDetail?.endpoint ?? "";
  const a2aEndpoint = normalizeRuntimeA2aEndpoint(
    selectedIntegrationProbe?.a2a?.endpoint ?? "",
    runtimeEndpoint,
  );
  const updateCapabilityRequestKey = JSON.stringify([
    selectedAgent?.runtimeId ?? "",
    selectedAgent?.region ?? "",
    selectedAgentAppName,
  ]);
  const selectedUpdateCapability =
    updateCapability?.requestKey === updateCapabilityRequestKey
      ? updateCapability.value
      : null;
  useEffect(() => {
    const requestId = updateCapabilityRequestRef.current + 1;
    updateCapabilityRequestRef.current = requestId;
    setUpdateCapability(null);
    setUpdateCapabilityError("");

    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "";
    if (!canUpdate || !runtimeId || !region) {
      setUpdateCapabilityLoading(false);
      return;
    }

    const controller = new AbortController();
    setUpdateCapabilityLoading(true);
    void getRuntimeUpdateCapability({
      runtimeId,
      region,
      appName: selectedAgentAppName,
      signal: controller.signal,
    }).then((value) => {
      if (requestId !== updateCapabilityRequestRef.current) return;
      if (
        value.runtime.runtimeId !== runtimeId ||
        value.runtime.region !== region ||
        (selectedAgentAppName &&
          value.agent?.appName !== selectedAgentAppName) ||
        (value.canUpdate && !value.agent?.appName)
      ) {
        setUpdateCapabilityError("Runtime 更新能力响应与当前选择不匹配。");
        return;
      }
      setUpdateCapability({ requestKey: updateCapabilityRequestKey, value });
    }).catch((error: unknown) => {
      if (
        requestId !== updateCapabilityRequestRef.current ||
        controller.signal.aborted
      ) return;
      setUpdateCapabilityError(
        error instanceof Error ? error.message : "检查 Runtime 更新能力失败。",
      );
    }).finally(() => {
      if (
        requestId === updateCapabilityRequestRef.current &&
        !controller.signal.aborted
      ) {
        setUpdateCapabilityLoading(false);
      }
    });
    return () => controller.abort();
  }, [
    canUpdate,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
    selectedAgentAppName,
    updateCapabilityRequestKey,
  ]);
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
    selectedPendingTask?.agentName ||
    selectedPendingTask?.agentDraft?.name ||
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
  const draft = useMemo(() => {
    if (selectedPendingTask?.agentDraft) return selectedPendingTask.agentDraft;
    if (selectedDraft?.draft) return selectedDraft.draft;
    const cloudProvider = selectedAgent?.region?.startsWith("ap-")
      ? "byteplus"
      : "volcengine";
    if (selectedUpdateCapability?.agent) {
      return runtimeAgentDraftFromCloud(
        selectedUpdateCapability.agent,
        cloudProvider,
      );
    }
    return infoToDraft(
      selectedAgentInfo,
      selectedAgentAppName || selectedAgent?.label || "agent",
      cloudProvider,
    );
  },
    [
      selectedAgentInfo,
      selectedAgentAppName,
      selectedAgent?.label,
      selectedAgent?.region,
      selectedDraft?.draft,
      selectedPendingTask?.agentDraft,
      selectedUpdateCapability?.agent,
    ],
  );
  const publishedHarnessSidecar =
    selectedAgentInfo?.draft?.harnessSidecar ??
    harnessIntentFromRuntimeEnvs(runtimeDetail?.envs);
  const publishedHarnessOptimizations = publishedHarnessSidecar
    ? HARNESS_SIDECAR_OPTION_IDS.filter(
        (id) => publishedHarnessSidecar.componentOverrides[id],
      )
    : [];
  const updateBlockedReason = selectedDraft
    ? canCreate ? "" : "当前账号没有新建 Agent 的权限。"
    : !canUpdate
      ? "当前账号没有管理 Agent 的权限。"
      : !selectedAgent?.runtimeId
        ? "仅支持更新已部署的云端智能体。"
        : !selectedAgent.region
          ? "Runtime 缺少地域信息，无法更新。"
          : updateCapabilityLoading
            ? "正在检查 Runtime 更新能力…"
            : updateCapabilityError
              ? updateCapabilityError
              : !selectedUpdateCapability
                ? "尚未完成 Runtime 更新能力检查。"
                : !selectedUpdateCapability.canUpdate
                  ? selectedUpdateCapability.reason || "当前 Runtime 不支持原地更新。"
                  : selectedUpdateCapability.agent?.appName
                    ? ""
                    : "Runtime 更新能力响应缺少智能体信息。";
  const updateReasonId = "aw-update-disabled-reason";
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
            task.agentName === selectedDraft.draft.name ||
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
          task.agentName === selectedAgent.label,
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
  const deploymentInProgress = deploymentTask?.status === "running";
  const deploymentDraft = deploymentTask?.draftId
    ? drafts.find((item) => item.id === deploymentTask.draftId) ??
      (deploymentTask.agentDraft
        ? {
            id: deploymentTask.draftId,
            draft: deploymentTask.agentDraft,
            updatedAt: deploymentTask.startedAt,
          }
        : undefined)
    : undefined;
  const draftFlowKey = useMemo(() => canvasDraftKey(draft), [draft]);
  const displayCurrentVersion =
    selectedAgent?.currentVersion ?? runtimeDetail?.currentVersion ?? null;
  const runtimeVersionKey =
    displayCurrentVersion ?? selectedPendingTask?.startedAt ?? "unknown";
  const executionFlowKey = selectedAgentInfo
    ? `runtime:${selectedAgent?.runtimeId ?? selectedAgentInfo.name}:v${runtimeVersionKey}:${draftFlowKey}`
    : `draft:${selectedPendingTask?.id ?? selectedDraft?.id ?? selectedAgent?.id ?? selectedName}:${draftFlowKey}`;
  useEffect(() => {
    if (section === "usage" && !canViewUsage) setSection("basic");
  }, [canViewUsage, section]);

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
    const focusKey = `${focusedAgentId}:${focusedAgentSection}:${focusedCaseKind}:${canViewUsage}`;
    if (appliedFocusKeyRef.current === focusKey) return;
    if (!agents.some((agent) => agent.id === focusedAgentId)) return;
    appliedFocusKeyRef.current = focusKey;
    setActiveDraftId("");
    setActiveAgentId(focusedAgentId);
    setSection(focusedAgentSection === "usage" && !canViewUsage ? "basic" : focusedAgentSection);
    if (focusedAgentSection === "evaluations") {
      setCaseFilter(focusedCaseKind);
      setCaseQuery("");
    }
  }, [agents, canViewUsage, focusedAgentId, focusedAgentSection, focusedCaseKind]);

  useEffect(() => {
    for (const agent of listedAgents.slice(0, 8)) {
      if (!agent.runtimeId) continue;
      const region = agent.region ?? "cn-beijing";
      prefetchRuntimeDetail(agent.runtimeId, region);
      prefetchRuntimeAgentInfo(agent.runtimeId, region, agent.runtimeApp ?? "");
    }
  }, [listedAgents]);

  useEffect(() => {
    let cancelled = false;
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    const knownApp = selectedAgent?.runtimeApp ?? "";
    const cached = runtimeId
      ? getCachedRuntimeAgentInfo(runtimeId, region, knownApp)
      : null;
    setDetailAgentInfo(cached);
    setDetailAgentInfoResolved(Boolean(cached) || !detailOnly || !runtimeId);
    if (!detailOnly || !runtimeId) return;
    void getRuntimeAgentInfo(
      runtimeId,
      region,
      knownApp,
      { force: true },
    )
      .then((info) => {
        if (!cancelled) setDetailAgentInfo(info);
      })
      .catch(() => {
        if (!cancelled && !cached) setDetailAgentInfo(null);
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
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    setOptimizationGroups([]);
    setOptimizationsError("");
    if (section !== "optimizations" || !runtimeId) {
      setOptimizationsLoading(false);
      return;
    }
    if (detailOnly && !selectedAgentAppName) {
      setOptimizationsLoading(!detailAgentInfoResolved);
      return;
    }
    setOptimizationsLoading(true);
    void getAgentOptimizations({
      runtimeId,
      region,
      appName: selectedAgentAppName,
    })
      .then((response) => {
        if (!cancelled) setOptimizationGroups(response.groups);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setOptimizationsError(
            cause instanceof Error ? cause.message : String(cause),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setOptimizationsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    detailAgentInfoResolved,
    detailOnly,
    optimizationsReloadToken,
    section,
    selectedAgentAppName,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
  ]);

  useEffect(() => {
    setAgentUsagePage(1);
  }, [selectedAgent?.runtimeId, selectedAgentAppName]);

  useEffect(() => {
    const requestId = agentUsageRequestRef.current + 1;
    agentUsageRequestRef.current = requestId;
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    const appName = selectedAgentAppName;
    setAgentUsageError("");
    if (section !== "usage" || !runtimeId) {
      setAgentUsageLoading(false);
      return;
    }
    if (!appName) {
      setAgentUsageLoading(detailOnly && !detailAgentInfoResolved);
      return;
    }

    const controller = new AbortController();
    setAgentUsageLoading(true);
    void getAgentUsage({
      runtimeId,
      region,
      appName,
      page: agentUsagePage,
      pageSize: AGENT_USAGE_PAGE_SIZE,
      signal: controller.signal,
    })
      .then((response) => {
        if (requestId !== agentUsageRequestRef.current) return;
        if (
          response.runtimeId !== runtimeId ||
          response.appName !== appName ||
          response.page !== agentUsagePage
        ) {
          setAgentUsageError("用量响应与当前 Agent 不匹配，请重试。");
          return;
        }
        setAgentUsage({ requestKey: agentUsageRequestKey, value: response });
      })
      .catch((cause: unknown) => {
        if (
          requestId !== agentUsageRequestRef.current ||
          controller.signal.aborted
        ) return;
        setAgentUsageError(
          cause instanceof Error ? cause.message : "加载 Agent 用量失败。",
        );
      })
      .finally(() => {
        if (requestId === agentUsageRequestRef.current) {
          setAgentUsageLoading(false);
        }
      });
    return () => {
      controller.abort();
    };
  }, [
    agentUsagePage,
    agentUsageReloadToken,
    agentUsageRequestKey,
    detailAgentInfoResolved,
    detailOnly,
    section,
    selectedAgentAppName,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
  ]);

  useEffect(() => {
    apiKeyRequestRef.current += 1;
    setRevealedApiKey(null);
    setApiKeyVisible(false);
    setApiKeyLoading(false);
    setApiKeyError("");
    setIntegrationProtocol("api-server");
  }, [integrationRequestKey, section]);

  function clearRevealedApiKey() {
    apiKeyRequestRef.current += 1;
    setRevealedApiKey(null);
    setApiKeyVisible(false);
    setApiKeyLoading(false);
    setApiKeyError("");
  }

  function selectIntegrationProtocol(protocol: IntegrationProtocol) {
    if (protocol === integrationProtocol) return;
    clearRevealedApiKey();
    setIntegrationProtocol(protocol);
  }

  async function toggleApiKeyVisibility() {
    if (apiKeyVisible) {
      clearRevealedApiKey();
      return;
    }
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    if (!runtimeId) return;
    const requestId = apiKeyRequestRef.current + 1;
    apiKeyRequestRef.current = requestId;
    setApiKeyLoading(true);
    setApiKeyError("");
    try {
      const value = await revealRuntimeApiKey(runtimeId, region);
      if (requestId !== apiKeyRequestRef.current) return;
      setRevealedApiKey({ requestKey: integrationRequestKey, value });
      setApiKeyVisible(true);
    } catch (error) {
      if (requestId !== apiKeyRequestRef.current) return;
      setRevealedApiKey(null);
      setApiKeyVisible(false);
      setApiKeyError(
        error instanceof Error ? error.message : "读取 Runtime API Key 失败。",
      );
    } finally {
      if (requestId === apiKeyRequestRef.current) setApiKeyLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    const cached = runtimeId
      ? getCachedRuntimeDetail(runtimeId, region)
      : null;
    setRuntimeDetail(cached);
    if (!runtimeId) return;
    void getRuntimeDetail(
      runtimeId,
      region,
      { force: true },
    )
      .then((detail) => {
        if (!cancelled) setRuntimeDetail(detail);
      })
      .catch(() => {
        if (!cancelled && !cached) setRuntimeDetail(null);
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
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    const requestKey = `${region}:${runtimeId}`;
    setIntegrationError("");
    if (section !== "integrations" || !runtimeId) {
      setIntegrationLoading(false);
      if (!runtimeId) setIntegrationProbe(null);
      return;
    }
    setIntegrationLoading(true);
    const apiServerProbe = probeRuntimeApps(runtimeId, region, {
      retryProbe: true,
    }).catch((error: unknown) => {
      if (error instanceof RuntimeProbeError && error.unsupported) return null;
      throw error;
    });
    void Promise.all([
      apiServerProbe,
      probeRuntimeA2a(runtimeId, region, { retryProbe: true }),
    ])
      .then(([apiApps, a2a]) => {
        if (!cancelled) setIntegrationProbe({ requestKey, apiApps, a2a });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setIntegrationProbe(null);
          setIntegrationError(
            error instanceof Error ? error.message : "探测集成方式失败。",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setIntegrationLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    integrationReloadToken,
    section,
    selectedAgent?.currentVersion,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
  ]);

  useEffect(() => {
    let cancelled = false;
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    const cached = runtimeId && selectedAgentAppName
      ? getCachedAgentFeedbackCases({
          runtimeId,
          region,
          appName: selectedAgentAppName,
          pageSize: 100,
        })
      : null;
    setFeedbackCases(cached ? feedbackCasesFromResponse(cached) : []);
    setFeedbackSets(cached?.sets ?? []);
    setFeedbackCasesError("");
    setFeedbackCasesUnsupported(cached?.unsupportedMessage ?? "");
    if (section !== "evaluations" || !runtimeId) {
      setFeedbackCasesLoading(false);
      return;
    }
    if (detailOnly && !selectedAgentAppName) {
      setFeedbackCasesLoading(!detailAgentInfoResolved);
      return;
    }
    setFeedbackCasesLoading(!cached);
    void getAgentFeedbackCases({
      runtimeId,
      region,
      appName: selectedAgentAppName,
      pageSize: 100,
    }, { force: true })
      .then((response) => {
        if (cancelled) return;
        setFeedbackSets(response.sets);
        setFeedbackCases(feedbackCasesFromResponse(response));
        setFeedbackCasesUnsupported(response.unsupportedMessage ?? "");
      })
      .catch((cause) => {
        if (!cancelled) {
          setFeedbackCasesError(cause instanceof Error ? cause.message : String(cause));
          setFeedbackCasesUnsupported("");
        }
      })
      .finally(() => {
        if (!cancelled) setFeedbackCasesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    detailAgentInfoResolved,
    detailOnly,
    feedbackReloadToken,
    section,
    selectedAgentAppName,
    selectedAgentInfo?.appName,
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

  const previewCase = useMemo<AgentCase | null>(() => {
    if (!feedbackCasePreview || !selectedAgent?.runtimeId) return null;
    if (feedbackCasePreview.runtimeId !== selectedAgent.runtimeId) return null;
    if (
      selectedAgentAppName &&
      feedbackCasePreview.agentName &&
      feedbackCasePreview.agentName !== selectedAgentAppName
    ) return null;
    return {
      ...feedbackCasePreview,
      tag: feedbackCasePreview.kind === "good" ? "Good case" : "Bad case",
    };
  }, [feedbackCasePreview, selectedAgent?.runtimeId, selectedAgentAppName]);
  const cases = useMemo(() => {
    if (!selectedAgent?.runtimeId) return DEFAULT_CASES;
    if (!previewCase) return feedbackCases;
    return [
      previewCase,
      ...feedbackCases.filter((item) =>
        item.id !== previewCase.id &&
        (!item.messageId || item.messageId !== previewCase.messageId)
      ),
    ];
  }, [feedbackCases, previewCase, selectedAgent?.runtimeId]);
  const visibleCases = cases.filter((item) => {
    if (item.kind !== caseFilter) return false;
    const source: AgentFeedbackSource = item.source === "auto" ? "auto" : "user";
    if (source !== caseSourceFilter) return false;
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
      !selectedAgentAppName ||
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
        region: selectedAgent.region ?? "cn-beijing",
        appName: selectedAgentAppName,
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

  const deleteSelectedItems = () => {
    if (selectedDeleteCount === 0 || deletingAgents) return;
    const runtimeCount = selectedDeletableAgents.length;
    const draftCount = selectedDeletableDrafts.length;
    setDeleteError("");
    setDeleteConfirmTarget({
      kind: "selection",
      title: runtimeCount === 1 && draftCount === 0
        ? "删除 Agent？"
        : runtimeCount === 0 && draftCount === 1
          ? "删除草稿？"
          : "删除所选项目？",
      description: runtimeCount === 1 && draftCount === 0
        ? `"${selectedDeletableAgents[0].label}" 对应的云端 Runtime 将被永久删除，此操作不可撤销。`
        : runtimeCount === 0 && draftCount === 1
          ? `"${selectedDeletableDrafts[0].draft.name || "未命名 Agent"}" 将从本地草稿中删除。`
          : `将删除选中的 ${selectedDeleteCount} 个项目。${runtimeCount > 0 ? `${runtimeCount} 个云端 Runtime 将被永久删除，此操作不可撤销。` : "草稿删除后无法恢复。"}`,
      confirmLabel: runtimeCount === 0 && draftCount === 1 ? "删除草稿" : "删除所选",
      agents: selectedDeletableAgents,
      drafts: selectedDeletableDrafts,
    });
  };

  const confirmDeleteTarget = async () => {
    if (!deleteConfirmTarget || deletingAgents) return;
    setDeletingAgents(true);
    setDeleteError("");
    try {
      if (deleteConfirmTarget.kind === "selection") {
        const { agents: agentsToDelete, drafts: draftsToDelete } = deleteConfirmTarget;
        if (agentsToDelete.length > 0) {
          if (!onDeleteAgents) throw new Error("当前页面不支持删除已部署 Agent。");
          await onDeleteAgents(agentsToDelete);
        }
        if (draftsToDelete.length > 0) {
          onDeleteDrafts?.(draftsToDelete);
        }
        setSelectedAgentIds(new Set());
        setSelectedDraftIds(new Set());
        setSelectionMode(false);
        if (agentsToDelete.some((agent) => agent.id === activeAgentId)) {
          setActiveAgentId("");
        }
        if (draftsToDelete.some((item) => item.id === activeDraftId)) {
          setActiveDraftId("");
        }
      } else if (deleteConfirmTarget.kind === "agent") {
        if (!onDeleteAgents) throw new Error("当前页面不支持删除已部署 Agent。");
        await onDeleteAgents([deleteConfirmTarget.agent]);
        if (activeAgentId === deleteConfirmTarget.agent.id) setActiveAgentId("");
      } else {
        if (!onDeleteDrafts) throw new Error("当前页面不支持删除草稿。");
        onDeleteDrafts([deleteConfirmTarget.draft]);
        if (activeDraftId === deleteConfirmTarget.draft.id) setActiveDraftId("");
      }
      setDeleteConfirmTarget(null);
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setDeletingAgents(false);
    }
  };

  const deleteSingleAgent = (agent: AgentEntry) => {
    if (!onDeleteAgents || agent.canDelete !== true || deletingAgents) return;
    setDeleteError("");
    setDeleteConfirmTarget({
      kind: "agent",
      title: "删除 Agent？",
      description: `"${agent.label}" 对应的云端 Runtime 将被永久删除，此操作不可撤销。`,
      confirmLabel: "删除 Agent",
      agent,
    });
  };

  const deleteSingleDraft = (draftItem: WorkspaceAgentDraft) => {
    if (!onDeleteDrafts || deletingAgents) return;
    const name = draftItem.draft.name || "未命名 Agent";
    setDeleteError("");
    setDeleteConfirmTarget({
      kind: "draft",
      title: "删除草稿？",
      description: `"${name}" 将从本地草稿中删除。`,
      confirmLabel: "删除草稿",
      draft: draftItem,
    });
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
    <>
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
          ref={(node) => {
            node?.toggleAttribute("inert", view === "evaluation");
          }}
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
                        candidate.agentName === item.draft.name ||
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
          <main className={`aw-main${deploymentInProgress ? " is-deploying" : ""}`}>
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
            {section === "integrations" && integrationLoading && (
              <div className="aw-detail-loading" role="status" aria-live="polite">
                <div className="aw-detail-loading-card">
                  <span className="loading-gap-spinner" aria-hidden="true" />
                  <span>
                    <strong>正在探测接入方式</strong>
                    <small>正在确认 API Server 与 A2A…</small>
                  </span>
                </div>
              </div>
            )}
            <div className="aw-agent-head">
              <div className="aw-agent-heading">
                {detailOnly && onBack ? (
                  <PageBackButton label="返回智能体列表" onClick={onBack} />
                ) : null}
                <div className="aw-agent-heading-copy">
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
              </div>
              {(selectedDraft || selectedAgentUpdateDraft || selectedAgent?.canDelete) && (
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
                  {selectedAgent?.canDelete && (
                    <button
                      type="button"
                      className="aw-head-delete"
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
            </div>
            {deploymentTask && shouldShowDeploymentTask && (
              <div
                className={`aw-detail-deployment${deploymentInProgress ? " is-running" : ""}`}
              >
                <DeploymentProgressCard
                  task={deploymentTask}
                  onReturnToEdit={deploymentDraft && onEditDraft
                    ? () => onEditDraft(deploymentDraft)
                    : undefined}
                />
              </div>
            )}
            <nav
              className="aw-agent-tabs"
              aria-label="智能体详情"
              role="tablist"
            >
              {visibleAgentSections.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  id={`agent-${item.id}-tab`}
                  className={section === item.id ? "is-active" : ""}
                  role="tab"
                  aria-selected={section === item.id}
                  aria-controls={`agent-${item.id}-panel`}
                  tabIndex={section === item.id ? 0 : -1}
                  onClick={() => setSection(item.id)}
                  onKeyDown={(event) => {
                    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                    event.preventDefault();
                    const currentIndex = visibleAgentSections.findIndex(
                      (sectionItem) => sectionItem.id === item.id,
                    );
                    const nextIndex = event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? visibleAgentSections.length - 1
                        : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + visibleAgentSections.length)
                          % visibleAgentSections.length;
                    const nextSection = visibleAgentSections[nextIndex];
                    setSection(nextSection.id);
                    document.getElementById(`agent-${nextSection.id}-tab`)?.focus();
                  }}
                >
                  {item.label}
                </button>
              ))}
            </nav>

            <div
              className="aw-content"
              id={`agent-${section}-panel`}
              role="tabpanel"
              aria-labelledby={`agent-${section}-tab`}
            >
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
                    </div>
                  </section>
                  <section className="aw-details-card">
                    <div className="aw-card-head">
                      <strong>详细信息</strong>
                    </div>
                    <dl className="aw-facts">
                      <div>
                        <dt>模型</dt>
                        <dd>
                          {modelNameFromRuntime(selectedAgentInfo?.model) ||
                            draft.modelName ||
                            "暂未提供"}
                        </dd>
                      </div>
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
                  <section
                    className="aw-sidecar-panel aw-settings-card"
                    aria-label="已选择的优化项"
                  >
                    <div className="aw-section-head">
                      <div>
                        <h3>已选择的优化项</h3>
                        <p>发布时选择的智能体优化项。</p>
                      </div>
                    </div>
                    <dl className="aw-readonly-config">
                      <div>
                        <dt>配置状态</dt>
                        <dd className={publishedHarnessSidecar?.enabled ? "is-ready" : undefined}>
                          {publishedHarnessSidecar
                            ? publishedHarnessSidecar.enabled
                              ? <><span className="aw-status-dot" />已启用</>
                              : "未启用"
                            : "未记录"}
                        </dd>
                      </div>
                      <div>
                        <dt>优化场景</dt>
                        <dd>
                          {publishedHarnessSidecar
                            ? harnessSidecarProfileLabel(publishedHarnessSidecar.profile)
                            : "旧版本未保存此配置"}
                        </dd>
                      </div>
                      <div>
                        <dt>已选优化项</dt>
                        <dd className="aw-fact-badges">
                          {!publishedHarnessSidecar
                            ? "旧版本未保存此配置"
                            : publishedHarnessOptimizations.length
                              ? publishedHarnessOptimizations.map((optionId) => (
                                  <span key={optionId}>
                                    {harnessSidecarOptionLabel(optionId)}
                                  </span>
                                ))
                              : "未选择"}
                        </dd>
                      </div>
                    </dl>
                  </section>
                </div>
              )}
              {section === "usage" && selectedAgent?.runtimeId && (
                <section
                  className="aw-usage"
                  aria-busy={agentUsageLoading}
                >
                  <div className="aw-usage-intro">
                    <h3>使用概览</h3>
                  </div>
                  {agentUsageLoading && !selectedAgentUsage && (
                    <div className="aw-usage-state" role="status" aria-live="polite">
                      <TextShimmer as="span">正在加载用量统计</TextShimmer>
                    </div>
                  )}
                  {agentUsageError && (
                    <div className="aw-usage-state is-error" role="alert">
                      <span>{agentUsageError}</span>
                      <button
                        type="button"
                        onClick={() => setAgentUsageReloadToken((value) => value + 1)}
                      >
                        重试
                      </button>
                    </div>
                  )}
                  {!agentUsageLoading &&
                    !agentUsageError &&
                    !selectedAgentUsage &&
                    !selectedAgentAppName && (
                      <div className="aw-usage-state">
                        当前 Runtime 未返回可用的 Agent 应用名称，暂时无法读取用量。
                      </div>
                    )}
                  {selectedAgentUsage && (
                    <>
                      <dl className="aw-usage-summary" aria-label="Agent 用量摘要">
                        <div>
                          <dt>总调用次数</dt>
                          <dd>{selectedAgentUsage.totalInvocations.toLocaleString("zh-CN")}</dd>
                        </div>
                        <div>
                          <dt>使用用户数</dt>
                          <dd>{selectedAgentUsage.totalUsers.toLocaleString("zh-CN")}</dd>
                        </div>
                      </dl>
                      <div className="aw-usage-users-head">
                        <h3>用户明细</h3>
                        {agentUsageLoading && (
                          <TextShimmer as="span" role="status" aria-live="polite">
                            正在刷新
                          </TextShimmer>
                        )}
                      </div>
                      {selectedAgentUsage.users.length === 0 ? (
                        <div className="aw-usage-state">
                          暂无使用记录。用户成功调用后将在这里显示。
                        </div>
                      ) : (
                        <div className="aw-usage-table-wrap">
                          <table className="aw-usage-table">
                            <caption>当前 Agent 的使用用户列表</caption>
                            <thead>
                              <tr>
                                <th scope="col">用户</th>
                                <th scope="col">调用次数</th>
                                <th scope="col">最近使用</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedAgentUsage.users.map((user) => (
                                <tr key={user.userId}>
                                  <td>
                                    <strong>{user.displayName || user.userId || "未知用户"}</strong>
                                    {user.displayName && user.userId && (
                                      <small title={user.userId}>{user.userId}</small>
                                    )}
                                  </td>
                                  <td>{user.invocationCount.toLocaleString("zh-CN")}</td>
                                  <td>
                                    <time dateTime={user.lastUsedAt}>
                                      {formatAgentUsageTime(user.lastUsedAt)}
                                    </time>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                      {selectedAgentUsage.totalPages > 1 && (
                        <nav className="aw-usage-pagination" aria-label="用量用户列表分页">
                          <button
                            type="button"
                            disabled={agentUsageLoading || selectedAgentUsage.page <= 1}
                            onClick={() => setAgentUsagePage((page) => Math.max(1, page - 1))}
                          >
                            上一页
                          </button>
                          <span aria-live="polite">
                            第 {selectedAgentUsage.page} / {selectedAgentUsage.totalPages} 页
                          </span>
                          <button
                            type="button"
                            disabled={
                              agentUsageLoading ||
                              selectedAgentUsage.page >= selectedAgentUsage.totalPages
                            }
                            onClick={() => setAgentUsagePage((page) => page + 1)}
                          >
                            下一页
                          </button>
                        </nav>
                      )}
                    </>
                  )}
                </section>
              )}
              {section === "integrations" && (
                <div className="aw-integration-stack">
                  <div className="aw-integration-intro">
                    <h3>接入方式</h3>
                    <p>仅展示当前 Runtime 可确认的公开协议与地址。</p>
                  </div>
                  {integrationError && (
                    <div className="aw-integration-error" role="alert">
                      <span>{integrationError}</span>
                      <button
                        type="button"
                        onClick={() => setIntegrationReloadToken((value) => value + 1)}
                      >
                        重试
                      </button>
                    </div>
                  )}
                  {!integrationError && (
                    <div className="aw-integration-body">
                      <div
                        className={`aw-integration-protocol-tabs${
                          integrationProtocol === "a2a" ? " is-a2a" : ""
                        }`}
                        role="tablist"
                        aria-label="接入协议"
                      >
                        <span
                          className="aw-integration-protocol-slider"
                          aria-hidden="true"
                        />
                        {INTEGRATION_PROTOCOLS.map((protocol, protocolIndex) => (
                          <button
                            type="button"
                            key={protocol.id}
                            id={`integration-${protocol.id}-tab`}
                            role="tab"
                            aria-selected={integrationProtocol === protocol.id}
                            aria-controls={`integration-${protocol.id}-panel`}
                            tabIndex={integrationProtocol === protocol.id ? 0 : -1}
                            onClick={() => selectIntegrationProtocol(protocol.id)}
                            onKeyDown={(event) => {
                              if (![
                                "ArrowLeft",
                                "ArrowRight",
                                "Home",
                                "End",
                              ].includes(event.key)) return;
                              event.preventDefault();
                              const nextIndex = event.key === "Home"
                                ? 0
                                : event.key === "End"
                                  ? INTEGRATION_PROTOCOLS.length - 1
                                  : (
                                      protocolIndex +
                                      (event.key === "ArrowRight" ? 1 : -1) +
                                      INTEGRATION_PROTOCOLS.length
                                    ) % INTEGRATION_PROTOCOLS.length;
                              const nextProtocol = INTEGRATION_PROTOCOLS[nextIndex];
                              selectIntegrationProtocol(nextProtocol.id);
                              document
                                .getElementById(`integration-${nextProtocol.id}-tab`)
                                ?.focus();
                            }}
                          >
                            {protocol.label}
                          </button>
                        ))}
                      </div>

                      {integrationProtocol === "api-server" ? (
                        <IntegrationPanel
                          protocol="api-server"
                          title="API Server"
                          available={apiIntegrationAvailable}
                          fields={[
                            {
                              label: "Agent",
                              value: apiIntegrationAvailable
                                ? selectedIntegrationProbe?.apiApps?.join("、") ?? ""
                                : "",
                            },
                            {
                              label: "发现接口",
                              value: apiIntegrationAvailable
                                ? endpointPath(runtimeEndpoint, "/list-apps")
                                : "",
                            },
                            {
                              label: "调用接口",
                              value: apiIntegrationAvailable
                                ? endpointPath(runtimeEndpoint, "/run_sse")
                                : "",
                            },
                            {
                              label: "鉴权方式",
                              value: apiIntegrationAvailable
                                ? authTypeLabel(runtimeDetail?.authType)
                                : "",
                            },
                            {
                              label: "API Key",
                              value: (
                                <IntegrationApiKey
                                  available={apiIntegrationAvailable}
                                  authType={runtimeDetail?.authType}
                                  value={selectedRevealedApiKey}
                                  visible={apiKeyVisible && Boolean(selectedRevealedApiKey)}
                                  loading={apiKeyLoading}
                                  error={apiKeyError}
                                  onToggle={() => void toggleApiKeyVisibility()}
                                />
                              ),
                            },
                          ]}
                          example={apiIntegrationAvailable
                            ? apiServerPythonExample(
                                runtimeEndpoint,
                                apiIntegrationAppName,
                                runtimeDetail?.authType,
                              )
                            : ""}
                        />
                      ) : (
                        <IntegrationPanel
                          protocol="a2a"
                          title="A2A"
                          available={a2aIntegrationAvailable}
                          fields={[
                            {
                              label: "Agent",
                              value: selectedIntegrationProbe?.a2a?.name ?? "",
                            },
                            {
                              label: "Agent Card",
                              value: a2aIntegrationAvailable
                                ? endpointPath(
                                    runtimeEndpoint,
                                    "/.well-known/agent-card.json",
                                  )
                                : "",
                            },
                            {
                              label: "调用地址",
                              value: a2aEndpoint,
                            },
                            {
                              label: "鉴权方式",
                              value: a2aIntegrationAvailable
                                ? authTypeLabel(runtimeDetail?.authType)
                                : "",
                            },
                            {
                              label: "API Key",
                              value: (
                                <IntegrationApiKey
                                  available={a2aIntegrationAvailable}
                                  authType={runtimeDetail?.authType}
                                  value={selectedRevealedApiKey}
                                  visible={apiKeyVisible && Boolean(selectedRevealedApiKey)}
                                  loading={apiKeyLoading}
                                  error={apiKeyError}
                                  onToggle={() => void toggleApiKeyVisibility()}
                                />
                              ),
                            },
                          ]}
                          example={a2aIntegrationAvailable
                            ? a2aPythonExample(
                                a2aEndpoint,
                                runtimeDetail?.authType,
                              )
                            : ""}
                        />
                      )}
                    </div>
                  )}
                </div>
              )}

              {section === "evaluations" && (
                <section className="aw-cases">
                  {selectedAgent?.runtimeId && (
                    <div className="aw-case-summary">
                      {(["good", "bad"] as const).map((kind) => {
                        const set = feedbackSetFor(feedbackSets, kind);
                        const localCount = cases.filter((item) => item.kind === kind).length;
                        const count = previewCase ? localCount : set?.itemCount ?? localCount;
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
                  )}
                  <div className="aw-case-filter-bar">
                    <div className="aw-case-filter-stack">
                      <div className="aw-case-filters" aria-label="案例结果筛选">
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
                      <div className="aw-case-source-filters" aria-label="回流方式筛选">
                        {(["auto", "user"] as const).map((source) => (
                          <button
                            type="button"
                            key={source}
                            className={caseSourceFilter === source ? "is-active" : ""}
                            aria-pressed={caseSourceFilter === source}
                            onClick={() => setCaseSourceFilter(source)}
                          >
                            {source === "auto" ? "自动回流" : "手动回流"}
                          </button>
                        ))}
                      </div>
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
                  </div>
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
                      loading={feedbackCasesLoading && visibleCases.length === 0}
                      error={feedbackCasesError}
                      notice={feedbackCasesUnsupported}
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
              {section === "optimizations" && (
                <section className="aw-optimizations">
                  <div className="aw-optimization-intro">
                    <h3>优化项</h3>
                    <p>根据评测结果汇总需要优先处理的改进建议。</p>
                  </div>
                  {optimizationsLoading ? (
                    <div className="aw-optimization-state" role="status">
                      <span className="loading-gap-spinner" aria-hidden="true" />
                      <span>正在读取优化项</span>
                    </div>
                  ) : optimizationsError ? (
                    <div className="aw-optimization-state is-error" role="alert">
                      <span>{optimizationsError}</span>
                      <button
                        type="button"
                        onClick={() => setOptimizationsReloadToken((value) => value + 1)}
                      >
                        重试
                      </button>
                    </div>
                  ) : optimizationGroups.length > 0 ? (
                    <OptimizationTable groups={optimizationGroups} />
                  ) : (
                    <div className="aw-optimization-state">
                      暂无优化项，自动评测完成后会在这里生成建议。
                    </div>
                  )}
                </section>
              )}
            </div>
            {section === "basic" && (selectedAgent || selectedDraft) && (
              <div className="aw-basic-actions">
                {selectedAgent && (
                  <button
                    type="button"
                    className="aw-talk studio-update-action"
                    onClick={() => onTalkAgent?.(selectedAgent)}
                  >
                    <MessageCircle aria-hidden />
                    <span>去对话</span>
                  </button>
                )}
                <span
                  className={`aw-update-wrap${updateBlockedReason ? " is-disabled" : ""}`}
                  tabIndex={updateBlockedReason ? 0 : undefined}
                  aria-describedby={updateBlockedReason ? updateReasonId : undefined}
                >
                  <button
                    type="button"
                    className="aw-update studio-update-action"
                    disabled={Boolean(updateBlockedReason)}
                    aria-busy={updateCapabilityLoading || undefined}
                    aria-describedby={updateBlockedReason ? updateReasonId : undefined}
                    onClick={() =>
                      selectedDraft
                        ? onEditDraft?.(selectedDraft)
                        : selectedUpdateCapability
                          ? onUpdateAgent(selectedUpdateCapability)
                          : undefined
                    }
                  >
                    {updateCapabilityLoading ? (
                      <>
                        <span
                          className="loading-gap-spinner aw-update-spinner"
                          aria-hidden="true"
                        />
                        <span>检测中</span>
                      </>
                    ) : selectedDraft || selectedAgentUpdateDraft ? (
                      "继续编辑"
                    ) : (
                      "更新"
                    )}
                  </button>
                  {updateBlockedReason && (
                    <span
                      id={updateReasonId}
                      className="aw-update-disabled-reason"
                      role="tooltip"
                    >
                      {updateBlockedReason}
                    </span>
                  )}
                </span>
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
    {deleteConfirmTarget && (
      <StudioConfirmDialog
        variant="danger"
        title={deleteConfirmTarget.title}
        description={deleteConfirmTarget.description}
        confirmLabel={deletingAgents ? "删除中..." : deleteConfirmTarget.confirmLabel}
        closeLabel="关闭删除确认"
        busy={deletingAgents}
        onCancel={() => setDeleteConfirmTarget(null)}
        onConfirm={() => void confirmDeleteTarget()}
      />
    )}
  </>
  );
}

function OptimizationTable({ groups }: { groups: OptimizationGroup[] }) {
  return (
    <div className="aw-optimization-table-wrap">
      <table className="aw-optimization-table">
        <thead>
          <tr>
            <th scope="col">修复优先级</th>
            <th scope="col">建议优化模块</th>
            <th scope="col">优化建议和理由</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr
              key={`${group.priority}:${group.module}:${group.customModule ?? ""}`}
            >
              <td>
                <span className={`aw-priority is-${group.priority}`}>
                  {optimizationPriorityLabel(group.priority)}
                </span>
              </td>
              <td>
                <span className="aw-optimization-module">
                  {optimizationModuleLabel(group)}
                </span>
              </td>
              <td>
                <ul className="aw-optimization-list">
                  {group.items.map((item) => (
                    <li key={`${item.suggestion}:${item.reason}`}>
                      <strong>{item.suggestion}</strong>
                      <p>{item.reason}</p>
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DeleteCaseIcon() {
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
      <path d="M4.5 7h15" />
      <path d="M9 7V4.8h6V7" />
      <path d="m6.5 7 .8 12h9.4l.8-12" />
      <path d="M10 10.5v5M14 10.5v5" />
    </svg>
  );
}

function CaseTable({
  cases,
  loading = false,
  error = "",
  notice = "",
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
  notice?: string;
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
        <span>用户输入</span>
        <span>Agent 输出</span>
        <span>评分</span>
        <span>评分理由</span>
        <span className="aw-case-action-head">操作</span>
      </div>
      {loading ? (
        <div className="aw-case-empty">正在读取 AgentKit 评测集…</div>
      ) : error ? (
        <div className="aw-case-empty aw-case-error">
          <span>{error}</span>
          {onRetry && <button type="button" onClick={onRetry}>重试</button>}
        </div>
      ) : notice ? (
        <div className="aw-case-empty">{notice}</div>
      ) : cases.length === 0 ? (
        <div className="aw-case-empty">
          {runtimeBacked ? "暂无用户反馈案例" : "没有匹配的案例"}
        </div>
      ) : (
        cases.map((item) => {
          const isLocalPreview = item.id.startsWith("local:");
          const isSelected = selectedCaseIds?.has(item.id) ?? false;
          const isExpanded = expandedCaseIds?.has(item.id) ?? false;
          const outputLength =
            item.output.length + item.referenceOutput.length;
          const canExpand = outputLength > 220 || (item.reason?.length ?? 0) > 120;
          const canDeleteCase = canDelete && !isLocalPreview;
          const showComment = Boolean(
            item.comment && item.comment.trim() !== item.reason?.trim(),
          );
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
                  if (canDeleteCase) onToggleCase?.(item);
                  return;
                }
                onOpenCase?.(item);
              }}
              onKeyDown={(event) => {
                if (event.target !== event.currentTarget) return;
                if (event.key !== "Enter" && event.key !== " ") return;
                event.preventDefault();
                if (selectionMode) {
                  if (canDeleteCase) onToggleCase?.(item);
                } else {
                  onOpenCase?.(item);
                }
              }}
            >
              <div className="aw-case-text aw-case-cell" data-label="用户输入">
                <span className="aw-case-title-line">
                  {selectionMode && canDeleteCase && (
                    <span
                      className={`aw-select-marker${isSelected ? " is-checked" : ""}`}
                      aria-hidden="true"
                    />
                  )}
                  <strong title={item.input}>{item.input || "无用户输入"}</strong>
                </span>
                {showComment && <small title={item.comment}>备注：{item.comment}</small>}
                <small className="aw-case-time">{formatCaseTime(item.createdAt)}</small>
                {(item.userId || item.sessionId) && (
                  <small title={[item.userId, item.sessionId].filter(Boolean).join(" · ")}>
                    {[item.userId, item.sessionId].filter(Boolean).join(" · ")}
                  </small>
                )}
              </div>
              <div
                className={`aw-case-output aw-case-cell${isExpanded ? " is-expanded" : ""}`}
                data-label="Agent 输出"
              >
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
              <div className="aw-case-score aw-case-cell" data-label="评分">
                {formatCaseScore(item)}
              </div>
              <div
                className={`aw-case-reason aw-case-cell${isExpanded ? " is-expanded" : ""}`}
                data-label="评分理由"
              >
                <p title={item.reason || undefined}>
                  {item.reason || "—"}
                </p>
              </div>
              <div className="aw-case-actions aw-case-cell" data-label="操作">
                {canDeleteCase && (
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
                    <DeleteCaseIcon />
                  </button>
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
