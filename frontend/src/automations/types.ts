import type {
  GitHubAutomationRegion,
  GitHubPullRequestResult,
} from "../adk/githubIntegration";

export type AutomationId =
  | "template"
  | "delivery"
  | "review"
  | "feishu"
  | "coding-agents";

export type GitHubAutomationId = Exclude<AutomationId, "feishu" | "coding-agents">;

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
  icon: "github" | "feishu" | "coding-agents";
  name: string;
  badge?: string;
  badgeTone?: "default" | "success";
  description: string;
}

export interface GitHubAutomationDefinition extends AutomationCardDefinition {
  id: GitHubAutomationId;
  kind: "github";
  title: string;
  subtitle: string;
  panel: string;
  submitLabel: string;
  fields: readonly AutomationFieldDefinition[];
  initialValues: AutomationFormValues;
  regionHelp: string;
  secrets: readonly string[];
  submit: (
    values: AutomationFormValues,
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

export type AutomationDefinition =
  | GitHubAutomationDefinition
  | FeishuAutomationDefinition
  | CodingAgentAutomationDefinition;
