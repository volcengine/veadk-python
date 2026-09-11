import { ComponentApi } from "../api/ComponentApi";
import { Item } from "../../components/composites/Item";

export function ItemPreview() {
  return (
    <section aria-labelledby="item-preview-title">
      <h2 id="item-preview-title" className="component-preview-title">Item</h2>
      <Item title="Platform-hosted storage" description="Auto-save. Cleared 24 hours after the session ends" />
      <div style={{ marginTop: 32 }}>
        <Item variant="compact" title="Upload code" description="View and one-click deploy" />
      </div>
    <ComponentApi names={["Item"]} />
    </section>
  );
}
