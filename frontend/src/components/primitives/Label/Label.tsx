import type { HTMLAttributes, ReactNode } from "react";
import closeIcon from "./assets/close.svg";
import "./Label.css";

export interface LabelProps extends HTMLAttributes<HTMLSpanElement> {
  startIcon?: ReactNode;
  dismissible?: boolean;
  onDismiss?: () => void;
  dismissLabel?: string;
  variant?: "default" | "status";
}

/** Compact dark label from Figma nodes 788:392339 and 788:392355 */
export function Label({ startIcon, dismissible = false, onDismiss, dismissLabel = "Remove label", variant = "default", children, className, ...props }: LabelProps) {
  return (
    <span {...props} className={["studio-label", variant === "status" ? "studio-label--status" : undefined, dismissible ? "studio-label--dismissible" : undefined, startIcon ? "studio-label--with-icon" : undefined, className].filter(Boolean).join(" ")}>
      {startIcon ? <span className="studio-label__icon" aria-hidden="true">{startIcon}</span> : null}
      <span className="studio-label__text">{children}</span>
      {dismissible ? <button type="button" className="studio-label__dismiss" aria-label={dismissLabel} onClick={onDismiss}>
        <span aria-hidden="true" style={{ maskImage: `url(${closeIcon})` }} />
      </button> : null}
    </span>
  );
}
