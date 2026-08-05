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

export const templateProjectAutomation: GitHubAutomationDefinition = {
  id: "template",
  kind: "github",
  category: "development",
  icon: "github",
  name: "模板项目导入",
  description: "在您的仓库中创建一个可持续交付到 AgentKit Runtime 的最简智能体",
  title: "模板项目导入",
  subtitle: "把可直接启动 Studio 的 basic Agent 和持续交付配置加入仓库",
  panel: "提交后将创建一个 PR，同时导入 basic 项目和 AgentKit Runtime 发布工作流。",
  submitLabel: "导入模板并提交 PR",
  fields: [
    repositoryField,
    baseBranchField,
    {
      name: "projectPath",
      label: "Agent 项目目录",
      placeholder: "agentkit-basic-agent",
      help: "将在此目录新增 basic 项目；app.py 挂载完整 Studio App Server，并作为服务入口启动",
      required: true,
    },
    runtimeNameField,
    runtimeIdField,
  ],
  initialValues: initialAutomationValues({ projectPath: "agentkit-basic-agent" }),
  regionHelp: "必须与目标 Runtime 所在地域一致",
  secrets: [
    "VOLCENGINE_ACCESS_KEY、VOLCENGINE_SECRET_KEY（必填）",
    "VOLCENGINE_SESSION_TOKEN（使用临时凭据时必填）",
  ],
  submit(values, signal) {
    return postGitHubPullRequest(
      "/web/integrations/github/template-pull-requests",
      {
        ...commonGitHubInput(values),
        projectPath: values.projectPath.trim() || "agentkit-basic-agent",
        runtimeName: values.runtimeName.trim(),
        runtimeId: values.runtimeId.trim(),
      },
      signal,
    );
  },
};
