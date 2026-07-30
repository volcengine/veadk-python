import type { DeployBuildLogSnapshot } from "../adk/client";

export const DEPLOY_BUILD_LOG_MAX_CHARS = 50000;

function appendSnapshotText(previous: string, next: string): string {
  if (!previous) return next;
  if (!next) return previous;
  if (previous.endsWith(next)) return previous;
  if (next.startsWith(previous)) return next;

  const previousLines = previous.split("\n");
  const nextLines = next.split("\n");
  const maxOverlap = Math.min(previousLines.length, nextLines.length, 260);
  for (let count = maxOverlap; count > 0; count -= 1) {
    const previousTail = previousLines.slice(-count).join("\n");
    const nextHead = nextLines.slice(0, count).join("\n");
    if (previousTail === nextHead) {
      const remaining = nextLines.slice(count).join("\n");
      return remaining ? `${previous}\n${remaining}` : previous;
    }
  }

  return `${previous}\n${next}`;
}

function trimEarlyLogText(text: string, maxChars: number): { text: string; omitted: boolean } {
  if (text.length <= maxChars) return { text, omitted: false };
  let trimmed = text.slice(-maxChars);
  const firstNewline = trimmed.indexOf("\n");
  if (firstNewline >= 0) trimmed = trimmed.slice(firstNewline + 1);
  return { text: trimmed, omitted: true };
}

export function mergeDeployBuildLog(
  previous: DeployBuildLogSnapshot | undefined,
  snapshot: DeployBuildLogSnapshot,
  maxChars = DEPLOY_BUILD_LOG_MAX_CHARS,
): DeployBuildLogSnapshot {
  const mergedText = appendSnapshotText(previous?.text ?? "", snapshot.text ?? "");
  const trimmed = trimEarlyLogText(mergedText, maxChars);
  const lineCount = trimmed.text ? trimmed.text.split("\n").length : 0;
  const snapshotTruncated = Boolean(snapshot.snapshotTruncated || snapshot.truncated);
  const omittedEarly = Boolean(previous?.omittedEarly || trimmed.omitted);

  return {
    ...snapshot,
    text: trimmed.text,
    lineCount,
    truncated: Boolean(previous?.truncated || snapshot.truncated || omittedEarly),
    omittedEarly,
    snapshotTruncated: Boolean(previous?.snapshotTruncated || snapshotTruncated),
  };
}
