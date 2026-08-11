import { codingAgentsAutomation } from "./codingAgents";
import { feishuBotAutomation } from "./feishuBot";
import { pullRequestReviewAutomation } from "./pullRequestReview";
import { runtimeDeliveryAutomation } from "./runtimeDelivery";
import { templateProjectAutomation } from "./templateProject";
import type {
  AutomationCategoryId,
  AutomationDefinition,
  AutomationId,
  GitHubAutomationDefinition,
} from "./types";

export const AUTOMATION_CATEGORIES: readonly {
  id: AutomationCategoryId;
  label: string;
}[] = [
  { id: "development", label: "研发" },
  { id: "channels", label: "消息渠道" },
];

export const AUTOMATIONS: readonly AutomationDefinition[] = [
  codingAgentsAutomation,
  templateProjectAutomation,
  runtimeDeliveryAutomation,
  pullRequestReviewAutomation,
  feishuBotAutomation,
];

const AUTOMATION_BY_ID = new Map(
  AUTOMATIONS.map((automation) => [automation.id, automation]),
);

export function getAutomation(id: AutomationId): AutomationDefinition {
  const automation = AUTOMATION_BY_ID.get(id);
  if (!automation) throw new Error(`Unknown automation: ${id}`);
  return automation;
}

export function getGitHubAutomation(
  id: AutomationId,
): GitHubAutomationDefinition {
  const automation = getAutomation(id);
  if (automation.kind !== "github") {
    throw new Error(`Automation is not backed by GitHub: ${id}`);
  }
  return automation;
}

export type { AutomationId, GitHubAutomationId } from "./types";
