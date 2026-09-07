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

export type MigrationEvaluationDimensionId =
  | "semantic_fidelity"
  | "output_contract"
  | "workflow_tool_fidelity"
  | "context_memory_fidelity"
  | "boundary_error_fidelity"
  | "safety_refusal_fidelity";

export type MigrationEvaluationState =
  | "disabled"
  | "waiting_dataset"
  | "pending"
  | "preparing"
  | "waiting_environment"
  | "deploying"
  | "executing"
  | "judging"
  | "aggregating"
  | "cleaning"
  | "completed"
  | "failed"
  | "blocked"
  | "cancelled";

export interface MigrationEvaluationAsset {
  schemaVersion: 1;
  kind: "dataset" | "report";
  assetId: string;
  version: string;
  versionId: string;
  sha256: string;
  sizeBytes: number;
  size: number;
  createdAt: string;
  acl: "owner";
  viewReady: boolean;
  downloadReady: boolean;
  caseCount?: number;
  attempt?: number;
}

export interface MigrationEvaluationStatus {
  enabled: boolean;
  state: MigrationEvaluationState;
  message: string;
  preset?: "standard" | "custom";
  dimensions?: MigrationEvaluationDimensionId[];
  attempt?: number;
  dataset?: MigrationEvaluationAsset;
  report?: MigrationEvaluationAsset;
  requiredEnvironment?: string[];
  canResume?: boolean;
  canRetry?: boolean;
  error?: {
    code: string;
    message: string;
    retryable: boolean;
  };
}

export interface MigrationEvaluationMessage {
  role: "user" | "assistant";
  content: string;
}

export interface MigrationEvaluationCase {
  caseId: string;
  userInput: string;
  expectedOutcome?: string | null;
  criteria: string[];
  priorMessages: MigrationEvaluationMessage[];
}

export interface MigrationEvaluationDataset {
  locked: boolean;
  asset?: MigrationEvaluationAsset;
  cases: MigrationEvaluationCase[];
}

export interface MigrationEvaluationDimensionResult {
  id: MigrationEvaluationDimensionId;
  score: number | null;
  reason: string;
  evidence: string[];
  evidence_sources: MigrationEvaluationEvidenceSource[];
  severity: MigrationEvaluationSeverity;
}

export type MigrationEvaluationEvidenceSource =
  | "user_reference"
  | "user_criteria"
  | "source_contract"
  | "observed_output"
  | "deterministic_assertion";

export type MigrationEvaluationSeverity =
  | "none"
  | "low"
  | "medium"
  | "high"
  | "critical"
  | "unknown";

export interface MigrationEvaluationExecutionError {
  code: string;
  message: string;
}

export interface MigrationEvaluationReport {
  schema_version: 1;
  task_id: string;
  attempt: number;
  dataset_sha256: string;
  dataset_version: string;
  artifact_sha256: string;
  prompt_version: number;
  model: {
    id: string;
    codex_version: string;
    agentkit_cli_version: string;
  };
  dimensions: MigrationEvaluationDimensionId[];
  dimension_weights: Partial<Record<MigrationEvaluationDimensionId, number>>;
  cases: Array<{
    case_id: string;
    execution: {
      state: "succeeded" | "failed";
      error: MigrationEvaluationExecutionError | null;
    };
    output: {
      text: string;
      truncated: boolean;
      original_bytes: number;
      captured_bytes: number;
    };
    dimensions: MigrationEvaluationDimensionResult[];
  }>;
  summary: {
    score: number | null;
    dimensions: MigrationEvaluationDimensionResult[];
  };
  execution: {
    total: number;
    succeeded: number;
    failed: number;
    success_rate: number;
  };
  evidence_coverage: {
    total: number;
    scored: number;
    na: number;
    rate: number;
  };
  source_contract_only_case_count: number;
  lowest_scoring_cases: Array<{ case_id: string; score: number }>;
  execution_failures: Array<
    { case_id: string } & MigrationEvaluationExecutionError
  >;
  critical_mismatches: Array<{
    case_id: string;
    dimension_id: MigrationEvaluationDimensionId;
    severity: "critical";
    reason: string;
    evidence_sources: MigrationEvaluationEvidenceSource[];
  }>;
  migration_gap_description: string;
  runtime_cleanup: { status: "confirmed" };
  limitations: string[];
  created_at: string;
  asset: MigrationEvaluationAsset;
}

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
  evaluation?: {
    available: boolean;
    reason: string;
    maxCases: number;
    maxDatasetBytes: number;
    maxMessagesPerCase: number;
    maxMessagesBytes: number;
    maxReferenceOutputBytes: number;
    maxCriteria: number;
    maxCriterionBytes: number;
    maxCapturedOutputBytes: number;
    inputMode: "page";
    pageInputMethods: Array<"manual" | "bulk_paste">;
    defaultPreset: "standard";
    maximumSessionTtlSeconds: number;
    dimensions: Array<{
      id: MigrationEvaluationDimensionId;
      label: string;
      description: string;
    }>;
  };
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
  evaluation?: MigrationEvaluationStatus;
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

