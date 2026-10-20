import { studioFetch } from "./client";

export type GitLabReviewRecordStatus = "started" | "completed" | "ignored" | "failed";
export type GitLabReviewRecordTrigger = "manual" | "webhook";

export interface GitLabAppConfig {
  configured: boolean;
  baseUrl: string;
  webhookUrl: string;
  reason: string;
  oauthConfigured: boolean;
  oauthConnected: boolean;
  oauthUser: GitLabOAuthUser | null;
}

export interface GitLabOAuthUser {
  credentialId: string;
  ownerId: string;
  baseUrl: string;
  gitlabUserId: number;
  gitlabUsername: string;
  gitlabName: string;
  expiresAt: number;
}

export interface GitLabProject {
  instanceId: string;
  baseUrl: string;
  projectId: number;
  pathWithNamespace: string;
  name: string;
  namespace: string;
  webUrl: string;
  private: boolean;
  reviewEnabled: boolean;
  permissionsNote: string;
  accessLevel: number;
  canManageWebhooks: boolean;
  reviewBindingStatus: string;
  reviewBindingReason: string;
  reviewCredentialOwner: string;
  reviewCredentialType: string;
}

export interface GitLabPagination {
  page: number;
  pageSize: number;
  hasNextPage: boolean;
}

export interface GitLabProjectsResult extends GitLabPagination {
  projects: GitLabProject[];
  reviewSettingsConfigured: boolean;
  reviewSettingsReason: string;
}

export interface GitLabReviewRecord {
  id: string;
  instanceId: string;
  baseUrl: string;
  projectId: number;
  pathWithNamespace: string;
  mergeRequestUrl: string;
  mergeRequestIid: number;
  status: GitLabReviewRecordStatus;
  trigger: GitLabReviewRecordTrigger;
  createdAt: string;
  deliveryId: string;
  action: string;
  sessionId: string;
  displayName: string;
  reason: string;
}

export interface GitLabReviewRecordsResult extends GitLabPagination {
  records: GitLabReviewRecord[];
  reviewSettingsConfigured: boolean;
  reviewSettingsReason: string;
}

export interface GitLabReviewResult {
  status: "started";
  sessionId: string;
  displayName: string;
}

async function gitLabReviewError(response: Response): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: { message?: string } } | null;
  const message = payload?.detail?.message;
  return new Error(message || `GitLab MR 评审请求失败（HTTP ${response.status}）。`);
}

export function projectFromGitLabMergeRequestUrl(baseUrl: string, value: string): string {
  const normalizedBase = baseUrl.trim().replace(/\/+$/, "");
  if (!normalizedBase) return "";
  const prefix = `${normalizedBase}/`;
  const candidate = value.trim();
  if (!candidate.startsWith(prefix)) return "";
  const suffix = candidate.slice(prefix.length).replace(/\/+$/, "");
  const marker = "/-/merge_requests/";
  const markerIndex = suffix.indexOf(marker);
  if (markerIndex <= 0) return "";
  const iid = suffix.slice(markerIndex + marker.length);
  if (!/^[1-9][0-9]*$/.test(iid)) return "";
  return suffix.slice(0, markerIndex);
}

