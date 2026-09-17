// @vitest-environment jsdom
import { expect, it, vi } from "vitest";
import { ArtifactPreviewCache } from "../src/runtime-artifacts/artifactCache";
import { warmArtifactPreviews } from "../src/runtime-artifacts/artifactWarmup";

const version = { updatedAt: "v1", sizeBytes: 4, mimeType: "text/plain" };

it("deduplicates in-flight reads and caches each file version within one drawer", async () => {
  const cache = new ArtifactPreviewCache();
  let finish!: (blob: Blob) => void;
  const load = vi.fn(() => new Promise<Blob>(resolve => { finish = resolve; }));
  const first = cache.get("a.txt", version, load);
  expect(cache.get("a.txt", version, load)).toBe(first);
  finish(new Blob(["data"]));
  await first;
  expect(await cache.get("a.txt", version, load)).toHaveProperty("size", 4);
  expect(load).toHaveBeenCalledTimes(1);
  const next = vi.fn(async () => new Blob(["new!"]));
  await cache.get("a.txt", { ...version, updatedAt: "v2" }, next);
  expect(next).toHaveBeenCalledTimes(1);
  await new ArtifactPreviewCache().get("a.txt", version, next);
  expect(next).toHaveBeenCalledTimes(2);
});

it("evicts least recently used blobs to bound memory and retries failed reads", async () => {
  const cache = new ArtifactPreviewCache(8, 2);
  const load = vi.fn(async () => new Blob(["data"]));
  await cache.get("a", version, load);
  await cache.get("b", version, load);
  await cache.get("a", version, load);
  await cache.get("c", version, load);
  await cache.get("a", version, load);
  expect(load).toHaveBeenCalledTimes(3);
  await cache.get("b", version, load);
  expect(load).toHaveBeenCalledTimes(4);
  const fail = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(new Blob(["data"]));
  await expect(cache.get("failed", version, fail)).rejects.toThrow("offline");
  await expect(cache.get("failed", version, fail)).resolves.toHaveProperty("size", 4);
});

it("clears completed blobs and cancels in-flight reads without allowing stale cache writes", async () => {
  const cache = new ArtifactPreviewCache();
  let finish!: (blob: Blob) => void;
  let signal!: AbortSignal;
  const pending = cache.get("a", version, input => {
    signal = input;
    return new Promise(resolve => { finish = resolve; });
  });
  cache.clear();
  expect(signal.aborted).toBe(true);
  finish(new Blob(["old!"]));
  await expect(pending).rejects.toHaveProperty("name", "AbortError");
  const load = vi.fn(async () => new Blob(["new!"]));
  await cache.get("a", version, load);
  cache.clear();
  await cache.get("a", version, load);
  expect(load).toHaveBeenCalledTimes(2);
});

it("preserves unchanged versions while removing changed or deleted files", async () => {
  const cache = new ArtifactPreviewCache();
  const load = vi.fn(async () => new Blob(["data"]));
  const first = { ...version, path: "a.txt", name: "a.txt" };
  const second = { ...version, path: "b.txt", name: "b.txt" };
  await cache.get(first.path, first, load);
  await cache.get(second.path, second, load);
  cache.reconcile([first, second], true);
  await cache.get(first.path, first, load);
  expect(load).toHaveBeenCalledTimes(2);
  cache.reconcile([{ ...first, updatedAt: "v2" }], true);
  await cache.get(first.path, first, load);
  await cache.get(second.path, second, load);
  expect(load).toHaveBeenCalledTimes(4);
});

it("bounds warmup to four small files, one MiB, and two concurrent requests", async () => {
  const items = [
    { path: "large.html", name: "large.html", mimeType: "text/html", sizeBytes: 2 * 1024 * 1024, updatedAt: "v1" },
    ...["report.html", "chart.svg", "a.txt", "b.txt", "c.txt"].map(path => ({ path, name: path, mimeType: path.endsWith("html") ? "text/html" : path.endsWith("svg") ? "image/svg+xml" : "text/plain", sizeBytes: 250 * 1024, updatedAt: "v1" })),
  ];
  let active = 0;
  let peak = 0;
  const load = vi.fn(async () => {
    peak = Math.max(peak, ++active);
    await Promise.resolve();
    active--;
    return new Blob();
  });
  await warmArtifactPreviews(items, load, new AbortController().signal);
  expect(load.mock.calls.map(call => call[0])).toEqual(["report.html", "chart.svg", "a.txt", "b.txt"]);
  expect(peak).toBe(2);
});
