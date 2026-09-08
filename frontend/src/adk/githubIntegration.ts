import type { CloudRegion } from "./cloudProvider";
import { studioFetch } from "./client";
import { adkT } from "./i18n";

export type GitHubAutomationRegion = CloudRegion;

export interface GitHubPullRequestResult {
  number: number;
  url: string;
  branch: string;
}

export interface GitHubPullRequestReviewResult {
  status: "started";
  sessionId: string;
  displayName: string;
}

export type GitHubPullRequestReviewRecordStatus = "started" | "completed" | "ignored" | "failed";
export type GitHubPullRequestReviewRecordTrigger = "manual" | "webhook";

export interface GitHubPullRequestReviewRecord {
  id: string;
  repository: string;
  pullRequestUrl: string;
  pullRequestNumber: number;
  status: GitHubPullRequestReviewRecordStatus;
  trigger: GitHubPullRequestReviewRecordTrigger;
  createdAt: string;
  deliveryId: string;
  action: string;
  sessionId: string;
  displayName: string;
  reason: string;
}

export interface GitHubAppConfig {
  configured: boolean;
  appSlug: string;
  installUrl: string;
  reason: string;
}

export interface GitHubAppRepository {
  installationId: number;
  account: string;
  fullName: string;
  htmlUrl: string;
  private: boolean;
  reviewEnabled: boolean;
}

export interface GitHubPagination {
  page: number;
  pageSize: number;
  hasNextPage: boolean;
}

export interface GitHubAppRepositoriesResult extends GitHubPagination {
  repositories: GitHubAppRepository[];
  reviewSettingsConfigured: boolean;
  reviewSettingsReason: string;
}

export interface GitHubPullRequestReviewRecordsResult extends GitHubPagination {
  records: GitHubPullRequestReviewRecord[];
  reviewSettingsConfigured: boolean;
  reviewSettingsReason: string;
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
  const message = String(payload?.message || "");
  if (status === 403 && /workflow/i.test(message)) {
    return "GitHub Token 缺少 Workflows 写权限，无法创建或更新 .github/workflows 下的文件";
  }
  if (status === 401 || status === 403) {
    return adkT("github.invalidToken");
  }
  if (status === 404) {
    return adkT("github.notFound");
  }
  if (status === 422) {
    return adkT("github.rejectedCommit");
  }
  const detail = message.split(token).join("***").trim();
  return detail.slice(0, 240) || adkT("github.requestFailed", { status });
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
    throw new Error(adkT("github.networkFailed"));
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
      throw new Error(adkT("github.invalidRepositoryFormat"));
    }
    if (
      repositoryUrl.protocol !== "https:"
      || !["github.com", "www.github.com"].includes(repositoryUrl.hostname)
      || repositoryUrl.username
      || repositoryUrl.password
      || repositoryUrl.search
      || repositoryUrl.hash
    ) {
      throw new Error(adkT("github.insecureRepositoryUrl"));
    }
    candidate = repositoryUrl.pathname;
  }
  candidate = candidate.replace(/\.git$/, "").replace(/^\/+|\/+$/g, "");
  if (!REPOSITORY_PATTERN.test(candidate)) {
    throw new Error(adkT("github.invalidRepositoryFormat"));
  }
  return candidate;
}

export function repositoryFromGitHubPullRequestUrl(value: string): string {
  const match = value.trim().match(
    /^https:\/\/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)\/pull\/[1-9][0-9]*\/?$/,
  );
  return match?.[1] ?? "";
}

export function normalizeRepositoryPath(value: string, fallback = "."): string {
  const candidate = value.trim() || fallback;
  const parts = candidate.split("/");
  if (
    candidate.startsWith("/")
    || !FILE_PATH_PATTERN.test(candidate)
    || parts.includes("..")
  ) {
    throw new Error(adkT("github.unsafeProjectPath"));
  }
  return candidate.replace(/\/+$/, "") || ".";
}

