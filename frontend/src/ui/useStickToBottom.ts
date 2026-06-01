import { useCallback, useLayoutEffect, useRef } from "react";

/**
 * Keeps a scroll container pinned to the bottom as content grows — but only
 * while the user is already at (or near) the bottom. If the user scrolls up,
 * auto-scroll pauses; when they scroll back to the bottom, it resumes.
 *
 * Returns a `ref` for the scroll container and an `onScroll` handler to attach.
 * Re-pins whenever `dep` changes (e.g. streamed text / new turns).
 */
export function useStickToBottom<T extends HTMLElement>(dep: unknown) {
  const ref = useRef<T>(null);
  const stick = useRef(true);
  const THRESHOLD = 28;

  const onScroll = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < THRESHOLD;
  }, []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [dep]);

  return { ref, onScroll };
}
