import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import type { AgentProject } from "../create/project";
import type { AgentDraft } from "../create/types";
import type {
  CandidateVersion,
  CreateCandidateInput,
  DatasetDraft,
  DatasetVersion,
  EvaluationPolicyDraft,
  EvaluationPolicyVersion,
  EvaluationRunVersion,
  EvaluatorDraft,
  EvaluatorDraftRecommendation,
  EvaluatorGroupPublicationResult,
  EvaluatorTrialReport,
  EvaluatorTrialSample,
  EvaluatorVersion,
  FeedbackCandidateVersion,
  PublishAudit,
  PublishIntentVersion,
  PublishedVersion,
  ScenarioEvaluationWorkspaceData,
  SceneDraft,
  SceneVersion,
} from "../evaluation/types";

const SCENARIO_API = "/web/scenario-evaluation";

function unique(values: Array<string | undefined>): string[] {
  return [...new Set(values.map((value) => value?.trim()).filter((value): value is string => Boolean(value)))];
}

function allDraftAgents(draft?: AgentDraft): AgentDraft[] {
  if (!draft) return [];
  return [draft, ...draft.subAgents.flatMap((item) => allDraftAgents(item))];
}

function hex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function sha256(value: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error("当前浏览器不支持安全摘要，无法生成待测版本。");
  }
  return hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

function canonicalJson(value: unknown): string {
  const normalize = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(normalize);
    if (item && typeof item === "object") {
      return Object.fromEntries(
        Object.entries(item as Record<string, unknown>)
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([key, nested]) => [key, normalize(nested)]),
      );
    }
    return item;
  };
  return JSON.stringify(normalize(value));
}

function topologySnapshot(draft: AgentDraft | undefined, projectName: string): unknown {
  if (!draft) return { name: projectName, agentType: "generated" };
  return {
    name: draft.name,
    agentType: draft.agentType ?? "llm",
    maxIterations: draft.maxIterations ?? null,
    subAgents: draft.subAgents.map((item) => topologySnapshot(item, item.name)),
  };
}

export async function buildProjectCandidateInput(
  agentId: string,
  project: AgentProject,
  draft?: AgentDraft,
  environmentKeys: string[] = [],
  deploymentProfile: Record<string, unknown> = {},
  agentIdentityAttestation = "",
): Promise<CreateCandidateInput> {
  const agents = allDraftAgents(draft);
  const frozenProject: AgentProject = {
    name: project.name,
    files: [...project.files]
      .map((file) => ({ path: file.path, content: file.content }))
      .sort((left, right) => left.path.localeCompare(right.path)),
    attestation: project.attestation,
  };
  const promptRefs = await Promise.all(
    agents
      .filter((item) => item.instruction.trim())
      .map(async (item) => `prompt:${item.name}:${await sha256(item.instruction)}`),
  );
  const modelApiKeyId = draft?.deployment?.modelApiKeyId?.trim();
  return {
    agentId,
    artifact: {
      codeDigest: await sha256(JSON.stringify(frozenProject.files)),
      topologyDigest: await sha256(canonicalJson({
        topology: topologySnapshot(draft, project.name),
        deploymentProfile,
      })),
      modelRefs: unique(agents.map((item) => item.modelName || item.model)),
      promptRefs,
      toolRefs: unique(agents.flatMap((item) => [
        ...item.tools,
        ...(item.builtinTools ?? []),
        ...(item.customTools ?? []).map((tool) => `custom:${tool.name}`),
        ...(item.mcpTools ?? []).map((tool) => `mcp:${tool.name}`),
      ])),
      skillRefs: unique(agents.flatMap((item) => [
        ...item.skills,
        ...(item.selectedSkills ?? []).map((skill) =>
          skill.version ? `${skill.source}:${skill.name}:${skill.version}` : `${skill.source}:${skill.name}`,
        ),
      ])),
      knowledgeRefs: unique(agents
        .filter((item) => item.knowledgebase)
        .map((item) => `${item.knowledgebaseBackend ?? "local"}:${item.knowledgebaseIndex || "configured"}`)),
      memoryRefs: unique(agents.flatMap((item) => [
        item.memory.shortTerm ? `short:${item.shortTermBackend ?? "local"}` : undefined,
        item.memory.longTerm ? `long:${item.longTermBackend ?? "local"}` : undefined,
      ])),
      environmentRefs: [
        ...(modelApiKeyId ? [{ name: "MODEL_AGENT_API_KEY", reference: `ark-api-key://${modelApiKeyId}` }] : []),
        ...unique(environmentKeys).map((name) => ({ name, reference: `env://${name}` })),
      ],
      runtimeProjectRef: null,
    },
    runtimeProject: {
      ...frozenProject,
      deploymentProfile,
      agentIdentityAttestation,
    },
  };
}

