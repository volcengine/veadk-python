import type { ComponentProps, ReactNode } from "react";
import { InputWithTailIcon } from "../InputWithTailIcon";
import "./InputWithHeaderIcon.css";

export type InputWithHeaderIconProps = ComponentProps<"input"> & {
  /** 前置图标，默认显示搜索图标 */
  headerIcon?: ReactNode;
  /** 前置图标按钮的无障碍名称 */
  headerIconLabel?: string;
  /** 前置图标点击回调；未设置时图标仅作展示 */
  onHeaderIconClick?: () => void;
};

function SearchIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>;
}

export function InputWithHeaderIcon({
  className = "",
  headerIcon = <SearchIcon />,
  headerIconLabel = "Search",
  onHeaderIconClick,
  ...props
}: InputWithHeaderIconProps) {
  return <InputWithTailIcon
    {...props}
    className={`studio-input-with-header-icon ${className}`.trim()}
    tailIcon={headerIcon}
    tailIconLabel={headerIconLabel}
    onTailIconClick={onHeaderIconClick}
  />;
}
