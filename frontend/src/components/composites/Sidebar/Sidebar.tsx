import type { ComponentProps, ReactNode } from "react";
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
};

export function SidebarItem({
  icon = <SearchIcon />,
  children,
  className = "",
  type = "button",
  ...props
}: SidebarItemProps) {
  return (
    <button {...props} type={type} className={`studio-sidebar-item ${className}`.trim()}>
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
