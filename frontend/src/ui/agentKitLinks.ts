import type { CloudProvider } from "../adk/cloudProvider";

export interface AgentKitLinks {
  console: string;
  docs: string;
}

const AGENTKIT_LINKS: Record<CloudProvider, AgentKitLinks> = {
  volcengine: {
    console: "https://console.volcengine.com/agentkit",
    docs: "https://www.volcengine.com/docs/86681/1844823",
  },
  byteplus: {
    console: "https://console.byteplus.com/agentkit",
    docs: "https://docs.byteplus.com/en/docs/AgentKit",
  },
};

export function agentKitLinks(provider: CloudProvider): AgentKitLinks {
  return AGENTKIT_LINKS[provider];
}
