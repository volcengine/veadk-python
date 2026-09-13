import { Menu as BaseMenu } from "@base-ui/react/menu";
import type { ComponentProps, CSSProperties, ReactNode } from "react";
import { ScrollArea } from "../ScrollArea";
import "./Menu.css";

export interface MenuItem {
  type?: "item";
  /** 同级列表内稳定且唯一的标识 */
  id: string;
  label: string;
  /** 可选的前置图标 */
  icon?: ReactNode;
  disabled?: boolean;
  /** 子菜单，可继续包含分组或多级菜单 */
  children?: readonly MenuEntry[];
  /** 仅点击末级菜单项时触发 */
  onSelect?: () => void;
}

export interface MenuGroup {
  type: "group";
  id: string;
  label?: string;
  items: readonly MenuEntry[];
}

export interface MenuSeparator {
  type: "separator";
  id: string;
}

export type MenuEntry = MenuItem | MenuGroup | MenuSeparator;

export type MenuProps = Omit<ComponentProps<"button">, "children" | "onSelect" | "type" | "value" | "defaultValue" | "onChange"> & {
  /** 入口文字，右侧自动显示向下箭头 */
  label: ReactNode;
  /** 菜单项、分组和分割线，可通过 children 递归设置子菜单 */
  items: readonly MenuEntry[];
  /** 末级菜单项选中回调；选中后关闭整个菜单 */
  onSelect?: (id: string, item: MenuItem) => void;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** 是否允许悬停入口按钮展开菜单；仍支持点击和键盘操作 */
  openOnHover?: boolean;
  /** 优先与入口左侧或右侧对齐；空间不足时自动换侧或移动 */
  align?: "start" | "end";
  /** 各级菜单宽度，单位 px；窄窗口内自动限制宽度 */
  menuWidth?: number;
  /** 各级菜单最大高度，单位 px；超出后复用 ScrollArea 滚动 */
  maxHeight?: number;
  emptyContent?: ReactNode;
};

function MenuChevron({ direction }: { direction: "down" | "right" }) {
  return <svg className={`studio-menu__chevron studio-menu__chevron--${direction}`} viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d={direction === "down" ? "m4.5 6.25 3.5 3.5 3.5-3.5" : "m6.25 4.5 3.5 3.5-3.5 3.5"} stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>;
}

function containsIcons(items: readonly MenuEntry[]): boolean {
  return items.some(item => item.type === "group" ? containsIcons(item.items) : item.type !== "separator" && item.icon != null);
}

function containsItems(items: readonly MenuEntry[]): boolean {
  return items.some(item => item.type === "group" ? containsItems(item.items) : item.type !== "separator");
}

type PanelProps = Pick<MenuProps, "items" | "onSelect" | "emptyContent"> & {
  align: "start" | "end";
  menuWidth: number;
  maxHeight: number;
  nested?: boolean;
};

function MenuEntries({ items, icons, ...panelProps }: PanelProps & { icons: boolean }) {
  return items.map(item => {
    if (item.type === "separator") {
      return <BaseMenu.Separator key={item.id} className="studio-menu__separator" />;
    }
    if (item.type === "group") {
      if (!containsItems(item.items)) return null;
      return <BaseMenu.Group key={item.id} className="studio-menu__group">
        {item.label && <BaseMenu.GroupLabel className="studio-menu__group-label">{item.label}</BaseMenu.GroupLabel>}
        <MenuEntries {...panelProps} items={item.items} icons={icons} />
      </BaseMenu.Group>;
    }
    const content = <>
      {icons && <span className="studio-menu__icon" aria-hidden="true">{item.icon}</span>}
      <span className="studio-menu__label">{item.label}</span>
    </>;
    if (item.children !== undefined) {
      return <BaseMenu.SubmenuRoot key={item.id} disabled={item.disabled}>
        <BaseMenu.SubmenuTrigger className="studio-menu__item" label={item.label} title={item.label} disabled={item.disabled} openOnHover delay={0} closeDelay={80}>
          {content}<MenuChevron direction="right" />
        </BaseMenu.SubmenuTrigger>
        <MenuPanel {...panelProps} items={item.children} align="start" nested />
      </BaseMenu.SubmenuRoot>;
    }
    return <BaseMenu.Item key={item.id} className="studio-menu__item" label={item.label} title={item.label} disabled={item.disabled} onClick={() => {
      item.onSelect?.();
      panelProps.onSelect?.(item.id, item);
    }}>{content}</BaseMenu.Item>;
  });
}

function MenuPanel({ nested = false, ...props }: PanelProps) {
  const { items, align, menuWidth, maxHeight, emptyContent } = props;
  return <BaseMenu.Portal>
    <BaseMenu.Positioner
      className="studio-menu__positioner"
      positionMethod="fixed"
      side={nested ? "right" : "bottom"}
      align={align}
      sideOffset={6}
      alignOffset={nested ? -5 : 0}
      collisionPadding={8}
      collisionAvoidance={{ side: "flip", align: nested ? "shift" : "flip", fallbackAxisSide: "none" }}
    >
      <BaseMenu.Popup
        className="studio-menu__panel"
        style={{ "--studio-menu-width": `${menuWidth}px`, "--studio-menu-max-height": `${maxHeight}px` } as CSSProperties}
        render={<ScrollArea contentClassName="studio-menu__entries" />}
      >
        {containsItems(items) ? <MenuEntries {...props} icons={containsIcons(items)} /> : <div className="studio-menu__empty">{emptyContent}</div>}
      </BaseMenu.Popup>
    </BaseMenu.Positioner>
  </BaseMenu.Portal>;
}

export function Menu({
  label,
  items,
  onSelect,
  open,
  defaultOpen = false,
  onOpenChange,
  openOnHover = false,
  align = "start",
  menuWidth = 220,
  maxHeight = 280,
  emptyContent = "暂无菜单项",
  disabled = false,
  className = "",
  ...props
}: MenuProps) {
  return <BaseMenu.Root modal={false} open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} disabled={disabled}>
    <BaseMenu.Trigger {...props} type="button" disabled={disabled} openOnHover={openOnHover} delay={0} closeDelay={80} className={`studio-menu__trigger ${className}`.trim()}>
      <span className="studio-menu__label">{label}</span><MenuChevron direction="down" />
    </BaseMenu.Trigger>
    <MenuPanel items={items} onSelect={onSelect} align={align} menuWidth={menuWidth} maxHeight={maxHeight} emptyContent={emptyContent} />
  </BaseMenu.Root>;
}
