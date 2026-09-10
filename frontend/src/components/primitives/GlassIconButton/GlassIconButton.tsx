import type { ComponentProps, ReactNode } from "react";
import messageIcon from "./assets/message-smile-square.svg";
import "./GlassIconButton.css";

export type GlassIconButtonProps = Omit<ComponentProps<"button">, "children"> & {
  "aria-label": string;
  icon?: ReactNode;
};

export function GlassIconButton({ icon, className = "", type = "button", ...props }: GlassIconButtonProps) {
  return <button {...props} type={type} className={`studio-glass-icon-button ${className}`.trim()}>
    <span className="studio-glass-icon-button__icon" aria-hidden="true">
      {icon ?? <img src={messageIcon} alt="" />}
    </span>
  </button>;
}