const EVALUATION_STATES = new Set<MigrationEvaluationState>([
  "disabled",
  "waiting_dataset",
  "pending",
  "preparing",
  "waiting_environment",
  "deploying",
  "executing",
  "judging",
  "aggregating",
  "cleaning",
  "completed",
  "failed",
  "blocked",
  "cancelled",
]);

const EVALUATION_DIMENSIONS = new Set<MigrationEvaluationDimensionId>([
  "semantic_fidelity",
  "output_contract",
  "workflow_tool_fidelity",
  "context_memory_fidelity",
  "boundary_error_fidelity",
  "safety_refusal_fidelity",
]);

const EVALUATION_EVIDENCE_SOURCES = new Set<MigrationEvaluationEvidenceSource>([
  "user_reference",
  "user_criteria",
  "source_contract",
  "observed_output",
  "deterministic_assertion",
]);

const EVALUATION_SEVERITIES = new Set<MigrationEvaluationSeverity>([
  "none",
  "low",
  "medium",
  "high",
  "critical",
  "unknown",
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
  if (
    !Array.isArray(value) ||
    !value.every((item) => typeof item === "string")
  ) {
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return value;
}

function framework(value: unknown, label: string): MigrationFramework {
  if (
    typeof value !== "string" ||
    !FRAMEWORKS.has(value as MigrationFramework)
  ) {
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return value as MigrationFramework;
}

function evaluationDimension(
  value: unknown,
  label: string,
): MigrationEvaluationDimensionId {
  if (
    typeof value !== "string" ||
    !EVALUATION_DIMENSIONS.has(value as MigrationEvaluationDimensionId)
  ) {
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return value as MigrationEvaluationDimensionId;
}

function evaluationEvidenceSources(
  value: unknown,
): MigrationEvaluationEvidenceSource[] {
  if (
    !Array.isArray(value) ||
    !value.every(
      (item) =>
        typeof item === "string" &&
        EVALUATION_EVIDENCE_SOURCES.has(
          item as MigrationEvaluationEvidenceSource,
        ),
    )
  ) {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.evaluationEvidence"),
      }),
    );
  }
  return value as MigrationEvaluationEvidenceSource[];
}

function normalizeEvaluationAsset(value: unknown): MigrationEvaluationAsset {
  const asset = record(value, adkT("migrations.labels.evaluationAsset"));
  if (
    asset.schemaVersion !== 1 ||
    !["dataset", "report"].includes(String(asset.kind)) ||
    typeof asset.assetId !== "string" ||
    typeof asset.version !== "string" ||
    typeof asset.versionId !== "string" ||
    typeof asset.sha256 !== "string" ||
    typeof asset.sizeBytes !== "number" ||
    typeof asset.size !== "number" ||
    typeof asset.createdAt !== "string" ||
    asset.acl !== "owner" ||
    typeof asset.viewReady !== "boolean" ||
    typeof asset.downloadReady !== "boolean"
  ) {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.evaluationAsset"),
      }),
    );
  }
  return {
    schemaVersion: 1,
    kind: asset.kind as "dataset" | "report",
    assetId: asset.assetId,
    version: asset.version,
    versionId: asset.versionId,
    sha256: asset.sha256,
    sizeBytes: asset.sizeBytes,
    size: asset.size,
    createdAt: asset.createdAt,
    acl: "owner",
    viewReady: asset.viewReady,
    downloadReady: asset.downloadReady,
    ...(typeof asset.caseCount === "number"
      ? { caseCount: asset.caseCount }
      : {}),
    ...(typeof asset.attempt === "number" ? { attempt: asset.attempt } : {}),
  };
}

