import type { ComponentProps, ReactNode } from "react";
import "./Button.css";

export type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "ghost";
  startIcon?: ReactNode;
};

export function Button({
  className = "",
  type = "button",
  variant = "primary",
  startIcon,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      className={`studio-button studio-button--${variant} ${className}`.trim()}
    >
      {startIcon && <span className="studio-button__icon" aria-hidden="true">{startIcon}</span>}
      <span className="studio-button__label">{children}</span>
    </button>
  );
}
