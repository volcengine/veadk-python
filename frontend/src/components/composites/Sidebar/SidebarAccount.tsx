import { Button } from "../../primitives/Button";
import { Menu, type MenuEntry, type MenuProps } from "../../primitives/Menu";
import { useStudioTheme } from "../../tokens/theme";
import bell from "../../layouts/DetailPageLayout/assets/bell.svg";
import "./Sidebar.css";

export interface SidebarAccountProps {
  /** 用户显示名称 */
  name: string;
  /** 用户头像地址，未提供时显示名称首字 */
  avatarSrc?: string;
  /** 默认 cover；figma 保留设计稿头像的 24px 外框与 30×28px 裁切 */
  avatarFit?: MenuProps["avatarFit"];
  /** 在账号菜单顶部显示的邮箱 */
  email?: string;
  /** 在账号菜单顶部显示的角色名称 */
  role?: string;
  /** 账号操作，语言等互斥选择使用 MenuRadioGroup */
  menuItems?: readonly MenuEntry[];
  /** 只显示头像，将通知与 Update 移入账号菜单 */
  collapsed?: boolean;
  /** 默认在账号菜单内提供深色 / 浅色选择 */
  showThemeSwitch?: boolean;
  /** 外观菜单及明暗选项的文案 */
  themeLabels?: { appearance: string; dark: string; light: string };
  /** 通知按钮配置，不提供时隐藏 */
  notification?: { label: string; onClick: () => void; disabled?: boolean };
  /** 紧凑胶囊操作按钮配置，不提供时隐藏 */
  update?: { label: string; onClick: () => void; disabled?: boolean };
}

export function SidebarAccount({ name, avatarSrc, avatarFit, email, role, menuItems = [], collapsed = false, showThemeSwitch = true,
  themeLabels = { appearance: "外观", dark: "深色", light: "浅色" }, notification, update }: SidebarAccountProps) {
  const [theme, setTheme] = useStudioTheme();
  const items: MenuEntry[] = [...menuItems];
  if (collapsed && (notification || update)) {
    if (items.length) items.push({ type: "separator", id: "sidebar-account-actions" });
    if (notification) items.push({ id: "sidebar-notification", label: notification.label, onSelect: notification.onClick, disabled: notification.disabled });
    if (update) items.push({ id: "sidebar-update", label: update.label, onSelect: update.onClick, disabled: update.disabled });
  }
  if (showThemeSwitch) {
    if (items.length) items.push({ type: "separator", id: "sidebar-theme-separator" });
    items.push({ id: "sidebar-appearance", label: themeLabels.appearance, children: [{
      type: "radio-group", id: "sidebar-theme", label: themeLabels.appearance, value: theme,
      onValueChange: value => { if (value === "dark" || value === "light") setTheme(value); },
      items: [{ id: "dark", label: themeLabels.dark }, { id: "light", label: themeLabels.light }],
    }] });
  }
  return <div className="studio-sidebar-account" data-collapsed={collapsed || undefined}>
    <div className="studio-sidebar-account__identity">
      <Menu label={name} aria-label={`${name} · 账号菜单`} triggerVariant={collapsed ? "avatar" : "account"}
        avatarSrc={avatarSrc} avatarFit={avatarFit} avatarFallback={name.slice(0, 1)} items={items}
        header={{ title: name, description: email, meta: role }} side={collapsed ? "right" : "top"} maxHeight={440} />
    </div>
    {!collapsed && <div className="studio-sidebar-account__actions">
      {notification && <Button variant="ghost" iconOnly aria-label={notification.label} title={notification.label}
        onClick={notification.onClick} disabled={notification.disabled}
        startIcon={<span className="studio-sidebar-account__bell" style={{ maskImage: `url(${bell})` }} />} />}
      {update && <Button variant="pill" onClick={update.onClick} disabled={update.disabled}>{update.label}</Button>}
    </div>}
  </div>;
}
