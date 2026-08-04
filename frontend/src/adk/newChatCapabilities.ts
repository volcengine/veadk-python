import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { requestSignal } from "./timeout";

const CAPABILITY_TIMEOUT_MS = 10_000;

export interface NewChatModeCapability {
  enabled: boolean;
  reason?: string;
}

async function getCapability(path: string): Promise<NewChatModeCapability> {
  const response = await fetch(withAuth(path), {
    headers: withLocalUser({ Accept: "application/json" }),
    signal: requestSignal(undefined, CAPABILITY_TIMEOUT_MS),
  });
  if (!response.ok) {
    throw new Error(`读取会话模式能力失败（HTTP ${response.status}）`);
  }
  const payload = await response.json() as Record<string, unknown>;
  if (typeof payload.enabled !== "boolean") {
    throw new Error("会话模式能力响应格式错误");
  }
  return {
    enabled: payload.enabled,
    reason: typeof payload.reason === "string" ? payload.reason : undefined,
  };
}

export async function getSandboxCapability(): Promise<NewChatModeCapability> {
  return getCapability("/web/sandbox/capabilities");
}

export async function getSkillCreatorCapability(): Promise<NewChatModeCapability> {
  return getCapability("/web/skill-creator/capabilities");
}
