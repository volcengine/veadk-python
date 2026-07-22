// SSO identity via veadk's OAuth2 endpoints (standard OIDC).
//
// The server (launched with `veadk frontend --oauth2-user-pool ...`) protects
// the API but exempts the SPA shell, so when the user is not signed in the app
// loads and shows its own login page. `/oauth2/userinfo` tells us the state:
//   200 -> authenticated (use the returned identity)
//   401 -> SSO enabled but not signed in (show the login page)
//   404 -> SSO not configured on legacy servers (local username mode)

import { BOOT_REQUEST_TIMEOUT_MS, requestSignal } from "./timeout";

const LOCAL_USER_KEY = "veadk_local_user";
const TAB_LOCAL_USER_KEY = "veadk_local_user_tab";

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
    const tabUser = sessionStorage.getItem(TAB_LOCAL_USER_KEY);
    if (tabUser) return tabUser;
    const savedUser = localStorage.getItem(LOCAL_USER_KEY);
    if (savedUser) sessionStorage.setItem(TAB_LOCAL_USER_KEY, savedUser);
    return savedUser;
  } catch {
    try {
      return localStorage.getItem(LOCAL_USER_KEY);
    } catch {
      return null;
    }
  }
}

export function setLocalUser(name: string): void {
  try {
    sessionStorage.setItem(TAB_LOCAL_USER_KEY, name);
  } catch {
    /* ignore */
  }
  try {
    localStorage.setItem(LOCAL_USER_KEY, name);
  } catch {
    /* ignore */
  }
}

export function clearLocalUser(): void {
  try {
    sessionStorage.removeItem(TAB_LOCAL_USER_KEY);
  } catch {
    /* ignore */
  }
  try {
    localStorage.removeItem(LOCAL_USER_KEY);
  } catch {
    /* ignore */
  }
}

/** Add the no-SSO username to same-origin API requests. OAuth deployments may
 *  receive this header too, but the server derives identity from OAuth there
 *  and deliberately ignores the browser-provided value. */
export function withLocalUser(headers?: HeadersInit): Headers {
  const next = new Headers(headers);
  const username = getLocalUser();
  if (username) next.set("X-VeADK-Local-User", username);
  return next;
}

export interface Provider {
  id: string;
  label: string;
  loginUrl: string;
}

/** Fetch the SSO providers the server has configured (unauthenticated). */
export async function fetchProviders(): Promise<Provider[]> {
  let res: Response;
  try {
    res = await fetch("/web/auth-config", {
      headers: { Accept: "application/json" },
      signal: requestSignal(undefined, BOOT_REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    console.warn("[identity] /web/auth-config is unreachable:", error);
    throw new Error("无法加载登录配置，请检查网络后重试。");
  }
  if (!res.ok) {
    throw new Error(`登录配置服务异常（HTTP ${res.status}），请稍后重试。`);
  }
  try {
    const data = (await res.json()) as { providers?: unknown };
    if (!Array.isArray(data.providers)) {
      throw new TypeError("providers is not an array");
    }
    return data.providers as Provider[];
  } catch (error) {
    console.warn("[identity] /web/auth-config returned an invalid response:", error);
    throw new Error("登录配置服务返回了无法解析的响应，请稍后重试。");
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
 *  use a locally chosen username, or prompt for one on the login page.
 *
 *  Network and server failures reject instead of silently changing identity
 *  mode. The caller can then show a retryable error. */
export async function resolveIdentity(): Promise<Identity> {
  let res: Response;
  try {
    res = await fetch("/oauth2/userinfo", {
      headers: { Accept: "application/json" },
      signal: requestSignal(undefined, BOOT_REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    console.warn("[identity] /oauth2/userinfo is unreachable:", error);
    throw new Error("无法连接身份服务，请检查网络后重试。");
  }

  // SSO enabled, signed in.
  if (res.ok) {
    let info: Record<string, unknown>;
    try {
      info = (await res.json()) as Record<string, unknown>;
    } catch (error) {
      console.warn("[identity] /oauth2/userinfo returned a non-JSON response:", error);
      throw new Error("身份服务返回了无法解析的响应，请稍后重试。");
    }
    const userId = String(info.sub ?? info.user_id ?? info.email ?? "");
    return { status: "authenticated", userId, info };
  }
  // SSO enabled, not signed in -> provider login page.
  if (res.status === 401) {
    return { status: "unauthenticated", userId: "", local: false };
  }

  if (res.status !== 404) {
    throw new Error(`身份服务异常（HTTP ${res.status}），请稍后重试。`);
  }

  // Legacy server without the identity endpoint: local username mode.
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

/** Standard OIDC profile picture URL, when provided by the identity service. */
export function profilePictureUrl(info?: Record<string, unknown>): string {
  const picture = info?.picture;
  return typeof picture === "string" ? picture.trim() : "";
}
