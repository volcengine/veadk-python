import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { withAuth } from "./auth";
import { withLocalUser } from "./identity";

export async function fetchIntelligentDevelopmentRelease(
  sessionId: string,
  artifactSha256: string,
  validationReportSha256: string,
  signal?: AbortSignal,
): Promise<IntelligentDevelopmentReleaseRef> {
  const params = new URLSearchParams({
    sessionId,
    artifactSha256,
    validationReportSha256,
  });
  const response = await fetch(
    withAuth(`/web/intelligent-development/releases/summary?${params}`),
    { headers: withLocalUser({ Accept: "application/json" }), signal },
  );
  if (!response.ok) {
    throw new Error(`无法读取源码快照（HTTP ${response.status}）`);
  }
  const value = await response.json() as Partial<IntelligentDevelopmentReleaseRef>;
  if (
    value.sessionId !== sessionId
    || value.artifactSha256 !== artifactSha256
    || value.validationReportSha256 !== validationReportSha256
    || typeof value.agentName !== "string"
    || typeof value.entryPoint !== "string"
    || typeof value.fileCount !== "number"
    || typeof value.artifactSize !== "number"
    || typeof value.validatedAt !== "string"
    || typeof value.verified !== "boolean"
    || typeof value.validationSummary !== "string"
    || !Array.isArray(value.gateSummary)
    || !value.gateSummary.every((item) => typeof item === "string")
    || !Array.isArray(value.files)
    || !value.files.every(
      (item) => item && typeof item.path === "string" && typeof item.content === "string",
    )
  ) {
    throw new Error("源码快照的响应格式无效。");
  }
  return value as IntelligentDevelopmentReleaseRef;
}
