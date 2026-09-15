import { useCallback, useEffect, useImperativeHandle, useRef, useState, type ComponentProps, type CSSProperties } from "react";
import { Loading } from "../Loading";
import "./ScrollArea.css";

export type ScrollAreaProps = ComponentProps<"div"> & {
  /** 原生滚动方向：vertical 纵向、horizontal 横向、both 双向 */
  orientation?: "vertical" | "horizontal" | "both";
  /** 滚动区域最大高度，数字单位为 px */
  maxHeight?: CSSProperties["maxHeight"];
  /** 完全隐藏滚动条，保留原生滚动；默认随鼠标进入/离开区域淡入淡出 */
  hideScrollbar?: boolean;
  /** 开启上下渐隐，仅在对应方向还有可滚动内容时显示；横向滚动不启用 */
  fadeEdges?: boolean;
  /** 是否还有更多内容，与 onLoadMore 配合使用 */
  hasMore?: boolean;
  /** 触底加载回调，失败时抛出异常；卸载时 signal 会取消 */
  onLoadMore?: (signal: AbortSignal) => Promise<void>;
  /** 距离底部多少像素时触发加载 */
  threshold?: number;
  /** 内容容器类名，可设置内容布局与间距 */
  contentClassName?: string;
};

export function ScrollArea({ orientation = "vertical", maxHeight, hideScrollbar = false, fadeEdges = false, contentClassName = "", className = "", style, children, hasMore = false, onLoadMore, threshold = 24, onScroll, ref, ...props }: ScrollAreaProps) {
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [edges, setEdges] = useState({ top: false, bottom: false });
  const areaRef = useRef<HTMLDivElement>(null);
  const request = useRef<AbortController | null>(null);
  const fading = fadeEdges && orientation !== "horizontal";
  const hasFooter = !!onLoadMore && orientation !== "horizontal";
  useImperativeHandle(ref, () => areaRef.current!, []);
  useEffect(() => () => { request.current?.abort(); }, []);

  const updateEdges = useCallback(() => {
    const area = areaRef.current;
    if (!fading || !area) return;
    const overflow = area.scrollHeight - area.clientHeight;
    const top = overflow > 1 && area.scrollTop > 1;
    const bottom = overflow > 1 && overflow - area.scrollTop > 1;
    setEdges(current => current.top === top && current.bottom === bottom ? current : { top, bottom });
  }, [fading]);

  useEffect(() => {
    const area = areaRef.current;
    if (!fading || !area) return;
    const observer = new ResizeObserver(updateEdges);
    observer.observe(area);
    for (const child of area.children) observer.observe(child);
    updateEdges();
    return () => observer.disconnect();
  }, [fading, hasFooter, updateEdges]);

  async function load() {
    if (!onLoadMore || !hasMore || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setFailed(false);
    try {
      await onLoadMore(controller.signal);
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
      if (request.current === controller) request.current = null;
    }
  }

  return <div {...props} ref={areaRef} className={`studio-scroll-area ${className}`.trim()} data-orientation={orientation} data-hide-scrollbar={hideScrollbar || undefined}
    data-fade-edges={fading && (edges.top || edges.bottom) || undefined}
    data-fade-top={fading && edges.top || undefined} data-fade-bottom={fading && edges.bottom || undefined}
    style={{ maxHeight, ...style }} onScroll={event => {
    onScroll?.(event);
    updateEdges();
    const area = event.currentTarget;
    if (!event.defaultPrevented && orientation !== "horizontal" && !failed && area.scrollTop > 0 && area.scrollHeight - area.clientHeight - area.scrollTop <= Math.max(0, threshold)) void load();
  }}>
    <div className={`studio-scroll-area__content ${contentClassName}`.trim()} aria-busy={onLoadMore ? loading : undefined}>{children}</div>
    {onLoadMore && orientation !== "horizontal" && <>
    <div className="studio-scroll-area__footer">
      {loading ? <Loading size={24} /> : <span role="status" aria-live="polite">
        {failed ? "加载失败" : hasMore ? "向下滚动加载更多" : "已加载全部"}
      </span>}
      {!loading && hasMore && <button type="button" onClick={() => void load()}>{failed ? "重试" : "加载更多"}</button>}
    </div>
    </>}
  </div>;
}
