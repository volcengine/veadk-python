import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import {
  DEFAULT_REQUEST_TIMEOUT_MS,
  requestSignal,
  TRANSFER_REQUEST_TIMEOUT_MS,
} from "./timeout";

const API_ROOT = "/web/agent-migrations";
const SESSION_START_TIMEOUT_MS = 390_000;

export type MigrationFramework =
  | "langchain"
  | "langgraph"
  | "adk"
  | "strands"
  | "agentcore"
  | "dify"
  | "any";

export type MigrationTaskState =
  | "awaiting_upload"
  | "analyzing"
  | "needs_input"
  | "analysis_ready"
  | "migrating"
  | "validating"
  | "packaging"
  | "succeeded"
  | "succeeded_with_warnings"
  | "partial"
  | "failed"
  | "cancelled"
  | "expired";

export interface MigrationCapabilities {
  enabled: boolean;
  reason: string;
  model?: {
    configured: boolean;
    id: string;
  };
  maxUploadBytes: number;
  sessionTtlSeconds: number;
  frameworks: MigrationFramework[];
}

export interface MigrationEvidence {
  path: string;
  line: number;
  reason: string;
}

export interface MigrationAnalysis {
  schema_version: 1;
  status: "needs_input" | "recommendation_ready" | "unsupported";
  attempt: number;
  input_sha256: string;
  summary: string;
  frameworks: Array<{
    id: MigrationFramework;
    confidence: "high" | "medium" | "low";
    evidence: MigrationEvidence[];
  }>;
  recommended: {
    framework: MigrationFramework;
    entry: string | null;
    reason: string;
  } | null;
  entries: Array<{
    value: string;
    framework: MigrationFramework;
    evidence: string;
  }>;
  boundary: {
    include: string[];
    exclude: string[];
  };
  assumptions: string[];
  questions: Array<{
    id: string;
    prompt: string;
    required: boolean;
  }>;
  warnings: string[];
}

export interface MigrationTask {
  id: string;
  state: MigrationTaskState;
  message: string;
  sourceFileName: string;
  instruction: string;
  modelId?: string;
  createdAt: string | number;
  expiresAt: string;
  sessionTtlSeconds: number;
  canModify: boolean;
  canUpload: boolean;
  canAnswer: boolean;
  canConfirm: boolean;
  canStop: boolean;
  artifact: {
    state: string;
    previewReady: boolean;
    downloadReady: boolean;
    deployReady: boolean;
  };
  analysis?: MigrationAnalysis;
  analysisRef?: {
    attempt: number;
    sha256: string;
    inputSha256: string;
  };
  confirmation?: {
    framework?: MigrationFramework;
    entry?: string | null;
    app_name?: string;
  };
  error?: {
    code: string;
    message: string;
    retryable: boolean;
  };
}

export type MigrationActivityKind =
  | "reasoning"
  | "message"
  | "plan"
  | "command"
  | "status";

export interface MigrationActivityTool {
  name: string;
  input?: unknown;
  output?: unknown;
  error?: string;
  exitCode?: number;
}

export interface MigrationActivityPlanItem {
  text: string;
  status: "pending" | "in_progress" | "completed" | "failed";
}

export interface MigrationActivityItem {
  id: string;
  kind: MigrationActivityKind;
  status: "running" | "completed" | "failed";
  title: string;
  detail?: string;
  tool?: MigrationActivityTool;
  plan?: MigrationActivityPlanItem[];
}

export interface MigrationActivity {
  available: boolean;
  complete: boolean;
  items: MigrationActivityItem[];
}

export interface MigrationArtifact {
  schema_version: 1;
  run_id?: string;
  cli: {
    name: string;
    version: string;
  };
  migration: {
    engine: "structured" | "agentic";
    framework: string;
    entry?: string;
    source_sha256?: string;
    provenance_sha256?: string;
  };
  status: "succeeded" | "succeeded_with_warnings" | "partial";
  files: Array<{
    path: string;
    size: number;
    sha256: string;
    mode: string;
  }>;
  startup: {
    module: string;
    object: string;
    command?: string[];
  };
  environment: {
    required: string[];
    optional: string[];
    defaults: Record<string, string>;
  };
  verification: {
    status: "passed" | "failed" | "degraded";
    checks: Array<{
      name: string;
      status: "passed" | "failed";
      detail?: string;
    }>;
  };
  warnings: string[];
  report: {
    path: string;
  };
  artifact: {
    path: "migration-result.zip";
    size: number;
    sha256: string;
  };
  created_at: string;
}

