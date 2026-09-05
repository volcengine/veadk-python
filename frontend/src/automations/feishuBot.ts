import type { FeishuAutomationDefinition } from "./types";

export const feishuBotAutomation: FeishuAutomationDefinition = {
  id: "feishu",
  kind: "feishu",
  category: "channels",
  icon: "feishu",
  name: "Feishu bot",
  badge: "Beta",
  description: "Create a Feishu bot and connect its messages directly to AgentKit Runtime.",
};
