import { useState } from "react";
import { UnderlineTabs } from "../../components/primitives/UnderlineTabs";
import "./UnderlineTabsPreview.css";

const items = [
  { value: "overview", label: "OverView" },
  { value: "configuration", label: "Configuration" },
  { value: "integration", label: "Integration" },
  { value: "evaluation", label: "Evaluation" },
  { value: "versions", label: "Versions" },
].map((item) => ({
  ...item,
  id: `underline-preview-tab-${item.value}`,
  panelId: `underline-preview-panel-${item.value}`,
}));

export function UnderlineTabsPreview() {
  const [value, setValue] = useState("configuration");
  return (
    <section aria-labelledby="underline-tabs-preview-title">
      <h2 id="underline-tabs-preview-title" className="component-preview-title">Tab with underline</h2>
      <div className="underline-tabs-preview-scroll">
        <UnderlineTabs
          items={items}
          value={value}
          onValueChange={setValue}
          aria-label="Agent sections"
          className="underline-tabs-preview-example"
        />
      </div>
      {items.map((item) => (
        <div key={item.value} role="tabpanel" id={item.panelId} aria-labelledby={item.id} hidden={value !== item.value} />
      ))}
    </section>
  );
}