export function deploymentProfileFingerprint(
  deploymentProfile: Record<string, unknown>,
): Promise<string> {
  return sha256(canonicalJson(deploymentProfile)).then((digest) => `sha256:${digest}`);
}

interface ScenarioErrorDetail {
  code?: string;
  message?: string;
}

export class ScenarioEvaluationApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryable: boolean;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ScenarioEvaluationApiError";
    this.status = status;
    this.code = code;
    this.retryable = status === 408 || status === 429 || status >= 500;
  }
}

async function scenarioRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = withLocalUser(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(withAuth(`${SCENARIO_API}${path}`), {
    ...init,
    headers,
  });
  if (!response.ok) {
    let detail: ScenarioErrorDetail | undefined;
    try {
      const body = (await response.json()) as { detail?: ScenarioErrorDetail };
      detail = body.detail;
    } catch {
      detail = undefined;
    }
    throw new ScenarioEvaluationApiError(
      response.status,
      detail?.code ?? "request_failed",
      detail?.message ?? `场景评测请求失败（HTTP ${response.status}）`,
    );
  }
  return response.json() as Promise<T>;
}

function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return scenarioRequest<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

export async function getScenarioEvaluationWorkspace(
  agentId: string,
  signal?: AbortSignal,
): Promise<ScenarioEvaluationWorkspaceData> {
  const params = new URLSearchParams({ agentId });
  return scenarioRequest<ScenarioEvaluationWorkspaceData>(
    `/workspace?${params.toString()}`,
    { signal },
  );
}

export function reviewFeedbackCandidate(
  candidateId: string,
  body: {
    agentId: string;
    expectedRevision: number;
    input: string;
    expectedOutput: string;
    comment?: string;
    labels?: string[];
  },
): Promise<FeedbackCandidateVersion> {
  return post(`/feedback-candidates/${encodeURIComponent(candidateId)}/review`, body);
}

export function rejectFeedbackCandidate(
  candidateId: string,
  body: { agentId: string; expectedRevision: number; reason: string },
): Promise<FeedbackCandidateVersion> {
  return post(`/feedback-candidates/${encodeURIComponent(candidateId)}/reject`, body);
}

export function mergeFeedbackCandidate(
  candidateId: string,
  body: {
    agentId: string;
    expectedRevision: number;
    targetCandidateId: string;
    reason: string;
  },
): Promise<FeedbackCandidateVersion> {
  return post(`/feedback-candidates/${encodeURIComponent(candidateId)}/merge`, body);
}

export function convertFeedbackCandidate(
  candidateId: string,
  body: {
    agentId: string;
    expectedRevision: number;
    datasetId: string;
    expectedDatasetRevision: number;
    datasetName: string;
    sceneVersionId: string;
    passCriteria: string[];
    redactionStatus?: "pending" | "redacted" | "not_required";
  },
): Promise<{ feedbackCandidate: FeedbackCandidateVersion; datasetDraft: DatasetDraft }> {
  return post(`/feedback-candidates/${encodeURIComponent(candidateId)}/convert`, body);
}

export function saveSceneDraft(
  body: {
    agentId: string;
    sceneId: string;
    expectedRevision: number;
    name: string;
    description: string;
    userTask: string;
    passCriteria: string[];
    hardFailureConditions: string[];
    ownerId: string;
    linkedDatasetIds?: string[];
    enabled?: boolean;
    requirement: "must_pass" | "observation";
  },
): Promise<SceneDraft> {
  return post("/scene-drafts", body);
}

export function publishSceneVersion(
  body: { agentId: string; assetId: string; draftRevision: number },
): Promise<SceneVersion> {
  return post("/scene-versions/publish", body);
}

export function saveDatasetDraft(
  body: {
    agentId: string;
    datasetId: string;
    expectedRevision: number;
    name: string;
    cases: DatasetDraft["cases"];
  },
): Promise<DatasetDraft> {
  return post("/dataset-drafts", body);
}