export async function getGitLabAppConfig(signal: AbortSignal): Promise<GitLabAppConfig> {
  const response = await studioFetch("/web/gitlab/app/config", {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw await gitLabReviewError(response);
  const value = (await response.json()) as Partial<GitLabAppConfig>;
  if (
    typeof value.configured !== "boolean" ||
    typeof value.baseUrl !== "string" ||
    typeof value.webhookUrl !== "string" ||
    typeof value.reason !== "string" ||
    typeof value.oauthConfigured !== "boolean" ||
    typeof value.oauthConnected !== "boolean" ||
    (
      value.oauthUser !== null &&
      value.oauthUser !== undefined &&
      (
        typeof value.oauthUser !== "object" ||
        typeof value.oauthUser.credentialId !== "string" ||
        typeof value.oauthUser.ownerId !== "string" ||
        typeof value.oauthUser.baseUrl !== "string" ||
        typeof value.oauthUser.gitlabUserId !== "number" ||
        typeof value.oauthUser.gitlabUsername !== "string" ||
        typeof value.oauthUser.gitlabName !== "string" ||
        typeof value.oauthUser.expiresAt !== "number"
      )
    )
  ) {
    throw new Error("GitLab 集成配置响应格式无效。");
  }
  return value as GitLabAppConfig;
}

export async function getGitLabProjects(
  signal: AbortSignal,
  options: { page: number; pageSize: number; query?: string },
): Promise<GitLabProjectsResult> {
  const params = new URLSearchParams({
    page: String(options.page),
    pageSize: String(options.pageSize),
  });
  if (options.query?.trim()) params.set("q", options.query.trim());
  const response = await studioFetch(`/web/gitlab/app/projects?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw await gitLabReviewError(response);
  const value = (await response.json()) as Partial<GitLabProjectsResult>;
  if (
    !Array.isArray(value.projects) ||
    typeof value.page !== "number" ||
    typeof value.pageSize !== "number" ||
    typeof value.hasNextPage !== "boolean" ||
    typeof value.reviewSettingsConfigured !== "boolean" ||
    typeof value.reviewSettingsReason !== "string" ||
    value.projects.some((project) => (
      typeof project !== "object" ||
      project === null ||
      typeof project.instanceId !== "string" ||
      typeof project.baseUrl !== "string" ||
      typeof project.projectId !== "number" ||
      typeof project.pathWithNamespace !== "string" ||
      typeof project.name !== "string" ||
      typeof project.namespace !== "string" ||
      typeof project.webUrl !== "string" ||
      typeof project.private !== "boolean" ||
      typeof project.reviewEnabled !== "boolean" ||
      typeof project.permissionsNote !== "string" ||
      typeof project.accessLevel !== "number" ||
      typeof project.canManageWebhooks !== "boolean" ||
      typeof project.reviewBindingStatus !== "string" ||
      typeof project.reviewBindingReason !== "string" ||
      typeof project.reviewCredentialOwner !== "string" ||
      typeof project.reviewCredentialType !== "string"
    ))
  ) {
    throw new Error("GitLab 集成项目列表响应格式无效。");
  }
  return value as GitLabProjectsResult;
}

export async function updateGitLabReviewProject(
  input: { projectId: number; reviewEnabled: boolean },
  signal: AbortSignal,
): Promise<Array<{ projectId: number }>> {
  const response = await studioFetch("/web/gitlab/app/review-projects", {
    method: "PUT",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });
  if (!response.ok) throw await gitLabReviewError(response);
  const value = (await response.json()) as { projects?: unknown };
  if (!Array.isArray(value.projects) || value.projects.some((project) => (
    typeof project !== "object" ||
    project === null ||
    typeof (project as { projectId?: unknown }).projectId !== "number"
  ))) {
    throw new Error("GitLab 集成评审项目保存响应格式无效。");
  }
  return value.projects as Array<{ projectId: number }>;
}

export async function disconnectGitLabOAuth(signal: AbortSignal): Promise<void> {
  const response = await studioFetch("/web/gitlab/oauth/disconnect", {
    method: "POST",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw await gitLabReviewError(response);
}

export async function getGitLabOAuthAuthorizationUrl(signal: AbortSignal): Promise<string> {
  const response = await studioFetch("/web/gitlab/oauth/start-url", {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw await gitLabReviewError(response);
  const value = (await response.json()) as { authorizationUrl?: unknown };
  if (typeof value.authorizationUrl !== "string" || !value.authorizationUrl) {
    throw new Error("GitLab OAuth 授权地址响应格式无效。");
  }
  return value.authorizationUrl;
}

export async function getGitLabReviewRecords(
  signal: AbortSignal,
  options: { page: number; pageSize: number },
): Promise<GitLabReviewRecordsResult> {
  const params = new URLSearchParams({
    page: String(options.page),
    pageSize: String(options.pageSize),
  });
  const response = await studioFetch(`/web/gitlab/app/review-records?${params.toString()}`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw await gitLabReviewError(response);
  const value = (await response.json()) as Partial<GitLabReviewRecordsResult>;
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
      typeof record.projectId !== "number" ||
      typeof record.pathWithNamespace !== "string" ||
      typeof record.mergeRequestUrl !== "string" ||
      typeof record.mergeRequestIid !== "number" ||
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
    throw new Error("GitLab MR 评审记录响应格式无效。");
  }
  return value as GitLabReviewRecordsResult;
}

export async function startGitLabMergeRequestReview(
  input: { mergeRequestUrl: string },
  signal: AbortSignal,
): Promise<GitLabReviewResult> {
  const response = await studioFetch("/web/gitlab/merge-request-reviews", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });
  if (!response.ok) throw await gitLabReviewError(response);
  const value = (await response.json()) as Partial<GitLabReviewResult>;
  if (
    value.status !== "started" ||
    typeof value.sessionId !== "string" ||
    !value.sessionId ||
    typeof value.displayName !== "string"
  ) {
    throw new Error("GitLab MR 评审服务返回了无效结果。");
  }
  return value as GitLabReviewResult;
}
