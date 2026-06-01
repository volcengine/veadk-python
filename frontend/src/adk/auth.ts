// Auth forwarding for cloud deployments.
//
// This frontend never puts anything in the page querystring itself, so any
// query params present on load must have been injected by the identity gateway
// (auth token, signature, etc.) — whatever their custom names. We therefore
// capture the entire incoming querystring, stash it, strip it from the visible
// address bar, and re-attach it verbatim to every API request and to any page
// navigation. Cookies (e.g. VeADK's `veadk_session`) are sent automatically.

const STORAGE_KEY = "veadk_auth_qs";

let cached: string | null = null;

/** The raw querystring (without leading "?") to forward on every request. */
function authQuery(): string {
  if (cached !== null) return cached;

  const incoming = window.location.search.replace(/^\?/, "");
  if (incoming) {
    sessionStorage.setItem(STORAGE_KEY, incoming);
    // Keep it out of the address bar / history / bookmarks.
    window.history.replaceState(null, "", window.location.pathname + window.location.hash);
    cached = incoming;
  } else {
    cached = sessionStorage.getItem(STORAGE_KEY) ?? "";
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