export function publishDatasetVersion(
  body: { agentId: string; assetId: string; draftRevision: number },
): Promise<DatasetVersion> {
  return post("/dataset-versions/publish", body);
}

export function saveEvaluatorDraft(
  body: {
    agentId: string;
    evaluatorId: string;
    expectedRevision: number;
    name: string;
    sceneVersionId: string;
    kind: "deterministic" | "llm_rubric";
    rule: string;
    rubric: string;
    regexPattern: string;
    hardFailure: boolean;
  },
): Promise<EvaluatorDraft> {
  return post("/evaluator-drafts", body);
}

export function recommendEvaluatorDrafts(
  agentId: string,
  sceneVersionId: string,
): Promise<EvaluatorDraftRecommendation> {
  return post("/evaluator-drafts/recommend", { agentId, sceneVersionId });
}

export function trialEvaluatorDraft(
  evaluatorId: string,
  body: {
    agentId: string;
    expectedRevision: number;
    datasetVersionId: string;
    samples: EvaluatorTrialSample[];
  },
): Promise<EvaluatorTrialReport> {
  return post(`/evaluator-drafts/${encodeURIComponent(evaluatorId)}/trial`, body);
}

export function publishEvaluatorVersion(
  body: { agentId: string; assetId: string; draftRevision: number },
): Promise<EvaluatorVersion> {
  return post("/evaluator-versions/publish", body);
}

export function publishEvaluatorGroup(body: {
  agentId: string;
  sceneVersionId: string;
  drafts: Array<{ evaluatorId: string; draftRevision: number }>;
}): Promise<EvaluatorGroupPublicationResult> {
  return post("/evaluator-groups/publish", body);
}

export function savePolicyDraft(
  body: {
    agentId: string;
    policyId: string;
    expectedRevision: number;
    name: string;
    bindings: EvaluationPolicyDraft["bindings"];
  },
): Promise<EvaluationPolicyDraft> {
  return post("/policy-drafts", body);
}

export function publishPolicyVersion(
  body: { agentId: string; assetId: string; draftRevision: number },
): Promise<EvaluationPolicyVersion> {
  return post("/policy-versions/publish", body);
}

export function createCandidateVersion(
  body: CreateCandidateInput,
): Promise<CandidateVersion> {
  return post("/candidates", body);
}

export function startFormalEvaluation(
  body: {
    agentId: string;
    candidateId: string;
    policyVersionId: string;
    environmentFingerprint: string;
  },
): Promise<EvaluationRunVersion> {
  return post("/runs", body);
}

export function getFormalEvaluation(
  agentId: string,
  evaluationId: string,
  signal?: AbortSignal,
): Promise<EvaluationRunVersion> {
  const params = new URLSearchParams({ agentId });
  return scenarioRequest(
    `/runs/${encodeURIComponent(evaluationId)}?${params.toString()}`,
    { signal },
  );
}

export function cancelFormalEvaluation(
  agentId: string,
  evaluationId: string,
): Promise<EvaluationRunVersion> {
  return post(`/runs/${encodeURIComponent(evaluationId)}/cancel`, { agentId });
}

export function retryInvalidEvaluationAttempt(
  evaluationId: string,
  body: {
    agentId: string;
    sceneVersionId: string;
    caseId: string;
    target: "candidate" | "baseline";
    attemptIndex: number;
  },
): Promise<EvaluationRunVersion> {
  return post(`/runs/${encodeURIComponent(evaluationId)}/attempts/retry`, body);
}

export function prepareScenarioPublish(body: {
  agentId: string;
  candidateId: string;
  policyVersionId: string | null;
  environmentFingerprint: string;
  secondConfirmation: boolean;
  reason: string;
  idempotencyKey: string;
}): Promise<PublishIntentVersion> {
  return post("/publish-intents/prepare", body);
}

export function getPublishAudits(
  agentId: string,
  intentId?: string,
  signal?: AbortSignal,
): Promise<PublishAudit[]> {
  const params = new URLSearchParams({ agentId });
  if (intentId) params.set("intentId", intentId);
  return scenarioRequest(`/publish-audits?${params.toString()}`, { signal });
}

export function finalizeScenarioPublishRecovery(
  intentId: string,
  body: { agentId: string },
): Promise<{ intent: PublishIntentVersion; publishedVersion: PublishedVersion }> {
  return post(`/publish-intents/${encodeURIComponent(intentId)}/reconcile`, body);
}
