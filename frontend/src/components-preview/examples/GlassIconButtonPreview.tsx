import { ComponentApi } from "../api/ComponentApi";
import { GlassIconButton } from "../../components/primitives/GlassIconButton";
export function GlassIconButtonPreview() {
  return <section aria-labelledby="glass-icon-button-preview-title">
    <h2 id="glass-icon-button-preview-title" className="component-preview-title">Glass icon button</h2>
    <GlassIconButton aria-label="Chat" />
  <ComponentApi names={["GlassIconButton"]} />
    </section>;
}
