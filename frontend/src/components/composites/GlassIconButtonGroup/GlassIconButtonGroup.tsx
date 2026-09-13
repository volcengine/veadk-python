import type { ComponentProps } from "react";
import zoomIn from "./assets/zoom-in.svg";
import zoomOut from "./assets/zoom-out.svg";
import maximize from "./assets/maximize.svg";
import layout from "./assets/layout-left.svg";
import "./GlassIconButtonGroup.css";

export type GlassIconButtonGroupProps = ComponentProps<"div"> & {
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onFitView?: () => void;
  onToggleLayout?: () => void;
};

export function GlassIconButtonGroup({ onZoomIn, onZoomOut, onFitView, onToggleLayout, className = "", ...props }: GlassIconButtonGroupProps) {
  return <div role="group" aria-label="Canvas controls" {...props} className={`studio-glass-icon-button-group ${className}`.trim()}>
    <div className="studio-glass-icon-button-group__zoom">
      <button type="button" aria-label="Zoom in" onClick={onZoomIn}><img src={zoomIn} alt="" /></button>
      <button type="button" aria-label="Zoom out" onClick={onZoomOut}><img src={zoomOut} alt="" /></button>
    </div>
    <button type="button" aria-label="Fit view" onClick={onFitView}><img src={maximize} alt="" /></button>
    <button type="button" aria-label="Toggle layout" onClick={onToggleLayout}><img className="studio-glass-icon-button-group__layout" src={layout} alt="" /></button>
  </div>;
}
