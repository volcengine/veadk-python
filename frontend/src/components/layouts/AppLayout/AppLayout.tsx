import { useId, useState, type CSSProperties, type ReactNode } from "react";
import { Sidebar, type SidebarProps } from "../../composites/Sidebar";
import { ScrollArea } from "../../primitives/ScrollArea";
import "./AppLayout.css";

export interface AppLayoutProps {
  /** 侧栏数据与回调，布局统一管理折叠 */
  sidebar: Omit<SidebarProps, "collapsed" | "onCollapsedChange">;
  /** 主内容，直接放入组件库的页面布局 */
  children: ReactNode;
  /** 受控折叠状态 */
  collapsed?: boolean;
  /** 非受控模式的初始折叠状态 */
  defaultCollapsed?: boolean;
  /** 侧栏请求展开或折叠时调用 */
  onCollapsedChange?: (collapsed: boolean) => void;
  /** 默认占满容器，预览可指定高度；数字单位为 px */
  height?: CSSProperties["height"];
  /** 主内容区的无障碍名称 */
  mainLabel?: string;
  /** 键盘跳过导航入口的文案 */
  skipLabel?: string;
}

/** 240px 侧栏 + 独立滚动主内容，折叠后为 56px */
export function AppLayout({ sidebar, children, collapsed, defaultCollapsed = false, onCollapsedChange, height = "100%", mainLabel = "主要内容", skipLabel = "跳到主要内容" }: AppLayoutProps) {
  const [internalCollapsed, setInternalCollapsed] = useState(defaultCollapsed);
  const isCollapsed = collapsed ?? internalCollapsed;
  const mainId = useId();
  return <div className="studio-app-layout" data-collapsed={isCollapsed || undefined} style={{ height }}>
    <a className="studio-app-layout__skip" href={`#${mainId}`} onClick={event => {
      event.preventDefault();
      document.getElementById(mainId)?.focus();
    }}>{skipLabel}</a>
    <Sidebar {...sidebar} collapsed={isCollapsed} onCollapsedChange={next => {
      if (collapsed === undefined) setInternalCollapsed(next);
      onCollapsedChange?.(next);
    }} />
    <ScrollArea id={mainId} role="main" aria-label={mainLabel} tabIndex={-1} className="studio-app-layout__main" contentClassName="studio-app-layout__content">{children}</ScrollArea>
  </div>;
}
