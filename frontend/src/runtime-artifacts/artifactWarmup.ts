import type { RuntimeArtifact } from "../adk/runtimeArtifacts";
import { artifactPreviewKind } from "./artifactPreview";

/** Warm only a small preview-sized set, with HTML and its neighboring images first */
export async function warmArtifactPreviews(items: readonly RuntimeArtifact[], load: (path: string) => Promise<Blob>, signal: AbortSignal): Promise<void> {
  const priority = (item: RuntimeArtifact) => {
    const kind = artifactPreviewKind(item.mimeType, item.path);
    return kind === "html" ? 0 : kind === "image" ? 1 : kind === "download" ? 3 : 2;
  };
  const sorted = items.filter(item => priority(item) < 3).slice().sort((a, b) => priority(a) - priority(b));
  const candidates: RuntimeArtifact[] = [];
  let bytes = 0;
  for (const item of sorted) {
    if (candidates.length === 4) break;
    if (bytes + item.sizeBytes > 1024 * 1024) continue;
    candidates.push(item);
    bytes += item.sizeBytes;
  }
  let next = 0;
  async function worker() {
    while (!signal.aborted && next < candidates.length) {
      const file = candidates[next++];
      // Optional warmup failures remain retryable through the normal preview UI
      await load(file.path).catch(() => undefined);
    }
  }
  await Promise.all([worker(), worker()]);
}
