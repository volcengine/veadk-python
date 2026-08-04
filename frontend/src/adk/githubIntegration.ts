export interface GitHubPullRequestInput {
  repository: string;
  baseBranch: string;
  projectPath: string;
  runtimeName: string;
  runtimeId: string;
  region: "cn-beijing" | "cn-shanghai";
  token: string;
}

export interface GitHubPullRequestResult {
  number: number;
  url: string;
  branch: string;
}

export async function createGitHubPullRequest(
  input: GitHubPullRequestInput,
): Promise<GitHubPullRequestResult> {
  const response = await fetch("/web/integrations/github/pull-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `提交 PR 失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<GitHubPullRequestResult>;
}

