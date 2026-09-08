import { httpErrorMessage, studioFetch } from "./client";
import { adkT } from "./i18n";

export type FeishuBotSetupStatus =
  | "waiting"
  | "success"
  | "failed"
  | "expired"
  | "cancelled";

export interface FeishuBotSetupSession {
  id: string;
  status: FeishuBotSetupStatus;
  expiresAt?: string;
  qrCodeDataUrl?: string;
  message?: string;
  credentials?: { appId: string; appSecret: string };
}

async function request(
  path: string,
  init: RequestInit,
): Promise<FeishuBotSetupSession> {
  const response = await studioFetch(path, {
    ...init,
    headers: { accept: "application/json", ...init.headers },
  });
  if (!response.ok) {
    throw new Error(await httpErrorMessage(response, adkT("feishuBot.autoConfigureFailed")));
  }
  return response.json() as Promise<FeishuBotSetupSession>;
}

export function createFeishuBotSetup(input: { agentName: string }) {
  return request("/web/feishu-bot-setup/sessions", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getFeishuBotSetup(sessionId: string) {
  return request(
    `/web/feishu-bot-setup/sessions/${encodeURIComponent(sessionId)}`,
    { method: "GET" },
  );
}

export function cancelFeishuBotSetup(sessionId: string) {
  return request(
    `/web/feishu-bot-setup/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}
