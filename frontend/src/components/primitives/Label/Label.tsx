import type { HTMLAttributes, ReactNode } from "react";
import "./Label.css";

export interface LabelProps extends HTMLAttributes<HTMLSpanElement> {
  startIcon?: ReactNode;
  variant?: "default" | "status";
}

/** Compact dark label from Figma nodes 788:392339 and 788:392355 */
export function Label({ startIcon, variant = "default", children, className, ...props }: LabelProps) {
  return (
    <span {...props} className={["studio-label", variant === "status" ? "studio-label--status" : undefined, startIcon ? "studio-label--with-icon" : undefined, className].filter(Boolean).join(" ")}>
      {startIcon ? <span className="studio-label__icon" aria-hidden="true">{startIcon}</span> : null}
      <span className="studio-label__text">{children}</span>
    </span>
  );
}
