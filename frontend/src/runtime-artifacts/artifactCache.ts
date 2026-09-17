import type { RuntimeArtifact } from "../adk/runtimeArtifacts";

interface CachedArtifact {
  path: string;
  controller: AbortController;
  promise: Promise<Blob>;
  size: number;
}

function artifactKey(path: string, version?: Pick<RuntimeArtifact, "updatedAt" | "sizeBytes" | "mimeType">) {
  return JSON.stringify([path, version?.updatedAt, version?.sizeBytes, version?.mimeType]);
}

/** Owned by one conversation drawer, never shared across sessions or identities */
export class ArtifactPreviewCache {
  private readonly entries = new Map<string, CachedArtifact>();
  private bytes = 0;

  constructor(private readonly maxBytes = 32 * 1024 * 1024, private readonly maxEntries = 40) {}

  get(path: string, version: Pick<RuntimeArtifact, "updatedAt" | "sizeBytes" | "mimeType"> | undefined,
    load: (signal: AbortSignal) => Promise<Blob>): Promise<Blob> {
    const key = artifactKey(path, version);
    const cached = this.entries.get(key);
    if (cached) {
      this.entries.delete(key);
      this.entries.set(key, cached);
      return cached.promise;
    }
    const controller = new AbortController();
    const promise = load(controller.signal).then(blob => {
      if (controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
      if (this.entries.get(key) === entry) {
        entry.size = blob.size;
        this.bytes += blob.size;
        this.trim();
      }
      return blob;
    }).catch(error => {
      if (this.entries.get(key) === entry) this.remove(key, entry);
      throw error;
    });
    const entry: CachedArtifact = { path, controller, promise, size: 0 };
    this.entries.set(key, entry);
    this.trim();
    return promise;
  }

  clear(): void {
    for (const entry of this.entries.values()) entry.controller.abort();
    this.entries.clear();
    this.bytes = 0;
  }

  reconcile(items: readonly RuntimeArtifact[], complete: boolean): void {
    const versions = new Map(items.map(item => [item.path, artifactKey(item.path, item)]));
    for (const [key, entry] of this.entries) {
      const version = versions.get(entry.path);
      if ((version !== undefined && version !== key) || (complete && version === undefined)) this.remove(key, entry);
    }
  }

  removePath(path: string): void {
    for (const [key, entry] of this.entries) if (entry.path === path) this.remove(key, entry);
  }

  private remove(key: string, entry: CachedArtifact) {
    entry.controller.abort();
    this.bytes -= entry.size;
    this.entries.delete(key);
  }

  private trim() {
    while (this.bytes > this.maxBytes || this.entries.size > this.maxEntries) {
      const oldest = this.entries.entries().next().value;
      if (!oldest) break;
      this.remove(...oldest);
    }
  }
}
