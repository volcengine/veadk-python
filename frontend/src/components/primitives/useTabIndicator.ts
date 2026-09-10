import { useLayoutEffect, useRef } from "react";

/** Keep the indicator aligned when labels, fonts, or the container resize */
export function useTabIndicator() {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const measure = () => {
      const selected = root.querySelector<HTMLButtonElement>('[aria-selected="true"]');
      if (!selected) {
        delete root.dataset.indicatorReady;
        return;
      }
      const bounds = selected.getBoundingClientRect();
      const parentBounds = root.getBoundingClientRect();
      root.style.setProperty("--tab-indicator-left", `${bounds.left - parentBounds.left}px`);
      root.style.setProperty("--tab-indicator-width", `${bounds.width}px`);
      root.dataset.indicatorReady = "true";
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    for (const child of root.children) observer.observe(child);
    return () => observer.disconnect();
  });
  return ref;
}
