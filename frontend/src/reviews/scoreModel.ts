export type ReviewScoreStatus = "queued" | "running" | "completed" | "failed";

export interface ReviewScoreSummary {
  status: ReviewScoreStatus;
  overallScore?: number | null;
  scoredAt?: string;
  modelName?: string;
  rubricVersion?: string;
  error?: string;
}

export const REVIEW_SCORE_DIMENSIONS = [
  "safety", "usability", "completeness", "reliability", "maintainability",
] as const;

export interface ReviewScoreResult {
  applicationId: string;
  skillName: string;
  skillVersion: string;
  provider: string;
  rubricVersion: string;
  modelName: string;
  scoredAt: string;
  dimensions: Record<typeof REVIEW_SCORE_DIMENSIONS[number], { score: number | null; reason: string }>;
  overallScore: number | null;
  riskFlags: { severity: "low" | "medium" | "high" | "critical"; reason: string }[];
  suggestions: string[];
  coverage: {
    complete: boolean;
    totalFiles: number;
    includedFiles: number;
    omittedFiles: { path: string; reason: string }[];
    truncatedFiles: { path: string; reason: string }[];
  };
}

export interface ReviewScoreResponse extends Omit<ReviewScoreSummary, "status"> {
  status: ReviewScoreStatus | "not_requested";
  result?: ReviewScoreResult;
}

export function scoreInProgress(score?: Pick<ReviewScoreResponse, "status">): boolean {
  return score?.status === "queued" || score?.status === "running";
}

export function reviewScoreSummary(response: ReviewScoreResponse): ReviewScoreSummary | undefined {
  if (response.status === "not_requested") return undefined;
  return {
    status: response.status, overallScore: response.overallScore,
    scoredAt: response.scoredAt, modelName: response.modelName,
    rubricVersion: response.rubricVersion, error: response.error,
  };
}
