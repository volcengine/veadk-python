import {
  getRuntimes,
  RuntimeListError,
  type RuntimePage,
} from "./client";
export {
  getRuntimes,
  probeRuntimeApps,
  RuntimeAccessDeniedError,
  RuntimeListError,
  RuntimeProbeError,
  runtimeRegionCandidates,
  setClientCloudProvider,
} from "./client";

export const RUNTIME_LIST_RETRY_DELAY_MS = 5_000;
export const RUNTIME_COMPATIBILITY_CONCURRENCY = 4;

let activeRuntimeCompatibilityChecks = 0;
const runtimeCompatibilityWaiters: Array<() => void> = [];

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function isTimeoutError(error: unknown): boolean {
  return error instanceof Error && error.name === "TimeoutError";
}

export function shouldRetryRuntimeList(error: unknown): boolean {
  return isTimeoutError(error) || (
    error instanceof RuntimeListError && [500, 502, 503, 504].includes(error.status)
  );
}

export function waitForRetryDelay(
  delayMs: number,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) {
    return Promise.reject(
      signal.reason ?? new DOMException("Request aborted", "AbortError"),
    );
  }
  return new Promise<void>((resolve, reject) => {
    const abort = () => {
      globalThis.clearTimeout(timer);
      reject(signal?.reason ?? new DOMException("Request aborted", "AbortError"));
    };
    const timer = globalThis.setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, delayMs);
    signal?.addEventListener("abort", abort, { once: true });
  });
}

interface RuntimeListRetryDependencies {
  request?: typeof getRuntimes;
  wait?: typeof waitForRetryDelay;
}

export async function getRuntimesWithTimeoutRetry(
  options: NonNullable<Parameters<typeof getRuntimes>[0]> = {},
  dependencies: RuntimeListRetryDependencies = {},
): Promise<RuntimePage> {
  const request = dependencies.request ?? getRuntimes;
  const wait = dependencies.wait ?? waitForRetryDelay;
  try {
    return await request(options);
  } catch (error) {
    if (!shouldRetryRuntimeList(error)) throw error;
    await wait(RUNTIME_LIST_RETRY_DELAY_MS, options.signal);
    return request(options);
  }
}

export async function withRuntimeCompatibilitySlot<T>(
  check: () => Promise<T>,
): Promise<T> {
  if (activeRuntimeCompatibilityChecks >= RUNTIME_COMPATIBILITY_CONCURRENCY) {
    await new Promise<void>((resolve) => runtimeCompatibilityWaiters.push(resolve));
  }
  activeRuntimeCompatibilityChecks += 1;
  try {
    return await check();
  } finally {
    activeRuntimeCompatibilityChecks -= 1;
    runtimeCompatibilityWaiters.shift()?.();
  }
}

export async function runRuntimeCompatibilityChecks<T>(
  items: T[],
  check: (item: T) => Promise<void>,
): Promise<void> {
  await Promise.allSettled(items.map((item) =>
    withRuntimeCompatibilitySlot(() => check(item)),
  ));
}
