import { studioFetch, type StudioRole } from "./client";

export const STUDIO_ROLES: StudioRole[] = ["super_admin", "admin", "developer", "user"];

export interface StudioUser {
  id: string;
  name: string;
  email: string;
  role: StudioRole;
  status: string;
  lastLogin: string;
  protected: boolean;
  currentUser: boolean;
  roleConflict: boolean;
}

export interface StudioUsersPage {
  items: StudioUser[];
  total: number;
  poolTotal: number;
  page: number;
  pageSize: number;
  userPoolId: string;
  clientId: string;
  provider: "volcengine" | "byteplus";
}

export class UserManagementError extends Error {
  constructor(public code: string, public status: number) {
    super(code);
  }
}

async function readResponse(response: Response): Promise<unknown> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new UserManagementError("invalid_response", response.status);
  }
  if (!response.ok) {
    const code = payload && typeof payload === "object" && "code" in payload && typeof payload.code === "string"
      ? payload.code : "request_failed";
    throw new UserManagementError(code, response.status);
  }
  return payload;
}

function isStudioUser(value: unknown): value is StudioUser {
  if (!value || typeof value !== "object") return false;
  return "id" in value && typeof value.id === "string"
    && "name" in value && typeof value.name === "string"
    && "email" in value && typeof value.email === "string"
    && "role" in value && STUDIO_ROLES.some((role) => role === value.role)
    && "status" in value && typeof value.status === "string"
    && "lastLogin" in value && typeof value.lastLogin === "string"
    && "protected" in value && typeof value.protected === "boolean"
    && "currentUser" in value && typeof value.currentUser === "boolean"
    && "roleConflict" in value && typeof value.roleConflict === "boolean";
}

export async function listStudioUsers(options: { page: number; query: string; role: StudioRole | ""; signal?: AbortSignal }): Promise<StudioUsersPage> {
  const query = new URLSearchParams({ page: String(options.page), pageSize: "20", query: options.query });
  if (options.role) query.set("role", options.role);
  const value = await readResponse(await studioFetch(`/web/users?${query}`, { signal: options.signal, cache: "no-store" }));
  if (!value || typeof value !== "object"
    || !("items" in value) || !Array.isArray(value.items) || !value.items.every(isStudioUser)
    || !("total" in value) || typeof value.total !== "number"
    || !("poolTotal" in value) || typeof value.poolTotal !== "number"
    || !("page" in value) || typeof value.page !== "number"
    || !("pageSize" in value) || typeof value.pageSize !== "number"
    || !("userPoolId" in value) || typeof value.userPoolId !== "string"
    || !("clientId" in value) || typeof value.clientId !== "string"
    || !("provider" in value) || !["volcengine", "byteplus"].includes(String(value.provider))) {
    throw new UserManagementError("invalid_response", 502);
  }
  return value as StudioUsersPage;
}

export async function updateStudioUserRole(user: StudioUser, role: StudioRole, signal?: AbortSignal): Promise<StudioUser> {
  const value = await readResponse(await studioFetch(`/web/users/${encodeURIComponent(user.id)}/role`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, expectedRole: user.role }), signal,
  }));
  if (!value || typeof value !== "object" || !("user" in value) || !isStudioUser(value.user)) {
    throw new UserManagementError("invalid_response", 502);
  }
  return value.user;
}
