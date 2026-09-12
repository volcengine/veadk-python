import { ComponentApi } from "../api/ComponentApi";
import { useId, useState } from "react";
import { GlassTabs } from "../../components/primitives/GlassTabs";

export function GlassTabsPreview() {
  const id = useId();
  const [value, setValue] = useState("development");
  const items = [
    { value: "development", label: "Development", panelId: `${id}-panel-0` },
    { value: "daily-work", label: "Daily Work", panelId: `${id}-panel-1` },
  ];
  return <section aria-labelledby={`${id}-title`}>
    <h2 id={`${id}-title`} className="component-preview-title">Glass tabs</h2>
    <GlassTabs id={id} items={items} value={value} onValueChange={setValue} aria-label="Work mode" />
    {items.map((item, index) => <div key={item.value} id={item.panelId} role="tabpanel" aria-labelledby={`${id}-tab-${index}`} hidden={value !== item.value} />)}
  <ComponentApi names={["GlassTabs"]} />
    </section>;
}
