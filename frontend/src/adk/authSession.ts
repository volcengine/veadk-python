export const AUTHENTICATION_REQUIRED_EVENT = "veadk:authentication-required";

let pendingAuthentication: Promise<void> | null = null;
let resolveAuthentication: (() => void) | null = null;

export function isAuthenticationRedirect(response: Response): boolean {
  if (!response.redirected || !response.url) return false;
  try {
    const url = new URL(response.url);
    return (
      url.pathname.includes("/authorize") ||
      url.pathname.includes("/oauth2/login") ||
      url.hostname.includes(".userpool.auth.")
    );
  } catch {
    return false;
  }
}

export function waitForAuthentication(signal?: AbortSignal | null): Promise<void> {
  if (!pendingAuthentication) {
    pendingAuthentication = new Promise<void>((resolve) => {
      resolveAuthentication = resolve;
    });
    window.dispatchEvent(new Event(AUTHENTICATION_REQUIRED_EVENT));
  }
  const authentication = pendingAuthentication;
  if (!signal) return authentication;
  if (signal.aborted) {
    return Promise.reject(signal.reason ?? new Error("Request aborted"));
  }
  return new Promise<void>((resolve, reject) => {
    const onAbort = () => reject(signal.reason ?? new Error("Request aborted"));
    signal.addEventListener("abort", onAbort, { once: true });
    authentication.then(
      () => {
        signal.removeEventListener("abort", onAbort);
        resolve();
      },
      (error) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

export function isAuthenticationPending(): boolean {
  return pendingAuthentication !== null;
}

export function authenticationRestored(): void {
  resolveAuthentication?.();
  resolveAuthentication = null;
  pendingAuthentication = null;
}