export class MigrationApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code = "MIGRATION_ERROR",
    readonly retryable = false,
    readonly statusText = "",
    readonly rawResponse = "",
  ) {
    super(message);
    this.name = "MigrationApiError";
  }
}

const FRAMEWORKS = new Set<MigrationFramework>([
  "langchain",
  "langgraph",
  "adk",
  "strands",
  "agentcore",
  "dify",
  "any",
]);

const TASK_STATES = new Set<MigrationTaskState>([
  "awaiting_upload",
  "analyzing",
  "needs_input",
  "analysis_ready",
  "migrating",
  "validating",
  "packaging",
  "succeeded",
  "succeeded_with_warnings",
  "partial",
  "failed",
  "cancelled",
  "expired",
]);

const ACTIVITY_KINDS = new Set<MigrationActivityKind>([
  "reasoning",
  "message",
  "plan",
  "command",
  "status",
]);

const ACTIVITY_STATES = new Set<MigrationActivityItem["status"]>([
  "running",
  "completed",
  "failed",
]);

const ACTIVITY_PLAN_STATES = new Set<MigrationActivityPlanItem["status"]>([
  "pending",
  "in_progress",
  "completed",
  "failed",
]);

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label}格式错误。`);
  }
  return value as Record<string, unknown>;
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`${label}格式错误。`);
  }
  return value;
}

function framework(value: unknown, label: string): MigrationFramework {
  if (typeof value !== "string" || !FRAMEWORKS.has(value as MigrationFramework)) {
    throw new Error(`${label}格式错误。`);
  }
  return value as MigrationFramework;
}

function normalizeAnalysis(value: unknown): MigrationAnalysis {
  const analysis = record(value, "迁移分析结果");
  const recommended =
    analysis.recommended === null
      ? null
      : record(analysis.recommended, "迁移建议");
  const boundary = record(analysis.boundary, "迁移边界");
  if (
    analysis.schema_version !== 1 ||
    !["needs_input", "recommendation_ready", "unsupported"].includes(
      String(analysis.status),
    ) ||
    typeof analysis.attempt !== "number" ||
    typeof analysis.input_sha256 !== "string" ||
    typeof analysis.summary !== "string" ||
    !Array.isArray(analysis.frameworks) ||
    !Array.isArray(analysis.entries) ||
    !Array.isArray(analysis.questions)
  ) {
    throw new Error("迁移分析结果格式错误。");
  }
  return {
    schema_version: 1,
    status: analysis.status as MigrationAnalysis["status"],
    attempt: analysis.attempt,
    input_sha256: analysis.input_sha256,
    summary: analysis.summary,
    frameworks: analysis.frameworks.map((item) => {
      const candidate = record(item, "框架候选");
      if (
        !["high", "medium", "low"].includes(String(candidate.confidence)) ||
        !Array.isArray(candidate.evidence)
      ) {
        throw new Error("框架候选格式错误。");
      }
      return {
        id: framework(candidate.id, "框架候选"),
        confidence: candidate.confidence as "high" | "medium" | "low",
        evidence: candidate.evidence.map((evidenceValue) => {
          const evidence = record(evidenceValue, "分析证据");
          if (
            typeof evidence.path !== "string" ||
            typeof evidence.line !== "number" ||
            typeof evidence.reason !== "string"
          ) {
            throw new Error("分析证据格式错误。");
          }
          return {
            path: evidence.path,
            line: evidence.line,
            reason: evidence.reason,
          };
        }),
      };
    }),
    recommended:
      recommended === null
        ? null
        : {
            framework: framework(recommended.framework, "推荐框架"),
            entry:
              recommended.entry === null || typeof recommended.entry === "string"
                ? recommended.entry
                : null,
            reason:
              typeof recommended.reason === "string" ? recommended.reason : "",
          },
    entries: analysis.entries.map((item) => {
      const entry = record(item, "入口候选");
      if (typeof entry.value !== "string" || typeof entry.evidence !== "string") {
        throw new Error("入口候选格式错误。");
      }
      return {
        value: entry.value,
        framework: framework(entry.framework, "入口框架"),
        evidence: entry.evidence,
      };
    }),
    boundary: {
      include: stringArray(boundary.include, "迁移包含范围"),
      exclude: stringArray(boundary.exclude, "迁移排除范围"),
    },
    assumptions: stringArray(analysis.assumptions, "分析假设"),
    questions: analysis.questions.map((item) => {
      const question = record(item, "待确认问题");
      if (
        typeof question.id !== "string" ||
        typeof question.prompt !== "string" ||
        typeof question.required !== "boolean"
      ) {
        throw new Error("待确认问题格式错误。");
      }
      return {
        id: question.id,
        prompt: question.prompt,
        required: question.required,
      };
    }),
    warnings: stringArray(analysis.warnings, "迁移警告"),
  };
}

function normalizeTask(value: unknown): MigrationTask {
  const task = record(value, "迁移会话");
  const artifact = record(task.artifact, "迁移产物状态");
  if (
    typeof task.id !== "string" ||
    typeof task.state !== "string" ||
    !TASK_STATES.has(task.state as MigrationTaskState) ||
    typeof task.message !== "string" ||
    typeof task.sourceFileName !== "string" ||
    typeof task.instruction !== "string" ||
    (typeof task.createdAt !== "string" && typeof task.createdAt !== "number") ||
    typeof task.expiresAt !== "string" ||
    typeof task.sessionTtlSeconds !== "number" ||
    typeof task.canModify !== "boolean" ||
    typeof task.canUpload !== "boolean" ||
    typeof task.canAnswer !== "boolean" ||
    typeof task.canConfirm !== "boolean" ||
    typeof task.canStop !== "boolean"
  ) {
    throw new Error("迁移会话格式错误。");
  }
  const normalized: MigrationTask = {
    id: task.id,
    state: task.state as MigrationTaskState,
    message: task.message,
    sourceFileName: task.sourceFileName,
    instruction: task.instruction,
    createdAt: task.createdAt,
    expiresAt: task.expiresAt,
    sessionTtlSeconds: task.sessionTtlSeconds,
    canModify: task.canModify,
    canUpload: task.canUpload,
    canAnswer: task.canAnswer,
    canConfirm: task.canConfirm,
    canStop: task.canStop,
    artifact: {
      state: typeof artifact.state === "string" ? artifact.state : "none",
      previewReady: artifact.previewReady === true,
      downloadReady: artifact.downloadReady === true,
      deployReady: artifact.deployReady === true,
    },
  };
  if (typeof task.modelId === "string" && task.modelId.trim()) {
    normalized.modelId = task.modelId;
  }
  if (task.analysis !== undefined) normalized.analysis = normalizeAnalysis(task.analysis);
  if (task.analysisRef !== undefined) {
    const reference = record(task.analysisRef, "分析结果引用");
    if (
      typeof reference.attempt !== "number" ||
      typeof reference.sha256 !== "string" ||
      typeof reference.inputSha256 !== "string"
    ) {
      throw new Error("分析结果引用格式错误。");
    }
    normalized.analysisRef = {
      attempt: reference.attempt,
      sha256: reference.sha256,
      inputSha256: reference.inputSha256,
    };
  }
  if (task.confirmation !== undefined) {
    const confirmation = record(task.confirmation, "迁移确认");
    normalized.confirmation = {
      ...(confirmation.framework !== undefined
        ? { framework: framework(confirmation.framework, "确认框架") }
        : {}),
      ...(confirmation.entry === null || typeof confirmation.entry === "string"
        ? { entry: confirmation.entry }
        : {}),
      ...(typeof confirmation.app_name === "string"
        ? { app_name: confirmation.app_name }
        : {}),
    };
  }
  if (task.error !== undefined) {
    const error = record(task.error, "迁移错误");
    normalized.error = {
      code: typeof error.code === "string" ? error.code : "MIGRATION_ERROR",
      message: typeof error.message === "string" ? error.message : task.message,
      retryable: error.retryable === true,
    };
  }
  return normalized;
}

function normalizeActivity(value: unknown): MigrationActivity {
  const activity = record(value, "迁移执行动态");
  if (
    typeof activity.available !== "boolean" ||
    typeof activity.complete !== "boolean" ||
    !Array.isArray(activity.items)
  ) {
    throw new Error("迁移执行动态格式错误。");
  }
  return {
    available: activity.available,
    complete: activity.complete,
    items: activity.items.map((value) => {
      const item = record(value, "迁移执行动态项");
      if (
        typeof item.id !== "string" ||
        typeof item.kind !== "string" ||
        !ACTIVITY_KINDS.has(item.kind as MigrationActivityKind) ||
        typeof item.status !== "string" ||
        !ACTIVITY_STATES.has(item.status as MigrationActivityItem["status"]) ||
        typeof item.title !== "string" ||
        (item.detail !== undefined && typeof item.detail !== "string")
      ) {
        throw new Error("迁移执行动态项格式错误。");
      }
      let tool: MigrationActivityTool | undefined;
      if (item.tool !== undefined) {
        const value = record(item.tool, "迁移执行工具项");
        if (
          typeof value.name !== "string" ||
          (value.error !== undefined && typeof value.error !== "string") ||
          (value.exitCode !== undefined && !Number.isInteger(value.exitCode))
        ) {
          throw new Error("迁移执行工具项格式错误。");
        }
        tool = {
          name: value.name,
          ...(Object.prototype.hasOwnProperty.call(value, "input")
            ? { input: value.input }
            : {}),
          ...(Object.prototype.hasOwnProperty.call(value, "output")
            ? { output: value.output }
            : {}),
          ...(typeof value.error === "string" ? { error: value.error } : {}),
          ...(typeof value.exitCode === "number"
            ? { exitCode: value.exitCode }
            : {}),
        };
      }
      let plan: MigrationActivityPlanItem[] | undefined;
      if (item.plan !== undefined) {
        if (!Array.isArray(item.plan)) {
          throw new Error("迁移执行计划格式错误。");
        }
        plan = item.plan.map((value) => {
          const planItem = record(value, "迁移执行计划项");
          if (
            typeof planItem.text !== "string" ||
            typeof planItem.status !== "string" ||
            !ACTIVITY_PLAN_STATES.has(
              planItem.status as MigrationActivityPlanItem["status"],
            )
          ) {
            throw new Error("迁移执行计划项格式错误。");
          }
          return {
            text: planItem.text,
            status: planItem.status as MigrationActivityPlanItem["status"],
          };
        });
      }
      return {
        id: item.id,
        kind: item.kind as MigrationActivityKind,
        status: item.status as MigrationActivityItem["status"],
        title: item.title,
        ...(typeof item.detail === "string" ? { detail: item.detail } : {}),
        ...(tool ? { tool } : {}),
        ...(plan ? { plan } : {}),
      };
    }),
  };
}

function normalizeArtifact(value: unknown): MigrationArtifact {
  const artifact = record(value, "迁移产物");
  const cli = record(artifact.cli, "CLI 信息");
  const migration = record(artifact.migration, "迁移信息");
  const startup = record(artifact.startup, "启动信息");
  const environment = record(artifact.environment, "环境变量信息");
  const verification = record(artifact.verification, "校验信息");
  const report = record(artifact.report, "迁移报告");
  const descriptor = record(artifact.artifact, "产物归档");
  const environmentDefaults =
    environment.defaults === undefined
      ? {}
      : record(environment.defaults, "环境变量默认值");
  if (
    artifact.schema_version !== 1 ||
    !["succeeded", "succeeded_with_warnings", "partial"].includes(
      String(artifact.status),
    ) ||
    typeof cli.name !== "string" ||
    typeof cli.version !== "string" ||
    !["structured", "agentic"].includes(String(migration.engine)) ||
    typeof migration.framework !== "string" ||
    !Array.isArray(artifact.files) ||
    typeof startup.module !== "string" ||
    typeof startup.object !== "string" ||
    !["passed", "failed", "degraded"].includes(String(verification.status)) ||
    !Array.isArray(verification.checks) ||
    typeof report.path !== "string" ||
    descriptor.path !== "migration-result.zip" ||
    typeof descriptor.size !== "number" ||
    typeof descriptor.sha256 !== "string" ||
    typeof artifact.created_at !== "string"
  ) {
    throw new Error("迁移产物格式错误。");
  }
  const requiredEnvironment = stringArray(
    environment.required,
    "必需环境变量",
  );
  const optionalEnvironment = stringArray(
    environment.optional,
    "可选环境变量",
  );
  const declaredEnvironment = new Set([
    ...requiredEnvironment,
    ...optionalEnvironment,
  ]);
  const normalizedEnvironmentDefaults = Object.fromEntries(
    Object.entries(environmentDefaults).map(([key, defaultValue]) => {
      if (!declaredEnvironment.has(key) || typeof defaultValue !== "string") {
        throw new Error("环境变量默认值格式错误。");
      }
      return [key, defaultValue];
    }),
  );
  return {
    schema_version: 1,
    ...(typeof artifact.run_id === "string" ? { run_id: artifact.run_id } : {}),
    cli: { name: cli.name, version: cli.version },
    migration: {
      engine: migration.engine as "structured" | "agentic",
      framework: migration.framework,
      ...(typeof migration.entry === "string" ? { entry: migration.entry } : {}),
      ...(typeof migration.source_sha256 === "string"
        ? { source_sha256: migration.source_sha256 }
        : {}),
      ...(typeof migration.provenance_sha256 === "string"
        ? { provenance_sha256: migration.provenance_sha256 }
        : {}),
    },
    status: artifact.status as MigrationArtifact["status"],
    files: artifact.files.map((item) => {
      const file = record(item, "迁移产物文件");
      if (
        typeof file.path !== "string" ||
        typeof file.size !== "number" ||
        typeof file.sha256 !== "string" ||
        typeof file.mode !== "string"
      ) {
        throw new Error("迁移产物文件格式错误。");
      }
      return {
        path: file.path,
        size: file.size,
        sha256: file.sha256,
        mode: file.mode,
      };
    }),
    startup: {
      module: startup.module,
      object: startup.object,
      ...(Array.isArray(startup.command) &&
      startup.command.every((item) => typeof item === "string")
        ? { command: startup.command as string[] }
        : {}),
    },
    environment: {
      required: requiredEnvironment,
      optional: optionalEnvironment,
      defaults: normalizedEnvironmentDefaults,
    },
    verification: {
      status: verification.status as MigrationArtifact["verification"]["status"],
      checks: verification.checks.map((item) => {
        const check = record(item, "迁移校验项");
        if (
          typeof check.name !== "string" ||
          !["passed", "failed"].includes(String(check.status))
        ) {
          throw new Error("迁移校验项格式错误。");
        }
        return {
          name: check.name,
          status: check.status as "passed" | "failed",
          ...(typeof check.detail === "string" ? { detail: check.detail } : {}),
        };
      }),
    },
    warnings: stringArray(artifact.warnings, "迁移产物警告"),
    report: { path: report.path },
    artifact: {
      path: "migration-result.zip",
      size: descriptor.size,
      sha256: descriptor.sha256,
    },
    created_at: artifact.created_at,
  };
}

async function request(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  return fetch(withAuth(`${API_ROOT}${path}`), {
    ...init,
    headers: withLocalUser(init.headers),
    signal: requestSignal(init.signal, timeoutMs),
  });
}

function validationErrorDetail(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value
    .map((item) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return "";
      const detail = item as Record<string, unknown>;
      const location = Array.isArray(detail.loc)
        ? detail.loc
            .filter(
              (part): part is string | number =>
                typeof part === "string" || typeof part === "number",
            )
            .join(".")
        : "";
      const message = typeof detail.msg === "string" ? detail.msg : "";
      if (!message) return "";
      return location ? `${location}: ${message}` : message;
    })
    .filter(Boolean)
    .join("；");
}

async function errorFrom(
  response: Response,
  fallback: string,
): Promise<MigrationApiError> {
  const text = await response.text().catch(() => "");
  try {
    const body = record(JSON.parse(text), "错误响应");
    if (Array.isArray(body.detail)) {
      const detail = validationErrorDetail(body.detail);
      return new MigrationApiError(
        detail ? `请求参数校验失败：${detail}` : fallback,
        response.status,
        "MIGRATION_REQUEST_INVALID",
        false,
        response.statusText,
        text,
      );
    }
    if (typeof body.detail === "string") {
      return new MigrationApiError(
        body.detail,
        response.status,
        typeof body.code === "string" ? body.code : "MIGRATION_ERROR",
        body.retryable === true,
        response.statusText,
        text,
      );
    }
    const detail =
      body.detail && typeof body.detail === "object"
        ? record(body.detail, "错误详情")
        : body;
    return new MigrationApiError(
      typeof detail.message === "string" ? detail.message : fallback,
      response.status,
      typeof detail.code === "string" ? detail.code : "MIGRATION_ERROR",
      detail.retryable === true,
      response.statusText,
      text,
    );
  } catch {
    const contentType =
      response.headers.get("content-type")?.split(";", 1)[0] ||
      "Content-Type 缺失";
    return new MigrationApiError(
      `${fallback}（HTTP ${response.status}，Content-Type: ${contentType}）。请检查代理或网关配置。`,
      response.status,
      "MIGRATION_ERROR",
      false,
      response.statusText,
      text,
    );
  }
}

async function json(response: Response, fallback: string): Promise<unknown> {
  if (!response.ok) throw await errorFrom(response, fallback);
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new MigrationApiError(
      `${fallback}：服务端返回非 JSON 响应（HTTP ${response.status}）。请检查代理或网关配置。`,
      response.status,
      "MIGRATION_RESPONSE_INVALID",
      false,
      response.statusText,
    );
  }
  return response.json();
}

export async function getMigrationCapabilities(
  signal?: AbortSignal,
): Promise<MigrationCapabilities> {
  const body = record(
    await json(
      await request("/capabilities", { signal }),
      "读取迁移能力失败",
    ),
    "迁移能力",
  );
  if (
    typeof body.enabled !== "boolean" ||
    typeof body.reason !== "string" ||
    typeof body.maxUploadBytes !== "number" ||
    typeof body.sessionTtlSeconds !== "number" ||
    !Array.isArray(body.frameworks)
  ) {
    throw new Error("迁移能力格式错误。");
  }
  const capability: MigrationCapabilities = {
    enabled: body.enabled,
    reason: body.reason,
    maxUploadBytes: body.maxUploadBytes,
    sessionTtlSeconds: body.sessionTtlSeconds,
    frameworks: body.frameworks.map((item) => framework(item, "迁移框架")),
  };
  if (body.model !== undefined) {
    const model = record(body.model, "迁移模型能力");
    if (typeof model.configured !== "boolean" || typeof model.id !== "string") {
      throw new Error("迁移模型能力格式错误。");
    }
    capability.model = { configured: model.configured, id: model.id };
  }
  return capability;
}

export async function listMigrationTasks(
  signal?: AbortSignal,
): Promise<MigrationTask[]> {
  const body = record(
    await json(await request("/tasks", { signal }), "读取迁移会话失败"),
    "迁移会话列表",
  );
  if (!Array.isArray(body.items)) throw new Error("迁移会话列表格式错误。");
  return body.items.map(normalizeTask);
}

export async function createMigrationTask(args: {
  taskId: string;
  sourceFileName: string;
  instruction: string;
  modelId?: string;
  signal?: AbortSignal;
}): Promise<MigrationTask> {
  return normalizeTask(
    await json(
      await request(
        "/tasks",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            taskId: args.taskId,
            sourceFileName: args.sourceFileName,
            instruction: args.instruction,
            ...(args.modelId ? { modelId: args.modelId } : {}),
          }),
          signal: args.signal,
        },
        SESSION_START_TIMEOUT_MS,
      ),
      "创建迁移会话失败",
    ),
  );
}

export async function uploadMigrationSource(
  taskId: string,
  file: File,
  signal?: AbortSignal,
): Promise<MigrationTask> {
  return normalizeTask(
    await json(
      await request(
        `/tasks/${encodeURIComponent(taskId)}/source`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/zip" },
          body: file,
          signal,
        },
        SESSION_START_TIMEOUT_MS,
      ),
      "上传迁移项目失败",
    ),
  );
}

export async function getMigrationTask(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationTask> {
  return normalizeTask(
    await json(
      await request(`/tasks/${encodeURIComponent(taskId)}`, { signal }),
      "读取迁移会话失败",
    ),
  );
}

export async function getMigrationActivity(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationActivity> {
  return normalizeActivity(
    await json(
      await request(
        `/tasks/${encodeURIComponent(taskId)}/activity`,
        { signal, cache: "no-store" },
      ),
      "读取迁移执行动态失败",
    ),
  );
}

export async function confirmMigrationTask(args: {
  taskId: string;
  framework: MigrationFramework;
  entry?: string;
  appName: string;
  instruction: string;
  analysisAttempt: number;
  analysisSha256: string;
  inputSha256: string;
  signal?: AbortSignal;
}): Promise<MigrationTask> {
  return normalizeTask(
    await json(
      await request(
        `/tasks/${encodeURIComponent(args.taskId)}/confirm`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            framework: args.framework,
            entry: args.entry || null,
            appName: args.appName,
            instruction: args.instruction,
            analysisAttempt: args.analysisAttempt,
            analysisSha256: args.analysisSha256,
            inputSha256: args.inputSha256,
            boundaryConfirmed: true,
          }),
          signal: args.signal,
        },
        SESSION_START_TIMEOUT_MS,
      ),
      "启动迁移失败",
    ),
  );
}

export async function submitMigrationAnalysisAnswers(args: {
  taskId: string;
  analysisAttempt: number;
  analysisSha256: string;
  inputSha256: string;
  answers: Record<string, string>;
  signal?: AbortSignal;
}): Promise<MigrationTask> {
  return normalizeTask(
    await json(
      await request(
        `/tasks/${encodeURIComponent(args.taskId)}/answers`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            analysisAttempt: args.analysisAttempt,
            analysisSha256: args.analysisSha256,
            inputSha256: args.inputSha256,
            answers: args.answers,
          }),
          signal: args.signal,
        },
        SESSION_START_TIMEOUT_MS,
      ),
      "提交分析补充信息失败",
    ),
  );
}

export async function stopMigrationTask(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationTask> {
  return normalizeTask(
    await json(
      await request(
        `/tasks/${encodeURIComponent(taskId)}/stop`,
        { method: "POST", signal },
      ),
      "终止迁移失败",
    ),
  );
}

export async function deleteMigrationTask(
  taskId: string,
  signal?: AbortSignal,
): Promise<void> {
  await json(
    await request(
      `/tasks/${encodeURIComponent(taskId)}`,
      { method: "DELETE", signal },
    ),
    "删除迁移会话失败",
  );
}

export async function getMigrationArtifact(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationArtifact> {
  return normalizeArtifact(
    await json(
      await request(
        `/tasks/${encodeURIComponent(taskId)}/artifact`,
        { signal },
      ),
      "读取迁移产物失败",
    ),
  );
}

export async function getMigrationArtifactFile(
  taskId: string,
  path: string,
  signal?: AbortSignal,
): Promise<{ blob: Blob; mimeType: string }> {
  const query = new URLSearchParams({ path });
  const response = await request(
    `/tasks/${encodeURIComponent(taskId)}/artifact/file?${query}`,
    { signal },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) throw await errorFrom(response, "读取迁移产物文件失败");
  return {
    blob: await response.blob(),
    mimeType:
      response.headers.get("content-type")?.split(";", 1)[0] ||
      "application/octet-stream",
  };
}

function responseFilename(response: Response, fallback: string): string {
  const disposition = response.headers.get("content-disposition") || "";
  return disposition.match(/filename="([^"]+)"/)?.[1] || fallback;
}

export async function downloadMigrationArtifact(
  taskId: string,
  fallbackName: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await request(
    `/tasks/${encodeURIComponent(taskId)}/download`,
    { signal },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) throw await errorFrom(response, "下载迁移产物失败");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = responseFilename(response, `${fallbackName}-migrated.zip`);
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
