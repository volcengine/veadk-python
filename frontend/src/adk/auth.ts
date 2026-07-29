// Auth forwarding for cloud deployments.
//
// Except for local development helpers, query params present on load are
// injected by the identity gateway (auth token, signature, etc.). Capture and
// forward those auth params while keeping local-only params in the address bar.
// Cookies (e.g. VeADK's `veadk_session`) are sent automatically.

const STORAGE_KEY = "veadk_auth_qs";

let cached: string | null = null;

/** The raw querystring (without leading "?") to forward on every request. */
function authQuery(): string {
  if (cached !== null) return cached;

  const params = new URLSearchParams(window.location.search);
  const incoming = params.toString();
  if (incoming) {
    sessionStorage.setItem(STORAGE_KEY, incoming);
    cached = incoming;
  } else {
    cached = sessionStorage.getItem(STORAGE_KEY) ?? "";
  }
  if (window.location.search) {
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.hash,
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
