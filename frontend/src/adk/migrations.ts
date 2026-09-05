import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { adkT, withLocaleHeaders } from "./i18n";
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
  unsupportedModelIds?: string[];
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
  persistence?: {
    state: "saving" | "saved" | "failed" | "unavailable";
    projectId?: string;
    versionId?: string;
    message: string;
    retryable?: boolean;
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
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return value as Record<string, unknown>;
}

function stringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return value;
}

function framework(value: unknown, label: string): MigrationFramework {
  if (typeof value !== "string" || !FRAMEWORKS.has(value as MigrationFramework)) {
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return value as MigrationFramework;
}

function normalizeAnalysis(value: unknown): MigrationAnalysis {
  const analysis = record(value, adkT("migrations.labels.analysisResult"));
  const recommended =
    analysis.recommended === null
      ? null
      : record(analysis.recommended, adkT("migrations.labels.recommendation"));
  const boundary = record(analysis.boundary, adkT("migrations.labels.boundary"));
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
    throw new Error(adkT("migrations.invalidAnalysisResult"));
  }
  return {
    schema_version: 1,
    status: analysis.status as MigrationAnalysis["status"],
    attempt: analysis.attempt,
    input_sha256: analysis.input_sha256,
    summary: analysis.summary,
    frameworks: analysis.frameworks.map((item) => {
      const candidate = record(item, adkT("migrations.labels.frameworkCandidate"));
      if (
        !["high", "medium", "low"].includes(String(candidate.confidence)) ||
        !Array.isArray(candidate.evidence)
      ) {
        throw new Error(adkT("migrations.invalidFrameworkCandidate"));
      }
      return {
        id: framework(candidate.id, adkT("migrations.labels.frameworkCandidate")),
        confidence: candidate.confidence as "high" | "medium" | "low",
        evidence: candidate.evidence.map((evidenceValue) => {
          const evidence = record(evidenceValue, adkT("migrations.labels.analysisEvidence"));
          if (
            typeof evidence.path !== "string" ||
            typeof evidence.line !== "number" ||
            typeof evidence.reason !== "string"
          ) {
            throw new Error(adkT("migrations.invalidAnalysisEvidence"));
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
            framework: framework(recommended.framework, adkT("migrations.labels.recommendedFramework")),
            entry:
              recommended.entry === null || typeof recommended.entry === "string"
                ? recommended.entry
                : null,
            reason:
              typeof recommended.reason === "string" ? recommended.reason : "",
          },
    entries: analysis.entries.map((item) => {
      const entry = record(item, adkT("migrations.labels.entryCandidate"));
      if (typeof entry.value !== "string" || typeof entry.evidence !== "string") {
        throw new Error(adkT("migrations.invalidEntryCandidate"));
      }
      return {
        value: entry.value,
        framework: framework(entry.framework, adkT("migrations.labels.entryFramework")),
        evidence: entry.evidence,
      };
    }),
    boundary: {
      include: stringArray(boundary.include, adkT("migrations.labels.includeScope")),
      exclude: stringArray(boundary.exclude, adkT("migrations.labels.excludeScope")),
    },
    assumptions: stringArray(analysis.assumptions, adkT("migrations.labels.assumptions")),
    questions: analysis.questions.map((item) => {
      const question = record(item, adkT("migrations.labels.question"));
      if (
        typeof question.id !== "string" ||
        typeof question.prompt !== "string" ||
        typeof question.required !== "boolean"
      ) {
        throw new Error(adkT("migrations.invalidQuestion"));
      }
      return {
        id: question.id,
        prompt: question.prompt,
        required: question.required,
      };
    }),
    warnings: stringArray(analysis.warnings, adkT("migrations.labels.analysisWarnings")),
  };
}

function normalizeTask(value: unknown): MigrationTask {
  const task = record(value, adkT("migrations.labels.task"));
  const artifact = record(task.artifact, adkT("migrations.labels.artifactStatus"));
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
    throw new Error(adkT("migrations.invalidTask"));
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
    const reference = record(task.analysisRef, adkT("migrations.labels.analysisReference"));
    if (
      typeof reference.attempt !== "number" ||
      typeof reference.sha256 !== "string" ||
      typeof reference.inputSha256 !== "string"
    ) {
      throw new Error(adkT("migrations.invalidAnalysisReference"));
    }
    normalized.analysisRef = {
      attempt: reference.attempt,
      sha256: reference.sha256,
      inputSha256: reference.inputSha256,
    };
  }
  if (task.confirmation !== undefined) {
    const confirmation = record(task.confirmation, adkT("migrations.labels.confirmation"));
    normalized.confirmation = {
      ...(confirmation.framework !== undefined
        ? { framework: framework(confirmation.framework, adkT("migrations.labels.confirmedFramework")) }
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
    const error = record(task.error, adkT("migrations.labels.error"));
    normalized.error = {
      code: typeof error.code === "string" ? error.code : "MIGRATION_ERROR",
      message: typeof error.message === "string" ? error.message : task.message,
      retryable: error.retryable === true,
    };
  }
  if (task.persistence !== undefined) {
    const persistence = record(task.persistence, adkT("migrations.labels.sourcePersistence"));
    if (
      !["saving", "saved", "failed", "unavailable"].includes(String(persistence.state))
      || typeof persistence.message !== "string"
      || (persistence.projectId !== undefined && typeof persistence.projectId !== "string")
      || (persistence.versionId !== undefined && typeof persistence.versionId !== "string")
      || (persistence.retryable !== undefined && typeof persistence.retryable !== "boolean")
    ) {
      throw new Error(adkT("migrations.invalidSourcePersistence"));
    }
    normalized.persistence = {
      state: persistence.state as "saving" | "saved" | "failed" | "unavailable",
      message: persistence.message,
      ...(typeof persistence.projectId === "string"
        ? { projectId: persistence.projectId }
        : {}),
      ...(typeof persistence.versionId === "string"
        ? { versionId: persistence.versionId }
        : {}),
      ...(typeof persistence.retryable === "boolean"
        ? { retryable: persistence.retryable }
        : {}),
    };
  }
  return normalized;
}

function normalizeActivity(value: unknown): MigrationActivity {
  const activity = record(value, adkT("migrations.labels.activity"));
  if (
    typeof activity.available !== "boolean" ||
    typeof activity.complete !== "boolean" ||
    !Array.isArray(activity.items)
  ) {
    throw new Error(adkT("migrations.invalidActivity"));
  }
  return {
    available: activity.available,
    complete: activity.complete,
    items: activity.items.map((value) => {
      const item = record(value, adkT("migrations.labels.activityItem"));
      if (
        typeof item.id !== "string" ||
        typeof item.kind !== "string" ||
        !ACTIVITY_KINDS.has(item.kind as MigrationActivityKind) ||
        typeof item.status !== "string" ||
        !ACTIVITY_STATES.has(item.status as MigrationActivityItem["status"]) ||
        typeof item.title !== "string" ||
        (item.detail !== undefined && typeof item.detail !== "string")
      ) {
        throw new Error(adkT("migrations.invalidActivityItem"));
      }
      let tool: MigrationActivityTool | undefined;
      if (item.tool !== undefined) {
        const value = record(item.tool, adkT("migrations.labels.activityTool"));
        if (
          typeof value.name !== "string" ||
          (value.error !== undefined && typeof value.error !== "string") ||
          (value.exitCode !== undefined && !Number.isInteger(value.exitCode))
        ) {
          throw new Error(adkT("migrations.invalidActivityTool"));
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
          throw new Error(adkT("migrations.invalidActivityPlan"));
        }
        plan = item.plan.map((value) => {
          const planItem = record(value, adkT("migrations.labels.activityPlanItem"));
          if (
            typeof planItem.text !== "string" ||
            typeof planItem.status !== "string" ||
            !ACTIVITY_PLAN_STATES.has(
              planItem.status as MigrationActivityPlanItem["status"],
            )
          ) {
            throw new Error(adkT("migrations.invalidActivityPlanItem"));
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
  const artifact = record(value, adkT("migrations.labels.artifact"));
  const cli = record(artifact.cli, adkT("migrations.labels.cli"));
  const migration = record(artifact.migration, adkT("migrations.labels.migration"));
  const startup = record(artifact.startup, adkT("migrations.labels.startup"));
  const environment = record(artifact.environment, adkT("migrations.labels.environment"));
  const verification = record(artifact.verification, adkT("migrations.labels.verification"));
  const report = record(artifact.report, adkT("migrations.labels.report"));
  const descriptor = record(artifact.artifact, adkT("migrations.labels.archive"));
  const environmentDefaults =
    environment.defaults === undefined
      ? {}
      : record(environment.defaults, adkT("migrations.labels.environmentDefaults"));
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
    throw new Error(adkT("migrations.invalidArtifact"));
  }
  const requiredEnvironment = stringArray(
    environment.required,
    adkT("migrations.labels.requiredEnvironment"),
  );
  const optionalEnvironment = stringArray(
    environment.optional,
    adkT("migrations.labels.optionalEnvironment"),
  );
  const declaredEnvironment = new Set([
    ...requiredEnvironment,
    ...optionalEnvironment,
  ]);
  const normalizedEnvironmentDefaults = Object.fromEntries(
    Object.entries(environmentDefaults).map(([key, defaultValue]) => {
      if (!declaredEnvironment.has(key) || typeof defaultValue !== "string") {
        throw new Error(adkT("migrations.invalidEnvironmentDefaults"));
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
      const file = record(item, adkT("migrations.labels.artifactFile"));
      if (
        typeof file.path !== "string" ||
        typeof file.size !== "number" ||
        typeof file.sha256 !== "string" ||
        typeof file.mode !== "string"
      ) {
        throw new Error(adkT("migrations.invalidArtifactFile"));
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
        const check = record(item, adkT("migrations.labels.verificationCheck"));
        if (
          typeof check.name !== "string" ||
          !["passed", "failed"].includes(String(check.status))
        ) {
          throw new Error(adkT("migrations.invalidVerificationCheck"));
        }
        return {
          name: check.name,
          status: check.status as "passed" | "failed",
          ...(typeof check.detail === "string" ? { detail: check.detail } : {}),
        };
      }),
    },
    warnings: stringArray(artifact.warnings, adkT("migrations.labels.artifactWarnings")),
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
    headers: withLocaleHeaders(withLocalUser(init.headers)),
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
    .join(adkT("migrations.validationSeparator"));
}

async function errorFrom(
  response: Response,
  fallback: string,
): Promise<MigrationApiError> {
  const text = await response.text().catch(() => "");
  try {
    const body = record(JSON.parse(text), adkT("migrations.labels.errorResponse"));
    if (Array.isArray(body.detail)) {
      const detail = validationErrorDetail(body.detail);
      return new MigrationApiError(
        detail ? adkT("migrations.requestValidationFailed", { detail }) : fallback,
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
        ? record(body.detail, adkT("migrations.labels.errorDetail"))
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
      adkT("common.contentTypeMissing");
    return new MigrationApiError(
      adkT("migrations.gatewayError", { fallback, status: response.status, contentType }),
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
      adkT("migrations.nonJsonResponse", { fallback, status: response.status }),
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
      adkT("migrations.loadCapabilitiesFailed"),
    ),
    adkT("migrations.labels.capabilities"),
  );
  if (
    typeof body.enabled !== "boolean" ||
    typeof body.reason !== "string" ||
    typeof body.maxUploadBytes !== "number" ||
    typeof body.sessionTtlSeconds !== "number" ||
    !Array.isArray(body.frameworks)
  ) {
    throw new Error(adkT("migrations.invalidCapabilities"));
  }
  const capability: MigrationCapabilities = {
    enabled: body.enabled,
    reason: body.reason,
    maxUploadBytes: body.maxUploadBytes,
    sessionTtlSeconds: body.sessionTtlSeconds,
    frameworks: body.frameworks.map((item) => framework(item, adkT("migrations.labels.framework"))),
  };
  if (body.model !== undefined) {
    const model = record(body.model, adkT("migrations.labels.modelCapabilities"));
    if (typeof model.configured !== "boolean" || typeof model.id !== "string") {
      throw new Error(adkT("migrations.invalidModelCapabilities"));
    }
    capability.model = { configured: model.configured, id: model.id };
  }
  return capability;
}

export async function listMigrationTasks(
  signal?: AbortSignal,
): Promise<MigrationTask[]> {
  const body = record(
    await json(await request("/tasks", { signal }), adkT("migrations.loadTasksFailed")),
    adkT("migrations.labels.taskList"),
  );
  if (!Array.isArray(body.items)) throw new Error(adkT("migrations.invalidTaskList"));
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
      adkT("migrations.createTaskFailed"),
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
      adkT("migrations.uploadProjectFailed"),
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
      adkT("migrations.loadTasksFailed"),
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
      adkT("migrations.loadActivityFailed"),
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
      adkT("migrations.startFailed"),
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
      adkT("migrations.submitAnswersFailed"),
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
      adkT("migrations.stopFailed"),
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
    adkT("migrations.deleteTaskFailed"),
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
      adkT("migrations.loadArtifactFailed"),
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
  if (!response.ok) throw await errorFrom(response, adkT("migrations.loadArtifactFileFailed"));
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
  if (!response.ok) throw await errorFrom(response, adkT("migrations.downloadArtifactFailed"));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = responseFilename(response, `${fallbackName}-migrated.zip`);
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
