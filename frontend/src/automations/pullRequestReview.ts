import { initialAutomationValues } from "./githubFields";
import type { GitHubAutomationDefinition } from "./types";

export const pullRequestReviewAutomation: GitHubAutomationDefinition = {
  id: "review",
  kind: "github",
  category: "development",
  icon: "github",
  name: "PR 自动评审",
  description: "通过 GitHub App 监听 Pull Request，并在隔离 Sandbox 中发布评审结果。",
  title: "PR 自动评审",
  subtitle: "通过 GitHub App 触发 Sandbox 评审并把结果发布到 Pull Request",
  panel: "安装 GitHub App 到目标仓库后，同仓库非草稿 PR 会自动触发评审。",
  submitLabel: "安装 GitHub App",
  fields: [],
  initialValues: ({ cloudProvider }) => initialAutomationValues(cloudProvider),
  regionHelp: "",
  secrets: () => [],
  async submit() {
    throw new Error("PR 自动评审已切换为 GitHub App 授权模式。");
  },
};
