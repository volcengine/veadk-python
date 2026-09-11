import type { ComponentProps, ReactNode } from "react";
import "./Button.css";

export type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "ghost" | "link";
  startIcon?: ReactNode;
  /** 文字右侧图标；link 类型在悬停或键盘聚焦时显示 */
  endIcon?: ReactNode;
  /** 纯图标按钮，使用 startIcon 提供图标，并设置 aria-label */
  iconOnly?: boolean;
};

export function Button({
  className = "",
  type = "button",
  variant = "primary",
  startIcon,
  endIcon,
  iconOnly = false,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      className={`studio-button studio-button--${variant}${iconOnly ? " studio-button--icon-only" : ""} ${className}`.trim()}
    >
      {startIcon && <span className="studio-button__icon" aria-hidden="true">{startIcon}</span>}
      {!iconOnly && <span className="studio-button__label">{children}</span>}
      {!iconOnly && endIcon && <span className="studio-button__icon studio-button__end-icon" aria-hidden="true">{endIcon}</span>}
    </button>
  );
}