function normalizeEvaluation(value: unknown): MigrationEvaluationStatus {
  const evaluation = record(value, adkT("migrations.labels.evaluation"));
  if (
    typeof evaluation.enabled !== "boolean" ||
    typeof evaluation.state !== "string" ||
    !EVALUATION_STATES.has(evaluation.state as MigrationEvaluationState) ||
    typeof evaluation.message !== "string"
  ) {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.evaluation"),
      }),
    );
  }
  const normalized: MigrationEvaluationStatus = {
    enabled: evaluation.enabled,
    state: evaluation.state as MigrationEvaluationState,
    message: evaluation.message,
  };
  if (evaluation.preset === "standard" || evaluation.preset === "custom") {
    normalized.preset = evaluation.preset;
  }
  if (Array.isArray(evaluation.dimensions)) {
    normalized.dimensions = evaluation.dimensions.map((item) =>
      evaluationDimension(item, adkT("migrations.labels.evaluationDimension")),
    );
  }
  if (typeof evaluation.attempt === "number")
    normalized.attempt = evaluation.attempt;
  if (evaluation.dataset !== undefined) {
    normalized.dataset = normalizeEvaluationAsset(evaluation.dataset);
  }
  if (evaluation.report !== undefined) {
    normalized.report = normalizeEvaluationAsset(evaluation.report);
  }
  if (evaluation.requiredEnvironment !== undefined) {
    normalized.requiredEnvironment = stringArray(
      evaluation.requiredEnvironment,
      adkT("migrations.labels.requiredEnvironment"),
    );
  }
  if (typeof evaluation.canResume === "boolean")
    normalized.canResume = evaluation.canResume;
  if (typeof evaluation.canRetry === "boolean")
    normalized.canRetry = evaluation.canRetry;
  if (evaluation.error !== undefined) {
    const error = record(evaluation.error, adkT("migrations.labels.error"));
    normalized.error = {
      code:
        typeof error.code === "string"
          ? error.code
          : "MIGRATION_EVALUATION_ERROR",
      message:
        typeof error.message === "string" ? error.message : evaluation.message,
      retryable: error.retryable === true,
    };
  }
  return normalized;
}

