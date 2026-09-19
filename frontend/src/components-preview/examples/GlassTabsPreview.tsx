import { useState } from "react";
import { GlassTabs } from "../../components/primitives/GlassTabs";

export function GlassTabsPreview() {
  const id = "preview-glass-tabs";
  const [value, setValue] = useState("development");
  const items = [
    { value: "development", label: "Development", panelId: `${id}-panel-0` },
    { value: "daily-work", label: "Daily Work", panelId: `${id}-panel-1` },
  ];
  return <section aria-labelledby={`${id}-title`}>
    <h2 data-preview-heading tabIndex={-1} id={`${id}-title`} className="component-preview-title">Glass</h2>
    <GlassTabs id={id} items={items} value={value} onValueChange={setValue} aria-label="Work mode" />
    {items.map((item, index) => <div key={item.value} id={item.panelId} role="tabpanel" aria-labelledby={`${id}-tab-${index}`} hidden={value !== item.value} />)}
    </section>;
}
