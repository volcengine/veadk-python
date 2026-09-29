import { DashedZone } from "../../components/composites/DashedZone";
import "./DashedZonePreview.css";

export function DashedZonePreview() {
  const id = "preview-dashed-zone";
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 data-preview-heading tabIndex={-1} id={`${id}-title`} className="component-preview-title">Default</h2>
      <div className="dashed-zone-preview-example">
        <DashedZone />
      </div>
    </section>
  );
}
