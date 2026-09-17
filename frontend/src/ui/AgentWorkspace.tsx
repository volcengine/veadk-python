import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";
import type { TFunction } from "i18next";
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
import { Alert } from "@openai/apps-sdk-ui/components/Alert";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { useTranslation } from "react-i18next";
import {
  deleteAgentFeedbackCases,
  createGithubDeliveryRollbackPr,
  getCachedAgentFeedbackCases,
  getCachedRuntimeAgentInfo,
  getCachedRuntimeDetail,
  getCachedRuntimeUpdateCapability,
  getAgentUsage,
  getAgentFeedbackCases,
  getAgentOptimizations,
  getGithubDeliveryVersions,
  getMpaAgentDeletePreview,
  getMpaAgentView,
  getMpaProfileStatus,
  getMpaRuntimeConsoleRuns,
  getMpaRuntimeConsoleTrace,
  getMpaSessionExecutionConfig,
  getRuntimeAgentInfo,
  getRuntimeDetail,
  getRuntimeUpdateCapability,
  mpaProfileFromAgentDraft,
  patchMpaSessionExecutionConfig,
  probeRuntimeA2a,
  probeRuntimeApps,
  prefetchRuntimeAgentInfo,
  prefetchRuntimeDetail,
  revealRuntimeApiKey,
  startMpaAgentOperation,
  upgradeMpaSessionProfile,
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
  type GithubDeliveryVersionsResult,
  type GithubDeliveryVersion,
  MpaExecutionConfigRequestError,
  type MpaAgentDeletePreview,
  type MpaAgentView,
  type MpaExecutionConfigMode,
  type MpaProfilePayload,
  type MpaProfileStatus,
  type MpaRuntimeConsoleRun,
  type MpaRuntimeTraceResponse,
  type MpaSessionExecutionConfig,
  type RuntimeA2aIntegration,
  RuntimeProbeError,
  type RuntimeDetail,
  type RuntimeUpdateCapability,
} from "../adk/client";
import type { AgentEntry } from "../adk/connections";
import { localizeDeployStageMessage } from "../adk/deploymentI18n";
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
import { localeCompatibleBackendText } from "../i18n/locales";
import type { DeploymentTaskUpdate } from "./ProjectPreview";
import { Markdown } from "./Markdown";
import { ResourceDetailLayout } from "./ResourceCollection";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./AgentWorkspace.css";

type WorkspaceView = "library" | "evaluation";
type AgentSection = "basic" | "profileConfig" | "sessionConfig" | "usage" | "diagnostics" | "evaluations" | "optimizations" | "integrations" | "versions";
type IntegrationProtocol = "api-server" | "a2a";
type EvaluationSection = "config" | "history";
type CaseKind = "good" | "bad";
type OptimizationPriority = AgentOptimizationPriority;
type OptimizationModule = AgentOptimizationModule;

