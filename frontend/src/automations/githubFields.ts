import {
  defaultCloudRegion,
  defaultModelApiBase,
  type CloudProvider,
} from "../adk/cloudProvider";
import type {
  AutomationFieldDefinition,
  AutomationFormValues,
} from "./types";
import { automationT } from "./i18n";

export const repositoryField: AutomationFieldDefinition = {
  name: "repository",
  label: "GitHub Repo",
  placeholder: "owner/repository",
  help: "Enter owner/repository or a full github.com URL",
  required: true,
};

export const baseBranchField: AutomationFieldDefinition = {
  name: "baseBranch",
  label: "Target branch",
  placeholder: "main",
  help: "Defaults to main; the pull request will use this branch as its base",
  required: false,
};

export const runtimeNameField: AutomationFieldDefinition = {
  name: "runtimeName",
  label: "Runtime name",
  placeholder: "support-agent",
  help: "Used by the AgentKit delivery configuration",
  required: true,
};

export const runtimeIdField: AutomationFieldDefinition = {
  name: "runtimeId",
  label: "Runtime ID",
  placeholder: "rt-xxxxxxxx",
  help: "The AgentKit Runtime that will receive continuous updates",
  required: true,
};

const VOLCENGINE_REVIEW_MODEL_BASE_URL =
  "https://ark.cn-beijing.volces.com/api/coding/v3";

export interface CloudCredentialSecretNames {
  accessKey: string;
  secretKey: string;
  sessionToken: string;
}

export function defaultReviewModelBaseUrl(provider: CloudProvider): string {
  return provider === "byteplus"
    ? defaultModelApiBase(provider)
    : VOLCENGINE_REVIEW_MODEL_BASE_URL;
}

export function cloudCredentialSecretNames(
  provider: CloudProvider,
): CloudCredentialSecretNames {
  if (provider === "byteplus") {
    return {
      accessKey: "BYTEPLUS_ACCESS_KEY",
      secretKey: "BYTEPLUS_SECRET_KEY",
      sessionToken: "BYTEPLUS_SESSION_TOKEN",
    };
  }
  return {
    accessKey: "VOLCENGINE_ACCESS_KEY",
    secretKey: "VOLCENGINE_SECRET_KEY",
    sessionToken: "VOLCENGINE_SESSION_TOKEN",
  };
}

export function cloudCredentialSecretLabels(
  provider: CloudProvider,
): readonly string[] {
  const secrets = cloudCredentialSecretNames(provider);
  return [
    automationT("github.secretPair", {
      accessKey: secrets.accessKey,
      secretKey: secrets.secretKey,
    }),
    automationT("github.sessionToken", { sessionToken: secrets.sessionToken }),
  ];
}

export function cloudProviderDisplayName(provider: CloudProvider): string {
  return provider === "byteplus" ? "BytePlus" : "Volcengine";
}

export function initialAutomationValues(
  provider: CloudProvider,
  overrides: Partial<AutomationFormValues> = {},
): AutomationFormValues {
  return {
    repository: "",
    baseBranch: "main",
    projectPath: ".",
    runtimeName: "",
    runtimeId: "",
    sandboxToolId: "",
    modelName: "",
    modelBaseUrl: defaultReviewModelBaseUrl(provider),
    region: defaultCloudRegion(provider),
    token: "",
    ...overrides,
  };
}

export function commonGitHubInput(values: AutomationFormValues) {
  return {
    repository: values.repository.trim(),
    baseBranch: values.baseBranch.trim() || "main",
    region: values.region,
    token: values.token.trim(),
  };
}
