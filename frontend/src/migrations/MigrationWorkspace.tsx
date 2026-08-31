import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import {
  confirmMigrationTask,
  createMigrationTask,
  downloadMigrationArtifact,
  getMigrationActivity,
  getMigrationArtifact,
  getMigrationArtifactFile,
  getMigrationCapabilities,
  getMigrationTask,
  listMigrationTasks,
  MigrationApiError,
  stopMigrationTask,
  submitMigrationAnalysisAnswers,
  uploadMigrationSource,
  type MigrationAnalysis,
  type MigrationActivity,
  type MigrationArtifact,
  type MigrationCapabilities,
  type MigrationFramework,
  type MigrationTask,
} from "../adk/migrations";
import {
  deployAgentkitProject,
  listModelOptions,
  type DeployStage,
  type ModelOption,
} from "../adk/client";
import {
  defaultCloudRegion,
  type CloudProvider,
} from "../adk/cloudProvider";
import type { AgentProject } from "../create/project";
import type {
  IntelligentCreateBaseVersion,
  IntelligentDevelopmentCapabilities,
  IntelligentPreparationStage,
} from "../create/IntelligentCreate";
import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import type { NetworkConfig } from "../create/types";
import type { EnvVar } from "../create/veadkCatalog";
import CodeEditor from "../ui/CodeEditor";
import { Blocks } from "../ui/Blocks";
import { Markdown } from "../ui/Markdown";
import { StudioConfirmDialog } from "../ui/StudioConfirmDialog";
import { NewChatCompactSelect } from "../ui/new-chat-modes/NewChatCompactSelect";
import {
  ProjectPreview,
  type DeployResult,
  type DeploymentTaskUpdate,
} from "../ui/ProjectPreview";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { useStickToBottom } from "../ui/useStickToBottom";
import {
  BackIcon,
  CloseIcon,
  DeployIcon,
  DownloadIcon,
  FileIcon,
  PlusIcon,
  UploadIcon,
} from "./MigrationIcons";
import {
  isMigrationRuntimeEnvironmentKey,
  isSecretEnvironmentKey,
  migrationDeploymentEnvDefaults,
} from "./deploymentEnvironment";
import { migrationActivityBlocks } from "./migrationActivityBlocks";
import { MigratedProjectsPage } from "./MigratedProjectsPage";
import "./MigrationWorkspace.css";

const MAX_SOURCE_BYTES = 20 * 1024 * 1024;
const POLL_INTERVAL_MS = 1_200;
const ACTIVITY_POLL_INTERVAL_MS = 3_000;
const LIST_POLL_INTERVAL_MS = 5_000;
const MAX_VISIBLE_FILES = 500;
const ignoreMigrationAction = () => undefined;

const FRAMEWORK_LABELS: Record<MigrationFramework, string> = {
  langchain: "LangChain",
  langgraph: "LangGraph",
  adk: "Google ADK",
  strands: "Strands",
  agentcore: "AgentCore",
  dify: "Dify",
  any: "Any（通用迁移）",
};

const STRUCTURED_FRAMEWORKS = new Set<MigrationFramework>([
  "langchain",
  "langgraph",
  "adk",
  "strands",
  "agentcore",
]);

interface MigrationWorkspaceProps {
  cloudProvider: CloudProvider;
  onBack: () => void;
  onAgentAdded?: (agentId: string, agentName: string) => void;
  onDeploymentTaskChange?: (task: DeploymentTaskUpdate) => void;
  onDeploymentStarted?: (task: DeploymentTaskUpdate) => void;
  onDeploymentComplete?: (result: DeployResult) => void | Promise<void>;
  initialDeployRegion?: string;
  projectCapabilities: IntelligentDevelopmentCapabilities | null;
  projectCapabilitiesLoading: boolean;
  optimizationPreparationStage: IntelligentPreparationStage | null;
  optimizationError: string;
  onOptimizeVersion: (
    goal: string,
    modelId: string,
    base: IntelligentCreateBaseVersion,
  ) => Promise<void>;
  onCancelOptimization: () => void;
  onDownloadSavedVersion: (
    delivery: IntelligentDevelopmentReleaseRef,
  ) => Promise<void>;
  onDeploySavedVersion: (delivery: IntelligentDevelopmentReleaseRef) => void;
  initialPage?: "new" | "projects";
  initialProjectId?: string;
}

interface PreviewState {
  path: string;
  loading: boolean;
  text?: string;
  imageUrl?: string;
  error?: string;
}

function stateLabel(state: MigrationTask["state"]): string {
  switch (state) {
    case "awaiting_upload":
      return "待上传";
    case "analyzing":
      return "分析中";
    case "needs_input":
      return "待补充";
    case "analysis_ready":
      return "待确认";
    case "migrating":
      return "迁移中";
    case "validating":
      return "校验中";
    case "packaging":
      return "打包中";
    case "succeeded":
      return "已完成";
    case "succeeded_with_warnings":
      return "已完成，有提示";
    case "partial":
      return "部分完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已终止";
    case "expired":
      return "已过期";
  }
}

function taskDisplayMessage(task: MigrationTask): string {
  if (task.state === "partial" && task.artifact.previewReady) {
    return "迁移产物已生成，但交付不完整，请查看迁移提示。";
  }
  if (
    ["succeeded", "succeeded_with_warnings"].includes(task.state) &&
    task.artifact.previewReady
  ) {
    return task.state === "succeeded_with_warnings"
      ? "迁移产物已生成，请查看迁移提示。"
      : "迁移产物已生成。";
  }
  return task.message;
}

function verificationLabel(
  status: MigrationArtifact["verification"]["status"],
): string {
  switch (status) {
    case "passed":
      return "产物校验通过";
    case "failed":
      return "产物校验未通过";
    case "degraded":
      return "产物校验未完成";
  }
}

function MigrationTransferProgress({
  stage,
}: {
  stage: "session" | "upload" | "analysis";
}) {
  const stages = [
    { id: "session", label: "创建迁移环境" },
    { id: "upload", label: "上传项目" },
    { id: "analysis", label: "分析项目" },
  ] as const;
  const activeIndex = stages.findIndex((item) => item.id === stage);
  return (
    <div className="migration-transfer-progress" role="status">
      {stages.map((item, index) => (
        <div
          key={item.id}
          className={
            index < activeIndex
              ? "is-complete"
              : index === activeIndex
                ? "is-active"
                : ""
          }
        >
          <span className="migration-transfer-progress__marker" aria-hidden="true" />
          {index === activeIndex ? (
            <TextShimmer>{item.label}</TextShimmer>
          ) : (
            <strong>{item.label}</strong>
          )}
        </div>
      ))}
    </div>
  );
}

function isActiveState(state: MigrationTask["state"]): boolean {
  return ["analyzing", "migrating", "validating", "packaging"].includes(state);
}

function isTerminalState(state: MigrationTask["state"]): boolean {
  return [
    "succeeded",
    "succeeded_with_warnings",
    "partial",
    "failed",
    "cancelled",
    "expired",
  ].includes(state);
}

function shouldShowCodexActivity(task: MigrationTask): boolean {
  return (
    task.state === "analyzing" ||
    Boolean(task.analysisRef) ||
    Boolean(task.confirmation) ||
    task.error?.code.startsWith("MIGRATION_ANALYSIS_") === true
  );
}

function sourceStem(name: string): string {
  return name.replace(/\.zip$/i, "");
}

function isSelectableMigrationModel(
  model: ModelOption,
  unsupportedModelIds: ReadonlySet<string>,
): boolean {
  return (
    !unsupportedModelIds.has(model.id) &&
    (model.available || model.lifecycleStatus === "Retiring")
  );
}

