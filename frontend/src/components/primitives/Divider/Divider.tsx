import type { HTMLAttributes } from "react";
import "./Divider.css";

export type DividerProps = HTMLAttributes<HTMLDivElement>;

export function Divider({ className = "", ...props }: DividerProps) {
  return <div {...props} role="separator" aria-orientation="horizontal" className={`studio-divider ${className}`} />;
}
