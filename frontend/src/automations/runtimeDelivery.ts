import { postGitHubPullRequest } from "../adk/githubIntegration";
import {
  baseBranchField,
  commonGitHubInput,
  initialAutomationValues,
  repositoryField,
  runtimeIdField,
  runtimeNameField,
} from "./githubFields";
import type { GitHubAutomationDefinition } from "./types";

export const runtimeDeliveryAutomation: GitHubAutomationDefinition = {
  id: "delivery",
  kind: "github",
  category: "development",
  icon: "github",
  name: "AgentKit Runtime 持续交付",
  description: "为您的仓库添加持续交付到 AgentKit Runtime 的自动化工作流。",
  title: "AgentKit Runtime 持续交付",
  subtitle: "用 Pull Request 把持续发布配置安全地加入代码仓库",
  panel: "提交后将在目标仓库创建发布分支，并发起包含 GitHub Actions 工作流的 PR。",
  submitLabel: "确定并提交 PR",
  fields: [
    repositoryField,
    baseBranchField,
    {
      name: "projectPath",
      label: "Agent 项目目录",
      placeholder: ".",
      help: "留空时使用仓库根目录；目录内需包含挂载完整 Studio App Server 的 app.py",
      required: false,
    },
    runtimeNameField,
    runtimeIdField,
  ],
  initialValues: initialAutomationValues(),
  regionHelp: "必须与目标 Runtime 所在地域一致",
  secrets: [
    "VOLCENGINE_ACCESS_KEY、VOLCENGINE_SECRET_KEY（必填）",
    "VOLCENGINE_SESSION_TOKEN（使用临时凭据时必填）",
  ],
  submit(values, signal) {
    return postGitHubPullRequest(
      "/web/integrations/github/pull-requests",
      {
        ...commonGitHubInput(values),
        projectPath: values.projectPath.trim() || ".",
        runtimeName: values.runtimeName.trim(),
        runtimeId: values.runtimeId.trim(),
      },
      signal,
    );
  },
};
