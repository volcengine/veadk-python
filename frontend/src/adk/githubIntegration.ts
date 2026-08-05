export type GitHubAutomationRegion = "cn-beijing" | "cn-shanghai";

export interface GitHubPullRequestResult {
  number: number;
  url: string;
  branch: string;
}

export async function postGitHubPullRequest(
  endpoint: string,
  input: object,
  signal?: AbortSignal,
): Promise<GitHubPullRequestResult> {
  const timeoutSignal = AbortSignal.timeout(30_000);
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal: signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(payload?.detail || `提交 PR 失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<GitHubPullRequestResult>;
}
