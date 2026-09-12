import { ComponentApi } from "../api/ComponentApi";
import { GlassIconButtonGroup } from "../../components/composites/GlassIconButtonGroup";
export function GlassIconButtonGroupPreview() {
  return <section aria-labelledby="glass-icon-button-group-preview-title">
    <h2 id="glass-icon-button-group-preview-title" className="component-preview-title">Glass icon button group</h2>
    <GlassIconButtonGroup />
  <ComponentApi names={["GlassIconButtonGroup"]} />
    </section>;
}
