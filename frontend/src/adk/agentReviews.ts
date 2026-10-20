import { withAuth } from "./auth";
import { withLocaleHeaders } from "./i18n";
import { withLocalUser } from "./identity";
import { requestSignal } from "./timeout";

export type AgentReviewStatus = "pending" | "approved" | "returned" | "withdrawn";
export interface ReviewPerson {
  id: string;
  name: string;
  avatarUrl: string;
  email: string;
}
export interface AgentReviewApplication {
  id: string;
  runtimeId: string;
  region: string;
  status: AgentReviewStatus;
  agent: {
    name: string;
    description: string;
    version: number | null;
    model: string;
    environmentKeys: string[];
    cpuMilli: number | null;
    memoryMb: number | null;
  };
  submitter: ReviewPerson;
  submittedAt: string;
  message: string;
  reviewer: ReviewPerson | null;
  reviewedAt: string;
  comment: string;
  reason: string;
  published: boolean;
  direct?: boolean;
  contentChanged?: boolean;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(withAuth(`/web/agent-reviews${path}`), {
    ...init,
    headers: withLocaleHeaders(withLocalUser({ "Content-Type": "application/json" })),
    signal: requestSignal(init.signal ?? undefined, 60_000),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export function listAgentReviews(region: string, signal?: AbortSignal) {
  return request<{ items: AgentReviewApplication[] }>(`?${new URLSearchParams({ region })}`, { signal });
}

export function readAgentReview(runtimeId: string, region: string, signal?: AbortSignal) {
  return request<{ application: AgentReviewApplication | null }>(`/${encodeURIComponent(runtimeId)}?${new URLSearchParams({ region })}`, { signal });
}

export function changeAgentReview(runtimeId: string, action: "submit" | "publish" | "withdraw" | "unpublish" | "decision", body: {
  region: string;
  message?: string;
  comment?: string;
  reason?: string;
  applicationId?: string;
  decision?: "approved" | "returned";
}) {
  return request<AgentReviewApplication>(`/${encodeURIComponent(runtimeId)}/${action}`, { method: "POST", body: JSON.stringify(body) });
}
