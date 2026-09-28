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

export async function pollDeploymentRecovery<T extends { done?: boolean }>({
  load,
  signal,
  timeoutMs = 30 * 60_000,
  intervalMs = 2_000,
  shouldRetry = () => true,
}: {
  load: (signal?: AbortSignal) => Promise<T>;
  signal?: AbortSignal;
  timeoutMs?: number;
  intervalMs?: number;
  shouldRetry?: (error: unknown) => boolean;
}): Promise<T | null> {
  if (signal?.aborted) {
    throw signal.reason ?? new DOMException("Aborted", "AbortError");
  }
  const deadline = Date.now() + Math.max(0, timeoutMs);
  while (!signal?.aborted && Date.now() <= deadline) {
    try {
      const status = await load(signal);
      if (status.done) return status;
    } catch (error) {
      if (signal?.aborted || isDeploymentAbortError(error)) throw error;
      if (!shouldRetry(error)) throw error;
      // Instance replacement can also interrupt an individual status read.
      // Keep polling until the bounded recovery window expires.
    }
    if (signal?.aborted) {
      throw signal.reason ?? new DOMException("Aborted", "AbortError");
    }
    if (intervalMs <= 0) continue;
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        globalThis.clearTimeout(timer);
        signal?.removeEventListener("abort", onAbort);
        reject(signal?.reason ?? new DOMException("Aborted", "AbortError"));
      };
      const timer = globalThis.setTimeout(() => {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      }, intervalMs);
      signal?.addEventListener("abort", onAbort, { once: true });
    });
  }
  return null;
}
