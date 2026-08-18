// Auth forwarding for cloud deployments.
//
// Except for local development helpers, query params present on load are
// injected by the identity gateway (auth token, signature, etc.). Capture and
// forward those auth params while keeping local-only params in the address bar.
// Cookies (e.g. VeADK's `veadk_session`) are sent automatically.

const STORAGE_KEY = "veadk_auth_qs";
const LOCAL_QUERY_KEYS = new Set([
  "view",
  "source",
  "sessionId",
  "artifactSha256",
  "validationReportSha256",
]);

let cached: string | null = null;

/** The raw querystring (without leading "?") to forward on every request. */
function authQuery(): string {
  if (cached !== null) return cached;

  const incoming = new URLSearchParams(window.location.search);
  const forwarded = new URLSearchParams();
  const local = new URLSearchParams();
  const intelligentDeploymentDeepLink =
    incoming.get("view") === "runtime-deploy"
    && incoming.get("source") === "intelligent-development";
  incoming.forEach((value, key) => {
    (
      intelligentDeploymentDeepLink && LOCAL_QUERY_KEYS.has(key)
        ? local
        : forwarded
    ).append(key, value);
  });
  const forwardedQuery = forwarded.toString();
  if (forwardedQuery) {
    sessionStorage.setItem(STORAGE_KEY, forwardedQuery);
    cached = forwardedQuery;
  } else {
    cached = sessionStorage.getItem(STORAGE_KEY) ?? "";
  }
  if (forwardedQuery) {
    const localQuery = local.toString();
    window.history.replaceState(
      null,
      "",
      window.location.pathname
        + (localQuery ? `?${localQuery}` : "")
        + window.location.hash,
    );
  }
  return cached;
}

/** Merge the forwarded auth params into a URL (absolute or relative). Existing
 *  params on the target win. */
export function withAuth(url: string): string {
  const qs = authQuery();
  if (!qs) return url;
  const u = new URL(url, window.location.origin);
  new URLSearchParams(qs).forEach((value, key) => {
    if (!u.searchParams.has(key)) u.searchParams.set(key, value);
  });
  return /^https?:\/\//i.test(url) ? u.toString() : u.pathname + u.search + u.hash;
}

export function hasAuth(): boolean {
  return authQuery().length > 0;
}

/** Full-page navigation that preserves the forwarded auth params. */
export function navigateWithAuth(url: string): void {
  window.location.assign(withAuth(url));
}
