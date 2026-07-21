/** Default deadline for non-streaming API calls. */
export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

/** Deadline for uploads and downloads. */
export const TRANSFER_REQUEST_TIMEOUT_MS = 120_000;

/** Short deadline for identity and boot-time probes. */
export const BOOT_REQUEST_TIMEOUT_MS = 10_000;

/**
 * Combine an optional caller cancellation signal with a request deadline.
 * A non-positive timeout keeps long-lived streaming requests deadline-free.
 */
export function requestSignal(
  signal: AbortSignal | null | undefined,
  timeoutMs: number = DEFAULT_REQUEST_TIMEOUT_MS,
): AbortSignal | undefined {
  if (timeoutMs <= 0) return signal ?? undefined;
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  return signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal;
}
