import { CanvasBackground } from "../../components/nodes/CanvasBackground";

export function CanvasBackgroundPreview() {
  return <section aria-labelledby="canvas-background-preview-title">
    <h2 id="canvas-background-preview-title" className="component-preview-title">画布背景</h2>
    <CanvasBackground aria-label="Dot grid canvas background" />
  </section>;
}
