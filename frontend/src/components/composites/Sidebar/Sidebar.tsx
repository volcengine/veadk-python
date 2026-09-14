import { useEffect, useId, useState, type ComponentProps, type ReactNode } from "react";
import { SidebarItemWithIcon } from "./SidebarItemWithIcon";
import { SidebarAccount, type SidebarAccountProps } from "./SidebarAccount";
import { Button } from "../../primitives/Button";
import { Menu, type MenuEntry } from "../../primitives/Menu";
import { ScrollArea } from "../../primitives/ScrollArea";
import { Loading } from "../../primitives/Loading";
import { EmptyState } from "../../primitives/EmptyState";
import { ErrorState } from "../../primitives/ErrorState";
import collapseIcon from "../../layouts/DetailPageLayout/assets/collapse.svg";
import brandIcon from "../../layouts/DetailPageLayout/assets/brand.svg";
import "./Sidebar.css";

function SearchIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M14.0001 14L11.1335 11.1333M12.6667 7.33333C12.6667 10.2789 10.2789 12.6667 7.33333 12.6667C4.38781 12.6667 2 10.2789 2 7.33333C2 4.38781 4.38781 2 7.33333 2C10.2789 2 12.6667 4.38781 12.6667 7.33333Z"
        stroke="currentColor"
        strokeWidth="1.33333"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export type SidebarItemProps = ComponentProps<"button"> & {
  icon?: ReactNode;
  /** 当前导航项，使用持久选中态与 aria-current */
  selected?: boolean;
  /** 折叠为图标入口，保留 title 和无障碍名称 */
  collapsed?: boolean;
};

export function SidebarItem({
  icon = <SearchIcon />,
  children,
  className = "",
  type = "button",
  selected = false,
  collapsed = false,
  ...props
}: SidebarItemProps) {
  return (
    <button {...props} type={type} aria-current={props["aria-current"] ?? (selected ? "page" : undefined)} data-selected={selected || undefined} data-collapsed={collapsed || undefined} className={`studio-sidebar-item ${className}`.trim()}>
      {icon && <span className="studio-sidebar-item__icon" aria-hidden="true">{icon}</span>}
      <span className="studio-sidebar-item__label">{children}</span>
    </button>
  );
}

export type SidebarGroupTitleProps = ComponentProps<"h3">;

export function SidebarGroupTitle({ className = "", children, ...props }: SidebarGroupTitleProps) {
  return (
    <h3 {...props} className={`studio-sidebar-group-title ${className}`.trim()}>{children}</h3>
  );
}

export interface SidebarNavigationItem {
  id: string;
  label: string;
  icon?: ReactNode;
  selected?: boolean;
  disabled?: boolean;
  onSelect?: () => void;
}

export interface SidebarHistoryItem extends Omit<SidebarNavigationItem, "icon"> {
  icon?: ReactNode;
  status?: ReactNode;
  /** 加载动画与 more 共用尾部操作位 */
  loading?: boolean;
  loadingLabel?: string;
  menuItems?: readonly MenuEntry[];
}

export interface SidebarNavigationGroup {
  id: string;
  label: string;
  items: readonly SidebarNavigationItem[];
}

export interface SidebarHistoryGroup {
  id: string;
  label: string;
  items: readonly SidebarHistoryItem[];
}

export interface SidebarProps {
  /** 默认使用组件库的 Figma 标志；logo 可传入 BytePlus 或自定义品牌 */
  brand: { name: string; logo?: ReactNode };
  /** 导航项；权限筛选由调用方完成 */
  navigation: readonly SidebarNavigationItem[];
  /** 主导航后的分组入口，例如 Admin；直接复用 SidebarItem */
  navigationGroups?: readonly SidebarNavigationGroup[];
  /** 已分组和排序的会话；各组标题固定，仅组内条目滚动 */
  history?: readonly SidebarHistoryGroup[];
  /** 账号信息与操作，折叠状态由侧栏统一管理 */
  account: Omit<SidebarAccountProps, "collapsed">;
  /** 是否收起为图标导航 */
  collapsed?: boolean;
  /** 点击 Logo 右侧按钮时请求切换折叠状态 */
  onCollapsedChange: (collapsed: boolean) => void;
  /** 加载时保留已有会话，同时显示 Loading */
  loading?: boolean;
  /** 会话加载错误说明，与 Empty 状态区分 */
  error?: string;
  /** 错误区域的重试操作 */
  onRetry?: () => void;
  /** 侧栏界面文案，可由应用的语言配置传入 */
  labels?: { navigation: string; collapse: string; expand: string; history: string; loading: string; empty: string; error: string; retry: string; more: string };
}

function MoreIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="3" cy="8" r=".7" fill="currentColor" /><circle cx="8" cy="8" r=".7" fill="currentColor" /><circle cx="13" cy="8" r=".7" fill="currentColor" /></svg>;
}