export async function createGitHubPullRequest(
  spec: GitHubPullRequestSpec,
  signal: AbortSignal,
): Promise<GitHubPullRequestResult> {
  const repository = normalizeGitHubRepository(spec.repository);
  const baseBranch = spec.baseBranch.trim() || "main";
  if (!spec.token.trim()) throw new Error(adkT("github.tokenRequired"));
  if (!BRANCH_PATTERN.test(baseBranch) || baseBranch.includes("..")) {
    throw new Error(adkT("github.invalidBaseBranch"));
  }
  if (!BRANCH_PATTERN.test(spec.branchPrefix)) {
    throw new Error(adkT("github.invalidPublishBranch"));
  }
  if (!spec.files.length) throw new Error(adkT("github.noFiles"));

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
  if (!baseSha) throw new Error(adkT("github.missingBaseSha"));

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
        throw new Error(adkT("github.fileAlreadyExists", { path: file.path }));
      }
      if (existing.status === 200 && !existing.payload.sha) {
        throw new Error(adkT("github.pathNotUpdatable", { path: file.path }));
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
      throw new Error(adkT("github.invalidPullRequest"));
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

export async function startGitHubPullRequestReview(
  input: {
    pullRequestUrl: string;
  },
  signal: AbortSignal,
): Promise<GitHubPullRequestReviewResult> {
  const response = await studioFetch(
    "/web/github/pull-request-reviews",
    {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal,
    },
  );
  if (!response.ok) {
    throw await responseErrorFromGitHubReview(response);
  }
  const value = (await response.json()) as Partial<GitHubPullRequestReviewResult>;
  if (
    value.status !== "started" ||
    typeof value.sessionId !== "string" ||
    !value.sessionId ||
    typeof value.displayName !== "string"
  ) {
    throw new Error("PR 评审服务返回了无效结果。");
  }
  return value as GitHubPullRequestReviewResult;
}

export async function getGitHubAppConfig(
  signal: AbortSignal,
): Promise<GitHubAppConfig> {
  const response = await studioFetch(
    "/web/github/app/config",
    {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    },
  );
  if (!response.ok) {
    throw await responseErrorFromGitHubReview(response);
  }
  const value = (await response.json()) as Partial<GitHubAppConfig>;
  if (
    typeof value.configured !== "boolean" ||
    typeof value.appSlug !== "string" ||
    typeof value.installUrl !== "string" ||
    typeof value.reason !== "string"
  ) {
    throw new Error("GitHub App 配置响应格式无效。");
  }
  return value as GitHubAppConfig;
}

export async function getGitHubAppRepositories(
  signal: AbortSignal,
  options: { page: number; pageSize: number; query?: string },
): Promise<GitHubAppRepositoriesResult> {
  const params = new URLSearchParams({
    page: String(options.page),
    pageSize: String(options.pageSize),
  });
  if (options.query?.trim()) params.set("q", options.query.trim());
  const response = await studioFetch(
    `/web/github/app/repositories?${params.toString()}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    },
  );
  if (!response.ok) {
    throw await responseErrorFromGitHubReview(response);
  }
  const value = (await response.json()) as Partial<GitHubAppRepositoriesResult>;
  if (
    !Array.isArray(value.repositories) ||
    typeof value.page !== "number" ||
    typeof value.pageSize !== "number" ||
    typeof value.hasNextPage !== "boolean" ||
    typeof value.reviewSettingsConfigured !== "boolean" ||
    typeof value.reviewSettingsReason !== "string" ||
    value.repositories.some((repository) => (
      typeof repository !== "object" ||
      repository === null ||
      typeof repository.installationId !== "number" ||
      typeof repository.account !== "string" ||
      typeof repository.fullName !== "string" ||
      typeof repository.htmlUrl !== "string" ||
      typeof repository.private !== "boolean" ||
      typeof repository.reviewEnabled !== "boolean"
    ))
  ) {
    throw new Error("GitHub App 仓库列表响应格式无效。");
  }
  return value as GitHubAppRepositoriesResult;
}

export async function getGitHubPullRequestReviewRecords(
  signal: AbortSignal,
  options: { page: number; pageSize: number },
): Promise<GitHubPullRequestReviewRecordsResult> {
  const params = new URLSearchParams({
    page: String(options.page),
    pageSize: String(options.pageSize),
  });
  const response = await studioFetch(
    `/web/github/app/review-records?${params.toString()}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    },
  );
  if (!response.ok) {
    throw await responseErrorFromGitHubReview(response);
  }
  const value = (await response.json()) as Partial<GitHubPullRequestReviewRecordsResult>;
  if (
    !Array.isArray(value.records) ||
    typeof value.page !== "number" ||
    typeof value.pageSize !== "number" ||
    typeof value.hasNextPage !== "boolean" ||
    typeof value.reviewSettingsConfigured !== "boolean" ||
    typeof value.reviewSettingsReason !== "string" ||
    value.records.some((record) => (
      typeof record !== "object" ||
      record === null ||
      typeof record.id !== "string" ||
      typeof record.repository !== "string" ||
      typeof record.pullRequestUrl !== "string" ||
      typeof record.pullRequestNumber !== "number" ||
      !["started", "completed", "ignored", "failed"].includes(String(record.status)) ||
      !["manual", "webhook"].includes(String(record.trigger)) ||
      typeof record.createdAt !== "string" ||
      typeof record.deliveryId !== "string" ||
      typeof record.action !== "string" ||
      typeof record.sessionId !== "string" ||
      typeof record.displayName !== "string" ||
      typeof record.reason !== "string"
    ))
  ) {
    throw new Error("PR 评审记录响应格式无效。");
  }
  return value as GitHubPullRequestReviewRecordsResult;
}

