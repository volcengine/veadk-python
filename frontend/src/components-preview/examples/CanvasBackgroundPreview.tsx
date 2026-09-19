import { CanvasBackground } from "../../components/nodes/CanvasBackground";
import { ScrollArea } from "../../components/primitives/ScrollArea";

export function CanvasBackgroundPreview() {
  return <section aria-labelledby="canvas-background-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="canvas-background-preview-title" className="component-preview-title">Default</h2>
    <ScrollArea orientation="horizontal" role="region" aria-label="Canvas Background 预览，可横向滚动" tabIndex={0}>
      <CanvasBackground aria-label="Dot grid canvas background" />
    </ScrollArea>
    </section>;
}
