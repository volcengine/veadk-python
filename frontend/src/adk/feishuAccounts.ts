import { channelRequest, ChannelApiError, type AdkEndpoint } from "./client";

export interface FeishuAccount {
  channel: "feishu";
  appId: string;
  appName?: string;
  enabled: boolean;
}

export async function listFeishuAccounts(
  ep: AdkEndpoint,
  signal: AbortSignal,
): Promise<FeishuAccount[]> {
  const data = await channelRequest<{ channels: unknown[] }>(ep, "", {
    signal,
  });
  if (!data || !Array.isArray(data.channels)) throw new ChannelApiError(502);
  const accounts: FeishuAccount[] = [];
  const ids = new Set<string>();
  for (const value of data.channels) {
    if (!value || typeof value !== "object" || !("channel" in value))
      throw new ChannelApiError(502);
    if (value.channel !== "feishu") continue;
    if (
      !("appId" in value) ||
      typeof value.appId !== "string" ||
      !value.appId.trim() ||
      ids.has(value.appId)
    )
      throw new ChannelApiError(502);
    if (!("enabled" in value) || typeof value.enabled !== "boolean")
      throw new ChannelApiError(502);
    ids.add(value.appId);
    accounts.push({
      channel: "feishu",
      appId: value.appId,
      enabled: value.enabled,
      ...("appName" in value && typeof value.appName === "string"
        ? { appName: value.appName }
        : {}),
    });
  }
  return accounts;
}