export async function updateGitHubAppReviewRepositories(
  repositories: string[],
  signal: AbortSignal,
): Promise<string[]> {
  const response = await studioFetch(
    "/web/github/app/review-repositories",
    {
      method: "PUT",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ repositories }),
      signal,
    },
  );
  if (!response.ok) {
    throw await responseErrorFromGitHubReview(response);
  }
  const value = (await response.json()) as { repositories?: unknown };
  if (
    !Array.isArray(value.repositories) ||
    value.repositories.some((repository) => typeof repository !== "string")
  ) {
    throw new Error("GitHub App 启用仓库响应格式无效。");
  }
  return value.repositories;
}

export async function updateGitHubAppReviewRepository(
  input: {
    repository: string;
    reviewEnabled: boolean;
  },
  signal: AbortSignal,
): Promise<string[]> {
  const response = await studioFetch(
    "/web/github/app/review-repositories",
    {
      method: "PUT",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal,
    },
  );
  if (!response.ok) {
    throw await responseErrorFromGitHubReview(response);
  }
  const value = (await response.json()) as { repositories?: unknown };
  if (
    !Array.isArray(value.repositories) ||
    value.repositories.some((repository) => typeof repository !== "string")
  ) {
    throw new Error("GitHub App 评审仓库保存响应格式无效。");
  }
  return value.repositories;
}

async function responseErrorFromGitHubReview(response: Response): Promise<Error> {
  const text = await response.text().catch(() => "");
  try {
    const payload = JSON.parse(text) as {
      detail?: { message?: unknown } | string;
      message?: unknown;
      error?: unknown;
    };
    const detail = typeof payload.detail === "object" && payload.detail
      ? payload.detail.message
      : payload.detail ?? payload.message ?? payload.error;
    const detailText = typeof detail === "string" ? detail : "";
    return new Error(
      detailText || `PR 评审发起失败（HTTP ${response.status}）`,
    );
  } catch {
    return new Error(text || `PR 评审发起失败（HTTP ${response.status}）`);
  }
}
