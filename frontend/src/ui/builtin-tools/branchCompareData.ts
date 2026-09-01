export type BranchCompareStatus = "pending" | "running" | "completed" | "failed";

export interface BranchCompareBranch {
  label: string;
  content: string;
  status: BranchCompareStatus;
  error: string;
}

export interface BranchCompareView {
  branches: [BranchCompareBranch, BranchCompareBranch];
}

export interface BranchCompareProgress {
  toolName: string;
  requestId: string;
  branchIndex: number;
  label: string;
  delta: string;
  status: BranchCompareStatus;
  error?: string;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function statusOf(value: unknown, fallback: BranchCompareStatus): BranchCompareStatus {
  return value === "pending" || value === "running" || value === "completed" || value === "failed"
    ? value
    : fallback;
}

function unwrapPayload(value: unknown): Record<string, unknown> {
  let parsed = value;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return {};
    }
  }
  const record = asRecord(parsed) ?? {};
  return asRecord(record.result) ?? record;
}

function argumentLabels(args: unknown): string[] {
  const branches = asRecord(args)?.branches;
  if (!Array.isArray(branches)) return [];
  return branches.map((value) => asString(asRecord(value)?.label));
}

export function parseBranchCompare(
  args: unknown,
  response: unknown,
  toolStatus: "running" | "completed" | "failed",
): BranchCompareView {
  const labels = argumentLabels(args);
  const payload = unwrapPayload(response);
  const rawBranches = Array.isArray(payload.branches) ? payload.branches : [];
  const fallbackStatus: BranchCompareStatus = toolStatus === "running" ? "running" : "pending";
  const parsed = [0, 1].map((index) => {
    const branch = asRecord(rawBranches[index]) ?? {};
    return {
      label: asString(branch.label) || labels[index] || `方向 ${index + 1}`,
      content: asString(branch.content),
      status: statusOf(branch.status, fallbackStatus),
      error: asString(branch.error),
    } satisfies BranchCompareBranch;
  });
  return { branches: parsed as [BranchCompareBranch, BranchCompareBranch] };
}

export function parseBranchCompareProgress(partMetadata: unknown): BranchCompareProgress | null {
  const metadata = asRecord(partMetadata);
  const progress = asRecord(metadata?.veadkStudioToolProgress);
  if (
    !progress
    || progress.toolName !== "branch_compare"
    || typeof progress.branchIndex !== "number"
    || progress.branchIndex < 0
    || progress.branchIndex > 1
  ) return null;
  return {
    toolName: "branch_compare",
    requestId: asString(progress.requestId),
    branchIndex: progress.branchIndex,
    label: asString(progress.label),
    delta: asString(progress.delta),
    status: statusOf(progress.status, "running"),
    error: asString(progress.error) || undefined,
  };
}

export function applyBranchCompareProgress(
  args: unknown,
  response: unknown,
  progress: BranchCompareProgress,
): BranchCompareView {
  const current = parseBranchCompare(args, response, "running");
  const branches = current.branches.map((branch, index) => index === progress.branchIndex
    ? {
        ...branch,
        label: progress.label || branch.label,
        content: branch.content + progress.delta,
        status: progress.status,
        error: progress.error ?? branch.error,
      }
    : branch) as [BranchCompareBranch, BranchCompareBranch];
  return { branches };
}
