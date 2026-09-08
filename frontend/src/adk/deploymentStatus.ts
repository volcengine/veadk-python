const AMBIGUOUS_DEPLOYMENT_RESULT =
  /RunPipeline result could not be reconciled|Polling build status failed/i;

export class DeploymentStatusUnconfirmedError extends Error {
  readonly taskId?: string;

  constructor({ taskId, cause }: { taskId?: string; cause?: unknown } = {}) {
    super("The deployment request may still be running, but its status could not be confirmed.");
    // The raw transport detail may contain upstream internals. Classification
    // happens before wrapping, so deliberately do not expose or retain it.
    void cause;
    this.name = "DeploymentStatusUnconfirmedError";
    this.taskId = taskId;
  }
}

export function isDeploymentStatusUnconfirmedError(
  error: unknown,
): error is DeploymentStatusUnconfirmedError {
  if (error instanceof DeploymentStatusUnconfirmedError) return true;
  const message = error instanceof Error ? error.message : String(error ?? "");
  return AMBIGUOUS_DEPLOYMENT_RESULT.test(message);
}

export function isDeploymentAbortError(error: unknown): boolean {
  return Boolean(
    error &&
      typeof error === "object" &&
      "name" in error &&
      error.name === "AbortError",
  );
}
