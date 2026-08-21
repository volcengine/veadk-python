import type { AgentProject } from "../create/project";

export type EvaluationRequirement = "must_pass" | "observation";
export type FeedbackDecision =
  | "pending"
  | "reviewed"
  | "rejected"
  | "merged"
  | "converted";
export type EvaluatorKind = "deterministic" | "llm_rubric";
export type DeterministicRule =
  | "output_contains_tool_evidence"
  | "output_contains_expected"
  | "output_excludes_forbidden";
export type EvaluationRunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
export type QualityRecommendationValue =
  | "recommend"
  | "do_not_recommend"
  | "indeterminate";
export type PublishPath = "normal" | "skip" | "risk";

export interface FeedbackSource {
  agentId: string;
  agentVersion: string;
  runtimeId: string;
  appName: string;
  userId: string;
  sessionId: string;
  messageId: string;
  invocationId: string;
  runId: string;
  traceRef: string;
  input: string;
  output: string;
  rating: "good" | "bad";
  comment: string;
}

export interface FeedbackCandidateVersion {
  candidateId: string;
  agentId: string;
  revision: number;
  source: FeedbackSource;
  decision: FeedbackDecision;
  reviewedInput: string;
  expectedOutput: string;
  reviewComment: string;
  labels: string[];
  decisionReason: string;
  targetCandidateId: string | null;
  targetDatasetId: string | null;
  createdAt: string;
  createdBy: string;
}

export interface DatasetCase {
  caseId: string;
  sceneVersionId?: string;
  input: string;
  expectedOutput: string;
  preloadedContext?: string;
  testDataRefs?: string[];
  prerequisites?: string[];
  passCriteria?: string[];
  labels: string[];
  forbiddenOutput: string[];
  sourceFeedbackCandidateIds: string[];
  sourceType?: "manual" | "file" | "debug_run" | "feedback";
  sourceRefs?: string[];
  redactionStatus?: "pending" | "redacted" | "not_required";
}

export interface SceneDraft {
  sceneId: string;
  agentId: string;
  revision: number;
  name: string;
  description: string;
  userTask: string;
  passCriteria: string[];
  hardFailureConditions: string[];
  ownerId: string;
  linkedDatasetIds: string[];
  enabled: boolean;
  requirement: EvaluationRequirement;
  updatedAt: string;
  updatedBy: string;
}

export interface SceneVersion extends Omit<SceneDraft, "revision" | "updatedAt" | "updatedBy"> {
  sceneVersionId: string;
  version: number;
  sourceDraftRevision: number;
  createdAt: string;
  createdBy: string;
}

export interface DatasetDraft {
  datasetId: string;
  agentId: string;
  revision: number;
  name: string;
  cases: DatasetCase[];
  updatedAt: string;
  updatedBy: string;
}

export interface DatasetVersion extends Omit<DatasetDraft, "revision" | "updatedAt" | "updatedBy"> {
  datasetVersionId: string;
  version: number;
  sourceDraftRevision: number;
  createdAt: string;
  createdBy: string;
}

export interface EvaluatorDraft {
  evaluatorId: string;
  agentId: string;
  revision: number;
  name: string;
  sceneVersionId: string;
  kind: EvaluatorKind;
  rule: DeterministicRule | null;
  rubric: string;
  hardFailure: boolean;
  updatedAt: string;
  updatedBy: string;
}

export interface EvaluatorVersion extends Omit<EvaluatorDraft, "revision" | "updatedAt" | "updatedBy"> {
  evaluatorVersionId: string;
  version: number;
  sourceDraftRevision: number;
  trialReportId: string;
  trialDatasetVersionId: string;
  createdAt: string;
  createdBy: string;
}

export interface EvaluatorGroupPublicationResult {
  sceneVersionId: string;
  evaluatorVersions: EvaluatorVersion[];
  checkCount: number;
  calibrationAccurate: boolean;
}

export interface EvaluatorDraftRecommendation {
  sceneVersionId: string;
  drafts: EvaluatorDraft[];
  items: Array<{
    evaluatorId: string;
    rationale: string;
    sceneStandard: string;
  }>;
}

export interface EvaluatorTrialSample {
  sampleId: string;
  input: string;
  expectedOutput: string;
  agentOutput: string;
  expectedOutcome: "pass" | "fail";
  forbiddenOutput?: string[];
  traceJson?: string;
}

export interface EvaluatorTrialReport {
  reportId: string;
  agentId: string;
  evaluatorId: string;
  evaluatorRevision: number;
  datasetVersionId: string;
  results: Array<{
    sampleId: string;
    expectedOutcome: "pass" | "fail";
    outcome: "pass" | "fail" | "infra_error" | "cancelled";
    matchesExpectation: boolean;
    hardFailure: boolean;
    reason: string;
    errorMessage: string;
  }>;
  createdAt: string;
  createdBy: string;
}

export interface PolicySceneBinding {
  sceneVersionId: string;
  datasetVersionId: string;
  evaluatorVersionIds: string[];
  requirement: EvaluationRequirement;
}

export interface EvaluationPolicyDraft {
  policyId: string;
  agentId: string;
  revision: number;
  name: string;
  bindings: PolicySceneBinding[];
  updatedAt: string;
  updatedBy: string;
}

export interface EvaluationPolicyVersion extends Omit<EvaluationPolicyDraft, "revision" | "updatedAt" | "updatedBy"> {
  policyVersionId: string;
  version: number;
  sourceDraftRevision: number;
  createdAt: string;
  createdBy: string;
}

export interface CredentialReference {
  name: string;
  reference: string;
}

export interface CandidateArtifact {
  codeDigest: string;
  topologyDigest: string;
  modelRefs: string[];
  promptRefs: string[];
  toolRefs: string[];
  skillRefs: string[];
  knowledgeRefs: string[];
  memoryRefs: string[];
  environmentRefs: CredentialReference[];
  runtimeProjectRef: string | null;
}