function normalizeAnalysis(value: unknown): MigrationAnalysis {
  const analysis = record(value, adkT("migrations.labels.analysisResult"));
  const recommended =
    analysis.recommended === null
      ? null
      : record(analysis.recommended, adkT("migrations.labels.recommendation"));
  const boundary = record(
    analysis.boundary,
    adkT("migrations.labels.boundary"),
  );
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
      const candidate = record(
        item,
        adkT("migrations.labels.frameworkCandidate"),
      );
      if (
        !["high", "medium", "low"].includes(String(candidate.confidence)) ||
        !Array.isArray(candidate.evidence)
      ) {
        throw new Error(adkT("migrations.invalidFrameworkCandidate"));
      }
      return {
        id: framework(
          candidate.id,
          adkT("migrations.labels.frameworkCandidate"),
        ),
        confidence: candidate.confidence as "high" | "medium" | "low",
        evidence: candidate.evidence.map((evidenceValue) => {
          const evidence = record(
            evidenceValue,
            adkT("migrations.labels.analysisEvidence"),
          );
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
            framework: framework(
              recommended.framework,
              adkT("migrations.labels.recommendedFramework"),
            ),
            entry:
              recommended.entry === null ||
              typeof recommended.entry === "string"
                ? recommended.entry
                : null,
            reason:
              typeof recommended.reason === "string" ? recommended.reason : "",
          },
    entries: analysis.entries.map((item) => {
      const entry = record(item, adkT("migrations.labels.entryCandidate"));
      if (
        typeof entry.value !== "string" ||
        typeof entry.evidence !== "string"
      ) {
        throw new Error(adkT("migrations.invalidEntryCandidate"));
      }
      return {
        value: entry.value,
        framework: framework(
          entry.framework,
          adkT("migrations.labels.entryFramework"),
        ),
        evidence: entry.evidence,
      };
    }),
    boundary: {
      include: stringArray(
        boundary.include,
        adkT("migrations.labels.includeScope"),
      ),
      exclude: stringArray(
        boundary.exclude,
        adkT("migrations.labels.excludeScope"),
      ),
    },
    assumptions: stringArray(
      analysis.assumptions,
      adkT("migrations.labels.assumptions"),
    ),
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
    warnings: stringArray(
      analysis.warnings,
      adkT("migrations.labels.analysisWarnings"),
    ),
  };
}

function normalizeTask(value: unknown): MigrationTask {
  const task = record(value, adkT("migrations.labels.task"));
  const artifact = record(
    task.artifact,
    adkT("migrations.labels.artifactStatus"),
  );
  if (
    typeof task.id !== "string" ||
    typeof task.state !== "string" ||
    !TASK_STATES.has(task.state as MigrationTaskState) ||
    typeof task.message !== "string" ||
    typeof task.sourceFileName !== "string" ||
    typeof task.instruction !== "string" ||
    (typeof task.createdAt !== "string" &&
      typeof task.createdAt !== "number") ||
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
  if (task.analysis !== undefined)
    normalized.analysis = normalizeAnalysis(task.analysis);
  if (task.analysisRef !== undefined) {
    const reference = record(
      task.analysisRef,
      adkT("migrations.labels.analysisReference"),
    );
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
    const confirmation = record(
      task.confirmation,
      adkT("migrations.labels.confirmation"),
    );
    normalized.confirmation = {
      ...(confirmation.framework !== undefined
        ? {
            framework: framework(
              confirmation.framework,
              adkT("migrations.labels.confirmedFramework"),
            ),
          }
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
    const persistence = record(
      task.persistence,
      adkT("migrations.labels.sourcePersistence"),
    );
    if (
      !["saving", "saved", "failed", "unavailable"].includes(
        String(persistence.state),
      ) ||
      typeof persistence.message !== "string" ||
      (persistence.projectId !== undefined &&
        typeof persistence.projectId !== "string") ||
      (persistence.versionId !== undefined &&
        typeof persistence.versionId !== "string") ||
      (persistence.retryable !== undefined &&
        typeof persistence.retryable !== "boolean")
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
  if (task.evaluation !== undefined) {
    normalized.evaluation = normalizeEvaluation(task.evaluation);
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
          const planItem = record(
            value,
            adkT("migrations.labels.activityPlanItem"),
          );
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
  const migration = record(
    artifact.migration,
    adkT("migrations.labels.migration"),
  );
  const startup = record(artifact.startup, adkT("migrations.labels.startup"));
  const environment = record(
    artifact.environment,
    adkT("migrations.labels.environment"),
  );
  const verification = record(
    artifact.verification,
    adkT("migrations.labels.verification"),
  );
  const report = record(artifact.report, adkT("migrations.labels.report"));
  const descriptor = record(
    artifact.artifact,
    adkT("migrations.labels.archive"),
  );
  const environmentDefaults =
    environment.defaults === undefined
      ? {}
      : record(
          environment.defaults,
          adkT("migrations.labels.environmentDefaults"),
        );
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
      ...(typeof migration.entry === "string"
        ? { entry: migration.entry }
        : {}),
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
      status:
        verification.status as MigrationArtifact["verification"]["status"],
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
    warnings: stringArray(
      artifact.warnings,
      adkT("migrations.labels.artifactWarnings"),
    ),
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
    const body = record(
      JSON.parse(text),
      adkT("migrations.labels.errorResponse"),
    );
    if (Array.isArray(body.detail)) {
      const detail = validationErrorDetail(body.detail);
      return new MigrationApiError(
        detail
          ? adkT("migrations.requestValidationFailed", { detail })
          : fallback,
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
      adkT("migrations.gatewayError", {
        fallback,
        status: response.status,
        contentType,
      }),
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
    frameworks: body.frameworks.map((item) =>
      framework(item, adkT("migrations.labels.framework")),
    ),
  };
  if (body.model !== undefined) {
    const model = record(
      body.model,
      adkT("migrations.labels.modelCapabilities"),
    );
    if (typeof model.configured !== "boolean" || typeof model.id !== "string") {
      throw new Error(adkT("migrations.invalidModelCapabilities"));
    }
    capability.model = { configured: model.configured, id: model.id };
  }
  if (body.evaluation !== undefined) {
    const evaluation = record(
      body.evaluation,
      adkT("migrations.labels.evaluationCapabilities"),
    );
    if (
      typeof evaluation.available !== "boolean" ||
      typeof evaluation.reason !== "string" ||
      typeof evaluation.maxCases !== "number" ||
      typeof evaluation.maxDatasetBytes !== "number" ||
      typeof evaluation.maxMessagesPerCase !== "number" ||
      typeof evaluation.maxMessagesBytes !== "number" ||
      typeof evaluation.maxReferenceOutputBytes !== "number" ||
      typeof evaluation.maxCriteria !== "number" ||
      typeof evaluation.maxCriterionBytes !== "number" ||
      typeof evaluation.maxCapturedOutputBytes !== "number" ||
      evaluation.inputMode !== "page" ||
      !Array.isArray(evaluation.pageInputMethods) ||
      !evaluation.pageInputMethods.every((item) =>
        ["manual", "bulk_paste"].includes(String(item)),
      ) ||
      evaluation.defaultPreset !== "standard" ||
      typeof evaluation.maximumSessionTtlSeconds !== "number" ||
      !Array.isArray(evaluation.dimensions)
    ) {
      throw new Error(
        adkT("migrations.invalidFormat", {
          label: adkT("migrations.labels.evaluationCapabilities"),
        }),
      );
    }
    capability.evaluation = {
      available: evaluation.available,
      reason: evaluation.reason,
      maxCases: evaluation.maxCases,
      maxDatasetBytes: evaluation.maxDatasetBytes,
      maxMessagesPerCase: evaluation.maxMessagesPerCase,
      maxMessagesBytes: evaluation.maxMessagesBytes,
      maxReferenceOutputBytes: evaluation.maxReferenceOutputBytes,
      maxCriteria: evaluation.maxCriteria,
      maxCriterionBytes: evaluation.maxCriterionBytes,
      maxCapturedOutputBytes: evaluation.maxCapturedOutputBytes,
      inputMode: "page",
      pageInputMethods: evaluation.pageInputMethods as Array<
        "manual" | "bulk_paste"
      >,
      defaultPreset: "standard",
      maximumSessionTtlSeconds: evaluation.maximumSessionTtlSeconds,
      dimensions: evaluation.dimensions.map((item) => {
        const dimension = record(
          item,
          adkT("migrations.labels.evaluationDimension"),
        );
        if (
          typeof dimension.label !== "string" ||
          typeof dimension.description !== "string"
        ) {
          throw new Error(
            adkT("migrations.invalidFormat", {
              label: adkT("migrations.labels.evaluationDimension"),
            }),
          );
        }
        return {
          id: evaluationDimension(
            dimension.id,
            adkT("migrations.labels.evaluationDimension"),
          ),
          label: dimension.label,
          description: dimension.description,
        };
      }),
    };
  }
  return capability;
}

export async function listMigrationTasks(
  signal?: AbortSignal,
): Promise<MigrationTask[]> {
  const body = record(
    await json(
      await request("/tasks", { signal }),
      adkT("migrations.loadTasksFailed"),
    ),
    adkT("migrations.labels.taskList"),
  );
  if (!Array.isArray(body.items))
    throw new Error(adkT("migrations.invalidTaskList"));
  return body.items.map(normalizeTask);
}

export async function createMigrationTask(args: {
  taskId: string;
  sourceFileName: string;
  instruction: string;
  modelId?: string;
  evaluation?: {
    enabled: true;
    preset: "standard" | "custom";
    dimensions?: MigrationEvaluationDimensionId[];
  };
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
            ...(args.evaluation ? { evaluation: args.evaluation } : {}),
          }),
          signal: args.signal,
        },
        SESSION_START_TIMEOUT_MS,
      ),
      adkT("migrations.createTaskFailed"),
    ),
  );
}

function normalizeEvaluationCase(value: unknown): MigrationEvaluationCase {
  const item = record(value, adkT("migrations.labels.evaluationCase"));
  if (
    typeof item.caseId !== "string" ||
    typeof item.userInput !== "string" ||
    !Array.isArray(item.priorMessages) ||
    !Array.isArray(item.criteria)
  ) {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.evaluationCase"),
      }),
    );
  }
  return {
    caseId: item.caseId,
    userInput: item.userInput,
    expectedOutcome:
      item.expectedOutcome === null || typeof item.expectedOutcome === "string"
        ? item.expectedOutcome
        : null,
    criteria: stringArray(
      item.criteria,
      adkT("migrations.labels.evaluationCriteria"),
    ),
    priorMessages: item.priorMessages.map((messageValue) => {
      const message = record(
        messageValue,
        adkT("migrations.labels.evaluationMessage"),
      );
      if (
        !["user", "assistant"].includes(String(message.role)) ||
        typeof message.content !== "string"
      ) {
        throw new Error(
          adkT("migrations.invalidFormat", {
            label: adkT("migrations.labels.evaluationMessage"),
          }),
        );
      }
      return {
        role: message.role as "user" | "assistant",
        content: message.content,
      };
    }),
  };
}

