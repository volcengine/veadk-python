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

export function initialAutomationValues(
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
    modelBaseUrl: "https://ark.cn-beijing.volces.com/api/coding/v3",
    region: "cn-beijing",
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