export interface CandidateVersion {
  candidateId: string;
  agentId: string;
  version: number;
  artifact: CandidateArtifact;
  environmentFingerprint: string;
  createdAt: string;
  createdBy: string;
}

export interface EvaluatorEvidence {
  evaluatorVersionId: string;
  outcome: "pass" | "fail" | "infra_error" | "cancelled";
  hardFailure: boolean;
  reason: string;
}

export interface AttemptEvidence {
  attemptIndex: number;
  outcome: "pass" | "fail" | "infra_error" | "cancelled";
  retryCount: number;
  manualRetryCount: number;
  supersededInvalidAttempts: Array<{
    sessionId: string;
    retryCount: number;
    traceRef: string;
    errorMessage: string;
  }>;
  evaluatorResults: EvaluatorEvidence[];
  sessionId: string;
  output: string;
  traceRef: string;
  traceJson: string;
  errorMessage: string;
}

export interface CaseEvidence {
  caseVersionId: string;
  sceneVersionId: string;
  requirement: EvaluationRequirement;
  candidateAttempts: AttemptEvidence[];
  baselineAttempts: AttemptEvidence[];
}

export interface SceneEvidence {
  sceneVersionId: string;
  requirement: EvaluationRequirement;
  cases: CaseEvidence[];
}

export interface SceneRecommendation {
  sceneVersionId: string;
  requirement: EvaluationRequirement;
  outcome: "pass" | "fail" | "indeterminate";
  caseResults: Array<{
    caseVersionId: string;
    outcome: "pass" | "fail" | "indeterminate";
    passCount: number;
    failCount: number;
    indeterminateCount: number;
    infrastructureRetryCount: number;
    hardFailure: boolean;
  }>;
}

export interface QualityRecommendation {
  value: QualityRecommendationValue;
  dependencyFingerprint: string;
  requiredSceneResults: SceneRecommendation[];
  observationSceneResults: SceneRecommendation[];
  warningSceneVersionIds: string[];
}

export interface EvaluationDependencies {
  candidateId: string;
  baselineVersionId: string | null;
  sceneVersionIds: string[];
  datasetVersionIds: string[];
  evaluatorVersionIds: string[];
  policyVersionId: string;
  environmentFingerprint: string;
}

export interface EvaluationRunVersion {
  evaluationId: string;
  agentId: string;
  revision: number;
  status: EvaluationRunStatus;
  candidateId: string;
  baselineVersionId: string | null;
  policyVersionId: string;
  dependencies: EvaluationDependencies;
  scenes: SceneEvidence[];
  recommendation: QualityRecommendation | null;
  errorMessage: string;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
}

export interface BadcaseVersion {
  badcaseId: string;
  agentId: string;
  revision: number;
  status: "open" | "verifying" | "closed";
  sceneVersionId: string;
  caseId: string;
  datasetVersionId: string;
  evaluatorVersionIds: string[];
  sourceEvaluationId: string;
  sourceCandidateId: string;
  verificationEvaluationId: string | null;
  verificationCandidateId: string | null;
  resolutionEvaluationId: string | null;
  resolutionCandidateId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PublishIntentVersion {
  intentId: string;
  agentId: string;
  revision: number;
  status: "prepared" | "started" | "submitted" | "failed" | "succeeded";
  candidateId: string;
  path: PublishPath;
  qualityState: string;
  recommendationValue: QualityRecommendationValue | null;
  riskItems: string[];
  policyVersionId: string | null;
  environmentFingerprint: string;
  permissionFingerprint: string;
  secondConfirmation: boolean;
  reason: string;
  expiresAt: string;
}

export interface PublishedVersion {
  publishedVersionId: string;
  agentId: string;
  version: number;
  candidateId: string;
  candidateArtifact: CandidateArtifact;
  publishIntentId: string;
  publishPath: PublishPath;
  deploymentRef: string;
  createdAt: string;
  createdBy: string;
}

export interface PublishRecoveryIssue {
  issueType: "published_intent_not_finalized" | "success_audit_missing";
  intent: PublishIntentVersion;
  publishedVersion: PublishedVersion;
}

export interface PublishAudit {
  auditId: string;
  intentId: string;
  eventIndex: number;
  event: "prepared" | "started" | "submitted" | "failed" | "succeeded";
  agentId: string;
  candidateId: string;
  actorId: string;
  path: PublishPath;
  qualityState: string;
  recommendationValue: QualityRecommendationValue | null;
  riskItems: string[];
  reason: string;
  deploymentRef: string | null;
  errorMessage: string;
  createdAt: string;
}

export interface ScenarioEvaluationWorkspaceData {
  agentId: string;
  feedbackCandidates: FeedbackCandidateVersion[];
  sceneDrafts: SceneDraft[];
  scenes: SceneVersion[];
  datasetDrafts: DatasetDraft[];
  datasets: DatasetVersion[];
  evaluatorDrafts: EvaluatorDraft[];
  evaluatorTrials: EvaluatorTrialReport[];
  evaluators: EvaluatorVersion[];
  policyDrafts: EvaluationPolicyDraft[];
  policies: EvaluationPolicyVersion[];
  candidates: CandidateVersion[];
  runs: EvaluationRunVersion[];
  badcases: BadcaseVersion[];
  publishRecoveryIssues: PublishRecoveryIssue[];
  publishedVersion: PublishedVersion | null;
}

export interface CreateCandidateInput {
  agentId: string;
  artifact: CandidateArtifact;
  runtimeProject?: AgentProject & {
    deploymentProfile?: Record<string, unknown>;
    agentIdentityAttestation?: string;
  };
}