export function Sidebar({ brand, navigation, navigationGroups = [], history = [], account, collapsed = false, onCollapsedChange, loading = false, error, onRetry,
  labels = { navigation: "主导航", collapse: "折叠侧栏", expand: "展开侧栏", history: "会话历史", loading: "正在加载会话", empty: "暂无会话", error: "会话加载失败", retry: "重试", more: "更多操作" } }: SidebarProps) {
  const id = useId();
  const [openHistoryMenu, setOpenHistoryMenu] = useState<string | null>(null);
  useEffect(() => { if (collapsed) setOpenHistoryMenu(null); }, [collapsed]);
  const historyGroups = history.length ? history : [{ id: "history", label: labels.history, items: [] }];
  return <aside className="studio-sidebar" data-collapsed={collapsed || undefined} aria-label={labels.navigation}>
    <header className="studio-sidebar__brand">
      <div className="studio-sidebar__identity" title={brand.name}>
        <span className="studio-sidebar__logo" aria-hidden="true">{brand.logo ?? <span className="studio-sidebar__brand-mark" style={{ maskImage: `url(${brandIcon})` }} />}</span>
        <span className="studio-sidebar__name" aria-hidden={collapsed || undefined}>{brand.name}</span>
      </div>
      <div className="studio-sidebar__toggle">
        <Button variant="ghost" iconOnly aria-label={collapsed ? labels.expand : labels.collapse} title={collapsed ? labels.expand : labels.collapse}
          aria-expanded={!collapsed} aria-controls={`${id}-navigation`} onClick={() => onCollapsedChange(!collapsed)}
          startIcon={<span className="studio-sidebar__collapse-icon" data-collapsed={collapsed || undefined} style={{ maskImage: `url(${collapseIcon})` }} />} />
      </div>
    </header>
    <div className="studio-sidebar__sections">
      <nav id={`${id}-navigation`} className="studio-sidebar__items studio-sidebar__fixed-navigation" aria-label={labels.navigation}>
        {navigation.map(item => <SidebarItem key={item.id} icon={item.icon} selected={item.selected} collapsed={collapsed}
          disabled={item.disabled} onClick={item.onSelect} title={item.label}>{item.label}</SidebarItem>)}
      </nav>
      {navigationGroups.map(group => group.items.length > 0 && <section key={group.id} className="studio-sidebar__fixed-navigation" aria-label={group.label}>
        <div className="studio-sidebar__group-heading" aria-hidden={collapsed || undefined}>
          <SidebarGroupTitle>{group.label}</SidebarGroupTitle>
        </div>
        <nav className="studio-sidebar__items" aria-label={group.label}>
          {group.items.map(item => <SidebarItem key={item.id} icon={item.icon} selected={item.selected} collapsed={collapsed}
            disabled={item.disabled} onClick={item.onSelect} title={item.label}>{item.label}</SidebarItem>)}
        </nav>
      </section>)}
      <div className="studio-sidebar__history" inert={collapsed || undefined} aria-hidden={collapsed || undefined}>
        {historyGroups.map((group, index) => <section key={group.id} className="studio-sidebar__history-group" aria-labelledby={`${id}-history-${index}`}>
          <SidebarGroupTitle id={`${id}-history-${index}`}>{group.label}</SidebarGroupTitle>
          <ScrollArea fadeEdges className="studio-sidebar__history-items"
            aria-labelledby={`${id}-history-${index}`} aria-busy={loading} tabIndex={0}>
          <div className="studio-sidebar__items">{group.items.map(item => {
            const menu = item.menuItems && <Menu triggerVariant="icon" triggerHoverEffect="icon" triggerIcon={<MoreIcon />}
              label={`${item.label} · ${labels.more}`} items={item.menuItems} disabled={item.disabled}
              open={!collapsed && openHistoryMenu === item.id} onOpenChange={open => setOpenHistoryMenu(open ? item.id : null)} />;
            return <SidebarItemWithIcon key={item.id} label={item.label} icon={item.icon}
              selected={item.selected} disabled={item.disabled} onClick={item.onSelect}
              loading={item.loading} loadingLabel={item.loadingLabel}
              trailing={openHistoryMenu === item.id ? menu : item.status}
              hoverTrailing={menu ?? item.status} />;
          })}</div>
          {index === historyGroups.length - 1 && loading && <div className="studio-sidebar__state"><Loading size={24} label={labels.loading} /></div>}
          {index === historyGroups.length - 1 && error && <div className="studio-sidebar__state"><ErrorState title={labels.error} description={error} />{onRetry && <Button variant="secondary" onClick={onRetry}>{labels.retry}</Button>}</div>}
          {!loading && !error && group.items.length === 0 && <div className="studio-sidebar__state"><EmptyState icon={null} title={labels.empty} /></div>}
          </ScrollArea>
        </section>)}
      </div>
    </div>
    <footer className="studio-sidebar__footer"><SidebarAccount {...account} collapsed={collapsed} /></footer>
  </aside>;
}
