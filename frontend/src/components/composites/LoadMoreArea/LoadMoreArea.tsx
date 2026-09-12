import { type CSSProperties, type ReactNode } from "react";
import { ScrollArea } from "../../primitives/ScrollArea";
import "./LoadMoreArea.css";

export interface LoadMoreAreaProps {
  children: ReactNode;
  /** 是否还有下一页 */
  hasMore: boolean;
  /** 加载并追加下一页，失败时抛出异常；卸载时 signal 会取消 */
  onLoadMore: (signal: AbortSignal) => Promise<void>;
  /** 滚动区域最大高度 */
  maxHeight?: CSSProperties["maxHeight"];
  /** 距离底部多少像素时开始加载 */
  threshold?: number;
  "aria-label": string;
  className?: string;
  /** 卡片容器布局类名 */
  contentClassName?: string;
}

export function LoadMoreArea({ children, hasMore, onLoadMore, maxHeight = 480, threshold = 24, "aria-label": label, className = "", contentClassName = "" }: LoadMoreAreaProps) {
  return <ScrollArea role="region" aria-label={label} tabIndex={0} maxHeight={maxHeight}
    hasMore={hasMore} onLoadMore={onLoadMore} threshold={threshold}
    className={`studio-load-more ${className}`.trim()} contentClassName={`studio-load-more__items ${contentClassName}`.trim()}>
    {children}
  </ScrollArea>;
}
