import { useState } from "react";
import { PillTabs } from "../../components/primitives/PillTabs";
import "./PillTabsPreview.css";

export function PillTabsPreview() {
  const id = "preview-pill-tabs";
  const [value, setValue] = useState("open-api");
  const items = [
    { value: "open-api", label: "Open API", panelId: `${id}-panel-0` },
    { value: "webhook", label: "Webhook", panelId: `${id}-panel-1` },
    { value: "web-embed", label: "Web embed", panelId: `${id}-panel-2` },
  ];

  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 data-preview-heading tabIndex={-1} id={`${id}-title`} className="component-preview-title">Pill</h2>
      <PillTabs
        id={id}
        className="pill-tabs-preview-specimen"
        aria-label="Integration type"
        items={items}
        value={value}
        onValueChange={setValue}
      />
      {items.map((item, index) => (
        <div key={item.value} id={item.panelId} role="tabpanel" aria-labelledby={`${id}-tab-${index}`} hidden={value !== item.value} />
      ))}
    </section>
  );
}
