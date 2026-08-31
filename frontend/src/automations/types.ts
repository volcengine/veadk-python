import type {
  GitHubAutomationRegion,
  GitHubPullRequestResult,
} from "../adk/githubIntegration";
import type { CloudProvider } from "../adk/cloudProvider";

export type AutomationId =
  | "template"
  | "delivery"
  | "review"
  | "feishu"
  | "coding-agents"
  | "website-integration";

export type GitHubAutomationId = Exclude<
  AutomationId,
  "feishu" | "coding-agents" | "website-integration"
>;

export type AutomationCategoryId = "development" | "channels";

export type AutomationFieldName =
  | "repository"
  | "baseBranch"
  | "projectPath"
  | "runtimeName"
  | "runtimeId"
  | "sandboxToolId"
  | "modelName"
  | "modelBaseUrl";

export interface AutomationFormValues {
  repository: string;
  baseBranch: string;
  projectPath: string;
  runtimeName: string;
  runtimeId: string;
  sandboxToolId: string;
  modelName: string;
  modelBaseUrl: string;
  region: GitHubAutomationRegion;
  token: string;
}

export interface AutomationFieldDefinition {
  name: AutomationFieldName;
  label: string;
  placeholder: string;
  help: string;
  required: boolean;
}

export interface AutomationCardDefinition {
  id: AutomationId;
  category: AutomationCategoryId;
  icon: "github" | "feishu" | "coding-agents" | "website-integration";
  name: string;
  badge?: string;
  badgeTone?: "default" | "success";
  description: string;
}

export interface GitHubAutomationContext {
  cloudProvider: CloudProvider;
}

export interface GitHubAutomationDefinition extends AutomationCardDefinition {
  id: GitHubAutomationId;
  kind: "github";
  title: string;
  subtitle: string;
  panel: string;
  submitLabel: string;
  fields: readonly AutomationFieldDefinition[];
  initialValues: (context: GitHubAutomationContext) => AutomationFormValues;
  regionHelp: string;
  secrets: (context: GitHubAutomationContext) => readonly string[];
  submit: (
    values: AutomationFormValues,
    context: GitHubAutomationContext,
    signal: AbortSignal,
  ) => Promise<GitHubPullRequestResult>;
}

export interface FeishuAutomationDefinition extends AutomationCardDefinition {
  id: "feishu";
  kind: "feishu";
}

export interface CodingAgentAutomationDefinition extends AutomationCardDefinition {
  id: "coding-agents";
  kind: "coding-agent";
}

export interface WebsiteIntegrationAutomationDefinition extends AutomationCardDefinition {
  id: "website-integration";
  kind: "website-integration";
}

export type AutomationDefinition =
  | GitHubAutomationDefinition
  | FeishuAutomationDefinition
  | CodingAgentAutomationDefinition
  | WebsiteIntegrationAutomationDefinition;