type AgentCase = AgentFeedbackCase & { tag?: string };
type OptimizationGroup = AgentOptimizationGroup;
type AgentCategory = "general" | "mpa";
type DeleteConfirmTarget =
  | {
      kind: "selection";
      title: string;
      description: ReactNode;
      confirmLabel: string;
      canConfirm?: boolean;
      agents: AgentEntry[];
      drafts: WorkspaceAgentDraft[];
    }
  | {
      kind: "agent";
      title: string;
      description: ReactNode;
      confirmLabel: string;
      canConfirm?: boolean;
      agent: AgentEntry;
    }
  | {
      kind: "draft";
      title: string;
      description: ReactNode;
      confirmLabel: string;
      canConfirm?: boolean;
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

function buildDefaultCases(t: TFunction): AgentCase[] {
  return [
    {
      id: "case-1",
      itemKey: "case-1",
      kind: "good",
      input: t("agentWorkspace.defaultCases.weeklyFeedback.input"),
      output: t("agentWorkspace.defaultCases.weeklyFeedback.output"),
      referenceOutput: t("agentWorkspace.defaultCases.weeklyFeedback.output"),
      comment: "",
      agentName: t("agentWorkspace.defaultCases.agentName"),
      sessionId: "",
      messageId: "",
      runtimeId: "",
      invocationId: "",
      userId: "",
      createdAt: "2026-08-05T09:12:00+08:00",
      evaluationSetId: "",
      evaluationSetName: t("agentWorkspace.defaultCases.goodSetName"),
      workspaceId: "",
      tag: t("agentWorkspace.defaultCases.weeklyFeedback.tag"),
      source: "auto",
      score: 0.92,
      reason: t("agentWorkspace.defaultCases.weeklyFeedback.reason"),
    },
    {
      id: "case-2",
      itemKey: "case-2",
      kind: "good",
      input: t("agentWorkspace.defaultCases.research.input"),
      output: t("agentWorkspace.defaultCases.research.output"),
      referenceOutput: t("agentWorkspace.defaultCases.research.output"),
      comment: "",
      agentName: t("agentWorkspace.defaultCases.agentName"),
      sessionId: "",
      messageId: "",
      runtimeId: "",
      invocationId: "",
      userId: "",
      createdAt: "2026-08-05T08:47:00+08:00",
      evaluationSetId: "",
      evaluationSetName: t("agentWorkspace.defaultCases.goodSetName"),
      workspaceId: "",
      tag: t("agentWorkspace.defaultCases.research.tag"),
      source: "user",
    },
    {
      id: "case-3",
      itemKey: "case-3",
      kind: "bad",
      input: t("agentWorkspace.defaultCases.uncertainConclusion.input"),
      output: t("agentWorkspace.defaultCases.uncertainConclusion.output"),
      referenceOutput: "",
      comment: "",
      agentName: t("agentWorkspace.defaultCases.agentName"),
      sessionId: "",
      messageId: "",
      runtimeId: "",
      invocationId: "",
      userId: "",
      createdAt: "2026-08-05T07:35:00+08:00",
      evaluationSetId: "",
      evaluationSetName: t("agentWorkspace.defaultCases.badSetName"),
      workspaceId: "",
      tag: t("agentWorkspace.defaultCases.uncertainConclusion.tag"),
      source: "auto",
      score: 0.28,
      reason: t("agentWorkspace.defaultCases.uncertainConclusion.reason"),
    },
    {
      id: "case-4",
      itemKey: "case-4",
      kind: "bad",
      input: t("agentWorkspace.defaultCases.repeatedTool.input"),
      output: t("agentWorkspace.defaultCases.repeatedTool.output"),
      referenceOutput: "",
      comment: "",
      agentName: t("agentWorkspace.defaultCases.agentName"),
      sessionId: "",
      messageId: "",
      runtimeId: "",
      invocationId: "",
      userId: "",
      createdAt: "2026-08-05T06:58:00+08:00",
      evaluationSetId: "",
      evaluationSetName: t("agentWorkspace.defaultCases.badSetName"),
      workspaceId: "",
      tag: t("agentWorkspace.defaultCases.repeatedTool.tag"),
      source: "user",
    },
  ];
}

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

const EVALUATION_TEXT_KEYS: Record<string, string> = {
  "核心能力回归": "agentWorkspace.evaluationDefaults.coreRegression",
  "安全与幻觉检查": "agentWorkspace.evaluationDefaults.safetyCheck",
  "核心回归集": "agentWorkspace.evaluationDefaults.coreSet",
  "安全边界集": "agentWorkspace.evaluationDefaults.safetySet",
  "工具调用集": "agentWorkspace.evaluationDefaults.toolSet",
  "综合质量评估器": "agentWorkspace.evaluationDefaults.qualityEvaluator",
  "事实一致性评估器": "agentWorkspace.evaluationDefaults.factualEvaluator",
  "工具调用评估器": "agentWorkspace.evaluationDefaults.toolEvaluator",
  "回答质量": "agentWorkspace.evaluationDefaults.responseQuality",
  "事实准确性": "agentWorkspace.evaluationDefaults.factualAccuracy",
  "工具调用": "agentWorkspace.evaluationDefaults.toolUse",
  "响应效率": "agentWorkspace.evaluationDefaults.responseEfficiency",
  "今天 10:32": "agentWorkspace.evaluationDefaults.todayTime",
  "昨天 16:08": "agentWorkspace.evaluationDefaults.yesterdayTime",
  "7 月 25 日 14:20": "agentWorkspace.evaluationDefaults.julyTime",
  "刚刚": "agentWorkspace.evaluationDefaults.justNow",
};

function evaluationText(value: string, t: TFunction): string {
  const key = EVALUATION_TEXT_KEYS[value];
  return key ? t(key) : value;
}

const AGENT_SECTIONS: AgentSection[] = [
  "basic",
  "profileConfig",
  "sessionConfig",
  "usage",
  "diagnostics",
  "evaluations",
  "optimizations",
  "integrations",
  "versions",
];

const AGENT_USAGE_PAGE_SIZE = 20;
function formatAgentUsageTime(value: string, locale: string, t: TFunction): string {
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp)
    ? t("agentWorkspace.notProvided")
    : new Intl.DateTimeFormat(locale, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(timestamp);
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

interface SessionExecutionConfigState {
  requestKey: string;
  value: MpaSessionExecutionConfig;
}

interface MpaProfileStatusState {
  requestKey: string;
  value: MpaProfileStatus;
}

interface MpaProfileApplyState {
  saving: boolean;
  error: string;
  notice: string;
}

interface MpaAgentViewState {
  requestKey: string;
  value: MpaAgentView;
}

interface MpaDiagnosticsState {
  requestKey: string;
  runs: MpaRuntimeConsoleRun[];
  trace: MpaRuntimeTraceResponse | null;
}

export interface MpaProfileEditTarget {
  draft: AgentDraft;
  runtimeId: string;
  mpaInstanceId: string;
  name: string;
  region: string;
  appName?: string;
  currentVersion?: number | null;
  runtimeRevision?: string;
}

function recordId(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const id = (value as { id?: unknown }).id;
  return typeof id === "string" ? id : "";
}

function effectiveModelId(config: MpaSessionExecutionConfig | null): string {
  return recordId(config?.effectiveRefs?.model);
}

function executionOverrideMode(
  config: MpaSessionExecutionConfig | null,
  category: string,
): MpaExecutionConfigMode | "" {
  const value = config?.overrides?.[category];
  if (!value || typeof value !== "object") return "";
  const mode = (value as { mode?: unknown }).mode;
  return mode === "replace" || mode === "clear" || mode === "inherit" ? mode : "";
}

function executionMcpIds(config: MpaSessionExecutionConfig | null): string[] {
  const values = config?.effectiveRefs?.mcpServers;
  if (!Array.isArray(values)) return [];
  return values.map(recordId).filter(Boolean);
}

function mpaDeleteBlockerLabel(code: string, t: TFunction<"ui">): string {
  switch (code) {
    case "active_operation":
      return t("agentWorkspace.mpaDeleteBlockerActiveOperation");
    case "active_sessions":
      return t("agentWorkspace.mpaDeleteBlockerActiveSessions");
    case "binding_ambiguous":
      return t("agentWorkspace.mpaDeleteBlockerBindingAmbiguous");
    case "runtime_missing":
      return t("agentWorkspace.mpaDeleteBlockerRuntimeMissing");
    case "orphan_runtime":
      return t("agentWorkspace.mpaDeleteBlockerOrphanRuntime");
    default:
      return code;
  }
}

function MpaDeletePreviewDetails({
  preview,
  t,
}: {
  preview: MpaAgentDeletePreview;
  t: TFunction<"ui">;
}) {
  const blockers = preview.blockers.map((code) => mpaDeleteBlockerLabel(code, t));
  return (
    <div className="aw-mpa-delete-preview">
      <p>{t("agentWorkspace.mpaDeletePreviewSummary")}</p>
      <dl className="aw-mpa-delete-preview__stats">
        <div>
          <dt>{t("agentWorkspace.mpaDeletePreviewSessions")}</dt>
          <dd>{preview.sessionCounts.total}</dd>
        </div>
        <div>
          <dt>{t("agentWorkspace.mpaDeletePreviewActiveSessions")}</dt>
          <dd>{preview.sessionCounts.active}</dd>
        </div>
        <div>
          <dt>{t("agentWorkspace.mpaDeletePreviewIdleSessions")}</dt>
          <dd>{preview.sessionCounts.idle}</dd>
        </div>
      </dl>
      {blockers.length > 0 ? (
        <div className="aw-mpa-delete-preview__blockers" role="status">
          <strong>{t("agentWorkspace.mpaDeleteBlocked")}</strong>
          <ul>
            {blockers.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : (
        <ol className="aw-mpa-delete-preview__plan">
          {preview.cleanupPlan.map((stage) => (
            <li key={stage.stage}>
              {t(`agentWorkspace.mpaDeleteStage.${stage.stage}`, {
                count: stage.count,
              })}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function executionConfigErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof MpaExecutionConfigRequestError && error.status === 412) {
    return fallback;
  }
  return error instanceof Error ? error.message : String(error);
}

function mcpServerCount(config: MpaSessionExecutionConfig | null): number {
  return executionMcpIds(config).length;
}

function formatMcpServerIds(
  config: MpaSessionExecutionConfig | null,
  t: TFunction,
): string {
  const ids = executionMcpIds(config);
  return ids.length ? ids.join(", ") : t("agentWorkspace.none");
}

function isCategoryOverridden(
  config: MpaSessionExecutionConfig | null,
  category: string,
): boolean {
  return Boolean(config?.overrides?.[category]);
}

function profileUpgradeIdempotencyKey(
  runtimeId: string,
  sessionId: string,
  targetProfileRevision: number,
): string {
  return `mpa-session-profile-upgrade:${runtimeId}:${sessionId}:${targetProfileRevision}`;
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

function authTypeLabel(
  authType: RuntimeDetail["authType"] | undefined,
  t: TFunction,
): string {
  if (authType === "key_auth") return "API Key";
  if (authType === "custom_jwt") return "OAuth / JWT";
  if (authType === "none") return t("agentWorkspace.noAuthentication");
  return t("agentWorkspace.notAvailable");
}

function githubRuntimeStatusLabel(status: string | undefined, t: TFunction): string {
  if (status === "published") return t("agentWorkspace.githubStatus.published");
  if (status === "publishing") return t("agentWorkspace.githubStatus.publishing");
  if (status === "failed") return t("agentWorkspace.githubStatus.failed");
  if (status === "pending") return t("agentWorkspace.githubStatus.pending");
  return t("agentWorkspace.githubStatus.unknown");
}

function githubVersionTitle(version: GithubDeliveryVersion, t: TFunction): string {
  if (version.changeType === "rollback") return t("agentWorkspace.rollbackEvent");
  return version.version;
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
  const { t } = useTranslation("ui");
  if (!available) return t("agentWorkspace.notAvailable");
  if (authType === "none") return t("agentWorkspace.noApiKeyRequired");
  if (authType === "custom_jwt") return t("agentWorkspace.usesOauthJwt");
  if (authType !== "key_auth") return t("agentWorkspace.notAvailable");
  return (
    <span className="aw-integration-secret">
      <span className="aw-integration-secret-value" aria-live="polite">
        {visible && value ? value : "****"}
      </span>
      <button
        type="button"
        className="aw-integration-secret-toggle"
        aria-label={visible ? t("agentWorkspace.hideApiKey") : t("agentWorkspace.showApiKey")}
        title={visible ? t("agentWorkspace.hideApiKey") : t("agentWorkspace.showApiKey")}
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
  const { t } = useTranslation("ui");
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
            <dd>{field.value || t("agentWorkspace.notAvailable")}</dd>
          </div>
        ))}
      </dl>
      {available && example && (
        <section className="aw-integration-example">
          <h4>{t("agentWorkspace.pythonExample")}</h4>
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

function summarizeProfileList(
  items: Array<Record<string, unknown>> | undefined,
  fallback: string,
): string {
  const values = (items ?? []).flatMap((item) => {
    const value = item.name ?? item.id ?? item.skillId ?? item.source;
    return typeof value === "string" && value.trim() ? [value.trim()] : [];
  });
  return values.length ? values.join(", ") : fallback;
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const fields = Object.entries(value as Record<string, unknown>)
      .filter(([, fieldValue]) => fieldValue !== undefined)
      .sort(([left], [right]) => left.localeCompare(right));
    return `{${fields.map(([key, fieldValue]) =>
      `${JSON.stringify(key)}:${canonicalJson(fieldValue)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function profileIdempotencyKey(
  runtimeId: string,
  operationKind: "create" | "update",
  profile: MpaProfilePayload,
): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(profile));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")).join("");
  return `mpa-profile:${runtimeId}:${operationKind}:${hex}`;
}

function MpaProfileConfigPanel({
  profile,
  profileStatus,
  runtimeReady,
  disabledReason,
  saving,
  error,
  notice,
  onApply,
  onEditProfile,
  onRefresh,
}: {
  profile: MpaProfilePayload;
  profileStatus: MpaProfileStatus | null;
  runtimeReady: boolean;
  disabledReason: string;
  saving: boolean;
  error: string;
  notice: string;
  onApply: () => void;
  onEditProfile: () => void;
  onRefresh: () => void;
}) {
  const { t } = useTranslation("ui");
  const applied = profileStatus?.status === "applied";
  const canApply = runtimeReady && !saving;
  return (
    <section className="aw-session-config aw-profile-config" aria-busy={saving}>
      <div className="aw-integration-intro">
        <h3>{t("agentWorkspace.profileConfigTitle")}</h3>
        <p>{t("agentWorkspace.profileConfigDescription")}</p>
      </div>

      {disabledReason ? (
        <div className="aw-session-config-state">{disabledReason}</div>
      ) : (
        <>
          {error && (
            <div className="aw-session-config-state is-error" role="alert">
              <span>{error}</span>
              <button type="button" onClick={onRefresh} disabled={saving}>
                {t("common.retry")}
              </button>
            </div>
          )}
          {notice && !error && (
            <div className="aw-session-config-notice" role="status">
              {notice}
            </div>
          )}

          <div className="aw-session-config-actions">
            <button type="button" onClick={onEditProfile} disabled={saving}>
              {t("agentWorkspace.editProfile")}
            </button>
            <button type="button" onClick={onRefresh} disabled={saving}>
              {t("common.refresh")}
            </button>
          </div>

          <dl className="aw-session-config-grid">
            <div>
              <dt>{t("agentWorkspace.profileStatus")}</dt>
              <dd>{applied ? t("agentWorkspace.profileApplied") : t("agentWorkspace.profileNotApplied")}</dd>
            </div>
            <div>
              <dt>{t("agentWorkspace.latestProfileRevision")}</dt>
              <dd>{profileStatus?.profileRevision ?? t("agentWorkspace.notAvailable")}</dd>
            </div>
            <div>
              <dt>{t("agentWorkspace.modelId")}</dt>
              <dd>{String(profile.model?.id || t("agentWorkspace.notAvailable"))}</dd>
            </div>
            <div>
              <dt>ETag</dt>
              <dd>{profileStatus?.etag || t("agentWorkspace.notAvailable")}</dd>
            </div>
          </dl>

          {!applied && (
            <div className="aw-session-config-upgrade" role="status">
              <span>{t("agentWorkspace.profileNotAppliedDescription")}</span>
              <button type="button" onClick={onApply} disabled={!canApply}>
                {saving
                  ? t("agentWorkspace.profileApplying")
                  : t("agentWorkspace.applyProfile")}
              </button>
            </div>
          )}

          {applied && (
            <div className="aw-session-config-actions">
              <button type="button" onClick={onApply} disabled={!canApply}>
                {saving
                  ? t("agentWorkspace.profileApplying")
                  : t("agentWorkspace.reapplyProfile")}
              </button>
            </div>
          )}

          <div className="aw-session-config-card">
            <div>
              <h4>{t("agentWorkspace.profilePrompt")}</h4>
              <p>{profile.system || t("agentWorkspace.notAvailable")}</p>
            </div>
          </div>

          <div className="aw-session-config-card">
            <div>
              <h4>{t("agentWorkspace.profileResources")}</h4>
              <p>
                {t("agentWorkspace.profileResourceSummary", {
                  tools: profile.tools.length,
                  skills: profile.skills.length,
                  mcp: profile.mcpServers.length,
                })}
              </p>
            </div>
            <div className="aw-profile-config-list">
              <span title={summarizeProfileList(profile.tools, t("agentWorkspace.notAvailable"))}>
                {t("agentSelector.tools")}: {summarizeProfileList(profile.tools, t("agentWorkspace.notAvailable"))}
              </span>
              <span title={summarizeProfileList(profile.skills, t("agentWorkspace.notAvailable"))}>
                {t("agentSelector.skills")}: {summarizeProfileList(profile.skills, t("agentWorkspace.notAvailable"))}
              </span>
              <span title={summarizeProfileList(profile.mcpServers, t("agentWorkspace.notAvailable"))}>
                MCP: {summarizeProfileList(profile.mcpServers, t("agentWorkspace.notAvailable"))}
              </span>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function SessionExecutionConfigPanel({
  config,
  profileStatus,
  loadable,
  disabledReason,
  loading,
  saving,
  upgrading,
  error,
  notice,
  modelValue,
  modelDirty,
  profileUpgradeAvailable,
  onModelChange,
  onSaveModel,
  onInheritModel,
  onClearMcp,
  onInheritMcp,
  onUpgradeProfile,
  onRefresh,
}: {
  config: MpaSessionExecutionConfig | null;
  profileStatus: MpaProfileStatus | null;
  loadable: boolean;
  disabledReason: string;
  loading: boolean;
  saving: boolean;
  upgrading: boolean;
  error: string;
  notice: string;
  modelValue: string;
  modelDirty: boolean;
  profileUpgradeAvailable: boolean;
  onModelChange: (value: string) => void;
  onSaveModel: () => void;
  onInheritModel: () => void;
  onClearMcp: () => void;
  onInheritMcp: () => void;
  onUpgradeProfile: () => void;
  onRefresh: () => void;
}) {
  const { t } = useTranslation("ui");
  const busy = loading || saving || upgrading;
  const modelMode = executionOverrideMode(config, "model");
  const mcpMode = executionOverrideMode(config, "mcpServers");
  const currentModel = effectiveModelId(config);
  const latestRevision = profileStatus?.status === "applied"
    ? profileStatus.profileRevision
    : null;
  return (
    <section className="aw-session-config" aria-busy={busy}>
      <div className="aw-integration-intro">
        <h3>{t("agentWorkspace.sessionConfigTitle")}</h3>
        <p>{t("agentWorkspace.sessionConfigDescription")}</p>
      </div>

      {!loadable ? (
        <div className="aw-session-config-state">{disabledReason}</div>
      ) : loading && !config ? (
        <div className="aw-session-config-state" role="status">
          <span className="loading-gap-spinner" aria-hidden="true" />
          <span>{t("agentWorkspace.loadingSessionConfig")}</span>
        </div>
      ) : (
        <>
          {error && (
            <div className="aw-session-config-state is-error" role="alert">
              <span>{error}</span>
              <button type="button" onClick={onRefresh} disabled={busy}>
                {t("common.retry")}
              </button>
            </div>
          )}
          {notice && !error && (
            <div className="aw-session-config-notice" role="status">
              {notice}
            </div>
          )}
          {config && (
            <>
              <dl className="aw-session-config-grid">
                <div>
                  <dt>{t("agentWorkspace.sessionConfigRevision")}</dt>
                  <dd>{config.revision}</dd>
                </div>
                <div>
                  <dt>{t("agentWorkspace.sessionProfileRevision")}</dt>
                  <dd>{config.profileRevision}</dd>
                </div>
                <div>
                  <dt>{t("agentWorkspace.latestProfileRevision")}</dt>
                  <dd>{latestRevision ?? t("agentWorkspace.notAvailable")}</dd>
                </div>
                <div>
                  <dt>ETag</dt>
                  <dd>{config.etag || t("agentWorkspace.notAvailable")}</dd>
                </div>
              </dl>

              {profileUpgradeAvailable && latestRevision != null && (
                <div className="aw-session-config-upgrade" role="status">
                  <span>
                    {t("agentWorkspace.sessionProfileUpgradeAvailable", {
                      current: config.profileRevision,
                      target: latestRevision,
                    })}
                  </span>
                  <button
                    type="button"
                    onClick={onUpgradeProfile}
                    disabled={busy}
                  >
                    {upgrading
                      ? t("agentWorkspace.sessionProfileUpgrading")
                      : t("agentWorkspace.upgradeSessionProfile")}
                  </button>
                </div>
              )}

              <div className="aw-session-config-card">
                <div>
                  <h4>{t("agentWorkspace.sessionModelOverride")}</h4>
                  <p>
                    {modelMode
                      ? t(`agentWorkspace.executionConfigMode.${modelMode}`)
                      : t("agentWorkspace.executionConfigMode.inherit")}
                  </p>
                </div>
                <label className="aw-session-config-field">
                  <span>{t("agentWorkspace.modelId")}</span>
                  <input
                    type="text"
                    value={modelValue}
                    onChange={(event) => onModelChange(event.currentTarget.value)}
                    placeholder={currentModel || t("agentWorkspace.inheritProfileDefault")}
                    disabled={busy}
                  />
                </label>
                <div className="aw-session-config-actions">
                  <button
                    type="button"
                    onClick={onSaveModel}
                    disabled={busy || !modelDirty}
                  >
                    {saving ? t("common.saving") : t("common.save")}
                  </button>
                  <button
                    type="button"
                    onClick={onInheritModel}
                    disabled={busy || !isCategoryOverridden(config, "model")}
                  >
                    {t("agentWorkspace.inheritProfileDefault")}
                  </button>
                </div>
              </div>

              <div className="aw-session-config-card">
                <div>
                  <h4>{t("agentWorkspace.sessionMcpServers")}</h4>
                  <p>
                    {mcpMode
                      ? t(`agentWorkspace.executionConfigMode.${mcpMode}`)
                      : t("agentWorkspace.executionConfigMode.inherit")}
                  </p>
                </div>
                <div className="aw-session-config-value">
                  <span>
                    {t("agentWorkspace.mcpServerCount", {
                      count: mcpServerCount(config),
                    })}
                  </span>
                  <small title={formatMcpServerIds(config, t)}>
                    {formatMcpServerIds(config, t)}
                  </small>
                </div>
                <div className="aw-session-config-actions">
                  <button
                    type="button"
                    onClick={onClearMcp}
                    disabled={busy || mcpMode === "clear"}
                  >
                    {t("agentWorkspace.clearSessionMcp")}
                  </button>
                  <button
                    type="button"
                    onClick={onInheritMcp}
                    disabled={busy || !isCategoryOverridden(config, "mcpServers")}
                  >
                    {t("agentWorkspace.inheritProfileDefault")}
                  </button>
                </div>
              </div>
            </>
          )}
        </>
      )}
    </section>
  );
}

function correlationValue(
  correlation: Record<string, unknown> | undefined,
  key: string,
): string {
  const value = correlation?.[key];
  return value == null || value === "" ? "" : String(value);
}

function workerCorrelationValue(
  correlation: Record<string, unknown> | undefined,
  key: string,
): string {
  const worker = correlation?.worker;
  if (!worker || typeof worker !== "object") return "";
  const value = (worker as Record<string, unknown>)[key];
  return value == null || value === "" ? "" : String(value);
}

function formatDurationMs(value: number | null | undefined, t: TFunction): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return t("agentWorkspace.notAvailable");
  }
  return `${Math.round(value)} ms`;
}

function MpaDiagnosticsPanel({
  data,
  loadable,
  disabledReason,
  loading,
  error,
  onRefresh,
  locale,
}: {
  data: MpaDiagnosticsState | null;
  loadable: boolean;
  disabledReason: string;
  loading: boolean;
  error: string;
  onRefresh: () => void;
  locale: string;
}) {
  const { t } = useTranslation("ui");
  const runs = data?.runs ?? [];
  const trace = data?.trace ?? null;
  const latestRun = runs[0];
  const correlation = trace?.correlation ?? {};
  const fields = [
    ["mpaInstanceId", t("agentWorkspace.mpaInstanceId")],
    ["profileRevision", t("agentWorkspace.sessionProfileRevision")],
    ["executionConfigRevision", t("agentWorkspace.sessionConfigRevision")],
    ["turnId", t("agentWorkspace.turnId")],
    ["taskId", t("agentWorkspace.taskId")],
    ["runtimeId", "Runtime ID"],
    ["runtimeVersion", t("systemInfo.currentVersion")],
  ] as const;
  const workerFields = [
    ["kind", t("agentWorkspace.workerKind")],
    ["sessionId", t("agentWorkspace.workerSession")],
    ["turnId", t("agentWorkspace.workerTurn")],
    ["profileId", t("agentWorkspace.workerProfile")],
    ["profileVersion", t("agentWorkspace.workerProfileVersion")],
  ] as const;
  return (
    <section className="aw-mpa-diagnostics" aria-busy={loading}>
      <div className="aw-integration-intro">
        <h3>{t("agentWorkspace.mpaDiagnosticsTitle")}</h3>
        <p>{t("agentWorkspace.mpaDiagnosticsDescription")}</p>
      </div>
      {!loadable ? (
        <div className="aw-session-config-state">{disabledReason}</div>
      ) : loading && !data ? (
        <div className="aw-session-config-state" role="status">
          <span className="loading-gap-spinner" aria-hidden="true" />
          <span>{t("agentWorkspace.loadingMpaDiagnostics")}</span>
        </div>
      ) : error ? (
        <div className="aw-session-config-state is-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={onRefresh} disabled={loading}>
            {t("common.retry")}
          </button>
        </div>
      ) : !latestRun ? (
        <div className="aw-session-config-state">
          {t("agentWorkspace.noMpaDiagnostics")}
        </div>
      ) : (
        <>
          <dl className="aw-session-config-grid">
            <div>
              <dt>{t("agentWorkspace.latestRun")}</dt>
              <dd>{latestRun.invocationId}</dd>
            </div>
            <div>
              <dt>{t("agentSelector.status")}</dt>
              <dd>{latestRun.status}</dd>
            </div>
            <div>
              <dt>{t("agentWorkspace.lastUsed")}</dt>
              <dd>{formatAgentUsageTime(latestRun.startedAt, locale, t)}</dd>
            </div>
            <div>
              <dt>{t("agentWorkspace.stepCount")}</dt>
              <dd>{latestRun.stepCount}</dd>
            </div>
          </dl>
          <section className="aw-session-config-card">
            <div>
              <h4>{t("agentWorkspace.traceCorrelation")}</h4>
              <p>{t("agentWorkspace.traceCorrelationDescription")}</p>
            </div>
            <dl className="aw-mpa-correlation">
              {fields.map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{correlationValue(correlation, key) || t("agentWorkspace.notAvailable")}</dd>
                </div>
              ))}
              {workerFields.map(([key, label]) => (
                <div key={`worker-${key}`}>
                  <dt>{label}</dt>
                  <dd>{workerCorrelationValue(correlation, key) || t("agentWorkspace.notAvailable")}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="aw-session-config-card">
            <div>
              <h4>{t("agentWorkspace.traceSteps")}</h4>
              <p>{t("agentWorkspace.traceStepsDescription")}</p>
            </div>
            {trace?.steps.length ? (
              <div className="aw-usage-table-wrap">
                <table className="aw-usage-table aw-mpa-trace-table">
                  <caption>{t("agentWorkspace.traceSteps")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("agentWorkspace.step")}</th>
                      <th scope="col">{t("agentSelector.status")}</th>
                      <th scope="col">{t("agentWorkspace.duration")}</th>
                      <th scope="col">{t("agentWorkspace.turnId")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trace.steps.slice(0, 20).map((step) => (
                      <tr key={step.stepId}>
                        <td><strong>{step.title || step.kind}</strong><small>{step.kind}</small></td>
                        <td>{step.status}</td>
                        <td>{formatDurationMs(step.durationMs, t)}</td>
                        <td>{correlationValue(step.correlation, "turnId") || t("agentWorkspace.notAvailable")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="aw-session-config-value">
                <span>{t("agentWorkspace.noTraceSteps")}</span>
              </div>
            )}
          </section>
        </>
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

function formatCaseTime(value: string, locale: string, t: TFunction): string {
  const time = caseTimeValue(value);
  if (!time) return t("agentWorkspace.unknownTime");
  return new Intl.DateTimeFormat(locale, {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(time));
}

function formatCaseScore(item: AgentCase, t: TFunction): string {
  if (typeof item.score !== "number") return "—";
  if (!Number.isFinite(item.score)) return "—";
  return t("agentWorkspace.scoreValue", { score: Math.round(item.score * 100) });
}

function optimizationPriorityLabel(priority: OptimizationPriority, t: TFunction): string {
  return t(`agentWorkspace.priority.${priority}`);
}

const OPTIMIZATION_MODULE_KEYS: Record<OptimizationModule, string> = {
  agent_structure: "agentWorkspace.modules.agentStructure",
  prompt: "agentWorkspace.modules.prompt",
  tool: "agentWorkspace.modules.tool",
  knowledge: "agentWorkspace.modules.knowledge",
  memory: "agentWorkspace.modules.memory",
  workflow: "agentWorkspace.modules.workflow",
  other: "agentWorkspace.modules.other",
};

function optimizationModuleLabel(group: OptimizationGroup, t: TFunction): string {
  if (group.module === "other") {
    return group.customModule?.trim() || t("agentWorkspace.modules.other");
  }
  return t(OPTIMIZATION_MODULE_KEYS[group.module]);
}

function feedbackSetFor(
  sets: AgentFeedbackSetSummary[],
  kind: CaseKind,
): AgentFeedbackSetSummary | undefined {
  return sets.find((set) => set.kind === kind);
}

function feedbackCasesFromResponse(
  response: AgentFeedbackCasesResponse,
  t: TFunction,
): AgentCase[] {
  return response.items
    .map((item) => ({
      ...item,
      tag: t(
        item.kind === "good"
          ? "agentWorkspace.goodCase"
          : "agentWorkspace.badCase",
      ),
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

function baseDeploymentSteps(t: TFunction) {
  return [
    { phase: "prepare", label: t("agentWorkspace.deploymentSteps.prepare.label"), description: t("agentWorkspace.deploymentSteps.prepare.description") },
    { phase: "build", label: t("agentWorkspace.deploymentSteps.build.label"), description: t("agentWorkspace.deploymentSteps.build.description") },
    { phase: "deploy", label: t("agentWorkspace.deploymentSteps.deploy.label"), description: t("agentWorkspace.deploymentSteps.deploy.description") },
    { phase: "publish", label: t("agentWorkspace.deploymentSteps.publish.label"), description: t("agentWorkspace.deploymentSteps.publish.description") },
    { phase: "complete", label: t("agentWorkspace.deploymentSteps.complete.label"), description: t("agentWorkspace.deploymentSteps.complete.description") },
  ];
}
function instanceUpdateStep(range: { min: number; max: number }, t: TFunction) {
  return {
    phase: "update",
    label: t("agentWorkspace.deploymentSteps.update.label"),
    description: t("agentWorkspace.deploymentSteps.update.description", range),
  };
}

function deploymentSteps(task: DeploymentTaskUpdate, t: TFunction): Array<{
  phase: string;
  label: string;
  description: string;
}> {
  const baseSteps = baseDeploymentSteps(t);
  const steps: Array<{ phase: string; label: string; description: string }> = [
    ...baseSteps.slice(0, -1),
  ];
  if (task.instanceRange) steps.push(instanceUpdateStep(task.instanceRange, t));
  if (task.createEvaluationSets) {
    steps.push({ phase: "evaluation", label: t("agentWorkspace.deploymentSteps.evaluation.label"), description: t("agentWorkspace.deploymentSteps.evaluation.description") });
  }
  if (task.mpaProfile) {
    steps.push({ phase: "profile_applying", label: t("agentWorkspace.deploymentSteps.profileApplying.label"), description: t("agentWorkspace.deploymentSteps.profileApplying.description") });
    if (task.mpaSmoke) {
      steps.push({ phase: "smoke_running", label: t("agentWorkspace.deploymentSteps.smokeRunning.label"), description: t("agentWorkspace.deploymentSteps.smokeRunning.description") });
      steps.push({ phase: "runnable", label: t("agentWorkspace.deploymentSteps.runnable.label"), description: t("agentWorkspace.deploymentSteps.runnable.description") });
    }
  }
  if (task.githubDelivery) {
    steps.push({ phase: "github", label: t("agentWorkspace.deploymentSteps.github.label"), description: t("agentWorkspace.deploymentSteps.github.description") });
  }
  steps.push(baseSteps[baseSteps.length - 1]);
  return steps;
}

function deploymentStepIndex(task: DeploymentTaskUpdate, t: TFunction): number {
  const steps = deploymentSteps(task, t);
  if (task.status === "success") return steps.length - 1;
  const phase = task.phase ?? ({
    准备部署: "prepare",
    构建镜像: "build",
    部署: "deploy",
    发布: "publish",
    创建评测集: "evaluation",
    "应用 MPA Profile": "profile_applying",
    "验证 MPA Runtime": "smoke_running",
    "MPA Runtime 可运行": "runnable",
    "挂载 GitHub 持续交付": "github",
    部署完成: "complete",
  } as Record<string, string>)[task.label];
  const index = steps.findIndex((step) => step.phase === phase);
  return index < 0 ? 0 : index;
}

function formatBuildLogTime(updatedAt: number, locale: string): string {
  if (!updatedAt) return "";
  try {
    return new Intl.DateTimeFormat(locale, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(updatedAt));
  } catch {
    return "";
  }
}

type DeploymentLogSnapshot = NonNullable<DeploymentTaskUpdate["buildLog"]>;

function DeploymentStepLog({
  log,
  autoExpand,
  title,
  ariaLabel,
  copyLabel,
  defaultPendingMessage,
}: {
  log?: DeploymentLogSnapshot;
  autoExpand: boolean;
  title: string;
  ariaLabel: string;
  copyLabel: string;
  defaultPendingMessage: string;
}) {
  const { t, i18n } = useTranslation("ui");
  const logTextRef = useRef<HTMLPreElement | null>(null);
  const shouldAutoExpand = Boolean(log?.status !== "complete" && autoExpand);
  const [expanded, setExpanded] = useState(shouldAutoExpand);
  const [copied, setCopied] = useState(false);
  const hasLogText = Boolean(log?.text || log?.error);
  const text = log?.text || log?.error || "";
  const lines = text.split("\n");
  const visibleText = expanded ? text : lines.slice(-36).join("\n");
  const pendingMessage = log?.pendingMessage || defaultPendingMessage;

  useEffect(() => {
    if (!log) return;
    setExpanded(shouldAutoExpand);
  }, [log?.status, shouldAutoExpand]);

  useEffect(() => {
    if (!expanded || !hasLogText) return;
    const node = logTextRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [expanded, hasLogText, visibleText]);

  if (!log || (!log.text && log.status !== "error" && !log.pendingMessage)) return null;

  const updatedAt = formatBuildLogTime(log.updatedAt, i18n.resolvedLanguage ?? i18n.language);
  const statusLabel = log.status === "complete"
    ? t("agentWorkspace.logStatus.synced")
    : log.status === "error"
      ? t("agentWorkspace.logStatus.failed")
      : t("agentWorkspace.logStatus.syncing");
  const truncationLabel = log.omittedEarly
    ? t("agentWorkspace.logStatus.earlyOmitted")
    : log.snapshotTruncated
      ? t("agentWorkspace.logStatus.recentOnly")
      : log.truncated
        ? t("agentWorkspace.logStatus.partiallyOmitted")
        : "";
  const meta = [
    statusLabel,
    log.lineCount ? t("agentWorkspace.logLines", { count: log.lineCount }) : "",
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
      aria-label={ariaLabel}
    >
      <header>
        <div>
          <strong>{title}</strong>
          <span>{meta}</span>
        </div>
        <div className="aw-deploy-log-actions">
          {hasLogText && (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? t("common.collapse") : t("common.expand")}
            </button>
          )}
          {hasLogText && (
            <button
              type="button"
              onClick={() => void copyLog()}
              aria-label={copied ? t("agentWorkspace.copiedLabel", { label: copyLabel }) : t("agentWorkspace.copyLabel", { label: copyLabel })}
              title={copied ? t("agentWorkspace.copied") : t("agentWorkspace.copyLabel", { label: copyLabel })}
            >
              {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
              <span>{copied ? t("agentWorkspace.copied") : t("agentWorkspace.copy")}</span>
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

function DeploymentBuildLog({ task }: { task: DeploymentTaskUpdate }) {
  const { t } = useTranslation("ui");
  return (
    <DeploymentStepLog
      log={task.buildLog}
      autoExpand={Boolean(
        task.buildLog?.status !== "complete"
        && (task.status === "running" || task.status === "error")
        && deploymentStepIndex(task, t) === 1,
      )}
      title={t("agentWorkspace.buildLog")}
      ariaLabel={t("agentWorkspace.buildLog")}
      copyLabel={t("agentWorkspace.buildLog")}
      defaultPendingMessage={t("agentWorkspace.waitingBuildLog")}
    />
  );
}

function DeploymentGithubLog({ task }: { task: DeploymentTaskUpdate }) {
  const { t } = useTranslation("ui");
  return (
    <DeploymentStepLog
      log={task.githubLog}
      autoExpand={Boolean(
        task.githubLog?.status !== "complete"
        && (task.status === "running" || task.status === "error")
        && task.phase === "github",
      )}
      title={t("agentWorkspace.githubMountLog")}
      ariaLabel={t("agentWorkspace.githubDeliveryMountLog")}
      copyLabel={t("agentWorkspace.githubMountLog")}
      defaultPendingMessage={t("agentWorkspace.waitingGithubMountLog")}
    />
  );
}

function DeploymentProgressCard({
  task,
  onReturnToEdit,
}: {
  task: DeploymentTaskUpdate;
  onReturnToEdit?: () => void;
}) {
  const { t } = useTranslation("ui");
  const steps = deploymentSteps(task, t);
  const currentIndex = deploymentStepIndex(task, t);
  const progress = task.status === "success"
    ? 100
    : Math.max(6, Math.min(100, task.pct ?? 6));
  const title = task.status === "running" && task.statusUnconfirmed
    ? t("agentWorkspace.deployStatus.unconfirmed")
    : task.status === "running"
      ? t("agentWorkspace.deployStatus.running")
      : task.status === "success"
        ? t("agentWorkspace.deployStatus.success")
        : task.status === "error"
          ? t("agentWorkspace.deployStatus.error")
          : t("agentWorkspace.deployStatus.cancelled");

  return (
    <section
      className={`aw-deploy-progress-card is-${task.status}`}
      aria-live="polite"
    >
      <div className="aw-deploy-progress-head">
        <div>
          <span className="aw-deploy-progress-icon" aria-hidden>
            {task.status === "running" && task.statusUnconfirmed ? (
              <CircleAlert />
            ) : task.status === "running" ? (
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
        <strong>
          {task.status === "running" && !task.statusUnconfirmed
            ? `${Math.round(progress)}%`
            : task.label}
        </strong>
      </div>

      <div
        className="aw-deploy-progress-track"
        role="progressbar"
        aria-label={t("agentWorkspace.deploymentProgress")}
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
          const message = index === currentIndex
            ? localizeDeployStageMessage(task)
            : undefined;
          return (
            <li key={step.phase} className={`is-${status}`}>
              <span className="aw-deploy-step-marker" aria-hidden>
                {status === "done" ? (
                  <Check />
                ) : status === "active" ? (
                  task.statusUnconfirmed ? <CircleAlert /> : <Loader2 className="spin" />
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
                {step.phase === "github" && task.githubLog && (
                  <div className="aw-deploy-step-log">
                    <DeploymentGithubLog task={task} />
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
          >{t("agentWorkspace.returnToEdit")}</button>
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
  currentSessionId?: string;
  currentRuntimeId?: string;
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
  onEditMpaProfile?: (target: MpaProfileEditTarget) => void;
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
  currentSessionId = "",
  currentRuntimeId = "",
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
  onEditMpaProfile,
  onEditDraft,
}: AgentWorkspaceProps) {
  const { t, i18n } = useTranslation("ui");
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
  const [githubVersions, setGithubVersions] =
    useState<GithubDeliveryVersionsResult | null>(null);
  const [githubVersionsLoading, setGithubVersionsLoading] = useState(false);
  const [githubVersionsError, setGithubVersionsError] = useState("");
  const [rollbackCommit, setRollbackCommit] = useState("");
  const [updateCapability, setUpdateCapability] = useState<{
    requestKey: string;
    value: RuntimeUpdateCapability;
  } | null>(null);
  const [updateCapabilityLoading, setUpdateCapabilityLoading] = useState(false);
  const [updateCapabilityError, setUpdateCapabilityError] = useState("");
  const [detailAgentInfo, setDetailAgentInfo] = useState<AgentInfo | null>(null);
  const [detailAgentInfoResolved, setDetailAgentInfoResolved] = useState(false);
  const [detailAgentInfoError, setDetailAgentInfoError] = useState("");
  const [detailAgentInfoUnsupported, setDetailAgentInfoUnsupported] = useState(false);
  const [runtimeDetailError, setRuntimeDetailError] = useState("");
  const [detailReloadToken, setDetailReloadToken] = useState(0);
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
  const [sessionExecutionConfig, setSessionExecutionConfig] =
    useState<SessionExecutionConfigState | null>(null);
  const [mpaProfileStatus, setMpaProfileStatus] =
    useState<MpaProfileStatusState | null>(null);
  const [mpaAgentView, setMpaAgentView] = useState<MpaAgentViewState | null>(null);
  const [mpaAgentViewLoading, setMpaAgentViewLoading] = useState(false);
  const [mpaAgentViewError, setMpaAgentViewError] = useState("");
  const [mpaDiagnostics, setMpaDiagnostics] =
    useState<MpaDiagnosticsState | null>(null);
  const [mpaDiagnosticsLoading, setMpaDiagnosticsLoading] = useState(false);
  const [mpaDiagnosticsError, setMpaDiagnosticsError] = useState("");
  const [mpaDiagnosticsReloadToken, setMpaDiagnosticsReloadToken] = useState(0);
  const [sessionConfigModelInput, setSessionConfigModelInput] = useState("");
  const [sessionConfigLoading, setSessionConfigLoading] = useState(false);
  const [sessionConfigSaving, setSessionConfigSaving] = useState(false);
  const [sessionConfigUpgradeRunning, setSessionConfigUpgradeRunning] = useState(false);
  const [sessionConfigError, setSessionConfigError] = useState("");
  const [sessionConfigNotice, setSessionConfigNotice] = useState("");
  const [sessionConfigReloadToken, setSessionConfigReloadToken] = useState(0);
  const [mpaProfileApply, setMpaProfileApply] = useState<MpaProfileApplyState>({
    saving: false,
    error: "",
    notice: "",
  });
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
  const sessionExecutionConfigRequestRef = useRef(0);
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
  const selectedAgentCategory: AgentCategory =
    selectedAgent?.agentCategory ?? "general";
  const runtimeDetailForSelectedAgent = runtimeDetail?.runtimeId === selectedAgent?.runtimeId
    ? runtimeDetail
    : null;
  const runtimeDetailMpaInstanceId =
    runtimeDetailForSelectedAgent?.mpaInstanceId;
  const selectedMpaInstanceId =
    selectedAgent?.mpaInstanceId ??
    runtimeDetailMpaInstanceId ??
    selectedAgent?.runtimeId ??
    "";
  const visibleAgentSectionIds = AGENT_SECTIONS.filter((item) => {
    if (item === "profileConfig") return selectedAgentCategory === "mpa";
    if (item === "usage") return canViewUsage && selectedAgent?.runtimeId;
    if (item === "sessionConfig") return selectedAgentCategory === "mpa";
    if (item === "diagnostics") return selectedAgentCategory === "mpa" && selectedAgent?.runtimeId;
    return true;
  });
  const visibleAgentSections = visibleAgentSectionIds.map((id) => ({
    id,
    label: t(`agentWorkspace.sections.${id}`),
  }));
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
  const sessionConfigRequestKey = JSON.stringify([
    selectedAgent?.runtimeId ?? "",
    selectedMpaInstanceId,
    selectedAgent?.region ?? "cn-beijing",
    currentSessionId,
  ]);
  const mpaAgentViewRequestKey = JSON.stringify([
    selectedAgent?.runtimeId ?? "",
    selectedMpaInstanceId,
    selectedAgent?.region ?? "cn-beijing",
  ]);
  const mpaProfileStatusRequestKey = mpaAgentViewRequestKey;
  const mpaDiagnosticsRequestKey = JSON.stringify([
    selectedAgent?.runtimeId ?? "",
    selectedAgent?.region ?? "cn-beijing",
    currentSessionId,
  ]);
  const selectedRevealedApiKey =
    revealedApiKey?.requestKey === integrationRequestKey
      ? revealedApiKey.value
      : "";
  const selectedIntegrationProbe =
    integrationProbe?.requestKey === integrationRequestKey
      ? integrationProbe
      : null;
  const selectedSessionExecutionConfig =
    sessionExecutionConfig?.requestKey === sessionConfigRequestKey && currentSessionId
      ? sessionExecutionConfig.value
      : null;
  const selectedMpaAgentView =
    mpaAgentView?.requestKey === mpaAgentViewRequestKey
      ? mpaAgentView.value
      : null;
  const selectedMpaProfileStatus =
    mpaProfileStatus?.requestKey === mpaProfileStatusRequestKey
      ? mpaProfileStatus.value
      : selectedMpaAgentView?.profile ?? null;
  const selectedMpaBindingStatus = selectedMpaAgentView?.bindingStatus ?? "";
  const mpaProfileCanWrite = selectedMpaAgentView?.capabilities.canWrite === true;
  const selectedMpaDiagnostics =
    mpaDiagnostics?.requestKey === mpaDiagnosticsRequestKey
      ? mpaDiagnostics
      : null;
  const mpaProfileRuntimeReady = Boolean(
    selectedAgent?.runtimeId &&
    selectedAgentCategory === "mpa" &&
    selectedMpaBindingStatus !== "runtime_missing" &&
    selectedMpaBindingStatus !== "binding_ambiguous",
  );
  const sessionExecutionConfigLoadable = Boolean(
    selectedAgent?.agentCategory === "mpa" &&
    selectedAgent?.runtimeId &&
    selectedAgent?.runtimeId === currentRuntimeId &&
    selectedMpaBindingStatus === "bound" &&
    currentSessionId,
  );
  const latestProfileRevision =
    selectedMpaProfileStatus?.status === "applied"
      ? selectedMpaProfileStatus.profileRevision
      : null;
  const profileUpgradeAvailable = Boolean(
    sessionExecutionConfigLoadable &&
    selectedSessionExecutionConfig &&
    latestProfileRevision != null &&
    latestProfileRevision > selectedSessionExecutionConfig.profileRevision,
  );
  const currentModelId = effectiveModelId(selectedSessionExecutionConfig);
  const modelInputDirty =
    sessionConfigModelInput.trim() !== currentModelId;
  const apiIntegrationAvailable = Boolean(selectedIntegrationProbe?.apiApps?.length);
  const a2aIntegrationAvailable = Boolean(selectedIntegrationProbe?.a2a);
  const apiIntegrationAppName =
    selectedIntegrationProbe?.apiApps?.[0] ?? selectedAgentAppName;
  const runtimeEndpoint = runtimeDetail?.endpoint ?? "";
  const a2aEndpoint = normalizeRuntimeA2aEndpoint(
    selectedIntegrationProbe?.a2a?.endpoint ?? "",
    runtimeEndpoint,
  );
  const capabilityRuntimeAppName = selectedAgent?.runtimeApp || "";
  const updateCapabilityRequestKey = JSON.stringify([
    selectedAgent?.runtimeId ?? "",
    selectedAgent?.region ?? "",
    selectedAgent?.currentVersion ?? null,
    capabilityRuntimeAppName,
  ]);
  const cachedUpdateCapability = canUpdate &&
    selectedAgent?.runtimeId &&
    selectedAgent.region &&
    detailReloadToken === 0
    ? getCachedRuntimeUpdateCapability({
        runtimeId: selectedAgent.runtimeId,
        region: selectedAgent.region,
        appName: capabilityRuntimeAppName,
        currentVersion: selectedAgent.currentVersion,
      })
    : null;
  const selectedUpdateCapability =
    updateCapability?.requestKey === updateCapabilityRequestKey
      ? updateCapability.value
      : cachedUpdateCapability;
  const updateCapabilityReason = selectedUpdateCapability?.reason
    ? localeCompatibleBackendText(
        selectedUpdateCapability.reason,
        i18n.resolvedLanguage || i18n.language,
      )
    : "";
  const updateCapabilityWarnings = selectedUpdateCapability?.warnings.filter(
    (warning) => localeCompatibleBackendText(
      warning,
      i18n.resolvedLanguage || i18n.language,
    ),
  ) ?? [];
  const shouldLoadUpdateCapability = selectedAgentCategory !== "mpa";
  useEffect(() => {
    const requestId = updateCapabilityRequestRef.current + 1;
    updateCapabilityRequestRef.current = requestId;
    setUpdateCapability(null);
    setUpdateCapabilityError("");

    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "";
    if (!shouldLoadUpdateCapability || !canUpdate || !runtimeId || !region) {
      setUpdateCapabilityLoading(false);
      return;
    }

    const cached = detailReloadToken === 0
      ? getCachedRuntimeUpdateCapability({
          runtimeId,
          region,
          appName: capabilityRuntimeAppName,
          currentVersion: selectedAgent?.currentVersion,
        })
      : null;
    if (cached) {
      setUpdateCapability({ requestKey: updateCapabilityRequestKey, value: cached });
      setUpdateCapabilityLoading(false);
      return;
    }

    const controller = new AbortController();
    let pollTimer: number | undefined;
    let pollAttempts = 0;
    const maxPollAttempts = 60;
    setUpdateCapabilityLoading(true);
    const loadCapability = (initial: boolean) => {
      void getRuntimeUpdateCapability({
        runtimeId,
        region,
        appName: capabilityRuntimeAppName,
        currentVersion: selectedAgent?.currentVersion,
        signal: controller.signal,
        force: initial && detailReloadToken > 0,
      }).then((value) => {
        if (requestId !== updateCapabilityRequestRef.current) return;
        const preparing = value.recoveryStatus === "preparing";
        if (
          value.runtime.runtimeId !== runtimeId ||
          value.runtime.region !== region ||
          (!preparing && capabilityRuntimeAppName &&
            value.agent?.appName !== capabilityRuntimeAppName) ||
          (value.canUpdate && !value.agent?.appName)
        ) {
          setUpdateCapabilityError(t("agentWorkspace.errors.updateCapabilityMismatch"));
          return;
        }
        setUpdateCapability({ requestKey: updateCapabilityRequestKey, value });
        setUpdateCapabilityLoading(false);
        if (!preparing) return;
        pollAttempts += 1;
        if (pollAttempts >= maxPollAttempts) {
          setUpdateCapabilityError(
            t("agentWorkspace.errors.updateConfigRestoring"),
          );
          return;
        }
        pollTimer = window.setTimeout(() => loadCapability(false), 1_000);
      }).catch(() => {
        if (
          requestId !== updateCapabilityRequestRef.current ||
          controller.signal.aborted
        ) return;
        setUpdateCapabilityError(t("agentWorkspace.errors.checkUpdateCapability"));
      }).finally(() => {
        if (
          requestId === updateCapabilityRequestRef.current &&
          !controller.signal.aborted
        ) {
          setUpdateCapabilityLoading(false);
        }
      });
    };
    loadCapability(true);
    return () => {
      controller.abort();
      if (pollTimer != null) window.clearTimeout(pollTimer);
    };
  }, [
    canUpdate,
    capabilityRuntimeAppName,
    detailReloadToken,
    selectedAgent?.currentVersion,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
    shouldLoadUpdateCapability,
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
    t("agentWorkspace.noAgentSelected");
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
    if (
      selectedUpdateCapability?.agent &&
      (selectedUpdateCapability.recoveryStatus === "complete" ||
        selectedUpdateCapability.recoveryStatus === "draft-only")
    ) {
      return runtimeAgentDraftFromCloud(
        selectedUpdateCapability.agent,
        cloudProvider,
        selectedUpdateCapability.runtime.configuredEnvKeys,
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
      selectedUpdateCapability,
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
  const profileDraft = useMemo(() => mpaProfileFromAgentDraft(draft), [draft]);
  const updateBlockedReason = selectedDraft
    ? canCreate ? "" : t("agentWorkspace.errors.noCreatePermission")
    : selectedAgentCategory === "mpa"
      ? ""
    : !canUpdate
      ? t("agentWorkspace.errors.noManagePermission")
      : !selectedAgent?.runtimeId
        ? t("agentWorkspace.errors.cloudOnlyUpdate")
        : !selectedAgent.region
          ? t("agentWorkspace.errors.runtimeRegionMissing")
          : updateCapabilityLoading
            ? t("agentWorkspace.errors.checkingUpdateConfig")
            : updateCapabilityError
              ? updateCapabilityError
              : !selectedUpdateCapability
                ? t("agentWorkspace.errors.updateCapabilityPending")
                : selectedUpdateCapability.recoveryStatus !== "complete" &&
                    selectedUpdateCapability.recoveryStatus !== "draft-only"
                  ? updateCapabilityReason ||
                    t("agentWorkspace.errors.originalConfigUnavailable")
                : !selectedUpdateCapability.canUpdate
                  ? updateCapabilityReason || t("agentWorkspace.errors.updateUnsupported")
                  : selectedUpdateCapability.agent?.appName
                    ? ""
                    : t("agentWorkspace.errors.agentInfoMissing");
  const updateReasonId = "aw-update-disabled-reason";
  const profileConfigDisabledReason = !selectedAgent
    ? t("agentWorkspace.sessionConfigNoAgent")
    : selectedAgentCategory !== "mpa"
      ? t("agentWorkspace.sessionConfigNonMpa")
      : mpaAgentViewLoading
        ? t("agentWorkspace.loadingMpaAgentView")
        : mpaAgentViewError
          ? mpaAgentViewError
          : selectedMpaBindingStatus === "runtime_missing"
            ? t("agentWorkspace.mpaRuntimeMissing")
            : selectedMpaBindingStatus === "binding_ambiguous"
              ? t("agentWorkspace.mpaRuntimeBindingAmbiguous")
              : selectedMpaBindingStatus && !mpaProfileRuntimeReady
                ? t("agentWorkspace.mpaRuntimeMissing")
                : !mpaProfileCanWrite
                  ? t("agentWorkspace.errors.noManagePermission")
              : "";
  const sessionConfigDisabledReason = !selectedAgent
    ? t("agentWorkspace.sessionConfigNoAgent")
    : selectedAgentCategory !== "mpa"
      ? t("agentWorkspace.sessionConfigNonMpa")
      : mpaAgentViewLoading
        ? t("agentWorkspace.loadingMpaAgentView")
        : mpaAgentViewError
          ? mpaAgentViewError
          : selectedMpaBindingStatus === "runtime_missing"
            ? t("agentWorkspace.mpaRuntimeMissing")
            : selectedMpaBindingStatus === "binding_ambiguous"
              ? t("agentWorkspace.mpaRuntimeBindingAmbiguous")
              : selectedMpaBindingStatus === "orphan_runtime"
                ? t("agentWorkspace.mpaRuntimeOrphan")
                : !currentSessionId
                  ? t("agentWorkspace.sessionConfigNoSession")
                  : selectedAgent.runtimeId !== currentRuntimeId
                    ? t("agentWorkspace.sessionConfigDifferentRuntime")
                    : "";
  const diagnosticsDisabledReason = !selectedAgent
    ? t("agentWorkspace.sessionConfigNoAgent")
    : selectedAgentCategory !== "mpa"
      ? t("agentWorkspace.sessionConfigNonMpa")
      : mpaAgentViewLoading
        ? t("agentWorkspace.loadingMpaAgentView")
        : mpaAgentViewError
          ? mpaAgentViewError
          : selectedMpaBindingStatus !== "bound"
            ? sessionConfigDisabledReason
            : !currentSessionId
              ? t("agentWorkspace.sessionConfigNoSession")
              : selectedAgent.runtimeId !== currentRuntimeId
                ? t("agentWorkspace.sessionConfigDifferentRuntime")
                : "";
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
      const taskForDraftId = deploymentTasks
        .filter((task) => task.draftId === selectedDraft.id)
        .sort((left, right) => right.startedAt - left.startedAt)[0];
      if (taskForDraftId) return taskForDraftId;
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
    let cancelled = false;
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const mpaInstanceId = selectedMpaInstanceId || runtimeId;
    const region = selectedAgent?.region ?? "cn-beijing";
    const requestKey = mpaAgentViewRequestKey;
    setMpaAgentViewError("");
    if (selectedAgentCategory !== "mpa" || !runtimeId) {
      setMpaAgentView(null);
      setMpaAgentViewLoading(false);
      return;
    }
    const controller = new AbortController();
    setMpaAgentViewLoading(true);
    void getMpaAgentView({
      mpaInstanceId,
      runtimeId,
      region,
      signal: controller.signal,
    })
      .then((value) => {
        if (cancelled) return;
        setMpaAgentView({ requestKey, value });
        setMpaProfileStatus(
          value.profile
            ? { requestKey: mpaProfileStatusRequestKey, value: value.profile }
            : null,
        );
      })
      .catch((error: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setMpaAgentView(null);
        setMpaAgentViewError(
          error instanceof Error ? error.message : t("agentWorkspace.errors.loadMpaAgentView"),
        );
      })
      .finally(() => {
        if (!cancelled) setMpaAgentViewLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [
    detailReloadToken,
    mpaAgentViewRequestKey,
    selectedMpaInstanceId,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
    selectedAgentCategory,
    mpaProfileStatusRequestKey,
    t,
  ]);

  useEffect(() => {
    if (section === "usage" && !canViewUsage) setSection("basic");
  }, [canViewUsage, section]);

  useEffect(() => {
    if (
      section === "sessionConfig" &&
      (!selectedAgent?.runtimeId || selectedAgentCategory !== "mpa")
    ) {
      setSection("basic");
    }
  }, [section, selectedAgent?.runtimeId, selectedAgentCategory]);

  useEffect(() => {
    if (
      section === "diagnostics" &&
      (!selectedAgent?.runtimeId || selectedAgentCategory !== "mpa")
    ) {
      setSection("basic");
    }
  }, [section, selectedAgent?.runtimeId, selectedAgentCategory]);

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
    setDetailAgentInfoError("");
    setDetailAgentInfoUnsupported(false);
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
      .catch((error: unknown) => {
        if (!cancelled && !cached) setDetailAgentInfo(null);
        if (!cancelled) {
          setDetailAgentInfoUnsupported(
            error instanceof RuntimeProbeError && error.unsupported,
          );
          setDetailAgentInfoError(t("agentWorkspace.errors.loadAgentInfo"));
        }
      })
      .finally(() => {
        if (!cancelled) setDetailAgentInfoResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [
    detailOnly,
    detailReloadToken,
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
      .catch(() => {
        if (!cancelled) {
          setOptimizationsError(t("agentWorkspace.errors.loadOptimizations"));
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
          setAgentUsageError(t("agentWorkspace.errors.usageMismatch"));
          return;
        }
        setAgentUsage({ requestKey: agentUsageRequestKey, value: response });
      })
      .catch(() => {
        if (
          requestId !== agentUsageRequestRef.current ||
          controller.signal.aborted
        ) return;
        setAgentUsageError(t("agentWorkspace.errors.loadUsage"));
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

  useEffect(() => {
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const region = selectedAgent?.region ?? "cn-beijing";
    const requestKey = mpaDiagnosticsRequestKey;
    setMpaDiagnosticsError("");
    if (
      section !== "diagnostics" ||
      selectedAgentCategory !== "mpa" ||
      selectedMpaBindingStatus !== "bound" ||
      !runtimeId ||
      !currentSessionId ||
      runtimeId !== currentRuntimeId
    ) {
      setMpaDiagnosticsLoading(false);
      if (section !== "diagnostics") setMpaDiagnostics(null);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    setMpaDiagnosticsLoading(true);
    void getMpaRuntimeConsoleRuns({
      runtimeId,
      region,
      sessionId: currentSessionId,
      signal: controller.signal,
    })
      .then(async (runsResult) => {
        const firstRun = runsResult.runs[0];
        const trace = firstRun
          ? await getMpaRuntimeConsoleTrace({
              runtimeId,
              region,
              sessionId: currentSessionId,
              invocationId: firstRun.invocationId,
              signal: controller.signal,
            })
          : null;
        return { runs: runsResult.runs, trace };
      })
      .then((value) => {
        if (cancelled) return;
        setMpaDiagnostics({ requestKey, ...value });
      })
      .catch((error: unknown) => {
        if (cancelled || controller.signal.aborted) return;
        setMpaDiagnostics(null);
        setMpaDiagnosticsError(
          error instanceof Error ? error.message : t("agentWorkspace.errors.loadMpaDiagnostics"),
        );
      })
      .finally(() => {
        if (!cancelled) setMpaDiagnosticsLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [
    currentRuntimeId,
    currentSessionId,
    mpaDiagnosticsReloadToken,
    mpaDiagnosticsRequestKey,
    section,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
    selectedAgentCategory,
    selectedMpaBindingStatus,
    t,
  ]);

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
        error instanceof Error ? error.message : t("agentWorkspace.errors.loadApiKey"),
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
    setRuntimeDetailError("");
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
        if (!cancelled) {
          setRuntimeDetailError(t("agentWorkspace.errors.loadRuntimeDetails"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    detailReloadToken,
    selectedAgent?.currentVersion,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
  ]);

  useEffect(() => {
    const requestId = sessionExecutionConfigRequestRef.current + 1;
    sessionExecutionConfigRequestRef.current = requestId;
    setSessionConfigError("");
    setSessionConfigNotice("");
    setSessionConfigSaving(false);
    setSessionConfigUpgradeRunning(false);
    if (
      section !== "sessionConfig" ||
      !sessionExecutionConfigLoadable ||
      !selectedAgent?.runtimeId
    ) {
      setSessionConfigLoading(false);
      setSessionExecutionConfig(null);
      setSessionConfigModelInput("");
      return;
    }

    const runtimeId = selectedAgent.runtimeId;
    const mpaInstanceId = selectedMpaInstanceId || runtimeId;
    const region = selectedAgent.region ?? "cn-beijing";
    const requestKey = sessionConfigRequestKey;
    const controller = new AbortController();
    setSessionConfigLoading(true);
    void Promise.all([
      getMpaSessionExecutionConfig({
        runtimeId,
        region,
        sessionId: currentSessionId,
        signal: controller.signal,
      }),
      getMpaProfileStatus({
        runtimeId,
        region,
        mpaInstanceId,
        signal: controller.signal,
      }).catch(() => null),
    ])
      .then(([config, profileStatus]) => {
        if (requestId !== sessionExecutionConfigRequestRef.current) return;
        setSessionExecutionConfig({ requestKey, value: config });
        setSessionConfigModelInput(effectiveModelId(config));
        setMpaProfileStatus(
          profileStatus
            ? { requestKey: mpaProfileStatusRequestKey, value: profileStatus }
            : null,
        );
      })
      .catch((error: unknown) => {
        if (
          requestId !== sessionExecutionConfigRequestRef.current ||
          controller.signal.aborted ||
          (error as Error)?.name === "AbortError"
        ) return;
        setSessionExecutionConfig(null);
        setSessionConfigModelInput("");
        setSessionConfigError(
          error instanceof Error
            ? error.message
            : t("agentWorkspace.errors.loadSessionConfig"),
        );
      })
      .finally(() => {
        if (
          requestId === sessionExecutionConfigRequestRef.current &&
          !controller.signal.aborted
        ) {
          setSessionConfigLoading(false);
        }
      });
    return () => {
      controller.abort();
    };
  }, [
    currentSessionId,
    sessionConfigReloadToken,
    sessionConfigRequestKey,
    sessionExecutionConfigLoadable,
    section,
    mpaProfileStatusRequestKey,
    selectedMpaInstanceId,
    selectedAgent?.region,
    selectedAgent?.runtimeId,
    t,
  ]);

  useEffect(() => {
    let cancelled = false;
    const runtimeId = selectedAgent?.runtimeId ?? "";
    setGithubVersionsError("");
    if (section !== "versions" || !runtimeId) {
      setGithubVersionsLoading(false);
      if (!runtimeId) setGithubVersions(null);
      return;
    }
    setGithubVersionsLoading(true);
    void getGithubDeliveryVersions(runtimeId)
      .then((value) => {
        if (!cancelled) setGithubVersions(value);
      })
      .catch(() => {
        if (!cancelled) {
          setGithubVersions(null);
          setGithubVersionsError(t("agentWorkspace.errors.loadGithubVersions"));
        }
      })
      .finally(() => {
        if (!cancelled) setGithubVersionsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [section, selectedAgent?.currentVersion, selectedAgent?.runtimeId]);

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
      .catch(() => {
        if (!cancelled) {
          setIntegrationProbe(null);
          setIntegrationError(t("agentWorkspace.errors.probeIntegration"));
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
    setFeedbackCases(cached ? feedbackCasesFromResponse(cached, t) : []);
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
        setFeedbackCases(feedbackCasesFromResponse(response, t));
        setFeedbackCasesUnsupported(response.unsupportedMessage ?? "");
      })
      .catch(() => {
        if (!cancelled) {
          setFeedbackCasesError(t("agentWorkspace.errors.loadEvaluations"));
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
    t,
  ]);

  async function createRollbackPr(version: GithubDeliveryVersion) {
    const runtimeId = selectedAgent?.runtimeId ?? "";
    const commitSha = version.commitSha ?? "";
    if (!runtimeId || !commitSha || rollbackCommit) return;
    setRollbackCommit(commitSha);
    setGithubVersionsError("");
    try {
      await createGithubDeliveryRollbackPr({
        runtimeId,
        targetCommitSha: commitSha,
        region: selectedAgent?.region,
        agentCategory: selectedAgentCategory,
      });
      const refreshed = await getGithubDeliveryVersions(runtimeId);
      setGithubVersions(refreshed);
    } catch (error) {
      setGithubVersionsError(
        error instanceof Error ? error.message : t("agentWorkspace.errors.rollbackVersion"),
      );
    } finally {
      setRollbackCommit("");
    }
  }

  function applySessionConfigConflict(error: unknown, fallback: string): boolean {
    if (!(error instanceof MpaExecutionConfigRequestError)) return false;
    if (error.status !== 412 || !error.currentState) return false;
    setSessionExecutionConfig({
      requestKey: sessionConfigRequestKey,
      value: error.currentState,
    });
    setSessionConfigModelInput(effectiveModelId(error.currentState));
    setSessionConfigError(fallback);
    return true;
  }

  async function saveSessionModelOverride(mode: MpaExecutionConfigMode = "replace") {
    if (!selectedAgent?.runtimeId || !selectedSessionExecutionConfig) return;
    const runtimeId = selectedAgent.runtimeId;
    const region = selectedAgent.region ?? "cn-beijing";
    const modelId = sessionConfigModelInput.trim();
    const change = mode === "inherit"
      ? { category: "model", mode }
      : modelId
        ? { category: "model", mode, value: { id: modelId } }
        : { category: "model", mode: "inherit" as const };
    setSessionConfigSaving(true);
    setSessionConfigError("");
    setSessionConfigNotice("");
    try {
      const next = await patchMpaSessionExecutionConfig({
        runtimeId,
        region,
        sessionId: currentSessionId,
        etag: selectedSessionExecutionConfig.etag,
        changes: [change],
      });
      setSessionExecutionConfig({ requestKey: sessionConfigRequestKey, value: next });
      setSessionConfigModelInput(effectiveModelId(next));
      setSessionConfigNotice(t("agentWorkspace.sessionConfigSaved"));
    } catch (error) {
      if (!applySessionConfigConflict(
        error,
        t("agentWorkspace.sessionConfigStale"),
      )) {
        setSessionConfigError(
          executionConfigErrorMessage(
            error,
            t("agentWorkspace.sessionConfigStale"),
          ),
        );
      }
    } finally {
      setSessionConfigSaving(false);
    }
  }

  async function updateSessionMcpMode(mode: Extract<MpaExecutionConfigMode, "clear" | "inherit">) {
    if (!selectedAgent?.runtimeId || !selectedSessionExecutionConfig) return;
    const runtimeId = selectedAgent.runtimeId;
    const region = selectedAgent.region ?? "cn-beijing";
    setSessionConfigSaving(true);
    setSessionConfigError("");
    setSessionConfigNotice("");
    try {
      const next = await patchMpaSessionExecutionConfig({
        runtimeId,
        region,
        sessionId: currentSessionId,
        etag: selectedSessionExecutionConfig.etag,
        changes: [{ category: "mcpServers", mode }],
      });
      setSessionExecutionConfig({ requestKey: sessionConfigRequestKey, value: next });
      setSessionConfigNotice(t("agentWorkspace.sessionConfigSaved"));
    } catch (error) {
      if (!applySessionConfigConflict(
        error,
        t("agentWorkspace.sessionConfigStale"),
      )) {
        setSessionConfigError(
          executionConfigErrorMessage(
            error,
            t("agentWorkspace.sessionConfigStale"),
          ),
        );
      }
    } finally {
      setSessionConfigSaving(false);
    }
  }

  async function upgradeSessionProfileRevision() {
    if (!selectedAgent?.runtimeId || !selectedSessionExecutionConfig || !latestProfileRevision) {
      return;
    }
    const runtimeId = selectedAgent.runtimeId;
    const region = selectedAgent.region ?? "cn-beijing";
    setSessionConfigUpgradeRunning(true);
    setSessionConfigError("");
    setSessionConfigNotice("");
    try {
      const next = await upgradeMpaSessionProfile({
        runtimeId,
        region,
        sessionId: currentSessionId,
        etag: selectedSessionExecutionConfig.etag,
        idempotencyKey: profileUpgradeIdempotencyKey(
          runtimeId,
          currentSessionId,
          latestProfileRevision,
        ),
        targetProfileRevision: latestProfileRevision,
      });
      setSessionExecutionConfig({ requestKey: sessionConfigRequestKey, value: next });
      setSessionConfigModelInput(effectiveModelId(next));
      setSessionConfigNotice(t("agentWorkspace.sessionProfileUpgraded"));
    } catch (error) {
      if (!applySessionConfigConflict(
        error,
        t("agentWorkspace.sessionConfigStale"),
      )) {
        setSessionConfigError(
          executionConfigErrorMessage(
            error,
            t("agentWorkspace.sessionProfileUpgradeFailed"),
          ),
        );
      }
    } finally {
      setSessionConfigUpgradeRunning(false);
    }
  }

  async function applyMpaProfileFromStudio() {
    if (!selectedAgent?.runtimeId) return;
    const runtimeId = selectedAgent.runtimeId;
    const region = selectedAgent.region ?? "cn-beijing";
    const mpaInstanceId = selectedMpaInstanceId || runtimeId;
    const operationKind = selectedMpaProfileStatus?.status === "applied"
      ? "update"
      : "create";
    const runtimeRevision = selectedMpaProfileStatus?.runtimeRevision ||
      selectedMpaProfileStatus?.etag ||
      "";
    const idempotencyKey = await profileIdempotencyKey(
      runtimeId,
      operationKind,
      profileDraft,
    );
    setMpaProfileApply({ saving: true, error: "", notice: "" });
    try {
      const operation = await startMpaAgentOperation({
        operationKind,
        runtimeId,
        region,
        mpaInstanceId,
        sourceProfileId: `studio-runtime:${runtimeId}:${selectedAgentAppName || "a2a-default"}`,
        targetKey: operationKind === "update"
          ? mpaInstanceId
          : `runtime:${region}:${runtimeId}`,
        runtimeRevision: operationKind === "update" ? runtimeRevision : undefined,
        draft,
        idempotencyKey,
      });
      setMpaProfileApply({
        saving: false,
        error: operation.status === "succeeded"
          ? ""
          : operation.safeErrorCode || t("agentWorkspace.profileApplyIncomplete"),
        notice: operation.status === "succeeded"
          ? t("agentWorkspace.profileAppliedNotice", {
              revision: operation.profileRevision ?? t("agentWorkspace.notAvailable"),
            })
          : "",
      });
      setDetailReloadToken((value) => value + 1);
      setSessionConfigReloadToken((value) => value + 1);
    } catch (error) {
      setMpaProfileApply({
        saving: false,
        error: error instanceof Error
          ? error.message
          : t("agentWorkspace.profileApplyFailed"),
        notice: "",
      });
    }
  }

  function editMpaProfileFromStudio() {
    if (!selectedAgent?.runtimeId || selectedAgentCategory !== "mpa") return;
    onEditMpaProfile?.({
      draft,
      runtimeId: selectedAgent.runtimeId,
      mpaInstanceId: selectedMpaInstanceId || selectedAgent.runtimeId,
      name: selectedName,
      region: selectedAgent.region ?? "cn-beijing",
      appName: selectedAgentAppName || "a2a-default",
      currentVersion: selectedAgent.currentVersion ?? runtimeDetail?.currentVersion,
      runtimeRevision:
        selectedMpaProfileStatus?.runtimeRevision ||
        selectedMpaProfileStatus?.etag ||
        undefined,
    });
  }

  useEffect(() => {
    setMpaProfileApply({ saving: false, error: "", notice: "" });
  }, [mpaAgentViewRequestKey]);

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
      tag: t(
        feedbackCasePreview.kind === "good"
          ? "agentWorkspace.goodCase"
          : "agentWorkspace.badCase",
      ),
    };
  }, [feedbackCasePreview, selectedAgent?.runtimeId, selectedAgentAppName, t]);
  const defaultCases = useMemo(() => buildDefaultCases(t), [t]);
  const cases = useMemo(() => {
    if (!selectedAgent?.runtimeId) return defaultCases;
    if (!previewCase) return feedbackCases;
    return [
      previewCase,
      ...feedbackCases.filter((item) =>
        item.id !== previewCase.id &&
        (!item.messageId || item.messageId !== previewCase.messageId)
      ),
    ];
  }, [defaultCases, feedbackCases, previewCase, selectedAgent?.runtimeId]);
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
      ? t("agentWorkspace.deleteOneCaseConfirm")
      : t("agentWorkspace.deleteCasesConfirm", { count: items.length });
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
    if (runtimeCount === 1 && draftCount === 0) {
      void deleteSingleAgent(selectedDeletableAgents[0]);
      return;
    }
    setDeleteError("");
    setDeleteConfirmTarget({
      kind: "selection",
      title: runtimeCount === 1 && draftCount === 0
        ? t("agentWorkspace.deleteAgentTitle")
        : runtimeCount === 0 && draftCount === 1
          ? t("myAgents.deleteDraftTitle")
          : t("agentWorkspace.deleteSelectedTitle"),
      description: runtimeCount === 1 && draftCount === 0
        ? t("agentWorkspace.deleteAgentDescription", { name: selectedDeletableAgents[0].label })
        : runtimeCount === 0 && draftCount === 1
          ? t("agentWorkspace.deleteDraftDescription", { name: selectedDeletableDrafts[0].draft.name || t("agentSelector.unnamedAgent") })
          : t("agentWorkspace.deleteSelectionDescription", {
              count: selectedDeleteCount,
              warning: runtimeCount > 0
                ? t("agentWorkspace.runtimeDeletionWarning", { count: runtimeCount })
                : t("agentWorkspace.draftDeletionWarning"),
            }),
      confirmLabel: runtimeCount === 0 && draftCount === 1 ? t("myAgents.deleteDraft") : t("agentWorkspace.deleteSelected"),
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
          if (!onDeleteAgents) throw new Error(t("agentWorkspace.errors.deleteDeployedUnsupported"));
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
        if (!onDeleteAgents) throw new Error(t("agentWorkspace.errors.deleteDeployedUnsupported"));
        await onDeleteAgents([deleteConfirmTarget.agent]);
        if (activeAgentId === deleteConfirmTarget.agent.id) setActiveAgentId("");
      } else {
        if (!onDeleteDrafts) throw new Error(t("agentWorkspace.errors.deleteDraftUnsupported"));
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

  const deleteSingleAgent = async (agent: AgentEntry) => {
    if (!onDeleteAgents || agent.canDelete !== true || deletingAgents) return;
    setDeleteError("");
    let preview: MpaAgentDeletePreview | null = null;
    if (agent.agentCategory === "mpa") {
      if (!agent.runtimeId || !agent.region) {
        setDeleteError(t("agentWorkspace.errors.loadMpaDeletePreview"));
        return;
      }
      try {
        preview = await getMpaAgentDeletePreview({
          mpaInstanceId: agent.mpaInstanceId ?? agent.runtimeId,
          runtimeId: agent.runtimeId,
          region: agent.region,
        });
      } catch (cause) {
        setDeleteError(cause instanceof Error ? cause.message : String(cause));
        return;
      }
    }
    setDeleteConfirmTarget({
      kind: "agent",
      title: t("agentWorkspace.deleteAgentTitle"),
      description: preview ? (
        <MpaDeletePreviewDetails preview={preview} t={t} />
      ) : (
        t("agentWorkspace.deleteAgentDescription", { name: agent.label })
      ),
      confirmLabel: t("agentWorkspace.deleteAgent"),
      canConfirm: preview ? preview.canDelete : true,
      agent,
    });
  };

  const deleteSingleDraft = (draftItem: WorkspaceAgentDraft) => {
    if (!onDeleteDrafts || deletingAgents) return;
    const name = draftItem.draft.name || t("agentSelector.unnamedAgent");
    setDeleteError("");
    setDeleteConfirmTarget({
      kind: "draft",
      title: t("myAgents.deleteDraftTitle"),
      description: t("agentWorkspace.deleteDraftDescription", { name }),
      confirmLabel: t("myAgents.deleteDraft"),
      draft: draftItem,
    });
  };

  const createEvaluationGroup = () => {
    const id = `eval-${Date.now()}`;
    const nextGroup: EvaluationGroup = {
      id,
      name: t("agentWorkspace.newEvaluationGroupName", { count: evaluationGroups.length + 1 }),
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
          createdAt: t("agentWorkspace.evaluationDefaults.justNow"),
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
      <nav className="aw-view-tabs" aria-label={t("agentWorkspace.workspace")}>
        <button
          type="button"
          className={view === "library" ? "is-active" : ""}
          aria-pressed={view === "library"}
          onClick={() => {
            setView("library");
            setQuery("");
          }}
        >
          {t("agentWorkspace.library")}
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
          {t("agentWorkspace.evaluation")}
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
        <aside className="aw-sidebar" aria-label={view === "library" ? t("agentWorkspace.agentList") : t("agentWorkspace.evaluationGroupList")}>
          <label className="aw-search">
            <Search aria-hidden />
            <input
              value={query}
              onChange={(event) => setQuery(event.currentTarget.value)}
              placeholder={view === "library" ? t("myAgents.searchAgents") : t("agentWorkspace.searchEvaluationGroups")}
              aria-label={view === "library" ? t("myAgents.searchAgents") : t("agentWorkspace.searchEvaluationGroups")}
            />
          </label>
          <button
            type="button"
            className="aw-create-card"
            onClick={view === "library" ? onCreateAgent : createEvaluationGroup}
            disabled={view === "library" && !canCreate}
          >
            <Plus aria-hidden />
            <span>{view === "library" ? t("agentWorkspace.newAgent") : t("agentWorkspace.newEvaluationGroup")}</span>
          </button>
          {view === "library" && (onDeleteAgents || onDeleteDrafts) && (
            <div className={`aw-selection-toolbar${selectionMode ? " is-active" : ""}`}>
              {selectionMode ? (
                <>
                  <span className="aw-selection-count">
                    {t("agentWorkspace.selectedCount", { count: selectedDeleteCount })}
                  </span>
                  <button
                    type="button"
                    onClick={selectAllListedAgents}
                    disabled={deletableItemCount === 0 || deletingAgents}
                  >
                    {t("agentWorkspace.selectAll")}
                  </button>
                  <button
                    type="button"
                    className="aw-selection-danger"
                    onClick={() => void deleteSelectedItems()}
                    disabled={selectedDeleteCount === 0 || deletingAgents}
                  >
                    {deletingAgents ? t("common.deleting") : t("agentWorkspace.deleteSelected")}
                  </button>
                  <button
                    type="button"
                    onClick={clearAgentSelection}
                    disabled={deletingAgents}
                  >
                    {t("common.cancel")}
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
                  {t("common.select")}
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
                <div className="aw-list-empty">{t("agentWorkspace.noMatchingEvaluationGroups")}</div>
              ) : (
                filteredEvaluationGroups.map((group) => (
                  <button
                    type="button"
                    key={group.id}
                    className={`aw-agent-item${group.id === activeEvaluationGroupId ? " is-active" : ""}`}
                    onClick={() => setActiveEvaluationGroupId(group.id)}
                  >
                    <span className="aw-agent-copy aw-eval-group-copy">
                      <strong>{evaluationText(group.name, t)}</strong>
                      <small>{t("agentWorkspace.groupStats", { agents: group.agentIds.length, runs: group.history.length })}</small>
                    </span>
                    <ArrowRight aria-hidden />
                  </button>
                ))
              )
            ) : loadingAgents && listedAgents.length === 0 && filteredDrafts.length === 0 ? (
              <div className="aw-list-empty">{t("agentWorkspace.loadingCloudAgents")}</div>
            ) : agentsError && listedAgents.length === 0 && filteredDrafts.length === 0 ? (
              <div className="aw-list-empty aw-list-error">
                <span>{agentsError}</span>
                {onRetryAgents && (
                  <button type="button" onClick={onRetryAgents}>{t("common.retry")}</button>
                )}
              </div>
            ) : listedAgents.length === 0 && filteredDrafts.length === 0 ? (
              <div className="aw-list-empty">{t("myAgents.noMatchingAgents")}</div>
            ) : (
              <>
                {filteredDrafts.map((item) => {
                  const taskForDraftId = deploymentTasks
                    .filter((candidate) => candidate.draftId === item.id)
                    .sort((left, right) => right.startedAt - left.startedAt)[0];
                  const task = taskForDraftId ?? deploymentTasks
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
                          <strong>{item.draft.name || t("agentSelector.unnamedAgent")}</strong>
                          <span className={`aw-draft-badge${task?.status === "running" ? " is-deploying" : ""}`}>
                            {task?.status === "running" ? t("myAgents.deploying") : t("myAgents.draft")}
                          </span>
                        </span>
                        <small>{item.deploymentTarget ? t("agentWorkspace.updatePending") : t("agentWorkspace.notPublished")}</small>
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
                      ? { label: t("myAgents.deploying"), className: " is-deploying" }
                    : runtimeTask?.status === "error"
                      ? { label: t("agentWorkspace.failed"), className: " is-error" }
                      : runtimeTask?.status === "cancelled"
                        ? { label: t("agentWorkspace.cancelled"), className: " is-muted" }
                        : updateDraft
                          ? { label: t("agentWorkspace.updatePending"), className: "" }
                          : null;
                const metaText = runtimeTask?.status === "running"
                  ? t("agentWorkspace.updatingDeployment")
                  : updateDraft
                    ? t("agentWorkspace.updatePending")
                    : agent.remote
                      ? agent.host || t("agentWorkspace.remoteAgent")
                      : t("agentWorkspace.localAgent");
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
            {t("agentWorkspace.totalCount", { count: view === "library" ? agents.length + standaloneDraftCount : evaluationGroups.length })}
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
            <p>{t("agentWorkspace.noEvaluationGroupSelected")}</p>
          </main>
        ) : !selectedAgent && !selectedDraft && !selectedPendingTask ? (
          <main className="aw-main aw-empty-selection">
            <p>{t("agentWorkspace.noAgentSelected")}</p>
          </main>
        ) : (
          <main className={`aw-main${deploymentInProgress ? " is-deploying" : ""}${detailOnly ? " resource-page" : ""}`}>
            {selectedAgent && !selectedAgentInfo && loadingAgentInfo && (
              <div className="aw-detail-loading" role="status" aria-live="polite">
                <div className="aw-detail-loading-card">
                  <span className="loading-gap-spinner" aria-hidden="true" />
                  <span>
                    <strong>{t("agentWorkspace.loadingAgent")}</strong>
                    <small>{t("agentWorkspace.loadingAgentDescription")}</small>
                  </span>
                </div>
              </div>
            )}
            {section === "integrations" && integrationLoading && (
              <div className="aw-detail-loading" role="status" aria-live="polite">
                <div className="aw-detail-loading-card">
                  <span className="loading-gap-spinner" aria-hidden="true" />
                  <span>
                    <strong>{t("agentWorkspace.probingIntegration")}</strong>
                    <small>{t("agentWorkspace.probingIntegrationDescription")}</small>
                  </span>
                </div>
              </div>
            )}
            <ResourceDetailLayout
              className="aw-agent-detail"
              title={selectedName}
              description={draft.description || (loadingAgentInfo || (detailOnly && !detailAgentInfoResolved) ? t("agentWorkspace.loadingAgentInfo") : t("common.noDescription"))}
              identitySeed={selectedName}
              backLabel={t("agentWorkspace.backToAgentList")}
              onBack={detailOnly ? onBack : undefined}
              meta={(
                <>
                  {displayCurrentVersion != null && <span className="aw-agent-meta">v{displayCurrentVersion}</span>}
                  {selectedDraft && <span className="aw-agent-meta">{t("myAgents.draft")}</span>}
                  {selectedAgentUpdateDraft && <span className="aw-agent-meta">{t("agentWorkspace.updatePending")}</span>}
                  {!selectedAgent && !selectedDraft && selectedPendingTask && (
                    <span className="aw-agent-meta">{selectedPendingTask.label}</span>
                  )}
                </>
              )}
              actionsClassName="aw-head-actions"
              bodyClassName="aw-agent-detail__body"
              actions={(selectedDraft || selectedAgentUpdateDraft || selectedAgent?.canDelete) ? (
                <>
                  {(selectedDraft || selectedAgentUpdateDraft) && (
                    <Button
                      type="button"
                      color="danger"
                      variant="soft"
                      size="lg"
                      pill={false}
                      onClick={() => {
                        const draftToDelete = selectedDraft ?? selectedAgentUpdateDraft;
                        if (draftToDelete) deleteSingleDraft(draftToDelete);
                      }}
                      disabled={deletingAgents}
                      aria-label={t("myAgents.deleteDraft")}
                      title={t("myAgents.deleteDraft")}
                    >
                      <Trash2 aria-hidden />
                      <span>{t("myAgents.deleteDraft")}</span>
                    </Button>
                  )}
                  {selectedAgent?.canDelete && (
                    <Button
                      type="button"
                      color="danger"
                      variant="soft"
                      size="lg"
                      pill={false}
                      onClick={() => void deleteSingleAgent(selectedAgent)}
                      disabled={deletingAgents}
                      aria-label={t("agentWorkspace.deleteAgent")}
                      title={t("agentWorkspace.deleteAgent")}
                    >
                      <Trash2 aria-hidden />
                      <span>{deletingAgents ? t("common.deleting") : t("agentWorkspace.deleteAgent")}</span>
                    </Button>
                  )}
                </>
              ) : undefined}
              sections={visibleAgentSections.map((item) => ({
                key: item.id,
                label: item.label,
                disabled: deploymentInProgress,
                content: item.id === section ? (
                  <>
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
            <div className="aw-content">
              {section === "basic" && (
                <div className="aw-basic-stack">
                  {detailAgentInfoUnsupported && (
                    <Alert
                      className="aw-detail-fetch-alert"
                      color="warning"
                      variant="soft"
                      title={t("agentWorkspace.partialInfoUnavailable")}
                      description={t("agentWorkspace.upgradeRuntimeForDetails")}
                    />
                  )}
                  {((detailAgentInfoError && !detailAgentInfoUnsupported) ||
                    runtimeDetailError) && (
                    <Alert
                      className="aw-detail-fetch-alert"
                      color="danger"
                      variant="soft"
                      title={t("agentWorkspace.detailLoadFailed")}
                      description={t("agentWorkspace.detailLoadFailedDescription")}
                      actions={(
                        <Button
                          type="button"
                          color="danger"
                          variant="soft"
                          size="sm"
                          pill={false}
                          onClick={() => setDetailReloadToken((value) => value + 1)}
                        >
                          {t("common.retry")}
                        </Button>
                      )}
                    />
                  )}
                  {selectedAgentCategory === "mpa" &&
                    (mpaAgentViewLoading ||
                      mpaAgentViewError ||
                      selectedMpaBindingStatus) && (
                      <Alert
                        className="aw-detail-fetch-alert"
                        color={
                          selectedMpaBindingStatus === "bound" &&
                          !mpaAgentViewError
                            ? "success"
                            : "warning"
                        }
                        variant="soft"
                        title={t("agentWorkspace.mpaControlPlane")}
                        description={
                          mpaAgentViewLoading
                            ? t("agentWorkspace.loadingMpaAgentView")
                            : mpaAgentViewError ||
                              t(
                                selectedMpaBindingStatus === "bound"
                                  ? "agentWorkspace.mpaRuntimeBound"
                                  : selectedMpaBindingStatus === "binding_ambiguous"
                                    ? "agentWorkspace.mpaRuntimeBindingAmbiguous"
                                    : selectedMpaBindingStatus === "orphan_runtime"
                                      ? "agentWorkspace.mpaRuntimeOrphan"
                                      : "agentWorkspace.mpaRuntimeMissing",
                              )
                        }
                      />
                    )}
                  {selectedAgent &&
                    selectedAgentCategory !== "mpa" &&
                    selectedUpdateCapability &&
                    !selectedUpdateCapability.canUpdate && (
                      <div
                        className="aw-update-recovery-notice"
                        role={
                          selectedUpdateCapability.recoveryStatus === "preparing"
                            ? "status"
                            : "alert"
                        }
                      >
                        <strong>
                          {selectedUpdateCapability.recoveryStatus === "preparing"
                            ? t("agentWorkspace.restoringUpdateConfig")
                            : t("agentWorkspace.updateConfigUnavailable")}
                        </strong>
                        {updateCapabilityReason && (
                          <span>{updateCapabilityReason}</span>
                        )}
                        {updateCapabilityWarnings.map((warning) => (
                          <span key={warning}>{warning}</span>
                        ))}
                      </div>
                    )}
                  <section className="aw-deployment-panel aw-settings-card">
                    <div className="aw-section-head">
                      <div><h3>{t("agentWorkspace.deploymentConfig")}</h3><p>{t("agentWorkspace.deploymentConfigDescription")}</p></div>
                    </div>
                    <dl className="aw-readonly-config">
                      <div>
                        <dt>{t("agentWorkspace.runtimeStatus")}</dt>
                        <dd className={runtimeDetail?.status.toLowerCase() === "ready" ? "is-ready" : undefined}>
                          {runtimeDetail?.status.toLowerCase() === "ready" && <span className="aw-status-dot" />}
                          {runtimeDetail?.status || t("agentWorkspace.loading")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("agentWorkspace.deploymentRegion")}</dt>
                        <dd>{runtimeDetail?.region || selectedAgent?.region || deploymentTask?.region || t("agentWorkspace.notAvailable")}</dd>
                      </div>
                      <div>
                        <dt>{t("agentWorkspace.networkAccess")}</dt>
                        <dd>
                          {runtimeDetail?.networkTypes.length
                            ? runtimeDetail.networkTypes.join(" / ")
                            : t("agentWorkspace.notAvailable")}
                        </dd>
                      </div>
                    </dl>
                  </section>
                  <section className="aw-canvas-card">
                    <div className="aw-card-head">
                      <strong>{t("agentWorkspace.executionFlow")}</strong>
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
                      <strong>{t("agentWorkspace.details")}</strong>
                    </div>
                    <dl className="aw-facts">
                      <div>
                        <dt>{t("agentSelector.model")}</dt>
                        <dd>
                          {modelNameFromRuntime(selectedAgentInfo?.model) ||
                            draft.modelName ||
                            t("agentWorkspace.notAvailable")}
                        </dd>
                      </div>
                      <div><dt>{t("agentWorkspace.agentCountLabel")}</dt><dd>{selectedAgentInfo?.graph ? countNodes(selectedAgentInfo.graph) : countDraftNodes(draft)}</dd></div>
                      <div>
                        <dt>{t("agentSelector.tools")}</dt>
                        <dd className="aw-fact-badges">
                          {toolNames.length ? toolNames.map((name) => <span key={name}>{name}</span>) : t("agentWorkspace.none")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("agentSelector.skills")}</dt>
                        <dd className="aw-fact-badges">
                          {skillNames === null
                            ? t("agentSelector.previewUnsupported")
                            : skillNames.length
                              ? skillNames.map((name) => <span key={name}>{name}</span>)
                              : t("agentWorkspace.none")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("systemInfo.currentVersion")}</dt>
                        <dd>
                          {displayCurrentVersion != null
                            ? `v${displayCurrentVersion}`
                            : t("agentWorkspace.notAvailable")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("agentSelector.status")}</dt>
                        <dd>
                          {selectedDraft
                            ? t("myAgents.draft")
                            : deploymentTask?.status === "error"
                              ? t("agentWorkspace.deploymentFailed")
                              : deploymentTask?.status === "cancelled"
                                ? t("agentWorkspace.cancelled")
                                : selectedAgentUpdateDraft
                                  ? t("agentWorkspace.updatePending")
                                  : <><span className="aw-status-dot" />{t("skillCenter.status.available")}</>}
                        </dd>
                      </div>
                    </dl>
                  </section>
                  <section
                    className="aw-sidecar-panel aw-settings-card"
                    aria-label={t("agentWorkspace.selectedOptimizations")}
                  >
                    <div className="aw-section-head">
                      <div>
                        <h3>{t("agentWorkspace.selectedOptimizations")}</h3>
                        <p>{t("agentWorkspace.selectedOptimizationsDescription")}</p>
                      </div>
                    </div>
                    <dl className="aw-readonly-config">
                      <div>
                        <dt>{t("agentWorkspace.configurationStatus")}</dt>
                        <dd className={publishedHarnessSidecar?.enabled ? "is-ready" : undefined}>
                          {publishedHarnessSidecar
                            ? publishedHarnessSidecar.enabled
                              ? <><span className="aw-status-dot" />{t("skillCenter.status.enabled")}</>
                              : t("skillCenter.status.inactive")
                            : t("agentWorkspace.notRecorded")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("agentWorkspace.optimizationProfile")}</dt>
                        <dd>
                          {publishedHarnessSidecar
                            ? harnessSidecarProfileLabel(publishedHarnessSidecar.profile)
                            : t("agentWorkspace.legacyConfigMissing")}
                        </dd>
                      </div>
                      <div>
                        <dt>{t("agentWorkspace.selectedOptimizations")}</dt>
                        <dd className="aw-fact-badges">
                          {!publishedHarnessSidecar
                            ? t("agentWorkspace.legacyConfigMissing")
                            : publishedHarnessOptimizations.length
                              ? publishedHarnessOptimizations.map((optionId) => (
                                  <span key={optionId}>
                                    {harnessSidecarOptionLabel(optionId)}
                                  </span>
                                ))
                              : t("agentWorkspace.noneSelected")}
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
                    <h3>{t("agentWorkspace.usageOverview")}</h3>
                  </div>
                  {agentUsageLoading && !selectedAgentUsage && (
                    <div className="aw-usage-state" role="status" aria-live="polite">
                      <TextShimmer as="span">{t("agentWorkspace.loadingUsage")}</TextShimmer>
                    </div>
                  )}
                  {agentUsageError && (
                    <div className="aw-usage-state is-error" role="alert">
                      <span>{agentUsageError}</span>
                      <button
                        type="button"
                        onClick={() => setAgentUsageReloadToken((value) => value + 1)}
                      >
                        {t("common.retry")}
                      </button>
                    </div>
                  )}
                  {!agentUsageLoading &&
                    !agentUsageError &&
                    !selectedAgentUsage &&
                    !selectedAgentAppName && (
                      <div className="aw-usage-state">
                        {t("agentWorkspace.usageUnavailable")}
                      </div>
                    )}
                  {selectedAgentUsage && (
                    <>
                      <dl className="aw-usage-summary" aria-label={t("agentWorkspace.usageSummary")}>
                        <div>
                          <dt>{t("agentWorkspace.totalCalls")}</dt>
                          <dd>{selectedAgentUsage.totalInvocations.toLocaleString(i18n.resolvedLanguage ?? i18n.language)}</dd>
                        </div>
                        <div>
                          <dt>{t("agentWorkspace.userCount")}</dt>
                          <dd>{selectedAgentUsage.totalUsers.toLocaleString(i18n.resolvedLanguage ?? i18n.language)}</dd>
                        </div>
                      </dl>
                      <div className="aw-usage-users-head">
                        <h3>{t("agentWorkspace.userDetails")}</h3>
                        {agentUsageLoading && (
                          <TextShimmer as="span" role="status" aria-live="polite">
                            {t("agentWorkspace.refreshing")}
                          </TextShimmer>
                        )}
                      </div>
                      {selectedAgentUsage.users.length === 0 ? (
                        <div className="aw-usage-state">
                          {t("agentWorkspace.noUsage")}
                        </div>
                      ) : (
                        <div className="aw-usage-table-wrap">
                          <table className="aw-usage-table">
                            <caption>{t("agentWorkspace.usageUserList")}</caption>
                            <thead>
                              <tr>
                                <th scope="col">{t("agentWorkspace.user")}</th>
                                <th scope="col">{t("agentWorkspace.callCount")}</th>
                                <th scope="col">{t("agentWorkspace.lastUsed")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedAgentUsage.users.map((user) => (
                                <tr key={user.userId}>
                                  <td>
                                    <strong>{user.displayName || user.userId || t("agentWorkspace.unknownUser")}</strong>
                                    {user.displayName && user.userId && (
                                      <small title={user.userId}>{user.userId}</small>
                                    )}
                                  </td>
                                  <td>{user.invocationCount.toLocaleString(i18n.resolvedLanguage ?? i18n.language)}</td>
                                  <td>
                                    <time dateTime={user.lastUsedAt}>
                                      {formatAgentUsageTime(user.lastUsedAt, i18n.resolvedLanguage ?? i18n.language, t)}
                                    </time>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                      {selectedAgentUsage.totalPages > 1 && (
                        <nav className="aw-usage-pagination" aria-label={t("agentWorkspace.usagePagination")}>
                          <button
                            type="button"
                            disabled={agentUsageLoading || selectedAgentUsage.page <= 1}
                            onClick={() => setAgentUsagePage((page) => Math.max(1, page - 1))}
                          >
                            {t("common.previousPage")}
                          </button>
                          <span aria-live="polite">
                            {t("agentWorkspace.pageOf", { page: selectedAgentUsage.page, total: selectedAgentUsage.totalPages })}
                          </span>
                          <button
                            type="button"
                            disabled={
                              agentUsageLoading ||
                              selectedAgentUsage.page >= selectedAgentUsage.totalPages
                            }
                            onClick={() => setAgentUsagePage((page) => page + 1)}
                          >
                            {t("common.nextPage")}
                          </button>
                        </nav>
                      )}
                    </>
                  )}
                </section>
              )}
              {section === "sessionConfig" && (
                <SessionExecutionConfigPanel
                  config={selectedSessionExecutionConfig}
                  profileStatus={selectedMpaProfileStatus}
                  loadable={sessionExecutionConfigLoadable}
                  disabledReason={sessionConfigDisabledReason}
                  loading={sessionConfigLoading}
                  saving={sessionConfigSaving}
                  upgrading={sessionConfigUpgradeRunning}
                  error={sessionConfigError}
                  notice={sessionConfigNotice}
                  modelValue={sessionConfigModelInput}
                  modelDirty={modelInputDirty}
                  profileUpgradeAvailable={profileUpgradeAvailable}
                  onModelChange={setSessionConfigModelInput}
                  onSaveModel={() => void saveSessionModelOverride()}
                  onInheritModel={() => void saveSessionModelOverride("inherit")}
                  onClearMcp={() => void updateSessionMcpMode("clear")}
                  onInheritMcp={() => void updateSessionMcpMode("inherit")}
                  onUpgradeProfile={() => void upgradeSessionProfileRevision()}
                  onRefresh={() => setSessionConfigReloadToken((value) => value + 1)}
                />
              )}
              {section === "profileConfig" && (
                <MpaProfileConfigPanel
                  profile={profileDraft}
                  profileStatus={selectedMpaProfileStatus}
                  runtimeReady={Boolean(
                    selectedAgent?.runtimeId &&
                    selectedAgentCategory === "mpa" &&
                    selectedMpaBindingStatus !== "runtime_missing" &&
                    selectedMpaBindingStatus !== "binding_ambiguous",
                  )}
                  disabledReason={profileConfigDisabledReason}
                  saving={mpaProfileApply.saving}
                  error={mpaProfileApply.error}
                  notice={mpaProfileApply.notice}
                  onApply={() => void applyMpaProfileFromStudio()}
                  onEditProfile={editMpaProfileFromStudio}
                  onRefresh={() => setDetailReloadToken((value) => value + 1)}
                />
              )}
              {section === "diagnostics" && (
                <MpaDiagnosticsPanel
                  data={selectedMpaDiagnostics}
                  loadable={!diagnosticsDisabledReason}
                  disabledReason={diagnosticsDisabledReason}
                  loading={mpaDiagnosticsLoading}
                  error={mpaDiagnosticsError}
                  onRefresh={() => setMpaDiagnosticsReloadToken((value) => value + 1)}
                  locale={i18n.resolvedLanguage ?? i18n.language}
                />
              )}
              {section === "versions" && (
                <section className="aw-version-stack">
                  <div className="aw-integration-intro">
                    <h3>{t("agentWorkspace.githubVersions")}</h3>
                    <p>
                      {githubVersions?.cicd?.enabled
                        ? t("agentWorkspace.githubVersionsDescription")
                        : t("agentWorkspace.currentVersionOnly")}
                    </p>
                  </div>
                  {githubVersionsLoading && (
                    <div className="aw-case-empty">{t("agentWorkspace.loadingVersions")}</div>
                  )}
                  {githubVersionsError && (
                    <div className="aw-integration-error" role="alert">
                      <span>{githubVersionsError}</span>
                      {selectedAgent?.runtimeId && (
                        <button
                          type="button"
                          onClick={() =>
                            void getGithubDeliveryVersions(
                              selectedAgent.runtimeId ?? "",
                            ).then(setGithubVersions)
                          }
                        >
                          {t("common.retry")}
                        </button>
                      )}
                    </div>
                  )}
                  {!githubVersionsLoading && !githubVersionsError && (
                    <div className="aw-version-list">
                      {githubVersions?.githubSyncError && (
                        <div className="aw-integration-error" role="alert">
                          <span>{githubVersions.githubSyncError}</span>
                        </div>
                      )}
                      {githubVersions?.latestSourceRuntimeStatus
                        && githubVersions.latestSourceRuntimeStatus !== "published"
                        && githubVersions.versions[0]?.commitSha
                        && githubVersions.versions[0].commitSha
                          !== githubVersions.currentCommitSha && (
                          <div className="aw-integration-notice" role="status">
                            <span>
                              {t("agentWorkspace.sourceMergedRuntimeStill")}
                              {githubRuntimeStatusLabel(
                                githubVersions.latestSourceRuntimeStatus,
                                t,
                              )}
                              {t("agentWorkspace.currentProductionVersionHint")}
                            </span>
                          </div>
                        )}
                      {githubVersions?.versions.length ? (
                        githubVersions.versions.map((version) => {
                          const commitSha = version.commitSha ?? "";
                          const runtimeStatus = version.runtimeStatus ?? version.status;
                          const isRollbackEvent = version.changeType === "rollback";
                          const canRollback =
                            Boolean(githubVersions.cicd?.enabled) &&
                            Boolean(commitSha) &&
                            !isRollbackEvent &&
                            commitSha !== githubVersions.currentCommitSha;
                          return (
                            <article
                              className="aw-version-row"
                              key={`${version.version}-${commitSha || version.createdAt}`}
                            >
                              <div>
                                <strong>{githubVersionTitle(version, t)}</strong>
                                <small>{version.createdAt || t("agentWorkspace.noTime")}</small>
                              </div>
                              <div>
                                <span>{t("agentWorkspace.prLink")}</span>
                                {version.pullRequestUrl ? (
                                  <a
                                    href={version.pullRequestUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    {t("agentWorkspace.viewPr")}
                                  </a>
                                ) : (
                                  <em>{t("agentWorkspace.noPr")}</em>
                                )}
                              </div>
                              <div>
                                <span>{t("agentWorkspace.author")}</span>
                                <em>{version.author || "Studio"}</em>
                              </div>
                              <div>
                                <span>{t("agentWorkspace.publishStatus")}</span>
                                <em>{githubRuntimeStatusLabel(runtimeStatus, t)}</em>
                              </div>
                              <div className="aw-version-actions">
                                <button
                                  type="button"
                                  disabled={
                                    !canRollback || rollbackCommit === commitSha
                                  }
                                  onClick={() => void createRollbackPr(version)}
                                >
                                  {rollbackCommit === commitSha
                                    ? t("agentWorkspace.rollingBack")
                                    : t("agentWorkspace.rollbackToVersion")}
                                </button>
                                {version.workflowRunUrl && (
                                  <a
                                    href={version.workflowRunUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    {t("agentWorkspace.viewRelease")}
                                  </a>
                                )}
                              </div>
                            </article>
                          );
                        })
                      ) : (
                        <article className="aw-version-row">
                          <div>
                            <strong>
                              {displayCurrentVersion != null
                                ? `v${displayCurrentVersion}`
                                : t("agentWorkspace.noVersion")}
                            </strong>
                            <small>{runtimeDetail?.updatedAt || t("agentWorkspace.noTime")}</small>
                          </div>
                          <p>{t("agentWorkspace.currentVersionOnly")}</p>
                        </article>
                      )}
                    </div>
                  )}
                </section>
              )}
              {section === "integrations" && (
                <div className="aw-integration-stack">
                  <div className="aw-integration-intro">
                    <h3>{t("agentWorkspace.integrationMethods")}</h3>
                    <p>{t("agentWorkspace.integrationDescription")}</p>
                  </div>
                  {integrationError && (
                    <div className="aw-integration-error" role="alert">
                      <span>{integrationError}</span>
                      <button
                        type="button"
                        onClick={() => setIntegrationReloadToken((value) => value + 1)}
                      >
                        {t("common.retry")}
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
                        aria-label={t("agentWorkspace.integrationProtocol")}
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
                              label: t("agentWorkspace.discoveryEndpoint"),
                              value: apiIntegrationAvailable
                                ? endpointPath(runtimeEndpoint, "/list-apps")
                                : "",
                            },
                            {
                              label: t("agentWorkspace.invocationEndpoint"),
                              value: apiIntegrationAvailable
                                ? endpointPath(runtimeEndpoint, "/run_sse")
                                : "",
                            },
                            {
                              label: t("agentWorkspace.authentication"),
                              value: apiIntegrationAvailable
                                ? authTypeLabel(runtimeDetail?.authType, t)
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
                              label: t("agentWorkspace.invocationUrl"),
                              value: a2aEndpoint,
                            },
                            {
                              label: t("agentWorkspace.authentication"),
                              value: a2aIntegrationAvailable
                                ? authTypeLabel(runtimeDetail?.authType, t)
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
                            <span>{t(kind === "good" ? "agentWorkspace.goodCases" : "agentWorkspace.badCases")}</span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                  <div className="aw-case-filter-bar">
                    <div className="aw-case-filter-stack">
                      <div className="aw-case-filters" aria-label={t("agentWorkspace.caseResultFilter")}>
                        {(["good", "bad"] as const).map((filter) => (
                          <button
                            type="button"
                            key={filter}
                            className={caseFilter === filter ? "is-active" : ""}
                            aria-pressed={caseFilter === filter}
                            onClick={() => setCaseFilter(filter)}
                          >
                            {t(filter === "good" ? "agentWorkspace.goodCase" : "agentWorkspace.badCase")}
                          </button>
                        ))}
                      </div>
                      <div className="aw-case-source-filters" aria-label={t("agentWorkspace.feedbackSourceFilter")}>
                        {(["auto", "user"] as const).map((source) => (
                          <button
                            type="button"
                            key={source}
                            className={caseSourceFilter === source ? "is-active" : ""}
                            aria-pressed={caseSourceFilter === source}
                            onClick={() => setCaseSourceFilter(source)}
                          >
                            {source === "auto" ? t("agentWorkspace.automaticFeedback") : t("agentWorkspace.manualFeedback")}
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
                        placeholder={t("agentWorkspace.searchCasesPlaceholder")}
                        aria-label={t("agentWorkspace.searchCases")}
                      />
                    </label>
                  </div>
                  {canManageCases && (
                    <div className={`aw-case-toolbar${caseSelectionMode ? " is-active" : ""}`}>
                      {caseSelectionMode ? (
                        <>
                          <span className="aw-selection-count">
                            {t("agentWorkspace.selectedCaseCount", { count: selectedVisibleCases.length })}
                          </span>
                          <button
                            type="button"
                            onClick={selectAllVisibleCases}
                            disabled={visibleCases.length === 0 || deletingCases}
                          >
                            {t("agentWorkspace.selectAllVisible")}
                          </button>
                          <button
                            type="button"
                            className="aw-selection-danger"
                            onClick={() => void deleteCases(selectedVisibleCases)}
                            disabled={selectedVisibleCases.length === 0 || deletingCases}
                          >
                            {deletingCases ? t("common.deleting") : t("agentWorkspace.deleteSelected")}
                          </button>
                          <button
                            type="button"
                            onClick={clearCaseSelection}
                            disabled={deletingCases}
                          >
                            {t("common.cancel")}
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
                          {t("agentWorkspace.selectCases")}
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
                    <h3>{t("agentWorkspace.optimizations")}</h3>
                    <p>{t("agentWorkspace.optimizationsDescription")}</p>
                  </div>
                  {optimizationsLoading ? (
                    <div className="aw-optimization-state" role="status">
                      <span className="loading-gap-spinner" aria-hidden="true" />
                      <span>{t("agentWorkspace.loadingOptimizations")}</span>
                    </div>
                  ) : optimizationsError ? (
                    <div className="aw-optimization-state is-error" role="alert">
                      <span>{optimizationsError}</span>
                      <button
                        type="button"
                        onClick={() => setOptimizationsReloadToken((value) => value + 1)}
                      >
                        {t("common.retry")}
                      </button>
                    </div>
                  ) : optimizationGroups.length > 0 ? (
                    <OptimizationTable groups={optimizationGroups} />
                  ) : (
                    <div className="aw-optimization-state">
                      {t("agentWorkspace.noOptimizations")}
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
                    <span>{t("agentWorkspace.chat")}</span>
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
                    disabled={selectedAgentCategory === "mpa" ? false : Boolean(updateBlockedReason)}
                    aria-busy={updateCapabilityLoading || undefined}
                    aria-describedby={updateBlockedReason ? updateReasonId : undefined}
                    onClick={() => {
                      if (selectedAgentCategory === "mpa") {
                        setSection("profileConfig");
                        return;
                      }
                      if (selectedDraft) {
                        onEditDraft?.(selectedDraft);
                        return;
                      }
                      if (selectedUpdateCapability) {
                        onUpdateAgent(selectedUpdateCapability);
                      }
                    }}
                  >
                    {updateCapabilityLoading ? (
                      <>
                        <span
                          className="loading-gap-spinner aw-update-spinner"
                          aria-hidden="true"
                        />
                        <span>{t("agentWorkspace.preparing")}</span>
                      </>
                    ) : selectedAgentCategory === "mpa" ? (
                      t("agentWorkspace.profileConfig")
                    ) : selectedDraft || selectedAgentUpdateDraft ? (
                      t("agentWorkspace.continueEditing")
                    ) : (
                      t("agentWorkspace.update")
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
                  </>
                ) : null,
              }))}
              activeSectionKey={section}
              navigationLabel={t("agentWorkspace.agentDetails")}
              onSectionChange={setSection}
            />
          </main>
        )}
        </div>
        {view === "evaluation" && (
          <div className="aw-evaluation-glass" role="status">
            <span>{t("agentWorkspace.comingSoon")}</span>
          </div>
        )}
      </div>
    </div>
    {deleteConfirmTarget && (
      <StudioConfirmDialog
        variant="danger"
        title={deleteConfirmTarget.title}
        description={deleteConfirmTarget.description}
        confirmLabel={deletingAgents ? t("common.deleting") : deleteConfirmTarget.confirmLabel}
        closeLabel={t("agentWorkspace.closeDeleteConfirmation")}
        busy={deletingAgents}
        confirmDisabled={deleteConfirmTarget.canConfirm === false}
        onCancel={() => setDeleteConfirmTarget(null)}
        onConfirm={() => void confirmDeleteTarget()}
      />
    )}
  </>
  );
}

function OptimizationTable({ groups }: { groups: OptimizationGroup[] }) {
  const { t } = useTranslation("ui");
  return (
    <div className="aw-optimization-table-wrap">
      <table className="aw-optimization-table">
        <thead>
          <tr>
            <th scope="col">{t("agentWorkspace.fixPriority")}</th>
            <th scope="col">{t("agentWorkspace.suggestedModule")}</th>
            <th scope="col">{t("agentWorkspace.suggestionAndReason")}</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr
              key={`${group.priority}:${group.module}:${group.customModule ?? ""}`}
            >
              <td>
                <span className={`aw-priority is-${group.priority}`}>
                  {optimizationPriorityLabel(group.priority, t)}
                </span>
              </td>
              <td>
                <span className="aw-optimization-module">
                  {optimizationModuleLabel(group, t)}
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
  const { t, i18n } = useTranslation("ui");
  return (
    <div className="aw-case-table">
      <div className="aw-case-row aw-case-row-head">
        <span>{t("agentWorkspace.userInput")}</span>
        <span>{t("agentWorkspace.agentOutput")}</span>
        <span>{t("agentWorkspace.score")}</span>
        <span>{t("agentWorkspace.scoreReason")}</span>
        <span className="aw-case-action-head">{t("skillCenter.actions")}</span>
      </div>
      {loading ? (
        <div className="aw-case-empty">{t("agentWorkspace.loadingEvaluationSet")}</div>
      ) : error ? (
        <div className="aw-case-empty aw-case-error">
          <span>{error}</span>
          {onRetry && <button type="button" onClick={onRetry}>{t("common.retry")}</button>}
        </div>
      ) : notice ? (
        <div className="aw-case-empty">{notice}</div>
      ) : cases.length === 0 ? (
        <div className="aw-case-empty">
          {runtimeBacked ? t("agentWorkspace.noFeedbackCases") : t("agentWorkspace.noMatchingCases")}
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
              <div className="aw-case-text aw-case-cell" data-label={t("agentWorkspace.userInput")}>
                <span className="aw-case-title-line">
                  {selectionMode && canDeleteCase && (
                    <span
                      className={`aw-select-marker${isSelected ? " is-checked" : ""}`}
                      aria-hidden="true"
                    />
                  )}
                  <strong title={item.input}>{item.input || t("agentWorkspace.noUserInput")}</strong>
                </span>
                {showComment && <small title={item.comment}>{t("agentWorkspace.note")}{item.comment}</small>}
                <small className="aw-case-time">{formatCaseTime(item.createdAt, i18n.resolvedLanguage ?? i18n.language, t)}</small>
                {(item.userId || item.sessionId) && (
                  <small title={[item.userId, item.sessionId].filter(Boolean).join(" · ")}>
                    {[item.userId, item.sessionId].filter(Boolean).join(" · ")}
                  </small>
                )}
              </div>
              <div
                className={`aw-case-output aw-case-cell${isExpanded ? " is-expanded" : ""}`}
                data-label={t("agentWorkspace.agentOutput")}
              >
                <p className="aw-case-output-preview" title={item.output}>
                  {item.output || t("agentWorkspace.noVisibleResponse")}
                </p>
                {item.referenceOutput && (
                  <small
                    className="aw-case-output-preview"
                    title={item.referenceOutput}
                  >
                    {t("agentWorkspace.reference")}: {item.referenceOutput}
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
                    {isExpanded ? t("common.collapse") : t("common.expand")}
                  </button>
                )}
              </div>
              <div className="aw-case-score aw-case-cell" data-label={t("agentWorkspace.score")}>
                {formatCaseScore(item, t)}
              </div>
              <div
                className={`aw-case-reason aw-case-cell${isExpanded ? " is-expanded" : ""}`}
                data-label={t("agentWorkspace.scoreReason")}
              >
                <p title={item.reason || undefined}>
                  {item.reason || "—"}
                </p>
              </div>
              <div className="aw-case-actions aw-case-cell" data-label={t("skillCenter.actions")}>
                {canDeleteCase && (
                  <button
                    type="button"
                    className="aw-case-delete"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteCase?.(item);
                    }}
                    disabled={deleting}
                    title={t("agentWorkspace.deleteFeedbackCase")}
                    aria-label={t("agentWorkspace.deleteFeedbackCase")}
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
  const { t } = useTranslation("ui");
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
          <div className="aw-agent-title-row"><h2>{evaluationText(group.name, t)}</h2><span>{t("agentWorkspace.evaluationGroup")}</span></div>
          <p>{t("agentWorkspace.evaluationGroupStats", { agents: selectedAgents.length, caseSet: evaluationText(group.caseSet, t), runs: group.history.length })}</p>
        </div>
        <button type="button" className="aw-run" onClick={() => onRun(group)} disabled>
          <FlaskConical aria-hidden />{t("agentWorkspace.startEvaluation")}
        </button>
      </div>
      <nav className="aw-agent-tabs" aria-label={t("agentWorkspace.evaluationGroupDetails")}>
        <button type="button" className={section === "config" ? "is-active" : ""} aria-pressed={section === "config"} onClick={() => setSection("config")} disabled>{t("agentWorkspace.evaluationConfig")}</button>
        <button type="button" className={section === "history" ? "is-active" : ""} aria-pressed={section === "history"} onClick={() => setSection("history")} disabled>{t("agentWorkspace.historyResults")}</button>
      </nav>
      <div className="aw-content">
        {section === "config" ? (
          <div className="aw-eval-setup">
            <section className="aw-eval-block">
              <div className="aw-card-head"><strong>{t("agentWorkspace.participatingAgents")}</strong><span>{t("agentWorkspace.selectedCount", { count: selectedAgents.length })}</span></div>
              <div className="aw-eval-agent-grid">
                {agents.map((agent) => (
                  <label key={agent.id}>
                    <input type="checkbox" checked={group.agentIds.includes(agent.id)} onChange={() => toggleAgent(agent.id)} />
                    <span><strong>{agent.label}</strong><small>{agent.remote ? t("agentWorkspace.remote") : t("agentWorkspace.local")}</small></span>
                  </label>
                ))}
              </div>
            </section>
            <div className="aw-eval-setting-grid">
              <section className="aw-eval-block">
                <div className="aw-card-head"><strong>{t("agentWorkspace.evaluationResources")}</strong></div>
                <div className="aw-eval-fields">
                  <label><span>{t("agentWorkspace.evaluationSet")}</span><select value={group.caseSet} onChange={(event) => onChange({ ...group, caseSet: event.currentTarget.value })}><option value="核心回归集">{t("agentWorkspace.evaluationDefaults.coreSet")}</option><option value="安全边界集">{t("agentWorkspace.evaluationDefaults.safetySet")}</option><option value="工具调用集">{t("agentWorkspace.evaluationDefaults.toolSet")}</option></select><small>{t("agentWorkspace.caseCount", { count: cases.length })}</small></label>
                  <label><span>{t("agentWorkspace.evaluator")}</span><select value={group.evaluator} onChange={(event) => onChange({ ...group, evaluator: event.currentTarget.value })}><option value="综合质量评估器">{t("agentWorkspace.evaluationDefaults.qualityEvaluator")}</option><option value="事实一致性评估器">{t("agentWorkspace.evaluationDefaults.factualEvaluator")}</option><option value="工具调用评估器">{t("agentWorkspace.evaluationDefaults.toolEvaluator")}</option></select></label>
                  <label><span>{t("agentWorkspace.concurrency")}</span><select value={group.concurrency} onChange={(event) => onChange({ ...group, concurrency: event.currentTarget.value })}><option value="2">2</option><option value="4">4</option><option value="8">8</option></select></label>
                </div>
              </section>
              <section className="aw-eval-block">
                <div className="aw-card-head"><strong>{t("agentWorkspace.evaluationMetrics")}</strong><span>{t("agentWorkspace.selectedMetricCount", { count: group.metrics.length })}</span></div>
                <div className="aw-metric-list">
                  {metrics.map((metric) => (
                    <label key={metric}><input type="checkbox" checked={group.metrics.includes(metric)} onChange={() => toggleMetric(metric)} /><span>{evaluationText(metric, t)}</span></label>
                  ))}
                </div>
              </section>
            </div>
          </div>
        ) : (
          <section className="aw-eval-history">
            <div className="aw-section-head"><div><h3>{t("agentWorkspace.historyResults")}</h3><p>{t("agentWorkspace.historyDescription")}</p></div></div>
            {group.history.length === 0 ? (
              <div className="aw-results-empty"><strong>{t("agentWorkspace.noHistory")}</strong><span>{t("agentWorkspace.noHistoryDescription")}</span></div>
            ) : (
              <div className="aw-history-list">
                {group.history.map((run, index) => (
                  <button type="button" key={run.id}>
                    <span><strong>{t("agentWorkspace.evaluationRun", { index: group.history.length - index })}</strong><small>{t("agentWorkspace.evaluationRunMeta", { time: evaluationText(run.createdAt, t), agents: selectedAgents.length })}</small></span>
                    <span className="aw-history-score"><strong>{run.score}</strong><small>{t("agentWorkspace.overallScore")}</small></span>
                    <span className="aw-complete"><Check />{t("agentWorkspace.completed")}</span>
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
