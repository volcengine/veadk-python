import {
  defaultCloudRegion,
  defaultModelApiBase,
  type CloudProvider,
} from "../adk/cloudProvider";
import type {
  AutomationFieldDefinition,
  AutomationFormValues,
} from "./types";

export const repositoryField: AutomationFieldDefinition = {
  name: "repository",
  label: "GitHub Repo",
  placeholder: "owner/repository",
  help: "支持 owner/repository 或完整 github.com URL",
  required: true,
};

export const baseBranchField: AutomationFieldDefinition = {
  name: "baseBranch",
  label: "目标分支",
  placeholder: "main",
  help: "留空时使用 main，PR 将以此分支为 base",
  required: false,
};

export const runtimeNameField: AutomationFieldDefinition = {
  name: "runtimeName",
  label: "Runtime 名称",
  placeholder: "support-agent",
  help: "用于 AgentKit 发布配置",
  required: true,
};

export const runtimeIdField: AutomationFieldDefinition = {
  name: "runtimeId",
  label: "Runtime ID",
  placeholder: "rt-xxxxxxxx",
  help: "持续更新的目标 AgentKit Runtime",
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
    `${secrets.accessKey}、${secrets.secretKey}（必填）`,
    `${secrets.sessionToken}（使用临时凭据时必填）`,
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
