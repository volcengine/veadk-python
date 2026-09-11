import { useEffect, useRef, useState, type ComponentProps, type CSSProperties } from "react";
import "./ScrollArea.css";

export type ScrollAreaProps = ComponentProps<"div"> & {
  /** 滚动方向 */
  orientation?: "vertical" | "horizontal" | "both";
  /** 滚动区域最大高度，数字单位为 px */
  maxHeight?: CSSProperties["maxHeight"];
  /** 隐藏滚动条，保留原生滚动 */
  hideScrollbar?: boolean;
  /** 是否还有更多内容，与 onLoadMore 配合使用 */
  hasMore?: boolean;
  /** 触底加载回调，失败时抛出异常；卸载时 signal 会取消 */
  onLoadMore?: (signal: AbortSignal) => Promise<void>;
  /** 距离底部多少像素时触发加载 */
  threshold?: number;
  /** 内容容器类名，可设置内容布局与间距 */
  contentClassName?: string;
};

export function ScrollArea({ orientation = "vertical", maxHeight, hideScrollbar = false, contentClassName = "", className = "", style, children, hasMore = false, onLoadMore, threshold = 24, onScroll, ...props }: ScrollAreaProps) {
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => { request.current?.abort(); }, []);

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

  return <div {...props} className={`studio-scroll-area ${className}`.trim()} data-orientation={orientation} data-hide-scrollbar={hideScrollbar || undefined} style={{ maxHeight, ...style }} onScroll={event => {
    onScroll?.(event);
    const area = event.currentTarget;
    if (!event.defaultPrevented && orientation !== "horizontal" && !failed && area.scrollTop > 0 && area.scrollHeight - area.clientHeight - area.scrollTop <= Math.max(0, threshold)) void load();
  }}>
    <div className={`studio-scroll-area__content ${contentClassName}`.trim()} aria-busy={onLoadMore ? loading : undefined}>{children}</div>
    {onLoadMore && orientation !== "horizontal" && <>
    <div className="studio-scroll-area__footer">
      <span role="status" aria-live="polite">
        {loading ? <><svg className="studio-scroll-area__spinner" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="32 12" /></svg>加载中</> : failed ? "加载失败" : hasMore ? "向下滚动加载更多" : "已加载全部"}
      </span>
      {!loading && hasMore && <button type="button" onClick={() => void load()}>{failed ? "重试" : "加载更多"}</button>}
    </div>
    </>}
  </div>;
}
