import { ComponentApi } from "../api/ComponentApi";
import { useId } from "react";
import { DashedZone } from "../../components/composites/DashedZone";
import "./DashedZonePreview.css";

export function DashedZonePreview() {
  const id = useId();
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="component-preview-title">Dashed zone</h2>
      <div className="dashed-zone-preview-example">
        <DashedZone />
      </div>
    <ComponentApi names={["DashedZone"]} />
    </section>
  );
}
