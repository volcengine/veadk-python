import { Item } from "../../components/composites/Item";

export function ItemPreview() {
  return (
    <section aria-labelledby="item-preview-title">
      <h2 data-preview-heading tabIndex={-1} id="item-preview-title" className="component-preview-title">Default</h2>
      <Item title="Platform-hosted storage" description="Auto-save. Cleared 24 hours after the session ends" />
      <div className="components-preview-variant" style={{ marginTop: 40 }}>
        <h2 data-preview-heading tabIndex={-1} id="item-compact-title">Compact</h2>
        <Item variant="compact" title="Upload code" description="View and one-click deploy" />
      </div>
    </section>
  );
}
