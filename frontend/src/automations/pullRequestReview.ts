import { initialAutomationValues } from "./githubFields";
import type { GitHubAutomationDefinition } from "./types";
export const pullRequestReviewAutomation: GitHubAutomationDefinition = {
  id: "review",
  kind: "github",
  category: "development",
  icon: "github",
  name: "Automated PR review",
  description: "Use a GitHub App to review pull requests in an isolated Sandbox.",
  title: "Automated PR review",
  subtitle: "Trigger Sandbox reviews through the GitHub App and publish results to pull requests",
  panel: "Install the GitHub App to target repositories, then enable automated review for each repository.",
  submitLabel: "Install GitHub App",
  fields: [],
  initialValues: ({ cloudProvider }) => initialAutomationValues(cloudProvider),
  regionHelp: "",
  secrets: () => [],
  async submit() {
    throw new Error("PR 自动评审已切换为 GitHub App 授权模式。");
  },
};
