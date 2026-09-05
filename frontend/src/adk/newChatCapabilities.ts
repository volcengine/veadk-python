import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { adkT, withLocaleHeaders } from "./i18n";
import type { SandboxAgentKind } from "./sandbox";
import { requestSignal } from "./timeout";

const CAPABILITY_TIMEOUT_MS = 10_000;

export interface NewChatModeCapability {
  enabled: boolean;
  reason?: string;
  endpointExportEnabled?: boolean;
  persistentEnabled?: boolean;
  persistentReason?: string;
  persistentRequired?: boolean;
  storageMode?: "snapshot" | "disk";
  diskGbDefault?: number;
  diskGbMin?: number;
  diskGbMax?: number;
}

async function getCapability(
  path: string,
  signal?: AbortSignal,
): Promise<NewChatModeCapability> {
  const response = await fetch(withAuth(path), {
    headers: withLocaleHeaders(withLocalUser({ Accept: "application/json" })),
    signal: requestSignal(signal, CAPABILITY_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(adkT("newChatCapabilities.loadFailed", { status: response.status }));
  }
  const payload = await response.json() as Record<string, unknown>;
  if (typeof payload.enabled !== "boolean") {
    throw new Error(adkT("newChatCapabilities.invalidResponse"));
  }
  return {
    enabled: payload.enabled,
    reason: typeof payload.reason === "string" ? payload.reason : undefined,
    endpointExportEnabled: payload.endpointExportEnabled === true,
    persistentEnabled: payload.persistentEnabled === true,
    persistentReason: typeof payload.persistentReason === "string"
      ? payload.persistentReason
      : undefined,
    persistentRequired: payload.persistentRequired === true,
    storageMode: payload.storageMode === "disk" ? "disk" : "snapshot",
    diskGbDefault: typeof payload.diskGbDefault === "number"
      ? payload.diskGbDefault
      : undefined,
    diskGbMin: typeof payload.diskGbMin === "number" ? payload.diskGbMin : undefined,
    diskGbMax: typeof payload.diskGbMax === "number" ? payload.diskGbMax : undefined,
  };
}

export async function getSandboxCapability(
  signal?: AbortSignal,
): Promise<NewChatModeCapability> {
  return getCapability("/web/sandbox/capabilities", signal);
}

export async function getSandboxAgentCapability(
  kind: SandboxAgentKind,
  signal?: AbortSignal,
): Promise<NewChatModeCapability> {
  return getCapability(`/web/${kind}/capabilities`, signal);
}