function defaultAppName(name: string): string {
  const value = sourceStem(name)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (
    (value || "agent-migration").slice(0, 63).replace(/-+$/g, "") ||
    "agent-migration"
  );
}

function appNameError(value: string): string {
  if (!value.trim()) return "请输入 Agent 名称";
  if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(value.trim())) {
    return "Agent 名称必须为 1-63 位，只能包含小写字母、数字和连字符，且必须以字母或数字开头和结尾";
  }
  return "";
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 / 1024).toFixed(1)} MiB`;
}

function formatByteLimit(value: number): string {
  return formatBytes(value)
    .replace(".0 MiB", " MiB")
    .replace(".0 KiB", " KiB");
}

function formatElapsedTime(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function formatDate(value: string | number): string {
  const date =
    typeof value === "number"
      ? new Date(value * 1000)
      : new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function migrationExpiryCopy(
  task: MigrationTask,
  now: number,
): { title: string; detail: string } {
  const sourceSaved = task.persistence?.state === "saved";
  const sourceSaving = task.persistence?.state === "saving";
  const activeDetail = sourceSaved
    ? "已保存项目不受影响"
    : sourceSaving
      ? "源码正在保存，完成后不受环境期限影响"
      : "到期后任务记录和临时产物将无法访问";
  const expiry = new Date(task.expiresAt).getTime();
  if (!Number.isFinite(expiry)) {
    return {
      title: "临时迁移环境保留 1 小时",
      detail: activeDetail,
    };
  }
  if (task.state === "expired" || now >= expiry) {
    return {
      title: "临时迁移环境已结束",
      detail: sourceSaved
        ? "已保存项目仍可查看、下载、部署或优化"
        : "任务记录和临时产物已无法访问",
    };
  }
  const remaining = Math.max(0, expiry - now);
  const minutes = Math.floor(remaining / 60_000);
  const seconds = Math.floor((remaining % 60_000) / 1_000);
  return {
    title: `临时迁移环境将在 ${minutes} 分 ${seconds} 秒后结束`,
    detail: activeDetail,
  };
}

function expireTasksAtDeadline(
  tasks: MigrationTask[],
  now: number,
): MigrationTask[] {
  let changed = false;
  const next = tasks.map((task) => {
    if (task.state === "expired") return task;
    const expiry = new Date(task.expiresAt).getTime();
    if (!Number.isFinite(expiry) || now < expiry) return task;
    changed = true;
    const sourceSaved = task.persistence?.state === "saved";
    return {
      ...task,
      state: "expired" as const,
      message: sourceSaved
        ? "临时迁移环境已结束，已保存项目不受影响。"
        : "临时迁移环境已结束，任务记录和临时产物无法继续访问。",
      canModify: false,
      canUpload: false,
      canAnswer: false,
      canConfirm: false,
      canStop: false,
      artifact: {
        state: "none",
        previewReady: false,
        downloadReady: false,
        deployReady: false,
      },
    };
  });
  return changed ? next : tasks;
}

function upsertTask(
  tasks: MigrationTask[],
  task: MigrationTask,
): MigrationTask[] {
  const next = tasks.filter((item) => item.id !== task.id);
  return [task, ...next].sort((left, right) => {
    const leftTime =
      typeof left.createdAt === "number"
        ? left.createdAt * 1000
        : new Date(left.createdAt).getTime();
    const rightTime =
      typeof right.createdAt === "number"
        ? right.createdAt * 1000
        : new Date(right.createdAt).getTime();
    return rightTime - leftTime;
  });
}

function selectedTask(
  tasks: MigrationTask[],
  taskId: string,
): MigrationTask | null {
  return tasks.find((item) => item.id === taskId) ?? null;
}

function isTextMime(mimeType: string, path: string): boolean {
  return (
    mimeType.startsWith("text/") ||
    /(?:json|javascript|xml|yaml)/i.test(mimeType) ||
    /\.(?:py|ts|tsx|js|jsx|json|ya?ml|md|txt|toml|ini|cfg|env|sh|dockerfile)$/i.test(
      path,
    )
  );
}

function AnalysisSummary({ analysis }: { analysis: MigrationAnalysis }) {
  return (
    <div className="migration-analysis">
      <Markdown text={analysis.summary} allowRawHtml={false} />
      <div className="migration-analysis__facts">
        {analysis.recommended ? (
          <section>
            <h3>建议迁移方式</h3>
            <strong>{FRAMEWORK_LABELS[analysis.recommended.framework]}</strong>
            <p>{analysis.recommended.reason}</p>
          </section>
        ) : null}
        <section>
          <h3>迁移范围</h3>
          <ul>
            {analysis.boundary.include.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        {analysis.boundary.exclude.length > 0 ? (
          <section>
            <h3>不在本次范围</h3>
            <ul>
              {analysis.boundary.exclude.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
      {analysis.frameworks[0]?.evidence.length ? (
        <details className="migration-analysis__evidence">
          <summary>查看分析证据</summary>
          <ul>
            {analysis.frameworks.flatMap((candidate) =>
              candidate.evidence.map((item) => (
                <li key={`${candidate.id}:${item.path}:${item.line}`}>
                  <code>{item.path}:{item.line}</code>
                  <span>{item.reason}</span>
                </li>
              )),
            )}
          </ul>
        </details>
      ) : null}
      {analysis.warnings.length > 0 ? (
        <div className="migration-analysis__warnings">
          {analysis.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}
      {analysis.assumptions.length > 0 ? (
        <details className="migration-analysis__evidence">
          <summary>查看关键假设</summary>
          <ul>
            {analysis.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function MigrationActivityFeed({
  activity,
  loading,
  error,
  analyzing,
}: {
  activity: MigrationActivity | null;
  loading: boolean;
  error: string;
  analyzing: boolean;
}) {
  const items = activity?.items ?? [];
  const blocks = migrationActivityBlocks(items);

  return (
    <section className="migration-activity" aria-label="Codex 执行动态">
      <div className="migration-activity__heading">
        <span
          className={`migration-activity__marker${activity?.complete ? " is-complete" : ""}`}
          aria-hidden="true"
        />
        <strong>Codex 执行动态</strong>
      </div>
      {blocks.length > 0 ? (
        <div className="migration-activity__stream">
          <Blocks blocks={blocks} onAction={ignoreMigrationAction} />
        </div>
      ) : loading || !activity?.complete ? (
        <TextShimmer>
          {analyzing ? "Codex 正在开始分析…" : "Codex 正在开始迁移…"}
        </TextShimmer>
      ) : null}
      {error ? (
        <p className="migration-activity__error" role="status">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function ArtifactBrowser({
  task,
  artifact,
}: {
  task: MigrationTask;
  artifact: MigrationArtifact;
}) {
  const [query, setQuery] = useState("");
  const [activePath, setActivePath] = useState(
    artifact.files[0]?.path ?? "",
  );
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const activeFile =
    artifact.files.find((file) => file.path === activePath) ??
    artifact.files[0];
  const filteredFiles = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    const matches = normalized
      ? artifact.files.filter((file) =>
          file.path.toLocaleLowerCase().includes(normalized),
        )
      : artifact.files;
    return matches.slice(0, MAX_VISIBLE_FILES);
  }, [artifact.files, query]);

  useEffect(() => {
    if (!activeFile) return;
    if (activeFile.size > 2 * 1024 * 1024) {
      setPreview({
        path: activeFile.path,
        loading: false,
        error: "该文件超过 2 MiB，请下载完整产物后查看。",
      });
      return;
    }
    const controller = new AbortController();
    let objectUrl = "";
    setPreview({ path: activeFile.path, loading: true });
    void getMigrationArtifactFile(
      task.id,
      activeFile.path,
      controller.signal,
    )
      .then(async ({ blob, mimeType }) => {
        if (controller.signal.aborted) return;
        if (mimeType.startsWith("image/")) {
          objectUrl = URL.createObjectURL(blob);
          setPreview({
            path: activeFile.path,
            loading: false,
            imageUrl: objectUrl,
          });
          return;
        }
        if (isTextMime(mimeType, activeFile.path)) {
          const text = await blob.text();
          if (controller.signal.aborted) return;
          setPreview({
            path: activeFile.path,
            loading: false,
            text,
          });
          return;
        }
        setPreview({
          path: activeFile.path,
          loading: false,
          error: "该文件不支持在线预览，请下载完整产物后查看。",
        });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setPreview({
          path: activeFile.path,
          loading: false,
          error: cause instanceof Error ? cause.message : String(cause),
        });
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [activeFile, task.id]);

  return (
    <div className="migration-artifact-browser">
      <aside aria-label="迁移产物文件">
        <label className="migration-artifact-browser__search">
          <span className="sr-only">搜索产物文件</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
            placeholder="搜索文件"
          />
        </label>
        <div className="migration-artifact-browser__files">
          {filteredFiles.map((file) => (
            <button
              type="button"
              key={file.path}
              className={file.path === activeFile?.path ? "is-active" : ""}
              onClick={() => setActivePath(file.path)}
              title={file.path}
            >
              <FileIcon />
              <span>{file.path}</span>
              <small>{formatBytes(file.size)}</small>
            </button>
          ))}
        </div>
        {artifact.files.length > filteredFiles.length ? (
          <p className="migration-artifact-browser__limit">
            仅展示前 {MAX_VISIBLE_FILES} 项，请搜索具体文件。
          </p>
        ) : null}
      </aside>
      <section>
        <header>
          <span title={activeFile?.path}>{activeFile?.path || "未选择文件"}</span>
          {activeFile ? <small>{formatBytes(activeFile.size)}</small> : null}
        </header>
        <div className="migration-artifact-browser__preview">
          {!activeFile ? (
            <p>暂无可预览文件。</p>
          ) : preview?.path !== activeFile.path || preview.loading ? (
            <TextShimmer>正在读取产物文件…</TextShimmer>
          ) : preview.error ? (
            <p role="status">{preview.error}</p>
          ) : preview.imageUrl ? (
            <img src={preview.imageUrl} alt={activeFile.path} />
          ) : (
            <CodeEditor
              value={preview.text ?? ""}
              path={activeFile.path}
              readOnly
              onChange={() => undefined}
            />
          )}
        </div>
      </section>
    </div>
  );
}

export function MigrationWorkspace({
  cloudProvider,
  onBack,
  onAgentAdded,
  onDeploymentTaskChange,
  onDeploymentStarted,
  onDeploymentComplete,
  initialDeployRegion = defaultCloudRegion(cloudProvider),
  projectCapabilities,
  projectCapabilitiesLoading,
  optimizationPreparationStage,
  optimizationError,
  onOptimizeVersion,
  onCancelOptimization,
  onDownloadSavedVersion,
  onDeploySavedVersion,
  initialPage = "new",
  initialProjectId = "",
}: MigrationWorkspaceProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const preparedAnalysisRef = useRef("");
  const transferAbortRef = useRef<AbortController | null>(null);
  const [capability, setCapability] =
    useState<MigrationCapabilities | null>(null);
  const [tasks, setTasks] = useState<MigrationTask[]>([]);
  const [page, setPage] = useState<"new" | "projects">(initialPage);
  const [focusedProjectId, setFocusedProjectId] = useState(initialProjectId);
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState("");
  const [modelsReloadKey, setModelsReloadKey] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<
    "create" | "upload" | "answer" | "confirm" | "stop" | "download" | ""
  >("");
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [pollErrorRetryable, setPollErrorRetryable] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [createStartedAt, setCreateStartedAt] = useState<number | null>(null);
  const [framework, setFramework] =
    useState<MigrationFramework>("langchain");
  const [entry, setEntry] = useState("");
  const [appName, setAppName] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [artifact, setArtifact] = useState<MigrationArtifact | null>(null);
  const [artifactError, setArtifactError] = useState("");
  const [artifactErrorRetryable, setArtifactErrorRetryable] = useState(false);
  const [artifactReload, setArtifactReload] = useState(0);
  const [activity, setActivity] = useState<MigrationActivity | null>(null);
  const [activityLoading, setActivityLoading] = useState(false);
  const [activityError, setActivityError] = useState("");
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false);
  const [deploymentOpen, setDeploymentOpen] = useState(false);
  const [deployRegion, setDeployRegion] = useState(initialDeployRegion);
  const [network, setNetwork] = useState<NetworkConfig | undefined>();
  const [deploymentEnvValues, setDeploymentEnvValues] = useState<
    Record<string, string>
  >({});
  const task = selectedTask(tasks, selectedTaskId);
  const maxSourceBytes = capability?.maxUploadBytes ?? MAX_SOURCE_BYTES;
  const maxSourceSizeLabel = formatByteLimit(maxSourceBytes);
  const unsupportedMigrationModelIds = useMemo(
    () => new Set(capability?.unsupportedModelIds ?? []),
    [capability?.unsupportedModelIds],
  );
  const selectableModels = useMemo(
    () =>
      models.filter((model) =>
        isSelectableMigrationModel(model, unsupportedMigrationModelIds),
      ),
    [models, unsupportedMigrationModelIds],
  );
  const composerModelId = task?.modelId || selectedModelId;
  const modelSelectOptions = useMemo(() => {
    const options = selectableModels.map((model) => ({
      value: model.id,
      label: model.displayName,
      description: [
        model.id,
        model.vendorName,
        model.lifecycleStatus === "Retiring" ? "即将下线" : "",
      ]
        .filter(Boolean)
        .join(" · "),
    }));
    const fallbackId = (
      task?.modelId ||
      selectedModelId ||
      capability?.model?.id ||
      ""
    ).trim();
    const preservesExistingTaskModel = task?.modelId === fallbackId;
    if (
      fallbackId &&
      (preservesExistingTaskModel ||
        !unsupportedMigrationModelIds.has(fallbackId)) &&
      !options.some((option) => option.value === fallbackId)
    ) {
      options.unshift({
        value: fallbackId,
        label: fallbackId,
        description: "当前默认模型",
      });
    }
    return options;
  }, [
    capability?.model?.id,
    selectableModels,
    selectedModelId,
    task?.modelId,
    unsupportedMigrationModelIds,
  ]);
  const createElapsedSeconds = createStartedAt
    ? Math.max(0, Math.floor((now - createStartedAt) / 1_000))
    : 0;
  const latestActivity = activity?.items[activity.items.length - 1];
  const activityKey = [
    activity?.items.length ?? 0,
    latestActivity?.id ?? "",
    latestActivity?.status ?? "",
    latestActivity?.detail?.length ?? 0,
  ].join(":");
  const {
    ref: conversationRef,
    onScroll: handleConversationScroll,
  } = useStickToBottom<HTMLDivElement>(
    `${task?.id ?? "new"}:${task?.state ?? "new"}:${activityKey}`,
  );

  async function reconcileTaskState(
    taskId: string,
    surfaceError = true,
    signal?: AbortSignal,
  ) {
    try {
      const authoritative = await getMigrationTask(taskId, signal);
      if (signal?.aborted) return null;
      setTasks((current) => upsertTask(current, authoritative));
      setPollError("");
      setPollErrorRetryable(false);
      return authoritative;
    } catch (cause) {
      if (signal?.aborted) return null;
      if (surfaceError) {
        setPollError(cause instanceof Error ? cause.message : String(cause));
        setPollErrorRetryable(
          cause instanceof MigrationApiError && cause.retryable,
        );
      }
      return null;
    }
  }

  async function reconcileTaskList(signal?: AbortSignal) {
    try {
      const authoritative = await listMigrationTasks(signal);
      if (signal?.aborted) return;
      setTasks(authoritative);
      setPollError("");
      setPollErrorRetryable(false);
    } catch (cause) {
      if (signal?.aborted) return;
      setPollError(cause instanceof Error ? cause.message : String(cause));
      setPollErrorRetryable(
        cause instanceof MigrationApiError && cause.retryable,
      );
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void Promise.all([
      getMigrationCapabilities(controller.signal),
      listMigrationTasks(controller.signal),
    ])
      .then(([nextCapability, nextTasks]) => {
        if (controller.signal.aborted) return;
        setCapability(nextCapability);
        setTasks(nextTasks);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setModelsLoading(true);
    setModelsError("");
    void listModelOptions({
      signal: controller.signal,
      refresh: modelsReloadKey > 0,
    })
      .then((response) => {
        if (controller.signal.aborted) return;
        setModels(response.models);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setModelsError(
            cause instanceof Error ? cause.message : "加载模型列表失败",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setModelsLoading(false);
      });
    return () => controller.abort();
  }, [cloudProvider, modelsReloadKey]);

  useEffect(() => {
    if (!capability || selectedModelId) return;
    const configuredModelId = capability.model?.id.trim() || "";
    const defaultModelId =
      configuredModelId &&
      !unsupportedMigrationModelIds.has(configuredModelId)
        ? configuredModelId
        : selectableModels[0]?.id || "";
    if (defaultModelId) setSelectedModelId(defaultModelId);
  }, [
    capability,
    selectableModels,
    selectedModelId,
    unsupportedMigrationModelIds,
  ]);

  useEffect(
    () => () => {
      transferAbortRef.current?.abort();
      transferAbortRef.current = null;
    },
    [],
  );

  useEffect(() => {
    const timer = window.setInterval(() => {
      const currentNow = Date.now();
      setNow(currentNow);
      setTasks((current) => expireTasksAtDeadline(current, currentNow));
    }, 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!tasks.some((item) => isActiveState(item.state))) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      void listMigrationTasks(controller.signal)
        .then((nextTasks) => {
          if (!controller.signal.aborted) setTasks(nextTasks);
          setPollError("");
          setPollErrorRetryable(false);
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted) return;
          setPollError(cause instanceof Error ? cause.message : String(cause));
          setPollErrorRetryable(
            cause instanceof MigrationApiError && cause.retryable,
          );
          if (!(cause instanceof MigrationApiError && cause.retryable)) {
            window.clearInterval(timer);
          }
        });
    }, LIST_POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [tasks.some((item) => isActiveState(item.state))]);

  useEffect(() => {
    if (
      !task
      || (!isActiveState(task.state) && task.persistence?.state !== "saving")
    ) return;
    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getMigrationTask(task.id, controller.signal);
        if (controller.signal.aborted) return;
        setTasks((current) => upsertTask(current, next));
        setPollError("");
        setPollErrorRetryable(false);
        if (
          isActiveState(next.state)
          || next.persistence?.state === "saving"
        ) {
          timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        setPollError(cause instanceof Error ? cause.message : String(cause));
        setPollErrorRetryable(
          cause instanceof MigrationApiError && cause.retryable,
        );
        if (cause instanceof MigrationApiError && cause.retryable) {
          timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
        }
      }
    };
    timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [task?.id, task?.state, task?.persistence?.state]);

  useEffect(() => {
    const conversation = conversationRef.current;
    if (!conversation) return;
    conversation.scrollTop = conversation.scrollHeight;
    handleConversationScroll();
  }, [selectedTaskId, conversationRef, handleConversationScroll]);

  useEffect(() => {
    setActivity(null);
    setActivityError("");
    setActivityLoading(false);
  }, [task?.id]);

  useEffect(() => {
    if (!task || !shouldShowCodexActivity(task)) {
      return;
    }

    const controller = new AbortController();
    let timer: number | undefined;
    const poll = async () => {
      setActivityLoading(true);
      try {
        const next = await getMigrationActivity(task.id, controller.signal);
        if (controller.signal.aborted) return;
        setActivity(next);
        setActivityError("");
        if (!next.complete && isActiveState(task.state)) {
          timer = window.setTimeout(() => void poll(), ACTIVITY_POLL_INTERVAL_MS);
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        setActivityError("暂时无法读取 Codex 执行动态，不影响当前任务。");
        if (
          isActiveState(task.state) &&
          cause instanceof MigrationApiError &&
          cause.retryable
        ) {
          timer = window.setTimeout(() => void poll(), ACTIVITY_POLL_INTERVAL_MS);
        }
      } finally {
        if (!controller.signal.aborted) setActivityLoading(false);
      }
    };
    void poll();
    return () => {
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [
    task?.id,
    task?.state,
    task?.analysisRef?.sha256,
    task?.confirmation?.framework,
  ]);

  useEffect(() => {
    if (
      !task?.analysis ||
      !task.analysisRef ||
      !["needs_input", "analysis_ready"].includes(task.state)
    ) {
      return;
    }
    const analysisKey = `${task.id}:${task.analysisRef.attempt}:${task.analysisRef.sha256}`;
    if (preparedAnalysisRef.current === analysisKey) return;
    preparedAnalysisRef.current = analysisKey;
    setAnswers({});
    if (task.state !== "analysis_ready") return;
    const recommended = task.analysis.recommended;
    if (!recommended) return;
    setFramework(recommended.framework);
    setEntry(recommended.entry || "");
    setAppName(defaultAppName(task.sourceFileName));
  }, [task]);

  useEffect(() => {
    setArtifact(null);
    setArtifactError("");
    setArtifactErrorRetryable(false);
    setDeploymentOpen(false);
    setDeploymentEnvValues({});
    if (!task?.artifact.previewReady) return;
    const controller = new AbortController();
    void getMigrationArtifact(task.id, controller.signal)
      .then((next) => {
        if (!controller.signal.aborted) setArtifact(next);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setArtifactError(
            cause instanceof Error ? cause.message : String(cause),
          );
          setArtifactErrorRetryable(
            cause instanceof MigrationApiError && cause.retryable,
          );
        }
      });
    return () => controller.abort();
  }, [task?.id, task?.artifact.previewReady, artifactReload]);

  useEffect(() => {
    if (!artifact) return;
    const defaults = migrationDeploymentEnvDefaults(artifact, cloudProvider);
    setDeploymentEnvValues((current) => {
      const next = { ...current };
      for (const [key, value] of Object.entries(defaults)) {
        if (!next[key]?.trim()) next[key] = value;
      }
      return next;
    });
  }, [artifact, cloudProvider]);

  function selectFile(file: File | undefined) {
    if (transferAbortRef.current) return;
    setError("");
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setSourceFile(null);
      setError("请选择 .zip 格式的本地项目文件。");
      return;
    }
    if (
      file.name.length > 255 ||
      /[/\\\u0000-\u001f]/.test(file.name)
    ) {
      setSourceFile(null);
      setError("ZIP 文件名无效，请重命名后重新选择。");
      return;
    }
    if (file.size > maxSourceBytes) {
      setSourceFile(null);
      setError(`项目 ZIP 不能超过 ${maxSourceSizeLabel}。`);
      return;
    }
    if (file.size === 0) {
      setSourceFile(null);
      setError("项目 ZIP 不能为空。");
      return;
    }
    setSourceFile(file);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    selectFile(file);
  }

  async function createAndUpload() {
    if (!sourceFile || action || transferAbortRef.current) return;
    const controller = new AbortController();
    transferAbortRef.current = controller;
    const isCurrent = () =>
      transferAbortRef.current === controller && !controller.signal.aborted;
    const createdTaskId = `migration-v1-${crypto.randomUUID().replace(/-/g, "")}`;
    setAction("create");
    setCreateStartedAt(Date.now());
    setError("");
    try {
      const created = await createMigrationTask({
        taskId: createdTaskId,
        sourceFileName: sourceFile.name,
        instruction: "",
        modelId: selectedModelId || undefined,
        signal: controller.signal,
      });
      if (!isCurrent()) return;
      setTasks((current) => upsertTask(current, created));
      setSelectedTaskId(created.id);
      setAction("upload");
      setCreateStartedAt(null);
      const uploaded = await uploadMigrationSource(
        created.id,
        sourceFile,
        controller.signal,
      );
      if (!isCurrent()) return;
      setTasks((current) => upsertTask(current, uploaded));
      setSourceFile(null);
    } catch (cause) {
      if (!isCurrent()) return;
      const authoritative = await reconcileTaskState(
        createdTaskId,
        false,
        controller.signal,
      );
      if (!isCurrent()) return;
      if (authoritative) {
        setSelectedTaskId(authoritative.id);
        if (authoritative.state !== "awaiting_upload") {
          setSourceFile(null);
          return;
        }
      } else {
        await reconcileTaskList(controller.signal);
        if (!isCurrent()) return;
      }
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (transferAbortRef.current === controller) {
        transferAbortRef.current = null;
        setCreateStartedAt(null);
        setAction("");
      }
    }
  }

  async function uploadExistingTask() {
    if (!task?.canUpload || !sourceFile || action || transferAbortRef.current) {
      return;
    }
    const controller = new AbortController();
    transferAbortRef.current = controller;
    const isCurrent = () =>
      transferAbortRef.current === controller && !controller.signal.aborted;
    setAction("upload");
    setError("");
    try {
      const uploaded = await uploadMigrationSource(
        task.id,
        sourceFile,
        controller.signal,
      );
      if (!isCurrent()) return;
      setTasks((current) => upsertTask(current, uploaded));
      setSourceFile(null);
    } catch (cause) {
      if (!isCurrent()) return;
      const authoritative = await reconcileTaskState(
        task.id,
        true,
        controller.signal,
      );
      if (!isCurrent()) return;
      if (authoritative && authoritative.state !== "awaiting_upload") {
        setSourceFile(null);
        return;
      }
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (transferAbortRef.current === controller) {
        transferAbortRef.current = null;
        setAction("");
      }
    }
  }

  const entryOptions = useMemo(
    () =>
      (task?.analysis?.entries ?? [])
        .filter((candidate) => candidate.framework === framework)
        .map((candidate) => ({
          value: candidate.value,
          label: candidate.value,
          description: candidate.evidence,
        })),
    [framework, task?.analysis?.entries],
  );
  const requiredQuestionsAnswered = (task?.analysis?.questions ?? []).every(
    (question) => !question.required || Boolean(answers[question.id]?.trim()),
  );
  const confirmationNameError = appNameError(appName);
  const canConfirm = Boolean(
    task?.canConfirm &&
      task.analysisRef &&
      !action &&
      !confirmationNameError &&
      (!STRUCTURED_FRAMEWORKS.has(framework) || entry.trim()),
  );
  const canSubmitAnswers = Boolean(
    task?.canAnswer &&
      task.analysisRef &&
      !action &&
      requiredQuestionsAnswered,
  );

  async function submitAnswers() {
    if (!task?.analysisRef || !canSubmitAnswers) return;
    setAction("answer");
    setError("");
    try {
      const next = await submitMigrationAnalysisAnswers({
        taskId: task.id,
        analysisAttempt: task.analysisRef.attempt,
        analysisSha256: task.analysisRef.sha256,
        inputSha256: task.analysisRef.inputSha256,
        answers,
      });
      setTasks((current) => upsertTask(current, next));
    } catch (cause) {
      const authoritative = await reconcileTaskState(task.id);
      if (authoritative && authoritative.state !== "needs_input") return;
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAction("");
    }
  }

  async function confirmMigration() {
    if (!task?.analysisRef || !canConfirm) return;
    setAction("confirm");
    setError("");
    try {
      const next = await confirmMigrationTask({
        taskId: task.id,
        framework,
        entry: STRUCTURED_FRAMEWORKS.has(framework) ? entry.trim() : undefined,
        appName: appName.trim(),
        instruction: "",
        analysisAttempt: task.analysisRef.attempt,
        analysisSha256: task.analysisRef.sha256,
        inputSha256: task.analysisRef.inputSha256,
      });
      setTasks((current) => upsertTask(current, next));
    } catch (cause) {
      const authoritative = await reconcileTaskState(task.id);
      if (authoritative && authoritative.state !== "analysis_ready") return;
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAction("");
    }
  }

  async function stopTask() {
    if (!task?.canStop || action) return;
    setAction("stop");
    setError("");
    try {
      const next = await stopMigrationTask(task.id);
      setTasks((current) => upsertTask(current, next));
      setStopConfirmOpen(false);
    } catch (cause) {
      const authoritative = await reconcileTaskState(task.id);
      if (authoritative && !authoritative.canStop) {
        setStopConfirmOpen(false);
        return;
      }
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAction("");
    }
  }

  async function downloadArtifact() {
    if (!task?.artifact.downloadReady || action) return;
    setAction("download");
    setError("");
    try {
      await downloadMigrationArtifact(task.id, sourceStem(task.sourceFileName));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAction("");
    }
  }

  function startNewMigration() {
    setPage("new");
    setFocusedProjectId("");
    setSelectedTaskId("");
    setSourceFile(null);
    setError("");
    setPollError("");
    setPollErrorRetryable(false);
    setArtifact(null);
    setArtifactError("");
    setArtifactErrorRetryable(false);
    setDeploymentOpen(false);
    setStopConfirmOpen(false);
    setSelectedModelId(
      capability?.model?.id.trim() || selectableModels[0]?.id || "",
    );
  }

  const deploymentProject: AgentProject | null = artifact
    ? {
        name:
          task?.confirmation?.app_name ||
          defaultAppName(task?.sourceFileName || "migration.zip"),
        files: [
          {
            path: "migration-result.json",
            content: `${JSON.stringify(artifact, null, 2)}\n`,
          },
        ],
      }
    : null;
  const deploymentSecretEnv = artifact
    ? artifact.environment.required
        .filter(isMigrationRuntimeEnvironmentKey)
        .filter(isSecretEnvironmentKey)
        .map((key) => ({ key, label: key }))
    : [];
  const deploymentEnv: EnvVar[] = artifact
    ? [
        ...artifact.environment.required
          .filter(isMigrationRuntimeEnvironmentKey)
          .filter((key) => !isSecretEnvironmentKey(key))
          .map((key) => ({
            key,
            required: true,
            comment: key,
            placeholder: `请输入 ${key}`,
          })),
        ...artifact.environment.optional
          .filter(isMigrationRuntimeEnvironmentKey)
          .map((key) => ({
            key,
            required: false,
            comment: key,
            placeholder: `可选：${key}`,
          })),
      ]
    : [];

  async function handleDeploy(
    project: AgentProject,
    onStage?: (stage: DeployStage) => void,
    options?: Parameters<typeof deployAgentkitProject>[3],
  ) {
    if (!task || !artifact) throw new Error("迁移产物尚未准备完成。");
    const runtimeNetwork =
      network && network.mode !== "public"
        ? {
            mode: network.mode,
            vpc_id: network.vpcId,
            subnet_ids: network.subnetIds,
            enable_shared_internet_access: network.enableSharedInternetAccess,
          }
        : undefined;
    return deployAgentkitProject(
      project.name,
      project.files,
      {
        region: deployRegion,
        projectName: "default",
        network: runtimeNetwork,
      },
      {
        ...options,
        migrationTaskId: task.id,
        onStage,
      },
    );
  }

  if (deploymentOpen && deploymentProject && task && artifact) {
    return (
      <div className="migration-deployment">
        <ProjectPreview
          cloudProvider={cloudProvider}
          project={deploymentProject}
          agentName={deploymentProject.name}
          onDeploy={handleDeploy}
          onAgentAdded={onAgentAdded}
          onDeploymentTaskChange={onDeploymentTaskChange}
          onDeploymentStarted={onDeploymentStarted}
          onDeploymentComplete={onDeploymentComplete}
          network={network}
          onNetworkChange={setNetwork}
          deployRegion={deployRegion}
          onDeployRegionChange={setDeployRegion}
          deploymentEnv={deploymentEnv}
          requiredSecretEnv={deploymentSecretEnv}
          deploymentEnvValues={deploymentEnvValues}
          onDeploymentEnvChange={(key, value) =>
            setDeploymentEnvValues((current) => ({ ...current, [key]: value }))
          }
          deploymentTelemetry={{
            source: "migration",
            createMode: "migration",
            aiAssisted: true,
          }}
          onBack={() => setDeploymentOpen(false)}
          backLabel="返回迁移结果"
          deploymentPrimaryPane={
            <section className="migration-deployment-summary">
              <strong>迁移产物</strong>
              <span>{task.sourceFileName}</span>
              <dl>
                <div>
                  <dt>迁移方式</dt>
                  <dd>{artifact.migration.framework}</dd>
                </div>
                <div>
                  <dt>启动文件</dt>
                  <dd>{artifact.startup.module}</dd>
                </div>
                <div>
                  <dt>文件数</dt>
                  <dd>{artifact.files.length}</dd>
                </div>
              </dl>
            </section>
          }
        />
      </div>
    );
  }

  const composerFile = sourceFile;
  const composerBusy = action === "create" || action === "upload";
  const showComposer = !task || task.canUpload;
  const expiryCopy = task ? migrationExpiryCopy(task, now) : null;

  return (
    <>
      <section className="migration-workspace">
        <aside className="migration-history">
          <header>
            <button
              type="button"
              className="migration-icon-button"
              onClick={onBack}
              aria-label="返回添加 Agent"
              title="返回"
            >
              <BackIcon />
            </button>
            <h1>从存量迁移</h1>
          </header>
          <button
            type="button"
            className="migration-new-button"
            aria-current={page === "new" && !task ? "page" : undefined}
            onClick={startNewMigration}
            disabled={composerBusy}
          >
            <PlusIcon />
            <span>新建迁移</span>
          </button>
          <button
            type="button"
            className={`migration-new-button${page === "projects" ? " is-active" : ""}`}
            aria-current={page === "projects" ? "page" : undefined}
            onClick={() => setPage("projects")}
            disabled={composerBusy}
          >
            <FileIcon />
            <span>已迁移项目</span>
          </button>
          <div className="migration-history__label">最近迁移</div>
          <nav aria-label="迁移会话">
            {loading ? (
              <TextShimmer>正在读取迁移会话…</TextShimmer>
            ) : tasks.length === 0 ? (
              <p className="migration-history__empty">暂无迁移会话</p>
            ) : (
              tasks.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  className={item.id === selectedTaskId ? "is-active" : ""}
                  aria-current={
                    page === "new" && item.id === selectedTaskId
                      ? "page"
                      : undefined
                  }
                  disabled={composerBusy}
                  onClick={() => {
                    setPage("new");
                    setSelectedTaskId(item.id);
                    setError("");
                    setPollError("");
                    setPollErrorRetryable(false);
                  }}
                >
                  <span>{sourceStem(item.sourceFileName)}</span>
                  <small>
                    <span data-state={item.state}>{stateLabel(item.state)}</span>
                    <time>{formatDate(item.createdAt)}</time>
                  </small>
                </button>
              ))
            )}
          </nav>
        </aside>

        {page === "projects" ? (
          <MigratedProjectsPage
            capabilities={projectCapabilities}
            capabilitiesLoading={projectCapabilitiesLoading}
            preparationStage={optimizationPreparationStage}
            optimizationError={optimizationError}
            initialProjectId={focusedProjectId}
            onOptimize={onOptimizeVersion}
            onCancelOptimization={onCancelOptimization}
            onDownload={onDownloadSavedVersion}
            onDeploy={onDeploySavedVersion}
          />
        ) : (
          <main className="migration-main">
            <header className="migration-main__header">
            <div>
              <h2>
                {task ? sourceStem(task.sourceFileName) : "迁移存量 Agent 项目"}
              </h2>
              <p>
                {task
                  ? taskDisplayMessage(task)
                  : "上传本地项目 ZIP，Codex 将先进行只读分析，再由你确认迁移方式。"}
              </p>
            </div>
            {task ? (
              <div className="migration-main__header-actions">
                {task?.canStop ? (
                  <button
                    type="button"
                    className="migration-stop-button"
                    onClick={() => setStopConfirmOpen(true)}
                    disabled={Boolean(action)}
                  >
                    {action === "stop" ? "正在终止…" : "终止迁移"}
                  </button>
                ) : null}
                {expiryCopy ? (
                  <div className="migration-ttl" aria-live="off">
                    <strong>{expiryCopy.title}</strong>
                    <small>{expiryCopy.detail}</small>
                  </div>
                ) : null}
              </div>
            ) : null}
            </header>

          <div
            className="migration-conversation"
            role="log"
            aria-live="polite"
            ref={conversationRef}
            onScroll={handleConversationScroll}
          >
          {!capability?.enabled && !loading ? (
            <div className="migration-system-state is-error" role="alert">
              <strong>迁移能力暂不可用</strong>
              <p>{capability?.reason || "Dev Sandbox 暂不可用，请联系管理员检查配置。"}</p>
            </div>
          ) : null}

          {!task ? (
            <>
              <article className="migration-turn is-assistant">
                <div className="migration-assistant-mark">AI</div>
                <div>
                  <p>
                    请提供本地项目 ZIP。上传后我会识别框架、入口和迁移边界，
                    并在执行实际迁移前请你确认迁移方式。
                  </p>
                  <small>
                    仅支持本地 ZIP，最大 {maxSourceSizeLabel}
                    ；迁移环境从创建起保留 1 小时。
                  </small>
                </div>
              </article>
              {action === "create" && sourceFile ? (
                <>
                  <article className="migration-turn is-user">
                    <div className="migration-user-message">
                      <span className="migration-file-chip">
                        <FileIcon />
                        <span title={sourceFile.name}>{sourceFile.name}</span>
                      </span>
                    </div>
                  </article>
                  <article className="migration-turn is-assistant">
                    <div className="migration-assistant-mark">AI</div>
                    <div className="migration-assistant-content">
                      <MigrationTransferProgress stage="session" />
                      <TextShimmer as="strong">
                        正在创建 Dev Sandbox
                      </TextShimmer>
                      <p className="migration-running-note">
                        正在初始化迁移工作目录，并检查 AgentKit CLI、Codex 和迁移能力。环境就绪后将自动上传项目。
                      </p>
                      <small>
                        已等待 {formatElapsedTime(createElapsedSeconds)}
                      </small>
                    </div>
                  </article>
                </>
              ) : null}
            </>
          ) : (
            <>
              <article className="migration-turn is-user">
                <div className="migration-user-message">
                  <span className="migration-file-chip">
                    <FileIcon />
                    <span title={task.sourceFileName}>{task.sourceFileName}</span>
                  </span>
                  {task.instruction ? <p>{task.instruction}</p> : null}
                </div>
              </article>

              <article className="migration-turn is-assistant">
                <div className="migration-assistant-mark">AI</div>
                <div className="migration-assistant-content">
                  {action === "upload" ? (
                    <>
                      <MigrationTransferProgress stage="upload" />
                      <p className="migration-running-note">
                        ZIP 上传完成后将自动开始只读分析。
                      </p>
                    </>
                  ) : task.state === "analyzing" ? (
                    <>
                      <MigrationTransferProgress stage="analysis" />
                      <p className="migration-running-note">
                        Codex 正在识别框架、入口和迁移边界，不会执行实际迁移。
                      </p>
                    </>
                  ) : isActiveState(task.state) ? (
                    <>
                      <TextShimmer>{taskDisplayMessage(task)}</TextShimmer>
                      <p className="migration-running-note">
                        迁移执行中不能修改附件或迁移方式。你可以等待当前任务结束，或主动终止。
                      </p>
                    </>
                  ) : task.state === "needs_input" && task.analysis ? (
                    <>
                      <p>{task.analysis.summary}</p>
                      <p>
                        只读分析已暂停。请仅回答下面列出的问题，提交后会在同一
                        迁移环境中重新分析，不会开始实际迁移。
                      </p>
                      {task.analysis.frameworks[0]?.evidence.length ? (
                        <details className="migration-analysis__evidence">
                          <summary>查看源码证据</summary>
                          <ul>
                            {task.analysis.frameworks.flatMap((candidate) =>
                              candidate.evidence.map((item) => (
                                <li
                                  key={`${candidate.id}:${item.path}:${item.line}`}
                                >
                                  <code>{item.path}:{item.line}</code>
                                  <span>{item.reason}</span>
                                </li>
                              )),
                            )}
                          </ul>
                        </details>
                      ) : null}
                    </>
                  ) : task.state === "analysis_ready" && task.analysis ? (
                    <>
                      <p>只读分析已完成。请检查建议，并确认最终迁移方式。</p>
                      <AnalysisSummary analysis={task.analysis} />
                    </>
                  ) : task.state === "awaiting_upload" ? (
                    <p>迁移环境已创建，请重新选择本地 ZIP 继续上传。</p>
                  ) : task.state === "expired" ? (
                    <div className="migration-expired">
                      <strong>迁移环境已过期</strong>
                      <p>
                        迁移内容和产物已无法预览、下载或部署。如已完成 Runtime 部署，可返回智能体页面继续使用。
                      </p>
                    </div>
                  ) : task.state === "failed" ? (
                    task.error?.code === "MIGRATION_ANALYSIS_UNSUPPORTED" &&
                    task.analysis ? (
                      <div className="migration-system-state is-error">
                        <strong>当前 ZIP 暂时无法迁移</strong>
                        <Markdown text={task.analysis.summary} allowRawHtml={false} />
                        {task.analysis.warnings.length > 0 ? (
                          <ul>
                            {task.analysis.warnings.map((warning) => (
                              <li key={warning}>{warning}</li>
                            ))}
                          </ul>
                        ) : null}
                        <p>请按提示整理项目后，新建迁移并重新上传。</p>
                      </div>
                    ) : (
                      <div className="migration-system-state is-error">
                        <strong>迁移未完成</strong>
                        <p>{task.message}</p>
                      </div>
                    )
                  ) : task.state === "cancelled" ? (
                    <p>当前迁移已终止。你可以新建迁移并重新上传项目。</p>
                  ) : (
                    <p>{taskDisplayMessage(task)}</p>
                  )}
                  {shouldShowCodexActivity(task) &&
                  (activityLoading || activity?.available || activityError) ? (
                    <MigrationActivityFeed
                      activity={activity}
                      loading={activityLoading}
                      error={activityError}
                      analyzing={task.state === "analyzing"}
                    />
                  ) : null}
                </div>
              </article>
            </>
          )}

          {task?.state === "needs_input" && task.analysis ? (
            <section
              className="migration-confirmation"
              aria-label="补充项目分析信息"
            >
              <div className="migration-confirmation__heading">
                <strong>补充分析所需信息</strong>
                <span>附件保持锁定，提交后仅继续只读分析</span>
              </div>
              {task.analysis.questions.map((question) => (
                <label className="migration-field" key={question.id}>
                  <span>
                    {question.prompt}
                    {question.required ? <b aria-hidden="true">*</b> : null}
                  </span>
                  <textarea
                    value={answers[question.id] || ""}
                    maxLength={4_000}
                    required={question.required}
                    aria-required={question.required}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      setAnswers((current) => ({
                        ...current,
                        [question.id]: value,
                      }));
                    }}
                    disabled={Boolean(action)}
                  />
                </label>
              ))}
              <div className="migration-confirmation__actions">
                <button
                  type="button"
                  className="migration-primary-button"
                  onClick={() => void submitAnswers()}
                  disabled={!canSubmitAnswers}
                >
                  {action === "answer" ? "正在继续分析…" : "提交并继续分析"}
                </button>
              </div>
            </section>
          ) : null}

          {task?.state === "analysis_ready" && task.analysis ? (
            <section
              className="migration-confirmation"
              aria-label="确认迁移方式"
            >
              <div className="migration-confirmation__heading">
                <strong>确认迁移方式</strong>
                <span>确认后才会执行实际迁移</span>
              </div>
              <div className="migration-confirmation__grid">
                <NewChatCompactSelect
                  label="迁移方式"
                  value={framework}
                  options={(capability?.frameworks ?? []).map((item) => ({
                    value: item,
                    label: FRAMEWORK_LABELS[item],
                  }))}
                  onChange={(value) => {
                    const next = value as MigrationFramework;
                    setFramework(next);
                    const candidate = task.analysis?.entries.find(
                      (item) => item.framework === next,
                    );
                    setEntry(candidate?.value || "");
                  }}
                  placeholder="选择迁移方式"
                  disabled={Boolean(action)}
                />
                <label className="migration-field">
                  <span>
                    Agent 名称<b aria-hidden="true">*</b>
                  </span>
                  <input
                    value={appName}
                    onChange={(event) => setAppName(event.currentTarget.value)}
                    maxLength={63}
                    required
                    disabled={Boolean(action)}
                    aria-invalid={Boolean(confirmationNameError)}
                    aria-required="true"
                  />
                  {confirmationNameError ? (
                    <small role="alert">{confirmationNameError}</small>
                  ) : null}
                </label>
                {STRUCTURED_FRAMEWORKS.has(framework) ? (
                  entryOptions.length > 0 ? (
                    <NewChatCompactSelect
                      label="项目入口"
                      value={entry}
                      options={entryOptions}
                      onChange={setEntry}
                      placeholder="选择项目入口"
                      disabled={Boolean(action)}
                    />
                  ) : (
                    <label className="migration-field">
                      <span>
                        项目入口<b aria-hidden="true">*</b>
                      </span>
                      <input
                        value={entry}
                        onChange={(event) => setEntry(event.currentTarget.value)}
                        placeholder="例如 agent.py:agent"
                        maxLength={512}
                        required
                        disabled={Boolean(action)}
                        aria-required="true"
                      />
                    </label>
                  )
                ) : null}
              </div>
              <p className="migration-running-note">
                点击“确认并开始迁移”即确认上述迁移范围、排除项和关键假设。
              </p>
              <div className="migration-confirmation__actions">
                <button
                  type="button"
                  className="migration-primary-button"
                  onClick={() => void confirmMigration()}
                  disabled={!canConfirm}
                >
                  {action === "confirm" ? "正在启动迁移…" : "确认并开始迁移"}
                </button>
              </div>
            </section>
          ) : null}

          {task && isTerminalState(task.state) && task.artifact.previewReady ? (
            <section className="migration-result">
              <header>
                <div>
                  <strong>迁移产物</strong>
                  <span>
                    {task.persistence?.state === "saved"
                      ? "源码已保存，可继续查看、下载、部署或优化。"
                      : task.persistence?.state === "saving"
                        ? "产物已生成，正在保存源码版本。"
                        : task.artifact.deployReady
                          ? "产物可预览、下载和部署，正在等待源码保存状态。"
                          : "产物可预览和下载，但当前交付状态不支持部署。"}
                  </span>
                </div>
                <div className="migration-result__actions">
                  {task.persistence?.state === "saved" ? (
                    <button
                      type="button"
                      onClick={() => {
                        setFocusedProjectId(task.persistence?.projectId ?? "");
                        setPage("projects");
                      }}
                    >
                      <span>查看已迁移项目</span>
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void downloadArtifact()}
                    disabled={!task.artifact.downloadReady || Boolean(action)}
                  >
                    <DownloadIcon />
                    <span>{action === "download" ? "下载中…" : "下载 ZIP"}</span>
                  </button>
                  <button
                    type="button"
                    className="is-primary"
                    onClick={() => setDeploymentOpen(true)}
                    disabled={!task.artifact.deployReady || !artifact}
                    title={
                      task.artifact.deployReady
                        ? "部署迁移产物"
                        : "当前交付状态不支持部署"
                    }
                  >
                    <DeployIcon />
                    <span>部署到 Runtime</span>
                  </button>
                </div>
              </header>
              {task.persistence
                && ["failed", "unavailable"].includes(task.persistence.state) ? (
                <div className="migration-system-state is-error" role="alert">
                  <p>{task.persistence.message}</p>
                </div>
              ) : null}
              {artifactError ? (
                <div className="migration-system-state is-error" role="alert">
                  <p>{artifactError}</p>
                  {artifactErrorRetryable ? (
                    <button
                      type="button"
                      className="migration-retry-button"
                      onClick={() => {
                        setArtifactError("");
                        setArtifactErrorRetryable(false);
                        setArtifactReload((current) => current + 1);
                      }}
                    >
                      重新读取
                    </button>
                  ) : null}
                </div>
              ) : artifact ? (
                <>
                  <div className="migration-result__summary">
                    <span>{artifact.files.length} 个文件</span>
                    <span>CLI {artifact.cli.version}</span>
                    <span>启动文件 {artifact.startup.module}</span>
                    <span>{verificationLabel(artifact.verification.status)}</span>
                  </div>
                  <ArtifactBrowser task={task} artifact={artifact} />
                </>
              ) : (
                <TextShimmer>正在读取迁移产物…</TextShimmer>
              )}
            </section>
          ) : null}

          {pollError ? (
            <div className="migration-inline-error" role="alert">
              <span>{pollError}</span>
              {pollErrorRetryable ? (
                <button
                  type="button"
                  onClick={() => {
                    if (!task) return;
                    setPollError("");
                    setPollErrorRetryable(false);
                    void getMigrationTask(task.id)
                      .then((next) =>
                        setTasks((current) => upsertTask(current, next)),
                      )
                      .catch((cause: unknown) => {
                        setPollError(
                          cause instanceof Error ? cause.message : String(cause),
                        );
                        setPollErrorRetryable(
                          cause instanceof MigrationApiError && cause.retryable,
                        );
                      });
                  }}
                >
                  刷新状态
                </button>
              ) : null}
            </div>
          ) : null}
          {error ? (
            <div className="migration-inline-error" role="alert">
              <span>{error}</span>
              <button type="button" onClick={() => setError("")} aria-label="关闭错误提示">
                <CloseIcon />
              </button>
            </div>
          ) : null}
          </div>

          {showComposer && capability?.enabled ? (
            <div className="migration-composer">
              <div
                className={`migration-composer__box${dragging ? " is-dragging" : ""}`}
                onDragEnter={(event) => {
                  event.preventDefault();
                  if (composerBusy) return;
                  setDragging(true);
                }}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = composerBusy ? "none" : "copy";
                }}
                onDragLeave={(event: DragEvent<HTMLDivElement>) => {
                  if (
                    !event.currentTarget.contains(
                      event.relatedTarget as Node | null,
                    )
                  ) {
                    setDragging(false);
                  }
                }}
                onDrop={(event) => {
                  event.preventDefault();
                  setDragging(false);
                  if (composerBusy) return;
                  selectFile(event.dataTransfer.files?.[0]);
                }}
              >
              <div className="migration-composer__content">
                {composerFile ? (
                  <div className="migration-composer__file">
                    <FileIcon />
                    <span>{composerFile.name}</span>
                    <small>{formatBytes(composerFile.size)}</small>
                    <button
                      type="button"
                      onClick={() => setSourceFile(null)}
                      aria-label="移除项目 ZIP"
                      disabled={composerBusy}
                    >
                      <CloseIcon />
                    </button>
                  </div>
                ) : (
                  <p>{task ? "重新选择项目 ZIP" : "选择或拖入本地项目 ZIP"}</p>
                )}
              </div>
              <div className="migration-composer__actions">
                <div className="migration-composer__tools">
                  <button
                    type="button"
                    className="migration-attach-button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={composerBusy}
                  >
                    <UploadIcon />
                    <span>{sourceFile ? "重新选择" : "选择 ZIP"}</span>
                  </button>
                  <div className="migration-composer__model-select">
                    <NewChatCompactSelect
                      label="模型"
                      hideLabel
                      value={composerModelId}
                      options={modelSelectOptions}
                      onChange={setSelectedModelId}
                      placeholder="选择模型"
                      searchable
                      loading={modelsLoading}
                      error={modelsError}
                      disabled={composerBusy || Boolean(task)}
                      onRetry={() =>
                        setModelsReloadKey((current) => current + 1)
                      }
                    />
                  </div>
                </div>
                <button
                  type="button"
                  className="migration-confirm-upload-button"
                  onClick={() =>
                    void (task ? uploadExistingTask() : createAndUpload())
                  }
                  disabled={!sourceFile || composerBusy}
                >
                  {task ? "继续上传" : "开始迁移"}
                </button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip,application/zip"
                onChange={handleFileChange}
                aria-label="选择本地项目 ZIP"
                disabled={composerBusy}
              />
              </div>
              <p>
                临时迁移环境从创建完成起保留 1 小时；保存成功的源码版本不受影响。
              </p>
            </div>
          ) : null}
          </main>
        )}
      </section>
      {stopConfirmOpen && task ? (
        <StudioConfirmDialog
          title="终止当前迁移？"
          description="终止后，当前分析或迁移进程将停止，已执行的步骤不会继续。"
          confirmLabel={action === "stop" ? "正在终止…" : "终止迁移"}
          variant="danger"
          busy={action === "stop"}
          onCancel={() => setStopConfirmOpen(false)}
          onConfirm={() => void stopTask()}
        />
      ) : null}
    </>
  );
}
