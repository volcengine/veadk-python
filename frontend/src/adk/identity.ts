// SSO identity via veadk's OAuth2 endpoints (standard OIDC).
//
// The server (launched with `veadk frontend --oauth2-user-pool ...`) protects
// the API but exempts the SPA shell, so when the user is not signed in the app
// loads and shows its own login page. `/oauth2/userinfo` tells us the state:
//   200 -> authenticated (use the returned identity)
//   401 -> SSO enabled but not signed in (show the login page)
//   404/err -> SSO not configured (local dev; use a default id)

const LOCAL_USER_KEY = "veadk_local_user";

export type AuthStatus = "authenticated" | "unauthenticated";

export interface Identity {
  status: AuthStatus;
  userId: string;
  info?: Record<string, unknown>;
  /** True when there is no SSO and the id comes from the local username flow. */
  local?: boolean;
}

/** Validation for the no-SSO local username (letters + digits, <= 16). */
export const USERNAME_RE = /^[A-Za-z0-9]{1,16}$/;

export function getLocalUser(): string | null {
  try {
    return localStorage.getItem(LOCAL_USER_KEY);
  } catch {
    return null;
  }
}

export function setLocalUser(name: string): void {
  try {
    localStorage.setItem(LOCAL_USER_KEY, name);
  } catch {
    /* ignore */
  }
}

export function clearLocalUser(): void {
  try {
    localStorage.removeItem(LOCAL_USER_KEY);
  } catch {
    /* ignore */
  }
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

/** Resolve identity. With SSO: via /oauth2/userinfo. Without SSO (endpoint 404):
 *  use a locally chosen username, or prompt for one on the login page. */
export async function resolveIdentity(): Promise<Identity> {
  let res: Response | null = null;
  try {
    res = await fetch("/oauth2/userinfo", { headers: { Accept: "application/json" } });
  } catch {
    res = null;
  }

  // SSO enabled, signed in.
  if (res && res.ok) {
    const info = (await res.json()) as Record<string, unknown>;
    const userId = String(info.sub ?? info.user_id ?? info.email ?? "");
    return { status: "authenticated", userId, info };
  }
  // SSO enabled, not signed in -> provider login page.
  if (res && res.status === 401) {
    return { status: "unauthenticated", userId: "", local: false };
  }

  // No SSO (404 / unreachable): local username mode.
  const saved = getLocalUser();
  if (saved) {
    return { status: "authenticated", userId: saved, info: { name: saved }, local: true };
  }
  return { status: "unauthenticated", userId: "", local: true };
}

/** A short display name for the signed-in user. */
export function displayName(info?: Record<string, unknown>): string {
  if (!info) return "";
  return String(info.name ?? info.preferred_username ?? info.email ?? info.sub ?? "");
}
