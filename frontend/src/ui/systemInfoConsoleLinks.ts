import type { CloudProvider } from "../adk/cloudProvider";

const CONSOLE_HOSTS: Record<CloudProvider, string> = {
  volcengine: "https://console.volcengine.com",
  byteplus: "https://console.byteplus.com",
};

function text(value: string): string {
  return value.trim();
}

function consoleHost(provider: CloudProvider): string {
  return CONSOLE_HOSTS[provider];
}

function tosLocation(address: string): { bucket: string; region: string } | null {
  const candidate = text(address);
  if (!candidate) return null;

  let hostname = candidate;
  try {
    hostname = new URL(
      candidate.includes("://") ? candidate : `https://${candidate}`,
    ).hostname;
  } catch {
    return null;
  }

  const match = hostname.match(
    /^(.+)\.tos-([a-z0-9-]+)\.(?:volces|bytepluses)\.com$/i,
  );
  if (!match) return null;
  return { bucket: match[1], region: match[2] };
}

export function tosConsoleUrl(
  provider: CloudProvider,
  address: string,
): string | null {
  const location = tosLocation(address);
  if (!location) return null;
  const query = new URLSearchParams({
    id: location.bucket,
    region: location.region,
    type: "objects",
  });
  return `${consoleHost(provider)}/tos/bucket/setting?${query.toString()}`;
}

export function sandboxToolConsoleUrl(
  provider: CloudProvider,
  region: string,
  toolId: string,
): string | null {
  const normalizedRegion = text(region);
  const normalizedToolId = text(toolId);
  if (!normalizedRegion || !normalizedToolId) return null;
  return `${consoleHost(provider)}/agentkit/region:agentkit+${encodeURIComponent(normalizedRegion)}/builtintools/${encodeURIComponent(normalizedToolId)}/detail`;
}

export function identityUserPoolConsoleUrl(
  provider: CloudProvider,
  region: string,
  userPoolUid: string,
): string | null {
  const normalizedRegion = text(region);
  const normalizedUid = text(userPoolUid);
  if (!normalizedRegion || !normalizedUid) return null;
  return `${consoleHost(provider)}/identity/region:identity+${encodeURIComponent(normalizedRegion)}/user-pools/${encodeURIComponent(normalizedUid)}/info`;
}
