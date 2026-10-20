import type { GitLabAutomationDefinition } from "./types";

export const gitLabMergeRequestReviewAutomation: GitLabAutomationDefinition = {
  id: "gitlab-review",
  kind: "gitlab",
  category: "development",
  icon: "gitlab",
  name: "GitLab MR review",
  description: "Use a GitLab integration to review merge requests in an isolated Sandbox.",
};
