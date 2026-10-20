import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { withLocaleHeaders } from "./i18n";
import { i18n } from "../i18n/runtime";
import { skillApiErrorFromResponse } from "./skills";
import { requestSignal, DEFAULT_REQUEST_TIMEOUT_MS } from "./timeout";
import type { ReviewScoreResponse } from "../reviews/scoreModel";

interface ReviewScoreTarget { id: string; region: string; signal?: AbortSignal }

async function requestScore(target: ReviewScoreTarget, retry: boolean): Promise<ReviewScoreResponse> {
  const params = new URLSearchParams({ region: target.region });
  const suffix = retry ? "/retry" : `?${params}`;
  const response = await fetch(withAuth(`/web/skill-management/reviews/${encodeURIComponent(target.id)}/score${suffix}`), {
    method: retry ? "POST" : "GET",
    headers: withLocaleHeaders(withLocalUser(retry ? { "Content-Type": "application/json" } : undefined)),
    ...(retry ? { body: JSON.stringify({ region: target.region }) } : {}),
    signal: requestSignal(target.signal, DEFAULT_REQUEST_TIMEOUT_MS),
  });
  if (!response.ok) throw await skillApiErrorFromResponse(response, i18n.t(retry ? "score.retryFailed" : "score.loadFailed", { ns: "reviews" }));
  return response.json() as Promise<ReviewScoreResponse>;
}

export const getReviewScore = (target: ReviewScoreTarget) => requestScore(target, false);
export const retryReviewScore = (target: ReviewScoreTarget) => requestScore(target, true);
