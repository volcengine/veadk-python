import { postGitHubPullRequest } from "../adk/githubIntegration";
import {
  baseBranchField,
  commonGitHubInput,
  initialAutomationValues,
  repositoryField,
} from "./githubFields";
import type { GitHubAutomationDefinition } from "./types";

export const pullRequestReviewAutomation: GitHubAutomationDefinition = {
  id: "review",
  kind: "github",
  category: "development",
  icon: "github",
  name: "PR 自动评审",
  description: "在隔离 Sandbox 中评审代码变更，并将结果发布到 Pull Request。",
  title: "PR 自动评审",
  subtitle: "在隔离 Sandbox 中检查代码变更并把结果发布到 Pull Request",
  panel: "工作流仅评审同仓库的非草稿 PR；fork PR 不会读取仓库 Secrets。",
  submitLabel: "添加评审并提交 PR",
  fields: [
    repositoryField,
    baseBranchField,
    {
      name: "sandboxToolId",
      label: "Sandbox Tool ID",
      placeholder: "tool-xxxxxxxx",
      help: "用于运行每次评审的 AgentKit CodeEnv",
      required: true,
    },
    {
      name: "modelName",
      label: "评审模型",
      placeholder: "doubao-seed-code-preview",
      help: "注入 Sandbox 的代码评审模型名称",
      required: true,
    },
    {
      name: "modelBaseUrl",
      label: "模型 API 地址",
      placeholder: "https://ark.cn-beijing.volces.com/api/coding/v3",
      help: "必须使用 OpenAI 兼容的 HTTPS 地址",
      required: true,
    },
  ],
  initialValues: initialAutomationValues(),
  regionHelp: "必须与 Sandbox Tool 所在地域一致",
  secrets: [
    "VOLCENGINE_ACCESS_KEY、VOLCENGINE_SECRET_KEY（必填）",
    "CODEX_MODEL_API_KEY（必填）",
    "VOLCENGINE_SESSION_TOKEN（使用临时凭据时必填）",
  ],
  submit(values, signal) {
    return postGitHubPullRequest(
      "/web/integrations/github/review-pull-requests",
      {
        ...commonGitHubInput(values),
        sandboxToolId: values.sandboxToolId.trim(),
        modelName: values.modelName.trim(),
        modelBaseUrl: values.modelBaseUrl.trim(),
      },
      signal,
    );
  },
};
