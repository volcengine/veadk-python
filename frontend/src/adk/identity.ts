// SSO identity via veadk's OAuth2 endpoints (standard OIDC).
//
// The server (launched with `veadk frontend --oauth2-user-pool ...`) protects
// the API but exempts the SPA shell, so when the user is not signed in the app
// loads and shows its own login page. `/oauth2/userinfo` tells us the state:
//   200 -> authenticated (use the returned identity)
//   401 -> SSO enabled but not signed in (show the login page)
//   404/err -> SSO not configured (local dev; use a default id)

const DEFAULT_USER_ID = "web-user";

export type AuthStatus = "authenticated" | "unauthenticated" | "disabled";

export interface Identity {
  status: AuthStatus;
  userId: string;
  info?: Record<string, unknown>;
}

export interface Provider {
  id: string;
  label: string;
  loginUrl: string;
}

/** Fetch the SSO providers the server has configured (unauthenticated). */
export async function fetchProviders(): Promise<Provider[]> {
  try {
    const res = await fetch("/web/auth-config", { headers: { Accept: "application/json" } });
    if (!res.ok) return [];
    const data = (await res.json()) as { providers?: Provider[] };
    return Array.isArray(data.providers) ? data.providers : [];
  } catch {
    return [];
  }
}

/** Start a provider's OAuth2 login flow, returning here afterwards. */
export function loginTo(loginUrl: string): void {
  const here = window.location.pathname + window.location.search + window.location.hash;
  const sep = loginUrl.includes("?") ? "&" : "?";
  window.location.assign(`${loginUrl}${sep}redirect=${encodeURIComponent(here)}`);
}

/** Start the default OAuth2 login flow. */
export function login(): void {
  loginTo("/oauth2/login");
}

export function logout(): void {
  window.location.assign("/oauth2/logout");
}

/** Resolve identity from the OAuth2 userinfo endpoint. */
export async function resolveIdentity(): Promise<Identity> {
  let res: Response;
  try {
    res = await fetch("/oauth2/userinfo", { headers: { Accept: "application/json" } });
  } catch {
    return { status: "disabled", userId: DEFAULT_USER_ID };
  }

  if (res.status === 401) {
    return { status: "unauthenticated", userId: DEFAULT_USER_ID };
  }
  if (!res.ok) {
    // 404 => SSO not configured; anything else => degrade to local mode.
    return { status: "disabled", userId: DEFAULT_USER_ID };
  }

  const info = (await res.json()) as Record<string, unknown>;
  const userId = String(info.sub ?? info.user_id ?? info.email ?? DEFAULT_USER_ID);
  return { status: "authenticated", userId, info };
}

/** A short display name for the signed-in user. */
export function displayName(info?: Record<string, unknown>): string {
  if (!info) return "";
  return String(info.name ?? info.preferred_username ?? info.email ?? info.sub ?? "");
}
