import type { FeishuAutomationDefinition } from "./types";

export const feishuBotAutomation: FeishuAutomationDefinition = {
  id: "feishu",
  kind: "feishu",
  category: "channels",
  icon: "feishu",
  name: "飞书机器人",
  badge: "Beta",
  description: "创建飞书机器人，并将消息直接接入 AgentKit Runtime。",
};
