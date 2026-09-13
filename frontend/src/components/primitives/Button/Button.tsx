import type { ComponentProps, ReactNode } from "react";
import { Loading } from "../Loading";
import "./Button.css";

export type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "link";
  /** default 保留各变体尺寸；large 为 36px；compact 用于 20px 无内边距图标按钮 */
  size?: "default" | "large" | "compact";
  startIcon?: ReactNode;
  /** 文字右侧图标；link 类型在悬停或键盘聚焦时显示 */
  endIcon?: ReactNode;
  /** 纯图标按钮，使用 startIcon 提供图标，并设置 aria-label */
  iconOnly?: boolean;
  /** 显示旋转加载图标并禁用按钮 */
  loading?: boolean;
};

export function Button({
  className = "",
  type = "button",
  variant = "primary",
  size = "default",
  startIcon,
  endIcon,
  iconOnly = false,
  loading = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || props["aria-busy"]}
      className={`studio-button studio-button--${variant} studio-button--size-${size}${iconOnly ? " studio-button--icon-only" : ""}${loading ? " studio-button--loading" : ""} ${className}`.trim()}
    >
      {startIcon && <span className="studio-button__icon" aria-hidden="true">{startIcon}</span>}
      {!iconOnly && <span className="studio-button__label">{children}</span>}
      {!iconOnly && endIcon && <span className="studio-button__icon studio-button__end-icon" aria-hidden="true">{endIcon}</span>}
      {loading && (
        <span className="studio-button__loading" aria-hidden="true">
          <Loading variant="ring" size={16} decorative />
        </span>
      )}
    </button>
  );
}