function normalizeEvaluationDataset(
  value: unknown,
): MigrationEvaluationDataset {
  const dataset = record(value, adkT("migrations.labels.evaluationDataset"));
  if (typeof dataset.locked !== "boolean" || !Array.isArray(dataset.cases)) {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.evaluationDataset"),
      }),
    );
  }
  return {
    locked: dataset.locked,
    cases: dataset.cases.map(normalizeEvaluationCase),
    ...(dataset.asset !== undefined
      ? { asset: normalizeEvaluationAsset(dataset.asset) }
      : {}),
  };
}

export async function putMigrationEvaluationDataset(
  taskId: string,
  cases: MigrationEvaluationCase[],
  signal?: AbortSignal,
): Promise<MigrationEvaluationDataset> {
  return normalizeEvaluationDataset(
    await json(
      await request(
        `/tasks/${encodeURIComponent(taskId)}/evaluation/dataset`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cases }),
          signal,
        },
        TRANSFER_REQUEST_TIMEOUT_MS,
      ),
      adkT("migrations.evaluation.datasetSaveFailed"),
    ),
  );
}

export async function getMigrationEvaluationDataset(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationEvaluationDataset> {
  return normalizeEvaluationDataset(
    await json(
      await request(`/tasks/${encodeURIComponent(taskId)}/evaluation/dataset`, {
        signal,
      }),
      adkT("migrations.evaluation.datasetLoadFailed"),
    ),
  );
}

export async function getMigrationEvaluation(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationEvaluationStatus> {
  return normalizeEvaluation(
    await json(
      await request(`/tasks/${encodeURIComponent(taskId)}/evaluation`, {
        signal,
      }),
      adkT("migrations.evaluation.statusLoadFailed"),
    ),
  );
}

export async function resumeMigrationEvaluation(
  taskId: string,
  environment: Record<string, string>,
  signal?: AbortSignal,
): Promise<MigrationEvaluationStatus> {
  return normalizeEvaluation(
    await json(
      await request(
        `/tasks/${encodeURIComponent(taskId)}/evaluation/resume`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ environment }),
          signal,
        },
        SESSION_START_TIMEOUT_MS,
      ),
      adkT("migrations.evaluation.resumeFailed"),
    ),
  );
}

