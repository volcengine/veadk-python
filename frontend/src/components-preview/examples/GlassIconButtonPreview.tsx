import { GlassIconButton } from "../../components/primitives/GlassIconButton";
export function GlassIconButtonPreview() {
  return <section aria-labelledby="glass-icon-button-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="glass-icon-button-preview-title" className="component-preview-title">Glass Icon Button</h2>
    <GlassIconButton aria-label="Chat" />
    </section>;
}
