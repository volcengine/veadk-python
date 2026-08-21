import type { MutationFeedback } from "./scenarioEvaluationPresentation";

export type MutationFeedbackState = MutationFeedback & { key: string };
export type MutationSuccess = string | {
  message: string;
  publishedVersion?: number;
};
export type MutationRunner = <T>(
  key: string,
  action: () => Promise<T>,
  successMessage?: (result: T) => MutationSuccess,
) => Promise<T | undefined>;
