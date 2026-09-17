import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getRuntimeArtifact, listRuntimeArtifacts, RuntimeArtifactRequestError, type RuntimeArtifactList, type RuntimeArtifactScope } from "../adk/runtimeArtifacts";
import { ArtifactPreviewCache } from "./artifactCache";
import { warmArtifactPreviews } from "./artifactWarmup";

const LIST_FRESHNESS_MS = 30_000;

export function useRuntimeArtifacts(scope: RuntimeArtifactScope, open: boolean, busy: boolean) {
  const [listing, setListing] = useState<RuntimeArtifactList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [previewRevision, setPreviewRevision] = useState(0);
  const cache = useMemo(() => new ArtifactPreviewCache(), [scope.runtimeId, scope.region, scope.appName, scope.sessionId]);
  const current = useRef<RuntimeArtifactList | null>(null);
  const request = useRef<AbortController | null>(null);
  const warmup = useRef<AbortController | null>(null);
  const lastValidated = useRef(0);
  const wasBusy = useRef(busy);
  const refreshAgain = useRef(false);

  const loadPreview = useCallback((path: string) => cache.get(
    path, current.current?.items.find(item => item.path === path),
    signal => getRuntimeArtifact(scope, path, signal),
  ).catch(cause => {
    if (cause instanceof RuntimeArtifactRequestError && (cause.status === 401 || cause.status === 403)) {
      cache.clear();
      warmup.current?.abort();
      current.current = null;
      setListing(null);
      setError(cause.message);
      lastValidated.current = 0;
    } else if (cause instanceof RuntimeArtifactRequestError && cause.status === 404) {
      cache.removePath(path);
    }
    throw cause;
  }), [cache, scope.runtimeId, scope.region, scope.appName, scope.sessionId]);

  const refresh = useCallback(async (cursor?: string, force = false) => {
    if (request.current) { if (force) refreshAgain.current = true; return; }
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    try {
      const page = await listRuntimeArtifacts(scope, controller.signal, cursor);
      if (controller.signal.aborted) return;
      const previous = current.current;
      const result = cursor && previous ? { ...page, items: [...new Map([...previous.items, ...page.items].map(item => [item.path, item])).values()] } : page;
      cache.reconcile(result.available ? result.items : [], !result.available || result.nextCursor === null);
      const changed = JSON.stringify(previous) !== JSON.stringify(result);
      if (changed) {
        current.current = result;
        setListing(result);
        setPreviewRevision(value => value + 1);
      }
      lastValidated.current = Date.now();
      if (changed && result.available) {
        warmup.current?.abort();
        const warming = new AbortController();
        warmup.current = warming;
        void warmArtifactPreviews(result.items, loadPreview, warming.signal);
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        if (cause instanceof RuntimeArtifactRequestError && [401, 403, 404].includes(cause.status)) {
          cache.clear();
          warmup.current?.abort();
          current.current = null;
          setListing(null);
          lastValidated.current = 0;
        }
        setError(cause instanceof Error ? cause.message : "无法加载会话产物，请重试");
      }
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        setLoading(false);
        if (refreshAgain.current) { refreshAgain.current = false; void refresh(); }
      }
    }
  }, [cache, loadPreview, scope.runtimeId, scope.region, scope.appName, scope.sessionId]);

  useEffect(() => {
    current.current = null;
    setListing(null);
    lastValidated.current = 0;
    void refresh();
    return () => {
      request.current?.abort();
      request.current = null;
      warmup.current?.abort();
      cache.clear();
      refreshAgain.current = false;
    };
  }, [cache, refresh]);

  useEffect(() => {
    if (wasBusy.current && !busy) void refresh(undefined, true);
    wasBusy.current = busy;
  }, [busy, refresh]);

  useEffect(() => {
    if (!open) return;
    const revalidate = () => { if (Date.now() - lastValidated.current >= LIST_FRESHNESS_MS) void refresh(); };
    revalidate();
    const timer = window.setInterval(revalidate, LIST_FRESHNESS_MS);
    return () => window.clearInterval(timer);
  }, [open, refresh]);

  return { listing, loading, error, previewRevision, loadPreview, refresh };
}