export async function retryMigrationEvaluation(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationEvaluationStatus> {
  return normalizeEvaluation(
    await json(
      await request(
        `/tasks/${encodeURIComponent(taskId)}/evaluation/retry`,
        { method: "POST", signal },
        SESSION_START_TIMEOUT_MS,
      ),
      adkT("migrations.evaluation.retryFailed"),
    ),
  );
}

function isEvaluationScore(value: unknown): value is number | null {
  return (
    value === null ||
    (typeof value === "number" &&
      Number.isInteger(value) &&
      value >= 0 &&
      value <= 100)
  );
}

function normalizeDimensionResult(
  value: unknown,
): MigrationEvaluationDimensionResult {
  const result = record(
    value,
    adkT("migrations.labels.evaluationDimensionResult"),
  );
  if (
    !isEvaluationScore(result.score) ||
    typeof result.reason !== "string" ||
    !Array.isArray(result.evidence) ||
    !result.evidence.every((item) => typeof item === "string") ||
    typeof result.severity !== "string" ||
    !EVALUATION_SEVERITIES.has(
      result.severity as MigrationEvaluationSeverity,
    )
  ) {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.evaluationDimensionResult"),
      }),
    );
  }
  return {
    id: evaluationDimension(
      result.id,
      adkT("migrations.labels.evaluationDimension"),
    ),
    score: result.score as number | null,
    reason: result.reason,
    evidence: stringArray(
      result.evidence,
      adkT("migrations.labels.evaluationEvidence"),
    ),
    evidence_sources: evaluationEvidenceSources(result.evidence_sources),
    severity: result.severity as MigrationEvaluationSeverity,
  };
}

function evaluationCount(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return value;
}

function evaluationPercentage(value: unknown, label: string): number {
  const normalized = evaluationCount(value, label);
  if (normalized > 100) {
    throw new Error(adkT("migrations.invalidFormat", { label }));
  }
  return normalized;
}

function normalizeEvaluationExecutionError(
  value: unknown,
): MigrationEvaluationExecutionError {
  const error = record(value, adkT("migrations.labels.error"));
  if (typeof error.code !== "string" || typeof error.message !== "string") {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.error"),
      }),
    );
  }
  return { code: error.code, message: error.message };
}

