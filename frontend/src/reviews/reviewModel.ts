import type { ReviewScoreSummary } from "./scoreModel";

export type ReviewKind = "skill" | "agent";
export type ReviewStatus = "pending" | "approving" | "approved" | "returned";
export type ReviewDecision = "approved" | "returned";

export interface ReviewPerson {
  id: string;
  name: string;
  email?: string;
  avatarUrl?: string;
}

export interface ReviewApplication {
  id: string;
  kind: ReviewKind;
  name: string;
  description: string;
  author: string;
  version: string;
  submittedAt: string;
  status: ReviewStatus;
  region: string;
  reviewSpaceId: string;
  reviewVersion: string;
  sourceSpaceId: string;
  sourceSkillId: string;
  reviewedAt?: string;
  reviewedBy?: string;
  reviewer?: ReviewPerson;
  reason?: string;
  comment?: string;
  sharedSkillId?: string;
  sharedSpaceId?: string;
  sharedVersion?: string;
  aiReview?: ReviewScoreSummary;
}

export function latestSourceReviews(applications: readonly ReviewApplication[]): Map<string, ReviewApplication> {
  const latest = new Map<string, ReviewApplication>();
  for (const application of applications) {
    const key = `${application.sourceSkillId}:${application.version}`;
    const previous = latest.get(key);
    if (!previous || application.submittedAt > previous.submittedAt) latest.set(key, application);
  }
  return latest;
}

export function filterReviewApplications(
  applications: readonly ReviewApplication[], kind: ReviewKind,
  status: ReviewStatus | "all", query: string,
): ReviewApplication[] {
  const search = query.trim().toLocaleLowerCase();
  return applications.filter((item) => item.kind === kind
    && (status === "all" || item.status === status)
    && `${item.name} ${item.description} ${item.author} ${item.version}`.toLocaleLowerCase().includes(search));
}
