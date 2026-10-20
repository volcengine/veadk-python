import type { HTMLAttributes } from "react";
import "./CanvasBackground.css";

export type CanvasBackgroundProps = HTMLAttributes<HTMLDivElement>;

export function CanvasBackground({ children, className = "", ...props }: CanvasBackgroundProps) {
  return <div {...props} className={`studio-canvas-background ${className}`.trim()}>
    <div className="studio-canvas-background__dots" aria-hidden="true" />
    <div className="studio-canvas-background__content">{children}</div>
  </div>;
}