export async function getMigrationEvaluationReport(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationEvaluationReport> {
  const value = record(
    await json(
      await request(`/tasks/${encodeURIComponent(taskId)}/evaluation/report`, {
        signal,
      }),
      adkT("migrations.evaluation.reportLoadFailed"),
    ),
    adkT("migrations.labels.evaluationReport"),
  );
  const summary = record(
    value.summary,
    adkT("migrations.labels.evaluationSummary"),
  );
  const model = record(value.model, adkT("migrations.labels.modelCapabilities"));
  const execution = record(
    value.execution,
    adkT("migrations.labels.evaluationReport"),
  );
  const coverage = record(
    value.evidence_coverage,
    adkT("migrations.labels.evaluationReport"),
  );
  const cleanup = record(
    value.runtime_cleanup,
    adkT("migrations.labels.evaluationReport"),
  );
  const weights = record(
    value.dimension_weights,
    adkT("migrations.labels.evaluationReport"),
  );
  if (
    value.schema_version !== 1 ||
    typeof value.task_id !== "string" ||
    typeof value.attempt !== "number" ||
    typeof value.dataset_sha256 !== "string" ||
    typeof value.dataset_version !== "string" ||
    typeof value.artifact_sha256 !== "string" ||
    typeof value.prompt_version !== "number" ||
    !Number.isInteger(value.prompt_version) ||
    value.prompt_version < 1 ||
    typeof model.id !== "string" ||
    typeof model.codex_version !== "string" ||
    typeof model.agentkit_cli_version !== "string" ||
    !Array.isArray(value.dimensions) ||
    !Array.isArray(value.cases) ||
    !Array.isArray(value.lowest_scoring_cases) ||
    !Array.isArray(value.execution_failures) ||
    !Array.isArray(value.critical_mismatches) ||
    typeof value.migration_gap_description !== "string" ||
    cleanup.status !== "confirmed" ||
    !Array.isArray(value.limitations) ||
    typeof value.created_at !== "string" ||
    !isEvaluationScore(summary.score) ||
    !Array.isArray(summary.dimensions)
  ) {
    throw new Error(
      adkT("migrations.invalidFormat", {
        label: adkT("migrations.labels.evaluationReport"),
      }),
    );
  }
  const dimensions = value.dimensions.map((item) =>
    evaluationDimension(item, adkT("migrations.labels.evaluationDimension")),
  );
  const dimensionWeights = Object.fromEntries(
    dimensions.map((dimension) => {
      const weight = weights[dimension];
      if (typeof weight !== "number" || weight <= 0) {
        throw new Error(
          adkT("migrations.invalidFormat", {
            label: adkT("migrations.labels.evaluationReport"),
          }),
        );
      }
      return [dimension, weight];
    }),
  ) as Partial<Record<MigrationEvaluationDimensionId, number>>;
  return {
    schema_version: 1,
    task_id: value.task_id,
    attempt: value.attempt,
    dataset_sha256: value.dataset_sha256,
    dataset_version: value.dataset_version,
    artifact_sha256: value.artifact_sha256,
    prompt_version: value.prompt_version,
    model: {
      id: model.id,
      codex_version: model.codex_version,
      agentkit_cli_version: model.agentkit_cli_version,
    },
    dimensions,
    dimension_weights: dimensionWeights,
    cases: value.cases.map((caseValue) => {
      const item = record(
        caseValue,
        adkT("migrations.labels.evaluationCaseResult"),
      );
      const output = record(
        item.output,
        adkT("migrations.labels.evaluationOutput"),
      );
      const caseExecution = record(
        item.execution,
        adkT("migrations.labels.evaluationCaseResult"),
      );
      if (
        typeof item.case_id !== "string" ||
        !Array.isArray(item.dimensions) ||
        !["succeeded", "failed"].includes(String(caseExecution.state)) ||
        (caseExecution.state === "succeeded" && caseExecution.error !== null) ||
        (caseExecution.state === "failed" && caseExecution.error === null) ||
        typeof output.text !== "string" ||
        typeof output.truncated !== "boolean" ||
        typeof output.original_bytes !== "number" ||
        typeof output.captured_bytes !== "number"
      ) {
        throw new Error(
          adkT("migrations.invalidFormat", {
            label: adkT("migrations.labels.evaluationCaseResult"),
          }),
        );
      }
      return {
        case_id: item.case_id,
        execution: {
          state: caseExecution.state as "succeeded" | "failed",
          error:
            caseExecution.error === null
              ? null
              : normalizeEvaluationExecutionError(caseExecution.error),
        },
        output: {
          text: output.text,
          truncated: output.truncated,
          original_bytes: output.original_bytes,
          captured_bytes: output.captured_bytes,
        },
        dimensions: item.dimensions.map(normalizeDimensionResult),
      };
    }),
    summary: {
      score: summary.score as number | null,
      dimensions: summary.dimensions.map(normalizeDimensionResult),
    },
    execution: {
      total: evaluationCount(
        execution.total,
        adkT("migrations.labels.evaluationReport"),
      ),
      succeeded: evaluationCount(
        execution.succeeded,
        adkT("migrations.labels.evaluationReport"),
      ),
      failed: evaluationCount(
        execution.failed,
        adkT("migrations.labels.evaluationReport"),
      ),
      success_rate: evaluationPercentage(
        execution.success_rate,
        adkT("migrations.labels.evaluationReport"),
      ),
    },
    evidence_coverage: {
      total: evaluationCount(
        coverage.total,
        adkT("migrations.labels.evaluationReport"),
      ),
      scored: evaluationCount(
        coverage.scored,
        adkT("migrations.labels.evaluationReport"),
      ),
      na: evaluationCount(
        coverage.na,
        adkT("migrations.labels.evaluationReport"),
      ),
      rate: evaluationPercentage(
        coverage.rate,
        adkT("migrations.labels.evaluationReport"),
      ),
    },
    source_contract_only_case_count: evaluationCount(
      value.source_contract_only_case_count,
      adkT("migrations.labels.evaluationReport"),
    ),
    lowest_scoring_cases: value.lowest_scoring_cases.map((itemValue) => {
      const item = record(
        itemValue,
        adkT("migrations.labels.evaluationCaseResult"),
      );
      if (typeof item.case_id !== "string" || !isEvaluationScore(item.score) || item.score === null) {
        throw new Error(
          adkT("migrations.invalidFormat", {
            label: adkT("migrations.labels.evaluationCaseResult"),
          }),
        );
      }
      return { case_id: item.case_id, score: item.score };
    }),
    execution_failures: value.execution_failures.map((itemValue) => {
      const item = record(
        itemValue,
        adkT("migrations.labels.evaluationCaseResult"),
      );
      if (typeof item.case_id !== "string") {
        throw new Error(
          adkT("migrations.invalidFormat", {
            label: adkT("migrations.labels.evaluationCaseResult"),
          }),
        );
      }
      return {
        case_id: item.case_id,
        ...normalizeEvaluationExecutionError(item),
      };
    }),
    critical_mismatches: value.critical_mismatches.map((itemValue) => {
      const item = record(
        itemValue,
        adkT("migrations.labels.evaluationDimensionResult"),
      );
      if (
        typeof item.case_id !== "string" ||
        item.severity !== "critical" ||
        typeof item.reason !== "string"
      ) {
        throw new Error(
          adkT("migrations.invalidFormat", {
            label: adkT("migrations.labels.evaluationDimensionResult"),
          }),
        );
      }
      return {
        case_id: item.case_id,
        dimension_id: evaluationDimension(
          item.dimension_id,
          adkT("migrations.labels.evaluationDimension"),
        ),
        severity: "critical" as const,
        reason: item.reason,
        evidence_sources: evaluationEvidenceSources(item.evidence_sources),
      };
    }),
    migration_gap_description: value.migration_gap_description,
    runtime_cleanup: { status: "confirmed" },
    limitations: stringArray(
      value.limitations,
      adkT("migrations.labels.evaluationLimitations"),
    ),
    created_at: value.created_at,
    asset: normalizeEvaluationAsset(value.asset),
  };
}

export async function downloadMigrationEvaluationReport(
  taskId: string,
  signal?: AbortSignal,
): Promise<void> {
  const response = await request(
    `/tasks/${encodeURIComponent(taskId)}/evaluation/report/download`,
    { signal },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw await errorFrom(
      response,
      adkT("migrations.evaluation.reportDownloadFailed"),
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = responseFilename(response, `${taskId}-evaluation-report.md`);
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
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
      await request(`/tasks/${encodeURIComponent(taskId)}/activity`, {
        signal,
        cache: "no-store",
      }),
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
      await request(`/tasks/${encodeURIComponent(taskId)}/stop`, {
        method: "POST",
        signal,
      }),
      adkT("migrations.stopFailed"),
    ),
  );
}

export async function deleteMigrationTask(
  taskId: string,
  signal?: AbortSignal,
): Promise<void> {
  await json(
    await request(`/tasks/${encodeURIComponent(taskId)}`, {
      method: "DELETE",
      signal,
    }),
    adkT("migrations.deleteTaskFailed"),
  );
}

export async function getMigrationArtifact(
  taskId: string,
  signal?: AbortSignal,
): Promise<MigrationArtifact> {
  return normalizeArtifact(
    await json(
      await request(`/tasks/${encodeURIComponent(taskId)}/artifact`, {
        signal,
      }),
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
  if (!response.ok)
    throw await errorFrom(response, adkT("migrations.loadArtifactFileFailed"));
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
  if (!response.ok)
    throw await errorFrom(response, adkT("migrations.downloadArtifactFailed"));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = responseFilename(response, `${fallbackName}-migrated.zip`);
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
