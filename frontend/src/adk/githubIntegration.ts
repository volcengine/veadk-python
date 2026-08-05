export type GitHubAutomationRegion = "cn-beijing" | "cn-shanghai";

export interface GitHubPullRequestResult {
  number: number;
  url: string;
  branch: string;
}

export interface GitHubPullRequestFile {
  path: string;
  content: string;
  commitMessage: string;
  mustBeNew?: boolean;
}

export interface GitHubPullRequestSpec {
  repository: string;
  baseBranch: string;
  token: string;
  files: readonly GitHubPullRequestFile[];
  branchPrefix: string;
  title: string;
  description: string;
}

interface GitHubPayload {
  message?: string;
  number?: number;
  html_url?: string;
  sha?: string;
  object?: { sha?: string };
}

interface GitHubResponse<T> {
  status: number;
  payload: T;
}

const GITHUB_API_ROOT = "https://api.github.com";
const REPOSITORY_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;
const BRANCH_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$/;
const FILE_PATH_PATTERN = /^[A-Za-z0-9._/-]+$/;

function sanitizeGitHubError(status: number, payload: GitHubPayload | null, token: string): string {
  if (status === 401 || status === 403) {
    return "GitHub Token 无效或没有仓库写入权限";
  }
  if (status === 404) {
    return "仓库、分支或文件不存在，或 Token 无权访问";
  }
  if (status === 422) {
    return "GitHub 拒绝了提交，请检查分支和文件状态";
  }
  const detail = String(payload?.message || "").split(token).join("***").trim();
  return detail.slice(0, 240) || `GitHub 请求失败（HTTP ${status}）`;
}

