import type { CodingAgentAutomationDefinition } from "./types";

export function isCodingAgentsAutomationAvailable(hostname: string): boolean {
  return hostname === "127.0.0.1";
}

export const codingAgentsAutomation: CodingAgentAutomationDefinition = {
  id: "coding-agents",
  kind: "coding-agent",
  category: "development",
  icon: "coding-agents",
  name: "Configure coding agents",
  badge: "Local",
  badgeTone: "success",
  description: "Install built-in VeADK and AgentKit skills globally for Trae, Claude Code, or Codex.",
};
