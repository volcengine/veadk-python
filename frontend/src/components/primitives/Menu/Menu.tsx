import { Menu as BaseMenu } from "@base-ui/react/menu";
import type { ComponentProps, CSSProperties, ReactNode } from "react";
import { ScrollArea } from "../ScrollArea";
import { Button, type ButtonProps } from "../Button";
import "./Menu.css";

export interface MenuItem {
  type?: "item";
  /** 同级列表内稳定且唯一的标识 */
  id: string;
  label: string;
  /** 可选的前置图标 */
  icon?: ReactNode;
  disabled?: boolean;
  /** 删除、退出等操作的语义外观 */
  destructive?: boolean;
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

export interface MenuRadioGroup {
  type: "radio-group";
  id: string;
  label?: string;
  value: string;
  onValueChange: (value: string) => void;
  items: readonly Omit<MenuItem, "children">[];
}

export type MenuEntry = MenuItem | MenuGroup | MenuSeparator | MenuRadioGroup;

export type MenuProps = Omit<ComponentProps<"button">, "children" | "onSelect" | "type" | "value" | "defaultValue" | "onChange"> & {
  /** 入口文字，右侧自动显示向下箭头 */
  label: ReactNode;
  /** text 文字与箭头；icon 复用图标 Button；account 头像与名称；avatar 仅头像 */
  triggerVariant?: "text" | "icon" | "account" | "avatar";
  /** icon 入口的图标 */
  triggerIcon?: ReactNode;
  /** icon 入口复用 Button 的悬停反馈，默认显示背景 */
  triggerHoverEffect?: ButtonProps["hoverEffect"];
  /** account / avatar 入口的头像 */
  avatarSrc?: string;
  /** 无头像时显示的简称 */
  avatarFallback?: string;
  /** Figma 头像裁切；普通用户头像默认 cover */
  avatarFit?: "cover" | "figma";
  /** 顶部只读账号信息，仅显示在第一层菜单 */
  header?: { title: string; description?: string; meta?: string };
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
  /** 第一层菜单优先展开方向，空间不足时自动换侧 */
  side?: "bottom" | "top" | "right" | "left";
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
  return items.some(item => item.type === "group" || item.type === "radio-group" ? containsIcons(item.items) : item.type !== "separator" && item.icon != null);
}

function containsItems(items: readonly MenuEntry[]): boolean {
  return items.some(item => item.type === "group" || item.type === "radio-group" ? containsItems(item.items) : item.type !== "separator");
}

type PanelProps = Pick<MenuProps, "items" | "onSelect" | "emptyContent"> & {
  align: "start" | "end";
  menuWidth: number;
  maxHeight: number;
  nested?: boolean;
  side?: MenuProps["side"];
  header?: MenuProps["header"];
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
    if (item.type === "radio-group") {
      return <BaseMenu.RadioGroup key={item.id} value={item.value} onValueChange={item.onValueChange} className="studio-menu__group" aria-label={item.label}>
        {item.label && <BaseMenu.GroupLabel className="studio-menu__group-label">{item.label}</BaseMenu.GroupLabel>}
        {item.items.map(option => <BaseMenu.RadioItem key={option.id} value={option.id} label={option.label} disabled={option.disabled} className="studio-menu__item" closeOnClick onClick={() => {
          option.onSelect?.();
          panelProps.onSelect?.(option.id, option);
        }}>
          {icons && <span className="studio-menu__icon" aria-hidden="true">{option.icon}</span>}
          <span className="studio-menu__label">{option.label}</span>
          <BaseMenu.RadioItemIndicator className="studio-menu__check" keepMounted>
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m3 8 3 3 7-7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </BaseMenu.RadioItemIndicator>
        </BaseMenu.RadioItem>)}
      </BaseMenu.RadioGroup>;
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
    return <BaseMenu.Item key={item.id} className="studio-menu__item" data-destructive={item.destructive || undefined} label={item.label} title={item.label} disabled={item.disabled} onClick={() => {
      item.onSelect?.();
      panelProps.onSelect?.(item.id, item);
    }}>{content}</BaseMenu.Item>;
  });
}

function MenuPanel({ nested = false, ...props }: PanelProps) {
  const { items, align, menuWidth, maxHeight, emptyContent, side = "bottom", header } = props;
  return <BaseMenu.Portal>
    <BaseMenu.Positioner
      className="studio-menu__positioner"
      positionMethod="fixed"
      side={nested ? "right" : side}
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
        {!nested && header && <div className="studio-menu__header">
          <span className="studio-menu__header-title">{header.title}</span>
          {header.description && <span>{header.description}</span>}
          {header.meta && <span>{header.meta}</span>}
        </div>}
        {containsItems(items) ? <MenuEntries {...props} icons={containsIcons(items)} /> : <div className="studio-menu__empty">{emptyContent}</div>}
      </BaseMenu.Popup>
    </BaseMenu.Positioner>
  </BaseMenu.Portal>;
}

export function Menu({
  label,
  triggerVariant = "text",
  triggerIcon,
  triggerHoverEffect = "background",
  avatarSrc,
  avatarFallback = "?",
  avatarFit = "cover",
  header,
  items,
  onSelect,
  open,
  defaultOpen = false,
  onOpenChange,
  openOnHover = false,
  align = "start",
  side = "bottom",
  menuWidth = 220,
  maxHeight = 280,
  emptyContent = "暂无菜单项",
  disabled = false,
  className = "",
  ...props
}: MenuProps) {
  return <BaseMenu.Root modal={false} open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} disabled={disabled}>
    {triggerVariant === "icon" ? <BaseMenu.Trigger {...props} disabled={disabled} openOnHover={openOnHover} delay={0} closeDelay={80}
      aria-label={props["aria-label"] ?? (typeof label === "string" ? label : undefined)}
      render={<Button variant="ghost" iconOnly hoverEffect={triggerHoverEffect} startIcon={triggerIcon} className={className} />} /> :
      <BaseMenu.Trigger {...props} type="button" disabled={disabled} openOnHover={openOnHover} delay={0} closeDelay={80}
        aria-label={props["aria-label"] ?? (triggerVariant === "avatar" && typeof label === "string" ? label : undefined)}
        data-variant={triggerVariant} className={`studio-menu__trigger ${className}`.trim()}>
        {(triggerVariant === "account" || triggerVariant === "avatar") && <span className="studio-menu__avatar" data-fit={avatarFit} aria-hidden="true">
          {avatarSrc ? <img src={avatarSrc} alt="" /> : avatarFallback}
        </span>}
        {triggerVariant !== "avatar" && <span className="studio-menu__label">{label}</span>}
        {triggerVariant === "text" && <MenuChevron direction="down" />}
      </BaseMenu.Trigger>}
    <MenuPanel items={items} onSelect={onSelect} align={align} side={side} header={header} menuWidth={menuWidth} maxHeight={maxHeight} emptyContent={emptyContent} />
  </BaseMenu.Root>;
}