async function requestGitHub<T extends GitHubPayload | null>(
  path: string,
  options: {
    token: string;
    expected: readonly number[];
    signal: AbortSignal;
    method?: "GET" | "POST" | "PUT" | "DELETE";
    body?: object;
  },
): Promise<GitHubResponse<T>> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${options.token}`,
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (options.body) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${GITHUB_API_ROOT}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal.aborted) throw error;
    throw new Error("连接 GitHub 失败，请检查网络后重试");
  }

  const payload = await response.json().catch(() => null) as T;
  if (!options.expected.includes(response.status)) {
    throw new Error(sanitizeGitHubError(response.status, payload, options.token));
  }
  return { status: response.status, payload };
}

function encodeGitHubPath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

function encodeBase64(content: string): string {
  const bytes = new TextEncoder().encode(content);
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function createBranchName(prefix: string): string {
  const timestamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  return `${prefix}-${timestamp}-${crypto.randomUUID().slice(0, 8)}`;
}

export function normalizeGitHubRepository(value: string): string {
  let candidate = value.trim();
  if (candidate.startsWith("git@github.com:")) {
    candidate = candidate.slice("git@github.com:".length);
  } else if (candidate.includes("://")) {
    let repositoryUrl: URL;
    try {
      repositoryUrl = new URL(candidate);
    } catch {
      throw new Error("GitHub Repo 格式应为 owner/repository");
    }
    if (
      repositoryUrl.protocol !== "https:"
      || !["github.com", "www.github.com"].includes(repositoryUrl.hostname)
      || repositoryUrl.username
      || repositoryUrl.password
      || repositoryUrl.search
      || repositoryUrl.hash
    ) {
      throw new Error("仅支持安全的 github.com 仓库地址");
    }
    candidate = repositoryUrl.pathname;
  }
  candidate = candidate.replace(/\.git$/, "").replace(/^\/+|\/+$/g, "");
  if (!REPOSITORY_PATTERN.test(candidate)) {
    throw new Error("GitHub Repo 格式应为 owner/repository");
  }
  return candidate;
}

export function normalizeRepositoryPath(value: string, fallback = "."): string {
  const candidate = value.trim() || fallback;
  const parts = candidate.split("/");
  if (
    candidate.startsWith("/")
    || !FILE_PATH_PATTERN.test(candidate)
    || parts.includes("..")
  ) {
    throw new Error("Agent 项目目录必须是仓库内的安全相对路径");
  }
  return candidate.replace(/\/+$/, "") || ".";
}

export async function createGitHubPullRequest(
  spec: GitHubPullRequestSpec,
  signal: AbortSignal,
): Promise<GitHubPullRequestResult> {
  const repository = normalizeGitHubRepository(spec.repository);
  const baseBranch = spec.baseBranch.trim() || "main";
  if (!spec.token.trim()) throw new Error("GitHub Token 不能为空");
  if (!BRANCH_PATTERN.test(baseBranch) || baseBranch.includes("..")) {
    throw new Error("目标分支格式不正确");
  }
  if (!BRANCH_PATTERN.test(spec.branchPrefix)) {
    throw new Error("发布分支格式不正确");
  }
  if (!spec.files.length) throw new Error("没有需要提交的文件");

  const files = spec.files.map((file) => ({
    ...file,
    path: normalizeRepositoryPath(file.path, ""),
  }));
  const operationSignal = AbortSignal.any([signal, AbortSignal.timeout(60_000)]);
  const repoPath = `/repos/${repository}`;

  await requestGitHub(`${repoPath}`, {
    token: spec.token,
    expected: [200],
    signal: operationSignal,
  });
  const baseRef = await requestGitHub<GitHubPayload>(
    `${repoPath}/git/ref/heads/${encodeGitHubPath(baseBranch)}`,
    {
      token: spec.token,
      expected: [200],
      signal: operationSignal,
    },
  );
  const baseSha = baseRef.payload.object?.sha;
  if (!baseSha) throw new Error("目标分支缺少有效 Git SHA");

  const branch = createBranchName(spec.branchPrefix);
  await requestGitHub(`${repoPath}/git/refs`, {
    token: spec.token,
    expected: [201],
    signal: operationSignal,
    method: "POST",
    body: { ref: `refs/heads/${branch}`, sha: baseSha },
  });

  let branchCreated = true;
  try {
    for (const file of files) {
      const encodedPath = encodeGitHubPath(file.path);
      const existing = await requestGitHub<GitHubPayload>(
        `${repoPath}/contents/${encodedPath}?ref=${encodeURIComponent(baseBranch)}`,
        {
          token: spec.token,
          expected: [200, 404],
          signal: operationSignal,
        },
      );
      if (file.mustBeNew && existing.status === 200) {
        throw new Error(`目标仓库中已存在 ${file.path}，未覆盖现有文件`);
      }
      if (existing.status === 200 && !existing.payload.sha) {
        throw new Error(`目标路径 ${file.path} 不是可更新的文件`);
      }

      await requestGitHub(`${repoPath}/contents/${encodedPath}`, {
        token: spec.token,
        expected: [200, 201],
        signal: operationSignal,
        method: "PUT",
        body: {
          message: file.commitMessage,
          content: encodeBase64(file.content),
          branch,
          ...(existing.payload.sha ? { sha: existing.payload.sha } : {}),
        },
      });
    }

    const pullRequest = await requestGitHub<GitHubPayload>(`${repoPath}/pulls`, {
      token: spec.token,
      expected: [201],
      signal: operationSignal,
      method: "POST",
      body: {
        title: spec.title,
        head: branch,
        base: baseBranch,
        body: spec.description,
      },
    });
    if (!pullRequest.payload.number || !pullRequest.payload.html_url) {
      throw new Error("GitHub 未返回有效的 Pull Request");
    }
    branchCreated = false;
    return {
      number: pullRequest.payload.number,
      url: pullRequest.payload.html_url,
      branch,
    };
  } finally {
    if (branchCreated) {
      await requestGitHub(`${repoPath}/git/refs/heads/${encodeGitHubPath(branch)}`, {
        token: spec.token,
        expected: [204],
        signal: AbortSignal.timeout(15_000),
        method: "DELETE",
      }).catch(() => undefined);
    }
  }
}
